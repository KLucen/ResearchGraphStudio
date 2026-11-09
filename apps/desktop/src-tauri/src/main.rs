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
const ENGINE_SCHEMA_VERSION: &str = "0022";

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

fn allowed(method: &str, path: &str) -> bool {
    // Requests are concatenated to the authenticated loopback origin. A missing
    // slash could turn an attacker-controlled prefix into URL userinfo/another host.
    if !path.starts_with('/') || path.starts_with("//") {
        return false;
    }
    if allowed_lite(method, path) {
        return true;
    }
    if allowed_p5(method, path) {
        return true;
    }
    if allowed_query(method, path) {
        return true;
    }
    if allowed_reading(method, path) {
        return true;
    }
    if allowed_projection(method, path) {
        return true;
    }
    if allowed_reasoning(method, path) {
        return true;
    }
    if allowed_knowledge(method, path) {
        return true;
    }
    fn valid_job_cursor(value: &str) -> bool {
        !value.is_empty()
            && value.len() <= 512
            && value.chars().all(|character| {
                character.is_ascii_alphanumeric() || matches!(character, '_' | '-')
            })
    }

    let parts: Vec<_> = path.split('/').collect();
    if parts.len() == 6
        && parts[1..3] == ["api", "v1"]
        && uuid::Uuid::parse_str(parts[4]).is_ok()
        && method == "POST"
        && parts[3] == "sources"
        && parts[5] == "check"
    {
        return true;
    }
    if method == "GET" {
        let (route, query) = path.split_once('?').unwrap_or((path, ""));
        let parts: Vec<_> = route.split('/').collect();
        if parts.len() == 6
            && parts[1..4] == ["api", "v1", "projects"]
            && uuid::Uuid::parse_str(parts[4]).is_ok()
            && parts[5] == "jobs"
        {
            let (mut cursor_seen, mut limit_seen) = (false, false);
            return query.is_empty()
                || query.split('&').all(|part| {
                    part.split_once('=').is_some_and(|(key, value)| match key {
                        "cursor" if !cursor_seen => {
                            cursor_seen = true;
                            valid_job_cursor(value)
                        }
                        "limit" if !limit_seen => {
                            limit_seen = true;
                            !value.is_empty() && value.chars().all(|c| c.is_ascii_digit())
                        }
                        _ => false,
                    })
                });
        }
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
            || (method == "POST"
                && parts.len() == 2
                && matches!(parts[1], "cancel" | "retry" | "resume-adapted"));
    }
    false
}

fn allowed_lite(method: &str, path: &str) -> bool {
    let (route, query) = path.split_once('?').unwrap_or((path, ""));
    let parts: Vec<_> = route.split('/').collect();
    if method != "GET"
        || parts.len() != 7
        || parts[1..4] != ["api", "v1", "projects"]
        || uuid::Uuid::parse_str(parts[4]).is_err()
        || parts[5..] != ["lite", "usage"]
    {
        return false;
    }
    if query.is_empty() {
        return true;
    }
    let mut seen = false;
    query.split('&').all(|part| {
        part.split_once('=').is_some_and(|(key, value)| {
            if key != "paper_id" || seen || uuid::Uuid::parse_str(value).is_err() {
                return false;
            }
            seen = true;
            true
        })
    })
}

fn allowed_p5(method: &str, path: &str) -> bool {
    let (route, query) = path.split_once('?').unwrap_or((path, ""));
    let p: Vec<_> = route.split('/').collect();
    let id = |v: &str| uuid::Uuid::parse_str(v).is_ok();
    if p.len() < 6 || p[1..4] != ["api", "v1", "projects"] || !id(p[4]) {
        return false;
    }
    let suffix = &p[5..];
    let is_id = |i: usize| suffix.get(i).is_some_and(|v| id(v));
    let route_ok = match (method, suffix) {
        ("GET", ["lint", "runs"]) | ("POST", ["lint", "runs"]) => true,
        ("GET", ["lint", "documents"] | ["p5", "personal-sources"]) => true,
        ("POST", ["p5", "annotations", _, "grant"]) => is_id(2),
        ("GET" | "POST", ["external-documents"]) => true,
        ("POST", ["external-documents", "preview"]) => true,
        ("GET", ["external-documents", _]) => is_id(1),
        ("GET", ["lint", "runs", _]) => is_id(2),
        ("GET", ["lint", "runs", _, "issues"]) => is_id(2),
        ("POST", ["lint", "runs", _, "advance" | "cancel"]) => is_id(2),
        ("GET", ["dependencies"] | ["lint", "dependencies"])
        | ("POST", ["dependencies", "rebuild"] | ["lint", "dependencies", "rebuild"]) => true,
        ("GET", ["wiki", "pages"]) | ("GET", ["wiki", "roots"]) => true,
        ("GET", ["wiki", "pages", _]) => is_id(2),
        ("POST", ["wiki", "pages", _, "save" | "publish" | "inspect-file"]) => is_id(2),
        ("POST", ["wiki", "roots", _, "revoke"]) => is_id(2),
        ("POST", ["wiki", "publications", _, "recover"]) => is_id(2),
        ("GET", ["wiki", "publications"]) => true,
        ("GET", ["workflows"]) | ("POST", ["workflows", "prepare"]) => true,
        ("GET", ["workflows", _]) => is_id(1),
        ("POST", ["workflows", _, "generate" | "materialize"]) => is_id(1),
        _ => false,
    };
    let external = suffix.first() == Some(&"external-documents");
    if !route_ok || (method != "GET" && !external && path.contains('?')) {
        return false;
    }
    if !path.contains('?') {
        return true;
    }
    if query.is_empty() {
        return false;
    }
    let mut seen = std::collections::HashSet::new();
    query.split('&').all(|part| {
        part.split_once('=').is_some_and(|(k, v)| {
            if !seen.insert(k) {
                return false;
            }
            let dependency = suffix == ["dependencies"] || suffix == ["lint", "dependencies"];
            let offset_paged = suffix == ["wiki", "pages"] || suffix == ["wiki", "publications"];
            let paged = suffix == ["lint", "runs"]
                || suffix == ["lint", "documents"]
                || suffix == ["p5", "personal-sources"]
                || dependency
                || (suffix.len() == 4 && suffix[0..2] == ["lint", "runs"] && suffix[3] == "issues");
            let issue =
                suffix.len() == 4 && suffix[0..2] == ["lint", "runs"] && suffix[3] == "issues";
            match k {
                "page" | "page_size" if paged => {
                    v.bytes().all(|c| c.is_ascii_digit())
                        && v.parse::<u32>()
                            .is_ok_and(|n| n >= 1 && (k == "page" || n <= 100))
                }
                "offset" | "limit" if offset_paged => {
                    v.bytes().all(|c| c.is_ascii_digit())
                        && v.parse::<u32>()
                            .is_ok_and(|n| k == "offset" || (1..=100).contains(&n))
                }
                "page_id" if suffix == ["wiki", "publications"] => id(v),
                "severity" if issue => matches!(v, "error" | "warning" | "info"),
                "category" | "lifecycle" | "code" if issue => {
                    !v.is_empty()
                        && v.len() <= 80
                        && v.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_')
                }
                "paper_id" if issue => id(v),
                "version_id" if suffix.len() == 3 && suffix[0..2] == ["wiki", "pages"] => id(v),
                "version_id" if external && suffix.len() == 2 && method == "GET" => id(v),
                "purpose" if external && suffix.len() == 2 && method == "GET" => {
                    matches!(v, "local" | "model")
                }
                "include_personal"
                    if suffix == ["wiki", "pages"]
                        || suffix == ["lint", "documents"]
                        || external
                        || (suffix.len() == 3 && suffix[0..2] == ["wiki", "pages"]) =>
                {
                    matches!(v, "true" | "false")
                }
                "object_type" if dependency => {
                    !v.is_empty()
                        && v.len() <= 32
                        && v.bytes().all(|c| c.is_ascii_lowercase() || c == b'_')
                }
                "object_id" if dependency => {
                    !v.is_empty()
                        && v.len() <= 200
                        && v.bytes()
                            .all(|c| c.is_ascii_alphanumeric() || c == b'-' || c == b'_')
                }
                "direction" if dependency => matches!(v, "dependents" | "dependencies"),
                _ => false,
            }
        })
    })
}

fn allowed_query(method: &str, path: &str) -> bool {
    let (route, query) = path.split_once('?').unwrap_or((path, ""));
    let parts: Vec<_> = route.split('/').collect();
    if !path.contains('?')
        && parts.len() == 7
        && parts[1..5] == ["api", "v1", "integrations", "obsidian"]
        && uuid::Uuid::parse_str(parts[5]).is_ok()
        && parts[6] == "query-permissions"
    {
        return method == "PUT";
    }
    if parts.len() < 7
        || parts[1..4] != ["api", "v1", "projects"]
        || uuid::Uuid::parse_str(parts[4]).is_err()
        || parts[5] != "query"
    {
        return false;
    }
    if method == "GET" && parts.len() == 7 && parts[6] == "runs" {
        let mut keys = std::collections::HashSet::new();
        return !path.contains('?')
            || (!query.is_empty()
                && query.split('&').all(|part| {
                    part.split_once('=').is_some_and(|(key, value)| {
                        keys.insert(key)
                            && match key {
                                "limit" => {
                                    !value.is_empty()
                                        && value.bytes().all(|c| c.is_ascii_digit())
                                        && value.parse::<u32>().is_ok_and(|n| (1..=50).contains(&n))
                                }
                                "cursor" => {
                                    // The browser encodes base64url '=' padding. Decode
                                    // only that byte, never arbitrary URL/path escapes.
                                    let decoded = value.replace("%3D", "=").replace("%3d", "=");
                                    !decoded.is_empty()
                                        && decoded.len() <= 500
                                        && decoded.bytes().all(|c| {
                                            c.is_ascii_alphanumeric()
                                                || matches!(c, b'-' | b'_' | b'=')
                                        })
                                }
                                _ => false,
                            }
                    })
                }));
    }
    if method == "GET"
        && ((parts.len() == 7 && matches!(parts[6], "documents" | "saved" | "derived-graph"))
            || (parts.len() == 8 && parts[6] == "saved" && uuid::Uuid::parse_str(parts[7]).is_ok()))
    {
        return !path.contains('?')
            || matches!(query, "include_personal=true" | "include_personal=false");
    }
    if parts.len() == 9
        && parts[6] == "saved"
        && uuid::Uuid::parse_str(parts[7]).is_ok()
        && matches!(
            (method, parts[8]),
            ("PUT", "annotation") | ("POST", "remove")
        )
    {
        return !path.contains('?')
            || matches!(query, "include_personal=true" | "include_personal=false");
    }
    if path.contains('?') {
        return false;
    }
    (parts.len() == 7 && method == "POST" && matches!(parts[6], "search" | "prepare"))
        || (parts.len() == 8 && method == "POST" && parts[6..8] == ["search", "page"])
        || (parts.len() == 8 && method == "POST" && parts[6..8] == ["index", "rebuild"])
        || (parts.len() == 8
            && method == "GET"
            && parts[6] == "runs"
            && uuid::Uuid::parse_str(parts[7]).is_ok())
        || (parts.len() == 9
            && method == "GET"
            && parts[6] == "runs"
            && uuid::Uuid::parse_str(parts[7]).is_ok()
            && parts[8] == "answer")
        || (parts.len() == 9
            && method == "POST"
            && parts[6] == "runs"
            && uuid::Uuid::parse_str(parts[7]).is_ok()
            && matches!(parts[8], "validate" | "generate" | "save"))
}

fn allowed_reading(method: &str, path: &str) -> bool {
    let (route, query) = path.split_once('?').unwrap_or((path, ""));
    let p: Vec<_> = route.split('/').collect();
    if p.len() < 6 || p[1..4] != ["api", "v1", "papers"] || uuid::Uuid::parse_str(p[4]).is_err() {
        return false;
    }
    if p.len() == 6 && method == "GET" {
        if p[5] == "candidates" {
            return query.is_empty()
                || query.split('&').all(|item| {
                    item.split_once('=').is_some_and(|(key, value)| {
                        matches!(key, "search" | "cursor") && value.len() <= 1000
                            || key == "limit"
                                && value.parse::<u32>().is_ok_and(|n| (1..=100).contains(&n))
                    })
                });
        }
        return query.is_empty() && matches!(p[5], "knowledge-units" | "graph-selection");
    }
    p.len() == 7
        && method == "POST"
        && query.is_empty()
        && p[5] == "graph-selection"
        && matches!(p[6], "rebuild" | "preferences")
}

fn allowed_projection(method: &str, path: &str) -> bool {
    if path.contains('?') {
        return false;
    }
    let p: Vec<_> = path.split('/').collect();
    if p.len() < 7
        || p[1..4] != ["api", "v1", "projects"]
        || uuid::Uuid::parse_str(p[4]).is_err()
        || p[5] != "graph"
    {
        return false;
    }
    (p.len() == 7
        && ((method == "POST" && matches!(p[6], "projection" | "layout" | "translate"))
            || (method == "GET" && p[6] == "layout")))
        || (p.len() == 8
            && method == "GET"
            && p[6] == "nodes"
            && uuid::Uuid::parse_str(p[7]).is_ok())
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

fn allowed_reasoning(method: &str, path: &str) -> bool {
    let (route, query) = path.split_once('?').unwrap_or((path, ""));
    if route == "/api/v1/graph/subgraph" && method == "GET" {
        let mut keys = std::collections::HashSet::new();
        let valid = !query.is_empty()
            && query.split('&').all(|item| {
                item.split_once('=').is_some_and(|(key, value)| {
                    keys.insert(key)
                        && match key {
                            "project_id" => uuid::Uuid::parse_str(value).is_ok(),
                            "cursor" | "focus_id" => {
                                value.is_empty() || uuid::Uuid::parse_str(value).is_ok()
                            }
                            "limit" => value.parse::<u32>().is_ok_and(|n| (1..=120).contains(&n)),
                            "kind" => matches!(value, "claim" | "concept" | "method"),
                            "status" => {
                                matches!(value, "all" | "proposed" | "accepted" | "rejected")
                            }
                            _ => false,
                        }
                })
            });
        return valid && keys.contains("project_id");
    }
    if !query.is_empty() || path.contains('?') {
        return false;
    }
    if method == "POST"
        && matches!(
            route,
            "/api/v1/knowledge/candidates"
                | "/api/v1/knowledge/semantic-reviews"
                | "/api/v1/knowledge/relations/infer"
                | "/api/v1/knowledge/alignments/infer"
        )
    {
        return true;
    }
    let parts: Vec<_> = route.split('/').collect();
    if method != "GET" || parts.len() < 6 || parts[1..3] != ["api", "v1"] {
        return false;
    }
    (parts.len() == 6
        && parts[3] == "projects"
        && uuid::Uuid::parse_str(parts[4]).is_ok()
        && parts[5] == "reasoning")
        || (parts.len() == 6
            && parts[3] == "knowledge"
            && matches!(parts[4], "relations" | "alignments")
            && uuid::Uuid::parse_str(parts[5]).is_ok())
        || (parts.len() == 7
            && parts[3..5] == ["knowledge", "nodes"]
            && uuid::Uuid::parse_str(parts[5]).is_ok()
            && matches!(parts[6], "context" | "reasoning"))
}

fn allowed_knowledge(method: &str, path: &str) -> bool {
    let (route, query) = path.split_once('?').unwrap_or((path, ""));
    let parts: Vec<_> = route.split('/').collect();
    if !query.is_empty() {
        if method != "GET"
            || !matches!(
                route,
                "/api/v1/integrations/zotero/items" | "/api/v1/integrations/zotero/collections"
            )
        {
            return false;
        }
        let mut keys = std::collections::HashSet::new();
        return query.split('&').all(|part| {
            part.split_once('=').is_some_and(|(key, value)| {
                if !keys.insert(key) {
                    return false;
                }
                match key {
                    "start" => !value.is_empty() && value.chars().all(|c| c.is_ascii_digit()),
                    "library" => value.split_once('/').is_some_and(|(kind, id)| {
                        matches!(kind, "users" | "groups")
                            && !id.is_empty()
                            && id.chars().all(|c| c.is_ascii_digit())
                    }),
                    _ => false,
                }
            })
        });
    }
    if method == "GET"
        && matches!(
            route,
            "/api/v1/providers"
                | "/api/v1/integrations/zotero/status"
                | "/api/v1/integrations/zotero/items"
                | "/api/v1/integrations/zotero/collections"
        )
    {
        return true;
    }
    if method == "POST"
        && matches!(
            route,
            "/api/v1/knowledge/extract"
                | "/api/v1/knowledge/reviews"
                | "/api/v1/integrations/zotero/annotations"
                | "/api/v1/integrations/zotero/browse"
        )
    {
        return true;
    }
    if parts.len() < 5 || parts[1..3] != ["api", "v1"] {
        return false;
    }
    if parts[3] == "settings" {
        return (parts.len() == 5
            && ((parts[4] == "models" && matches!(method, "GET" | "POST"))
                || (parts[4] == "model-roles" && method == "POST")))
            || (parts.len() == 7
                && parts[4] == "models"
                && uuid::Uuid::parse_str(parts[5]).is_ok()
                && matches!(parts[6], "update" | "delete" | "test")
                && method == "POST");
    }
    if parts[3] == "projects" && uuid::Uuid::parse_str(parts[4]).is_ok() {
        if parts.len() == 6
            && ((matches!(parts[5], "models" | "zotero-imports")
                && matches!(method, "GET" | "POST"))
                || (parts[5] == "model-roles" && method == "POST"))
        {
            return true;
        }
        if parts.len() == 8
            && parts[5] == "models"
            && method == "POST"
            && uuid::Uuid::parse_str(parts[6]).is_ok()
            && matches!(parts[7], "update" | "delete" | "test")
        {
            return true;
        }
    }
    if method == "GET" && uuid::Uuid::parse_str(parts[4]).is_ok() {
        if parts[3] == "evidence"
            && (parts.len() == 5 || (parts.len() == 6 && parts[5] == "preview"))
        {
            return true;
        }
        if parts.len() == 6
            && ((parts[3] == "revisions"
                && matches!(parts[5], "structure" | "knowledge" | "runs" | "annotations"))
                || (parts[3] == "projects" && parts[5] == "note-roots"))
        {
            return true;
        }
    }
    if parts.len() == 6
        && method == "GET"
        && parts[3..5] == ["knowledge", "nodes"]
        && uuid::Uuid::parse_str(parts[5]).is_ok()
    {
        return true;
    }
    parts.len() == 7
        && parts[3..5] == ["integrations", "obsidian"]
        && uuid::Uuid::parse_str(parts[5]).is_ok()
        && ((method == "POST" && matches!(parts[6], "scan" | "revoke"))
            || (method == "GET" && parts[6] == "notes"))
}

#[tauri::command]
async fn authorize_notes_directory(
    state: State<'_, Shared>,
    project_id: String,
    idempotency_key: String,
) -> Result<Option<Value>, String> {
    uuid::Uuid::parse_str(&project_id).map_err(|_| "无效项目")?;
    let chosen = tauri::async_runtime::spawn_blocking(|| {
        rfd::FileDialog::new()
            .set_title("授权只读扫描 Markdown 笔记目录")
            .pick_folder()
    })
    .await
    .map_err(|e| e.to_string())?;
    let Some(path) = chosen else { return Ok(None) };
    let (port, token) = {
        let host = state.0.lock().map_err(|_| "宿主状态不可用")?;
        (host.port.ok_or("引擎尚未就绪")?, host.token.clone())
    };
    let response = reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?
        .post(format!(
            "http://127.0.0.1:{port}/api/v1/integrations/obsidian/roots"
        ))
        .bearer_auth(token)
        .header("Idempotency-Key", idempotency_key)
        .json(&json!({"project_id":project_id,"path":path.to_string_lossy()}))
        .send()
        .await
        .map_err(|_| "授权笔记目录失败")?;
    let success = response.status().is_success();
    let value: Value = response.json().await.map_err(|_| "引擎返回无效响应")?;
    if !success {
        return Err(value["error"]["message"]
            .as_str()
            .unwrap_or("授权失败")
            .into());
    }
    Ok(Some(value))
}

#[tauri::command]
async fn wiki_authorize_output(
    state: State<'_, Shared>,
    project_id: String,
) -> Result<Option<Value>, String> {
    uuid::Uuid::parse_str(&project_id).map_err(|_| "无效项目")?;
    let chosen = tauri::async_runtime::spawn_blocking(|| {
        rfd::FileDialog::new()
            .set_title("授权 Wiki Markdown 导出目录（只写入受管子目录）")
            .pick_folder()
    })
    .await
    .map_err(|_| "目录选择失败")?;
    let Some(path) = chosen else { return Ok(None) };
    let (port, token) = {
        let host = state.0.lock().map_err(|_| "宿主状态不可用")?;
        (host.port.ok_or("引擎尚未就绪")?, host.token.clone())
    };
    let response = reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|_| "授权请求无法初始化")?
        .post(format!(
            "http://127.0.0.1:{port}/api/v1/projects/{project_id}/wiki/roots"
        ))
        .bearer_auth(&token)
        .header("X-ResearchGraph-Native-Token", &token)
        .header("Idempotency-Key", uuid::Uuid::new_v4().to_string())
        .json(&json!({"path":path.to_string_lossy()}))
        .send()
        .await
        .map_err(|_| "Wiki 导出授权失败，请检查引擎连接")?;
    let status = response.status();
    let body = response
        .bytes()
        .await
        .map_err(|_| "本地服务返回了无效响应")?;
    decode_engine_response(status, &body).map(Some)
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

fn request_body_limit(method: &str, path: &str) -> usize {
    // Layout accepts at most 2000 finite positions; preserve the smaller cap elsewhere.
    if method == "POST" && path.ends_with("/graph/layout") && allowed(method, path) {
        512 * 1024
    } else if method == "POST"
        && (path.ends_with("/query/search")
            || path.ends_with("/query/search/page")
            || path.ends_with("/query/prepare")
            || path.ends_with("/workflows/prepare"))
        && allowed(method, path)
    {
        // Query accepts 12,000 Unicode characters, which may exceed 16KB in UTF-8.
        64 * 1024
    } else if method == "PUT"
        && path
            .split('?')
            .next()
            .is_some_and(|route| route.ends_with("/annotation"))
        && allowed_query(method, path)
    {
        // Personal reading annotations use the same 12,000-character contract.
        64 * 1024
    } else {
        16384
    }
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
            authorize_notes_directory,
            wiki_authorize_output,
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
    fn p5_desktop_routes_cover_pagination_dependencies_and_publication_recovery() {
        let id = "b2d49eca-ec74-443c-9314-6b172d7f83a2";
        let base = format!("/api/v1/projects/{id}");
        for suffix in [
            "lint/runs?page=1&page_size=10".to_string(),
            "lint/documents?page=1&page_size=10&include_personal=false".to_string(),
            "p5/personal-sources?page=1&page_size=10".to_string(),
            "external-documents?include_personal=true".to_string(),
            format!("external-documents/{id}?include_personal=true&version_id={id}&purpose=local"),
            format!("lint/runs/{id}/issues?page=2&page_size=10&severity=error&lifecycle=new&paper_id={id}"),
            format!("lint/dependencies?object_type=node&object_id={id}&page=1&page_size=10&direction=dependents"),
            "wiki/pages?offset=10&limit=10&include_personal=false".to_string(),
            format!("wiki/pages/{id}?version_id={id}&include_personal=true"),
            format!("wiki/publications?page_id={id}&offset=0&limit=10"),
            format!("workflows/{id}"),
        ] {
            assert!(super::allowed("GET", &format!("{base}/{suffix}")), "{suffix}");
        }
        for suffix in [
            "lint/dependencies/rebuild".to_string(),
            format!("p5/annotations/{id}/grant"),
            "external-documents?include_personal=true".to_string(),
            "external-documents/preview?include_personal=true".to_string(),
            format!("wiki/pages/{id}/inspect-file"),
            format!("wiki/publications/{id}/recover"),
            format!("workflows/{id}/generate"),
        ] {
            assert!(
                super::allowed("POST", &format!("{base}/{suffix}")),
                "{suffix}"
            );
        }
        for suffix in [
            "wiki/roots".to_string(),
            format!("wiki/pages/{id}/publish?path=private"),
            "lint/dependencies/rebuild?path=private".to_string(),
            format!("p5/annotations/{id}/grant?allow_model=true"),
            "external-documents?include_personal=true&path=private".to_string(),
            "external-documents/preview?include_personal=true&purpose=model".to_string(),
        ] {
            assert!(
                !super::allowed("POST", &format!("{base}/{suffix}")),
                "{suffix}"
            );
        }
        for suffix in [
            "wiki/pages?offset=-1&limit=10".to_string(),
            "wiki/pages?offset=0&limit=101".to_string(),
            "wiki/pages?offset=0&offset=10".to_string(),
            "wiki/publications?page_id=private".to_string(),
            "wiki/publications?path=private".to_string(),
            "wiki/roots?include_personal=true".to_string(),
            "p5/personal-sources?page_size=101".to_string(),
            "lint/documents?include_personal=1".to_string(),
            "external-documents?include_personal=true&include_personal=false".to_string(),
            format!("external-documents/{id}?purpose=upload"),
            "lint/dependencies?object_id=../../private".to_string(),
        ] {
            assert!(
                !super::allowed("GET", &format!("{base}/{suffix}")),
                "{suffix}"
            );
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
            "schema_version": "0022",
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
            "schema_version": "0022",
            "database": "ready",
            "fts5": true
        })));
        for invalid in [
            super::json!({"protocol_version":1,"schema_version":"0022"}),
            super::json!({"protocol_version":1,"schema_version":"0022","database":"failed","fts5":true}),
            super::json!({"protocol_version":1,"schema_version":"0022","database":"ready","fts5":false}),
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

    #[test]
    fn query_routes_are_scoped_by_method_and_identity() {
        let id = "00000000-0000-4000-8000-000000000001";
        let prefix = format!("/api/v1/projects/{id}/query");
        for suffix in ["search", "search/page", "prepare", "index/rebuild"] {
            let path = format!("{prefix}/{suffix}");
            assert!(allowed("POST", &path));
            for method in ["GET", "PUT", "DELETE"] {
                assert!(!allowed(method, &path));
            }
        }
        let run = format!("{prefix}/runs/{id}");
        assert!(allowed("GET", &run));
        assert!(!allowed("POST", &run));
        assert!(allowed("POST", &format!("{run}/validate")));
        assert!(!allowed("GET", &format!("{run}/validate")));
        for suffix in [
            "documents",
            "documents?include_personal=true",
            "documents?include_personal=false",
        ] {
            assert!(allowed("GET", &format!("{prefix}/{suffix}")));
            assert!(!allowed("POST", &format!("{prefix}/{suffix}")));
        }
        let grant = format!("/api/v1/integrations/obsidian/{id}/query-permissions");
        assert!(allowed("PUT", &grant));
        for method in ["GET", "POST", "DELETE"] {
            assert!(!allowed(method, &grant));
        }
        assert!(!allowed("PUT", &format!("{grant}?allow_model=true")));
        assert!(!allowed(
            "PUT",
            "/api/v1/integrations/obsidian/../query-permissions"
        ));
        for path in [
            format!("@evil.test/api/v1/projects/{id}/query/search"),
            format!("evil.test/api/v1/projects/{id}/query/prepare"),
            format!("//evil.test/api/v1/projects/{id}/query/search"),
            "/api/v1/projects/../query/search".to_string(),
            "/api/v1/projects/private/query/prepare".to_string(),
            format!("{prefix}/../search"),
            format!("{prefix}/runs/../validate"),
            format!("{prefix}/runs/%2e%2e/validate"),
            format!("{prefix}/runs/{id}/validate/extra"),
            format!("{prefix}/search?path=private"),
            format!("{prefix}/prepare?"),
            format!("{prefix}/documents?include_personal=true&include_personal=false"),
            format!("{prefix}/documents?include_personal=1"),
            format!("{prefix}/documents?path=C:/private"),
            format!("{prefix}/documents?"),
        ] {
            for method in ["GET", "POST", "PUT"] {
                assert!(!allowed(method, &path), "accepted {method} {path}");
            }
        }
    }

    #[test]
    fn query_answer_and_saved_routes_use_exact_methods_and_scoped_ids() {
        let id = "00000000-0000-4000-8000-000000000001";
        let prefix = format!("/api/v1/projects/{id}/query");
        for (method, suffix) in [
            ("GET", "runs".to_string()),
            ("GET", format!("runs/{id}/answer")),
            ("POST", format!("runs/{id}/generate")),
            ("POST", format!("runs/{id}/save")),
            ("GET", "saved".to_string()),
            ("GET", format!("saved/{id}")),
            ("PUT", format!("saved/{id}/annotation")),
            ("POST", format!("saved/{id}/remove")),
            ("GET", "derived-graph".to_string()),
        ] {
            let path = format!("{prefix}/{suffix}");
            assert!(allowed(method, &path), "rejected {method} {path}");
            for other in ["GET", "POST", "PUT", "PATCH", "DELETE"] {
                if other != method {
                    assert!(!allowed(other, &path), "accepted {other} {path}");
                }
            }
            assert!(!allowed(method, &format!("{path}/extra")));
            assert!(!allowed(method, &format!("{path}?path=private")));
        }
        for suffix in [
            "runs/private/answer".to_string(),
            "runs/../generate".to_string(),
            "runs/%2e%2e/save".to_string(),
            "saved/private".to_string(),
            "saved/../document".to_string(),
            format!("runs/{id}/answer?"),
            format!("runs/{id}/generate?allow_network=true"),
            format!("runs/{id}/save?target_document_id={id}"),
            format!("runs/{id}/raw"),
            "documents/write".to_string(),
        ] {
            let path = format!("{prefix}/{suffix}");
            for method in ["GET", "POST", "PUT", "DELETE"] {
                assert!(!allowed(method, &path), "accepted {method} {path}");
            }
        }
    }

    #[test]
    fn query_history_cursor_accepts_browser_padding_but_rejects_encoding_bypasses() {
        let id = "00000000-0000-4000-8000-000000000001";
        let route = format!("/api/v1/projects/{id}/query/runs");
        // Frozen fixture cursor from a [created_at, UUID] JSON tuple, as emitted
        // by Python urlsafe_b64encode and encoded by queryApi.history.
        let cursor =
            "WyIyMDI2LTExLTA0VDAwOjAwOjAwWiIsIjAwMDAwMDAwLTAwMDAtNDAwMC04MDAwLTAwMDAwMDAwMDAwMSJd";
        for query in [
            "limit=1".to_string(),
            "limit=50".to_string(),
            format!("limit=20&cursor={cursor}"),
            "cursor=YWJjZA==&limit=20".to_string(),
            "cursor=YWJjZA%3D%3D&limit=20".to_string(),
            "cursor=YWJjZA%3d%3d".to_string(),
            format!("cursor={}", "a".repeat(500)),
        ] {
            assert!(
                allowed("GET", &format!("{route}?{query}")),
                "rejected {query}"
            );
        }
        for query in [
            "".to_string(),
            "cursor=".to_string(),
            "limit=0".to_string(),
            "limit=51".to_string(),
            "limit=+1".to_string(),
            "limit=1&limit=2".to_string(),
            "cursor=abc&cursor=def".to_string(),
            "cursor=abc&path=private".to_string(),
            "cursor=%2fprivate".to_string(),
            "cursor=%253D".to_string(),
            "cursor=abc%26limit%3D50".to_string(),
            "cursor=abc#private".to_string(),
            "cursor=../private".to_string(),
            "cursor=abc&".to_string(),
            format!("cursor={}", "a".repeat(501)),
        ] {
            assert!(
                !allowed("GET", &format!("{route}?{query}")),
                "accepted {query}"
            );
        }
    }

    #[test]
    fn query_private_scope_is_boolean_and_cannot_enable_writes() {
        let id = "00000000-0000-4000-8000-000000000001";
        let prefix = format!("/api/v1/projects/{id}/query");
        for suffix in [
            "documents".to_string(),
            "saved".to_string(),
            format!("saved/{id}"),
            "derived-graph".to_string(),
        ] {
            let route = format!("{prefix}/{suffix}");
            for value in ["true", "false"] {
                let path = format!("{route}?include_personal={value}");
                assert!(allowed("GET", &path));
                for method in ["POST", "PUT", "DELETE"] {
                    assert!(!allowed(method, &path));
                }
            }
            for query in [
                "",
                "include_personal=1",
                "include_personal=True",
                "include_personal=true&include_personal=false",
                "include_personal=true&path=private",
                "include_personal=%74rue",
                "include_personal=false#true",
            ] {
                assert!(
                    !allowed("GET", &format!("{route}?{query}")),
                    "accepted {route}?{query}"
                );
            }
        }
    }

    #[test]
    fn saved_metadata_routes_keep_method_identity_and_purpose_scope_exact() {
        let id = "00000000-0000-4000-8000-000000000001";
        let prefix = format!("/api/v1/projects/{id}/query/saved/{id}");
        for (method, suffix) in [("PUT", "annotation"), ("POST", "remove")] {
            let route = format!("{prefix}/{suffix}");
            for value in ["true", "false"] {
                assert!(allowed(
                    method,
                    &format!("{route}?include_personal={value}")
                ));
            }
            for value in ["1", "True", "%74rue", "true&path=private", ""] {
                assert!(!allowed(
                    method,
                    &format!("{route}?include_personal={value}")
                ));
            }
            assert!(!allowed(method, &format!("{route}?")));
            assert!(!allowed(method, &route.replace(id, "private")));
        }
        let annotation = format!("{prefix}/annotation?include_personal=true");
        assert_eq!(super::request_body_limit("PUT", &annotation), 64 * 1024);
        assert!(
            serde_json::json!({"annotation": "研".repeat(12000), "expected_revision": 0})
                .to_string()
                .len()
                < super::request_body_limit("PUT", &annotation)
        );
        assert_eq!(super::request_body_limit("POST", &annotation), 16384);
        assert_eq!(
            super::request_body_limit("PUT", &format!("{annotation}&path=private")),
            16384
        );
    }

    #[test]
    fn query_body_cap_supports_unicode_questions_only_on_valid_routes() {
        let id = "00000000-0000-4000-8000-000000000001";
        for suffix in ["search", "search/page", "prepare"] {
            let path = format!("/api/v1/projects/{id}/query/{suffix}");
            assert_eq!(super::request_body_limit("POST", &path), 64 * 1024);
            assert!(
                serde_json::json!({"question": "研".repeat(12000)})
                    .to_string()
                    .len()
                    < super::request_body_limit("POST", &path)
            );
            assert_eq!(super::request_body_limit("GET", &path), 16384);
            assert_eq!(
                super::request_body_limit("POST", &format!("{path}?path=private")),
                16384
            );
        }
        assert_eq!(
            super::request_body_limit("POST", "/api/v1/projects/../query/search"),
            16384
        );
    }

    #[test]
    fn reading_routes_are_scoped() {
        let id = "00000000-0000-4000-8000-000000000001";
        for suffix in [
            "graph-selection",
            "knowledge-units",
            "candidates?search=abc&limit=40&cursor=",
        ] {
            assert!(super::allowed(
                "GET",
                &format!("/api/v1/papers/{id}/{suffix}")
            ));
        }
        assert!(super::allowed(
            "POST",
            &format!("/api/v1/papers/{id}/graph-selection/preferences")
        ));
        assert!(super::allowed(
            "POST",
            &format!("/api/v1/papers/{id}/graph-selection/rebuild")
        ));
        assert!(!super::allowed(
            "GET",
            &format!("/api/v1/papers/{id}/candidates?path=private")
        ));
        assert!(!super::allowed(
            "GET",
            &format!("/api/v1/papers/{id}/candidates?limit=1000")
        ));
        assert!(!super::allowed(
            "POST",
            "/api/v1/papers/../graph-selection/rebuild"
        ));
    }

    #[test]
    fn projection_routes_and_zotero_links_are_scoped() {
        let id = "11111111-1111-4111-8111-111111111111";
        assert!(super::allowed(
            "POST",
            &format!("/api/v1/projects/{id}/graph/projection")
        ));
        assert!(super::allowed(
            "POST",
            &format!("/api/v1/projects/{id}/graph/layout")
        ));
        assert!(!super::allowed(
            "DELETE",
            &format!("/api/v1/projects/{id}/graph/layout")
        ));
        assert!(!super::allowed(
            "POST",
            "/api/v1/projects/../graph/projection"
        ));
        assert!(super::valid_zotero_url(
            "zotero://select/library/items/ABC12345"
        ));
        assert!(super::valid_zotero_url(
            "zotero://select/groups/12/items/ABC12345"
        ));
        for bad in [
            "https://example.com",
            "zotero://select/library/items/ABC12345?cmd=x",
            "zotero://select/library/items/../../x",
            "file:///private",
        ] {
            assert!(!super::valid_zotero_url(bad));
        }
    }
    use super::allowed;
    #[test]
    fn layout_payload_budget_is_scoped_and_fits_the_contract() {
        let id = "b2d49eca-ec74-443c-9314-6b172d7f83a2";
        let path = format!("/api/v1/projects/{id}/graph/layout");
        let positions: Vec<_> = (0..2000)
            .map(|_| serde_json::json!({"node_id": id, "x": 123456.123456789, "y": -123456.123456789, "pinned": false}))
            .collect();
        let bytes = serde_json::json!({"positions": positions})
            .to_string()
            .len();
        assert!(bytes > 16384);
        assert!(bytes < super::request_body_limit("POST", &path));
        assert_eq!(super::request_body_limit("GET", &path), 16384);
        assert_eq!(
            super::request_body_limit("POST", "/api/v1/settings/models"),
            16384
        );
        assert_eq!(
            super::request_body_limit("POST", "/api/v1/projects/../graph/layout"),
            16384
        );
    }
    #[test]
    fn reasoning_routes_are_bounded_and_scoped() {
        let id = "b2d49eca-ec74-443c-9314-6b172d7f83a2";
        assert!(allowed("GET", &format!("/api/v1/graph/subgraph?project_id={id}&kind=claim&limit=24&cursor=&focus_id=&status=all")));
        assert!(!allowed("GET", "/api/v1/graph/subgraph?limit=24"));
        assert!(!allowed(
            "GET",
            &format!("/api/v1/graph/subgraph?project_id={id}&limit=999")
        ));
        assert!(!allowed(
            "GET",
            &format!("/api/v1/graph/subgraph?project_id={id}&path=private")
        ));
        assert!(!allowed(
            "GET",
            &format!("/api/v1/graph/subgraph?project_id={id}&project_id={id}")
        ));
        assert!(allowed("POST", "/api/v1/knowledge/relations/infer"));
        assert!(allowed("POST", "/api/v1/knowledge/semantic-reviews"));
        assert!(allowed(
            "GET",
            &format!("/api/v1/knowledge/nodes/{id}/context")
        ));
        assert!(!allowed(
            "POST",
            "/api/v1/knowledge/relations/infer?key=private"
        ));
    }
    #[test]
    fn project_models_and_zotero_are_scoped() {
        let id = "b2d49eca-ec74-443c-9314-6b172d7f83a2";
        assert!(allowed("GET", "/api/v1/settings/models"));
        assert!(allowed("POST", "/api/v1/settings/model-roles"));
        assert!(allowed(
            "POST",
            &format!("/api/v1/settings/models/{id}/test")
        ));
        assert!(!allowed(
            "GET",
            &format!("/api/v1/settings/models/{id}/key")
        ));
        assert!(!allowed("POST", "/api/v1/settings/models?key=private"));
        for suffix in ["models", "zotero-imports"] {
            assert!(allowed("GET", &format!("/api/v1/projects/{id}/{suffix}")));
            assert!(allowed("POST", &format!("/api/v1/projects/{id}/{suffix}")));
        }
        for action in ["update", "delete", "test"] {
            assert!(allowed(
                "POST",
                &format!("/api/v1/projects/{id}/models/{id}/{action}")
            ));
        }
        assert!(allowed("POST", "/api/v1/integrations/zotero/browse"));
        assert!(!allowed(
            "GET",
            &format!("/api/v1/projects/{id}/models/{id}/key")
        ));
        assert!(!allowed("POST", "/api/v1/projects/private/models"));
        assert!(!allowed(
            "POST",
            "/api/v1/integrations/zotero/browse?path=private"
        ));
        assert!(!allowed(
            "POST",
            &format!("/api/v1/projects/{id}/models?key=private")
        ));
    }
    #[test]
    fn knowledge_routes_preserve_native_path_authorization() {
        let id = "b2d49eca-ec74-443c-9314-6b172d7f83a2";
        for suffix in ["structure", "knowledge", "runs", "annotations"] {
            assert!(allowed("GET", &format!("/api/v1/revisions/{id}/{suffix}")));
        }
        assert!(allowed("GET", &format!("/api/v1/evidence/{id}/preview")));
        assert!(allowed("GET", &format!("/api/v1/knowledge/nodes/{id}")));
        assert!(allowed("POST", "/api/v1/knowledge/extract"));
        assert!(allowed("POST", "/api/v1/knowledge/reviews"));
        assert!(allowed(
            "POST",
            &format!("/api/v1/integrations/obsidian/{id}/scan")
        ));
        assert!(allowed(
            "GET",
            "/api/v1/integrations/zotero/items?library=users/0&start=50"
        ));
        assert!(!allowed("POST", "/api/v1/integrations/obsidian/roots"));
        assert!(!allowed(
            "GET",
            &format!("/api/v1/evidence/{id}/preview?path=private")
        ));
        assert!(!allowed(
            "GET",
            "/api/v1/integrations/zotero/items?library=users/0&library=groups/1"
        ));
        assert!(!allowed(
            "GET",
            "/api/v1/integrations/zotero/items?library=users/0/../private"
        ));
        assert!(!allowed("POST", "/api/v1/knowledge/extract?path=private"));
    }
    #[test]
    fn rejects_unscoped_routes_and_traversal() {
        assert!(allowed("GET", "/api/v1/projects?cursor=0&limit=50"));
        assert!(allowed("POST", "/api/v1/projects"));
        let id = "b2d49eca-ec74-443c-9314-6b172d7f83a2";
        assert!(allowed("GET", &format!("/api/v1/projects/{id}/lite/usage")));
        assert!(allowed(
            "GET",
            &format!("/api/v1/projects/{id}/lite/usage?paper_id={id}")
        ));
        assert!(!allowed(
            "POST",
            &format!("/api/v1/projects/{id}/lite/usage")
        ));
        assert!(!allowed(
            "GET",
            &format!("/api/v1/projects/{id}/lite/usage?paper_id=private")
        ));
        assert!(allowed("POST", &format!("/api/v1/sources/{id}/check")));
        assert!(allowed(
            "POST",
            &format!("/api/v1/jobs/{id}/resume-adapted")
        ));
        assert!(!allowed(
            "GET",
            &format!("/api/v1/jobs/{id}/resume-adapted")
        ));
        assert!(!allowed(
            "POST",
            &format!("/api/v1/jobs/{id}/resume-adapted?model=other")
        ));
        assert!(allowed("GET", &format!("/api/v1/projects/{id}/jobs")));
        assert!(allowed(
            "GET",
            &format!("/api/v1/projects/{id}/jobs?limit=10&cursor=dGhpcy1pcy1hbi1vcGFxdWUtY3Vyc29y")
        ));
        assert!(!allowed(
            "GET",
            &format!("/api/v1/projects/{id}/jobs?cursor={}", "x".repeat(513))
        ));
        assert!(allowed(
            "GET",
            &format!("/api/v1/projects/{id}/jobs?limit=10&cursor={id}")
        ));
        for query in [
            "cursor=../../private",
            "cursor=invalid!",
            "limit=10&limit=20",
            "path=C:/private",
        ] {
            assert!(!allowed(
                "GET",
                &format!("/api/v1/projects/{id}/jobs?{query}")
            ));
        }
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
        assert!(!allowed(
            "GET",
            &format!("@evil.test/api/v1/projects/{id}/papers")
        ));
        assert!(!allowed(
            "GET",
            &format!("@evil.test/api/v1/knowledge/nodes/{id}")
        ));
    }
}
