#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use serde::Serialize;
use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, Write},
    path::PathBuf,
    process::{Child, ChildStdin, Command, Stdio},
    sync::{mpsc, Arc, Mutex},
    time::{Duration, Instant},
};
use tauri::{Manager, State};

const ENGINE_PROTOCOL_VERSION: u64 = 1;
const ENGINE_SCHEMA_VERSION: &str = "lite0001";

#[derive(Default)]
struct Host {
    child: Option<Child>,
    input: Option<ChildStdin>,
    port: Option<u16>,
    token: String,
    data_dir: PathBuf,
    executable: PathBuf,
    error: Option<String>,
}

#[derive(Clone)]
struct Shared(Arc<Mutex<Host>>);

#[derive(Serialize)]
struct HostStatus {
    running: bool,
    data_dir: String,
    error: Option<String>,
}

impl Host {
    fn status(&mut self) -> HostStatus {
        let running = self.port.is_some()
            && self
                .child
                .as_mut()
                .is_some_and(|child| matches!(child.try_wait(), Ok(None)));
        if !running && self.port.is_some() {
            self.port = None;
            self.error = Some("本地引擎已退出，请重新连接".into());
        }
        HostStatus {
            running,
            data_dir: self.data_dir.to_string_lossy().into(),
            error: self.error.clone(),
        }
    }

    fn stop(&mut self) {
        self.input.take(); // Closing the pipe also handles abrupt host termination.
        if let Some(mut child) = self.child.take() {
            let deadline = Instant::now() + Duration::from_secs(5);
            while Instant::now() < deadline {
                if !matches!(child.try_wait(), Ok(None)) {
                    break;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            if matches!(child.try_wait(), Ok(None)) {
                let _ = child.kill();
            }
            let _ = child.wait();
        }
        self.port = None;
        self.token.clear();
    }

    fn start(&mut self) -> Result<(), String> {
        self.stop();
        self.error = None;
        let result = self.launch();
        if let Err(ref error) = result {
            self.stop();
            self.error = Some(error.clone());
        }
        // Diagnostic receipt confirms the host accepted the health handshake.
        // No session token, port, source data or model credentials are written.
        let receipt = json!({
            "desktop_pid": std::process::id(),
            "engine_pid": self.child.as_ref().map(Child::id),
            "connected": result.is_ok() && self.port.is_some(),
            "protocol_version": ENGINE_PROTOCOL_VERSION,
            "schema_version": ENGINE_SCHEMA_VERSION,
            "error": self.error,
        });
        let _ = std::fs::write(self.data_dir.join("host-startup.json"), receipt.to_string());
        result
    }

    fn launch(&mut self) -> Result<(), String> {
        std::fs::create_dir_all(&self.data_dir).map_err(|_| "无法创建本地数据目录")?;
        let log = std::fs::File::create(self.data_dir.join("engine-startup.log"))
            .map_err(|_| "无法写入引擎启动日志")?;
        let mut command = Command::new(&self.executable);
        command
            .args(["--data-dir"])
            .arg(&self.data_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::from(log));
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command
            .spawn()
            .map_err(|e| format!("无法启动打包引擎：{e}"))?;
        self.input = child.stdin.take();
        let output = child.stdout.take().ok_or("无法读取引擎就绪信号")?;
        self.child = Some(child);
        self.token = format!(
            "{}{}",
            uuid::Uuid::new_v4().simple(),
            uuid::Uuid::new_v4().simple()
        );
        writeln!(
            self.input.as_mut().ok_or("无法建立私有配置通道")?,
            "{}",
            json!({"token":self.token})
        )
        .map_err(|_| "无法发送引擎配置")?;
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            for line in BufReader::new(output).lines().map_while(Result::ok) {
                if let Some(payload) = line.strip_prefix("RGS_READY ") {
                    let _ = tx.send(payload.to_owned());
                }
            }
        });
        let payload = rx
            .recv_timeout(Duration::from_secs(45))
            .map_err(|_| "引擎启动失败或超时，请查看数据目录中的 engine-startup.log")?;
        let ready: Value = serde_json::from_str(&payload).map_err(|_| "无效的就绪信号")?;
        if ready["protocol"] != ENGINE_PROTOCOL_VERSION {
            return Err("引擎协议版本不匹配".into());
        }
        let port = ready["port"]
            .as_u64()
            .filter(|p| *p > 0 && *p <= 65535)
            .ok_or("无效的回环端口")? as u16;
        let client = reqwest::blocking::Client::builder()
            .no_proxy()
            .timeout(Duration::from_secs(5))
            .build()
            .map_err(|e| e.to_string())?;
        let health: Value = client
            .get(format!("http://127.0.0.1:{port}/api/v1/health"))
            .bearer_auth(&self.token)
            .send()
            .and_then(|r| r.error_for_status())
            .map_err(|_| "引擎健康检查失败")?
            .json()
            .map_err(|_| "引擎健康响应无效")?;
        if !health_compatible(&health) {
            return Err("引擎或数据库版本不匹配".into());
        }
        self.port = Some(port);
        Ok(())
    }
}

fn health_compatible(health: &Value) -> bool {
    health["protocol_version"] == ENGINE_PROTOCOL_VERSION
        && health["schema_version"] == ENGINE_SCHEMA_VERSION
        && health["database"] == "ready"
        && health["fts5"] == true
}

fn valid_id(value: &str) -> bool {
    uuid::Uuid::parse_str(value).is_ok()
}

fn query_allowed(query: &str, keys: &[&str]) -> bool {
    if query.is_empty() {
        return true;
    }
    let Ok(url) = reqwest::Url::parse(&format!("http://localhost/?{query}")) else {
        return false;
    };
    let mut seen = std::collections::HashSet::new();
    url.query_pairs().all(|(key, value)| {
        if !keys.contains(&key.as_ref()) || !seen.insert(key.to_string()) {
            return false;
        }
        match key.as_ref() {
            "cursor" => {
                !value.is_empty()
                    && value.len() <= 512
                    && value
                        .chars()
                        .all(|c| c.is_ascii_alphanumeric() || matches!(c, '_' | '-'))
            }
            "limit" | "start" => value.parse::<u32>().is_ok(),
            "paper_id"
            | "revision_id"
            | "document_version_id"
            | "section_id"
            | "overview_result_id" => valid_id(&value),
            "library" => {
                value == "users/0"
                    || value
                        .strip_prefix("groups/")
                        .is_some_and(|v| !v.is_empty() && v.chars().all(|c| c.is_ascii_digit()))
            }
            "q" => !value.is_empty() && value.chars().count() <= 500,
            _ => false,
        }
    })
}

fn allowed(method: &str, path: &str) -> bool {
    if !path.starts_with('/') || path.starts_with("//") || path.contains('#') || path.contains('\\')
    {
        return false;
    }
    let (route, query) = path.split_once('?').unwrap_or((path, ""));
    let p: Vec<_> = route.trim_start_matches('/').split('/').collect();
    if p.len() < 3 || p[..2] != ["api", "v1"] {
        return false;
    }
    let suffix = &p[2..];
    let plain = query.is_empty();
    match (method, suffix) {
        ("GET", ["health"]) => plain,
        ("GET", ["projects"]) => query_allowed(query, &["cursor", "limit"]),
        ("POST", ["projects"] | ["jobs"]) => plain,
        ("GET", ["jobs"]) => plain,
        ("GET", ["jobs", job]) => plain && valid_id(job),
        ("POST", ["jobs", job, "cancel" | "retry"]) => plain && valid_id(job),
        ("GET", ["projects", project, "papers" | "jobs"]) => {
            valid_id(project) && query_allowed(query, &["cursor", "limit"])
        }
        ("GET", ["papers", paper]) => plain && valid_id(paper),
        ("GET", ["revisions", revision, "chunks"]) => {
            valid_id(revision) && query_allowed(query, &["cursor", "limit"])
        }
        ("GET", ["revisions", revision, "sections" | "structure"]) => plain && valid_id(revision),
        ("GET", ["papers", paper, "search"]) => {
            valid_id(paper) && query_allowed(query, &["q", "limit", "revision_id", "section_id"])
        }
        ("GET", ["projects", project, "search"]) => {
            valid_id(project)
                && query_allowed(
                    query,
                    &["q", "limit", "paper_id", "revision_id", "section_id"],
                )
        }
        ("POST", ["sources", source, "check"]) => plain && valid_id(source),
        ("GET", ["projects", project, "lite", "usage"]) => {
            valid_id(project) && query_allowed(query, &["paper_id"])
        }
        ("GET" | "POST", ["settings", "models"]) => plain,
        ("POST", ["settings", "model-roles"]) => plain,
        ("POST", ["settings", "models", profile, "update" | "delete" | "test"]) => {
            plain && valid_id(profile)
        }
        ("GET", ["integrations", "zotero", "status"]) => plain,
        ("GET", ["integrations", "zotero", "collections"]) => {
            query_allowed(query, &["library", "start"])
        }
        ("POST", ["integrations", "zotero", "browse"]) => plain,
        ("POST", ["projects", project, "zotero-imports"]) => plain && valid_id(project),
        ("GET", ["projects", project, "zotero-imports"]) => plain && valid_id(project),
        ("GET", ["papers", paper, "overview"]) => {
            valid_id(paper) && query_allowed(query, &["document_version_id"])
        }
        ("POST", ["papers", paper, "overview", "generate"]) => plain && valid_id(paper),
        ("GET", ["papers", paper, "overview", "graph", "layout"]) => {
            valid_id(paper) && query_allowed(query, &["overview_result_id"])
        }
        ("PUT", ["papers", paper, "overview", "graph", "layout"]) => plain && valid_id(paper),
        ("POST", ["papers", paper, "overview", "graph", "layout", "reset"]) => {
            plain && valid_id(paper)
        }
        _ => false,
    }
}

fn valid_zotero_url(url: &str) -> bool {
    let Some(path) = url.strip_prefix("zotero://select/") else {
        return false;
    };
    let p: Vec<_> = path.split('/').collect();
    let key = match p.as_slice() {
        ["library", "items", key] => *key,
        ["groups", id, "items", key]
            if !id.is_empty() && id.bytes().all(|b| b.is_ascii_digit()) =>
        {
            *key
        }
        _ => return false,
    };
    key.len() == 8
        && key
            .bytes()
            .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit())
}

#[tauri::command]
fn open_zotero(url: String) -> Result<(), String> {
    if !valid_zotero_url(&url) {
        return Err("无效的 Zotero 条目链接".into());
    }
    #[cfg(target_os = "windows")]
    {
        #[link(name = "shell32")]
        extern "system" {
            fn ShellExecuteW(
                hwnd: *mut std::ffi::c_void,
                op: *const u16,
                file: *const u16,
                params: *const u16,
                dir: *const u16,
                show: i32,
            ) -> isize;
        }
        let wide: Vec<u16> = url.encode_utf16().chain(Some(0)).collect();
        // Dispatch only validated Zotero URIs to their registered handler, without a command shell.
        let result = unsafe {
            ShellExecuteW(
                std::ptr::null_mut(),
                std::ptr::null(),
                wide.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                1,
            )
        };
        if result <= 32 {
            return Err("无法打开 Zotero，请确认已安装并注册链接处理程序".into());
        }
        Ok(())
    }
    #[cfg(not(target_os = "windows"))]
    {
        Err("当前平台尚未接入 Zotero 链接处理".into())
    }
}

#[tauri::command]
async fn import_pdf_file(
    state: State<'_, Shared>,
    project_id: String,
    mode: String,
    idempotency_key: String,
) -> Result<Option<Value>, String> {
    uuid::Uuid::parse_str(&project_id).map_err(|_| "无效项目")?;
    if !matches!(mode.as_str(), "reference" | "managed") {
        return Err("无效导入模式".into());
    }
    picked_pdf_request(
        state,
        format!("/api/v1/projects/{project_id}/papers/import/pdf"),
        json!({"mode":mode}),
        idempotency_key,
    )
    .await
}

#[tauri::command]
async fn relocate_source_file(
    state: State<'_, Shared>,
    source_id: String,
    expected_generation: u64,
    idempotency_key: String,
) -> Result<Option<Value>, String> {
    uuid::Uuid::parse_str(&source_id).map_err(|_| "无效来源")?;
    picked_pdf_request(
        state,
        format!("/api/v1/sources/{source_id}/relocate"),
        json!({"expected_generation":expected_generation}),
        idempotency_key,
    )
    .await
}

async fn picked_pdf_request(
    state: State<'_, Shared>,
    route: String,
    mut body: Value,
    idempotency_key: String,
) -> Result<Option<Value>, String> {
    // Paths come only from this native picker, never from web content or arbitrary IPC.
    let chosen = tauri::async_runtime::spawn_blocking(|| {
        rfd::FileDialog::new()
            .add_filter("PDF", &["pdf"])
            .pick_file()
    })
    .await
    .map_err(|e| e.to_string())?;
    let Some(path) = chosen else { return Ok(None) };
    body["path"] = json!(path.to_string_lossy());
    let (port, token) = {
        let host = state.0.lock().map_err(|_| "宿主状态不可用")?;
        (host.port.ok_or("引擎尚未就绪")?, host.token.clone())
    };
    let response = reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?
        .post(format!("http://127.0.0.1:{port}{route}"))
        .bearer_auth(token)
        .header("Idempotency-Key", idempotency_key)
        .json(&body)
        .send()
        .await
        .map_err(|_| "提交文件任务失败，请检查引擎连接")?;
    let success = response.status().is_success();
    let value: Value = response.json().await.map_err(|_| "引擎返回无效响应")?;
    if !success {
        return Err(value["error"]["message"]
            .as_str()
            .unwrap_or("导入失败")
            .into());
    }
    Ok(Some(value))
}

#[tauri::command]
async fn host_status(state: State<'_, Shared>) -> Result<HostStatus, String> {
    let shared = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        shared
            .0
            .lock()
            .map_err(|_| "宿主状态不可用".to_string())
            .map(|mut h| h.status())
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn restart_engine(state: State<'_, Shared>) -> Result<HostStatus, String> {
    let shared = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let mut host = shared.0.lock().map_err(|_| "宿主状态不可用".to_string())?;
        host.start()?;
        Ok(host.status())
    })
    .await
    .map_err(|e| e.to_string())?
}

fn request_body_limit(_method: &str, _path: &str) -> usize {
    64 * 1024
}

fn decode_engine_response(status: reqwest::StatusCode, body: &[u8]) -> Result<Value, String> {
    let value = serde_json::from_slice::<Value>(body);
    if !status.is_success() {
        // Only the structured engine error is user-facing. HTML, traceback or
        // plain-text error bodies may contain source data or credentials.
        return Err(value
            .ok()
            .and_then(|value| value["error"]["message"].as_str().map(str::to_owned))
            .filter(|message| !message.trim().is_empty())
            .unwrap_or_else(|| {
                format!(
                    "本地服务请求失败（HTTP {}），请稍后重试；若持续出现，请查看设置与诊断",
                    status.as_u16()
                )
            }));
    }
    value.map_err(|_| {
        format!(
            "本地服务返回了无效响应（HTTP {}），请重试或查看设置与诊断",
            status.as_u16()
        )
    })
}

#[tauri::command]
async fn engine_request(
    state: State<'_, Shared>,
    method: String,
    path: String,
    body: Option<Value>,
    idempotency_key: Option<String>,
) -> Result<Value, String> {
    if !allowed(&method, &path) {
        return Err("未授权的本地操作".into());
    }
    if body
        .as_ref()
        .is_some_and(|b| b.to_string().len() > request_body_limit(&method, &path))
    {
        return Err("请求内容过大".into());
    }
    let (port, token) = {
        let host = state.0.lock().map_err(|_| "宿主状态不可用")?;
        (
            host.port.ok_or("引擎尚未就绪，请稍候或重新连接")?,
            host.token.clone(),
        )
    };
    let client = reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(if path.ends_with("/test") {
            310
        } else if path == "/api/v1/integrations/zotero/browse" {
            90
        } else {
            15
        }))
        .build()
        .map_err(|e| e.to_string())?;
    let mut request = client
        .request(
            method.parse().map_err(|_| "无效方法")?,
            format!("http://127.0.0.1:{port}{path}"),
        )
        .bearer_auth(token);
    if let Some(key) = idempotency_key {
        request = request.header("Idempotency-Key", key);
    }
    if let Some(value) = body {
        request = request.json(&value);
    }
    let response = request
        .send()
        .await
        .map_err(|_| "本地引擎连接中断，请重新连接后重试")?;
    let status = response.status();
    let bytes = response
        .bytes()
        .await
        .map_err(|_| "本地引擎响应读取中断，请稍后重试")?;
    decode_engine_response(status, &bytes)
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        .setup(|app| {
            let data_dir = app.path().app_local_data_dir()?.join("lite");
            let executable = if cfg!(debug_assertions) {
                PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                    .join("binaries/researchgraph-engine-x86_64-pc-windows-msvc.exe")
            } else {
                app.path().resource_dir()?.join("researchgraph-engine.exe")
            };
            let shared = Shared(Arc::new(Mutex::new(Host {
                data_dir,
                executable,
                ..Host::default()
            })));
            app.manage(shared.clone());
            tauri::async_runtime::spawn_blocking(move || {
                if let Ok(mut host) = shared.0.lock() {
                    let _ = host.start();
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            host_status,
            restart_engine,
            import_pdf_file,
            relocate_source_file,
            engine_request,
            open_zotero
        ])
        .build(tauri::generate_context!())
        .expect("无法建立桌面宿主")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                if let Ok(mut host) = app.state::<Shared>().0.lock() {
                    host.stop();
                }
            }
        });
}

#[cfg(test)]
mod tests {
    #[test]
    fn lite_routes_accept_actual_frontend_queries_and_reject_retired_routes() {
        let paper = "11111111-1111-4111-8111-111111111111";
        let version = "22222222-2222-4222-8222-222222222222";
        let result = "33333333-3333-4333-8333-333333333333";
        for (method, path) in [
            ("GET", format!("/api/v1/papers/{paper}/search?q=sample&limit=5&revision_id={version}")),
            ("GET", format!("/api/v1/projects/{paper}/search?q=sample&paper_id={paper}&revision_id={version}")),
            ("GET", format!("/api/v1/papers/{paper}/overview?document_version_id={version}")),
            ("POST", format!("/api/v1/papers/{paper}/overview/generate")),
            ("GET", format!("/api/v1/papers/{paper}/overview/graph/layout?overview_result_id={result}")),
            ("PUT", format!("/api/v1/papers/{paper}/overview/graph/layout")),
            ("POST", format!("/api/v1/papers/{paper}/overview/graph/layout/reset")),
            ("GET", "/api/v1/integrations/zotero/collections?library=users%2F0&start=0".into()),
        ] {
            assert!(super::allowed(method, &path), "route rejected: {method} {path}");
        }
        for path in [
            format!("/api/v1/papers/{paper}/overview/graph/layout?overview_result_id=invalid"),
            format!("/api/v1/papers/{paper}/search?q=sample&arbitrary=1"),
            format!("/api/v1/projects/{paper}/query/search"),
            format!("/api/v1/projects/{paper}/lint/runs"),
            format!("/api/v1/projects/{paper}/wiki"),
        ] {
            assert!(!super::allowed("GET", &path));
        }
    }

    #[test]
    fn engine_response_preserves_success_and_structured_error_message() {
        let success = br#"{"items":[],"next_cursor":null}"#;
        assert_eq!(
            super::decode_engine_response(reqwest::StatusCode::OK, success).unwrap(),
            super::json!({"items": [], "next_cursor": null})
        );
        let error = super::json!({
            "error": {"code": "DATABASE_BUSY", "message": "本地数据库繁忙，请稍后重试", "retryable": true}
        });
        assert_eq!(
            super::decode_engine_response(
                reqwest::StatusCode::SERVICE_UNAVAILABLE,
                error.to_string().as_bytes()
            ),
            Err("本地数据库繁忙，请稍后重试".into())
        );
    }

    #[test]
    fn engine_non_json_errors_report_status_without_revealing_response_body() {
        for (status, body) in [
            (
                reqwest::StatusCode::SERVICE_UNAVAILABLE,
                "<html>private-paper-token SELECT secret</html>",
            ),
            (
                reqwest::StatusCode::INTERNAL_SERVER_ERROR,
                "Traceback private-paper-token SELECT secret",
            ),
        ] {
            let error = super::decode_engine_response(status, body.as_bytes()).unwrap_err();
            assert!(error.contains(&format!("HTTP {}", status.as_u16())));
            assert!(error.contains("稍后重试"));
            assert!(error.contains("设置与诊断"));
            for private in [
                "private-paper-token",
                "SELECT",
                "secret",
                "Traceback",
                "<html>",
            ] {
                assert!(!error.contains(private));
            }
        }
    }

    #[test]
    fn engine_success_with_invalid_json_is_distinct_from_http_error() {
        for body in [
            b"not-json".as_slice(),
            b"{\"items\":".as_slice(),
            &[0xff, 0xfe],
        ] {
            let error = super::decode_engine_response(reqwest::StatusCode::OK, body).unwrap_err();
            assert!(error.contains("无效响应（HTTP 200）"));
            assert!(!error.contains("not-json"));
        }
    }

    #[test]
    fn engine_error_without_valid_message_uses_safe_http_fallback() {
        for body in [
            super::json!({"detail": "private traceback"}),
            super::json!({"error": {"message": "  "}}),
            super::json!({"error": {"message": 123}}),
        ] {
            let error = super::decode_engine_response(
                reqwest::StatusCode::INTERNAL_SERVER_ERROR,
                body.to_string().as_bytes(),
            )
            .unwrap_err();
            assert!(error.contains("HTTP 500"));
            assert!(!error.contains("private traceback"));
        }
    }

    #[test]
    fn accepts_current_schema_and_rejects_previous_schema() {
        assert!(super::health_compatible(&super::json!({
            "protocol_version": 1,
            "schema_version": "lite0001",
            "database": "ready",
            "fts5": true
        })));
        assert!(!super::health_compatible(&super::json!({
            "protocol_version": 1,
            "schema_version": "0010",
            "database": "ready",
            "fts5": true
        })));
        assert!(!super::health_compatible(&super::json!({
            "protocol_version": 2,
            "schema_version": "lite0001",
            "database": "ready",
            "fts5": true
        })));
        for invalid in [
            super::json!({"protocol_version":1,"schema_version":"lite0001"}),
            super::json!({"protocol_version":1,"schema_version":"lite0001","database":"failed","fts5":true}),
            super::json!({"protocol_version":1,"schema_version":"lite0001","database":"ready","fts5":false}),
        ] {
            assert!(!super::health_compatible(&invalid));
        }
    }

    #[test]
    fn host_schema_tracks_engine_migration_head() {
        let storage = include_str!("../../../../services/engine/researchgraph/storage.py");
        let head = storage
            .lines()
            .find_map(|line| line.strip_prefix("SCHEMA_HEAD = \"")?.strip_suffix('"'))
            .expect("Python migration head missing");
        assert_eq!(super::ENGINE_SCHEMA_VERSION, head);
    }

    #[test]
    #[ignore = "requires packaged engine; run after build-engine with RGS_TEST_ENGINE_PATH"]
    fn packaged_engine_connects_through_native_host_and_restarts() {
        let executable = std::path::PathBuf::from(
            std::env::var_os("RGS_TEST_ENGINE_PATH").expect("RGS_TEST_ENGINE_PATH required"),
        );
        let data_dir = std::env::temp_dir().join(format!("rgs-host-{}", uuid::Uuid::new_v4()));
        let mut host = super::Host {
            executable,
            data_dir: data_dir.clone(),
            ..Default::default()
        };
        for _ in 0..2 {
            let result = host.start();
            let connected = host.status().running;
            let receipt: super::Value =
                serde_json::from_slice(&std::fs::read(data_dir.join("host-startup.json")).unwrap())
                    .unwrap();
            host.stop();
            assert!(result.is_ok(), "native handshake failed: {result:?}");
            assert!(connected);
            assert_eq!(receipt["connected"], true);
            assert_eq!(receipt["desktop_pid"], std::process::id());
            assert!(receipt["engine_pid"].is_u64());
            assert!(receipt["error"].is_null());
            assert!(!host.status().running);
        }
        let resolved = data_dir.canonicalize().unwrap();
        assert!(resolved.starts_with(std::env::temp_dir().canonicalize().unwrap()));
        std::fs::remove_dir_all(resolved).unwrap();
    }
}
