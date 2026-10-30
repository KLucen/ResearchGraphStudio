#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

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
        if ready["protocol"] != 1 {
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
        if health["protocol_version"] != 1 || health["schema_version"] != "0003" {
            return Err("引擎或数据库版本不匹配".into());
        }
        self.port = Some(port);
        Ok(())
    }
}

fn allowed(method: &str, path: &str) -> bool {
    let parts: Vec<_> = path.split('/').collect();
    if parts.len() == 6
        && parts[1..3] == ["api", "v1"]
        && uuid::Uuid::parse_str(parts[4]).is_ok()
        && ((method == "POST" && parts[3] == "sources" && parts[5] == "check")
            || (method == "GET" && parts[3] == "projects" && parts[5] == "jobs"))
    {
        return true;
    }
    if method == "GET" {
        let (route, query) = path.split_once('?').unwrap_or((path, ""));
        let parts: Vec<_> = route.split('/').collect();
        let paginated = (parts.len() == 6 && parts[1] == "api" && parts[2] == "v1")
            && ((parts[3] == "projects" && parts[5] == "papers")
                || (parts[3] == "revisions" && parts[5] == "chunks"))
            && uuid::Uuid::parse_str(parts[4]).is_ok();
        let detail = parts.len() == 5
            && parts[1..4] == ["api", "v1", "papers"]
            && uuid::Uuid::parse_str(parts[4]).is_ok()
            && query.is_empty();
        if detail
            || (paginated
                && (query.is_empty()
                    || query.split('&').all(|part| {
                        part.split_once('=').is_some_and(|(k, v)| {
                            matches!(k, "cursor" | "limit")
                                && !v.is_empty()
                                && v.chars().all(|c| c.is_ascii_digit())
                        })
                    })))
        {
            return true;
        }
    }
    if method == "GET" {
        if matches!(path, "/api/v1/health" | "/api/v1/projects" | "/api/v1/jobs") {
            return true;
        }
        if let Some(query) = path.strip_prefix("/api/v1/projects?") {
            return query.split('&').all(|part| {
                part.split_once('=').is_some_and(|(k, v)| {
                    matches!(k, "cursor" | "limit")
                        && !v.is_empty()
                        && v.chars().all(|c| c.is_ascii_digit())
                })
            });
        }
    }
    if method == "POST" && matches!(path, "/api/v1/projects" | "/api/v1/jobs") {
        return true;
    }
    if let Some(suffix) = path.strip_prefix("/api/v1/jobs/") {
        let parts: Vec<_> = suffix.split('/').collect();
        if uuid::Uuid::parse_str(parts[0]).is_err() {
            return false;
        }
        return (method == "GET" && parts.len() == 1)
            || (method == "POST" && parts.len() == 2 && matches!(parts[1], "cancel" | "retry"));
    }
    false
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
    if body.as_ref().is_some_and(|b| b.to_string().len() > 16384) {
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
        .timeout(Duration::from_secs(15))
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
    let success = response.status().is_success();
    let value: Value = response
        .json()
        .await
        .map_err(|_| "本地服务返回了无效响应")?;
    if !success {
        return Err(value["error"]["message"]
            .as_str()
            .unwrap_or("本地操作失败")
            .into());
    }
    Ok(value)
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        .setup(|app| {
            let data_dir = app.path().app_local_data_dir()?;
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
            engine_request
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
    use super::allowed;
    #[test]
    fn rejects_unscoped_routes_and_traversal() {
        assert!(allowed("GET", "/api/v1/projects?cursor=0&limit=50"));
        assert!(allowed("POST", "/api/v1/projects"));
        let id = "b2d49eca-ec74-443c-9314-6b172d7f83a2";
        assert!(allowed("POST", &format!("/api/v1/sources/{id}/check")));
        assert!(allowed("GET", &format!("/api/v1/projects/{id}/jobs")));
        assert!(!allowed("POST", &format!("/api/v1/sources/{id}/relocate")));
        assert!(!allowed(
            "POST",
            &format!("/api/v1/sources/{id}/check?path=private")
        ));
        assert!(allowed(
            "GET",
            &format!("/api/v1/projects/{id}/papers?cursor=0&limit=50")
        ));
        assert!(allowed(
            "GET",
            &format!("/api/v1/revisions/{id}/chunks?limit=10")
        ));
        assert!(!allowed(
            "POST",
            &format!("/api/v1/projects/{id}/papers/import/pdf")
        ));
        assert!(!allowed(
            "GET",
            &format!("/api/v1/revisions/{id}/chunks?path=C:/private")
        ));
        assert!(!allowed("GET", "/api/v1/papers/../../private"));
        for path in [
            "http://evil.test",
            "/api/v1/../admin",
            "/api/v1/projects?url=http://evil.test",
            "/api/v1/jobs/../../health",
        ] {
            assert!(!allowed("GET", path));
        }
        assert!(!allowed("DELETE", "/api/v1/projects"));
    }
}
