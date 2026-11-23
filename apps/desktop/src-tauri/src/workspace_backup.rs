use super::{Host, Shared};
use serde_json::{json, Value};
use std::{
    fs::{self, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::Duration,
};
use tauri::State;
use uuid::Uuid;

const ACTIVE_WORKSPACE: &str = "active-workspace.json";
const RESTORED_PREFIX: &str = "lite-restored-";

fn valid_workspace_name(name: &str) -> bool {
    name == "lite"
        || name
            .strip_prefix(RESTORED_PREFIX)
            .is_some_and(|suffix| Uuid::parse_str(suffix).is_ok_and(|id| id.to_string() == suffix))
}

pub fn active_workspace(root: &Path) -> PathBuf {
    let selected = (|| -> std::io::Result<Vec<u8>> {
        let mut value = Vec::new();
        fs::File::open(root.join(ACTIVE_WORKSPACE))?
            .take(1_025)
            .read_to_end(&mut value)?;
        Ok(value)
    })()
    .ok()
    .filter(|value| value.len() <= 1_024)
    .and_then(|bytes| serde_json::from_slice::<String>(&bytes).ok())
    .filter(|name| valid_workspace_name(name))
    .map(|name| root.join(name))
    .filter(|candidate| {
        candidate
            .canonicalize()
            .ok()
            .zip(root.canonicalize().ok())
            .is_some_and(|(dir, parent)| {
                dir == parent.join(candidate.file_name().unwrap_or_default())
                    && dir.join("researchgraph-lite.sqlite3").is_file()
            })
    });
    selected.unwrap_or_else(|| root.join("lite"))
}

fn store_workspace(root: &Path, workspace: &Path) -> Result<(), String> {
    let name = workspace
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| valid_workspace_name(name))
        .ok_or("无效的恢复工作区")?;
    let temporary = root.join(format!(".active-workspace-{}.tmp", Uuid::new_v4()));
    let write_result = (|| -> std::io::Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)?;
        file.write_all(json!(name).to_string().as_bytes())?;
        file.sync_all()?;
        drop(file);
        fs::rename(&temporary, root.join(ACTIVE_WORKSPACE))
    })();
    if write_result.is_err() {
        let _ = fs::remove_file(&temporary);
        return Err("无法保存恢复后的工作区位置，已保留原工作区".into());
    }
    Ok(())
}

fn ensure_idle(host: &mut Host) -> Result<(), String> {
    if host.in_flight_writes != 0 {
        return Err("当前有数据写入请求，请稍后再备份或恢复".into());
    }
    if !host.status().running {
        return Ok(());
    }
    let port = host.port.ok_or("无法确认任务是否结束")?;
    let reply = reqwest::blocking::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(6))
        .build()
        .and_then(|client| {
            client
                .get(format!("http://127.0.0.1:{port}/api/v1/health"))
                .bearer_auth(&host.token)
                .send()?
                .error_for_status()?
                .json::<Value>()
        })
        .map_err(|_| "无法确认任务是否结束，请稍后重试")?;
    if reply["active_jobs"].as_u64() != Some(0)
        || matches!(
            reply["worker_status"].as_str(),
            Some("running" | "recovering")
        )
    {
        return Err("请等待当前任务结束或先取消待执行任务，再备份或恢复".into());
    }
    Ok(())
}

fn quiesce(host: &mut Host) -> Result<(), String> {
    ensure_idle(host)?;
    let Some(port) = host.port else { return Ok(()) };
    let client = reqwest::blocking::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(5))
        .build()
        .map_err(|_| "无法暂停本地任务队列")?;
    for _ in 0..5 {
        let result = client
            .post(format!(
                "http://127.0.0.1:{port}/api/v1/maintenance/quiesce"
            ))
            .bearer_auth(&host.token)
            .send()
            .and_then(|reply| reply.error_for_status()?.json::<Value>())
            .map_err(|_| "无法暂停本地任务队列")?;
        if result["quiesced"].as_bool() == Some(true) {
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(65));
    }
    Err("本地任务队列暂时无法停稳，请等待任务结束后重试".into())
}

fn run_offline(
    host: &Host,
    operation: &str,
    selection: &Path,
    data_dir: &Path,
) -> Result<Value, String> {
    let mut command = Command::new(&host.executable);
    command
        .args(["--workspace-operation", operation, "--data-dir"])
        .arg(data_dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn().map_err(|_| "无法启动离线备份引擎")?;
    if let Some(mut input) = child.stdin.take() {
        if writeln!(input, "{}", json!({"directory": selection})).is_err() {
            let _ = child.kill();
            let _ = child.wait();
            return Err("无法提交备份选项".into());
        }
    }
    let output = child.wait_with_output().map_err(|_| "离线备份引擎中断")?;
    let envelope =
        serde_json::from_slice::<Value>(&output.stdout).map_err(|_| "离线备份引擎响应无效")?;
    if let Some(error) = envelope["error"].as_str() {
        return Err(error.into());
    }
    if !output.status.success() || !envelope["result"].is_object() {
        return Err("离线备份操作未完成".into());
    }
    Ok(envelope["result"].clone())
}

fn switch_workspace(host: &mut Host, selection: &Path) -> Result<Value, String> {
    let previous = host.data_dir.clone();
    let parent = previous.parent().ok_or("应用数据目录无效")?;
    let restored = parent.join(format!("{RESTORED_PREFIX}{}", Uuid::new_v4()));
    // Validate the independent copy before changing engine state or the active pointer.
    let mut result = run_offline(host, "restore", selection, &restored)?;
    quiesce(host)?;
    host.data_dir = restored;
    if let Err(error) = host
        .start()
        .and_then(|()| store_workspace(parent, &host.data_dir))
    {
        host.data_dir = previous;
        let _ = host.start();
        return Err(error);
    }
    result["previous_path"] = json!(previous);
    Ok(result)
}

#[tauri::command]
pub async fn workspace_backup(
    operation: String,
    state: State<'_, Shared>,
) -> Result<Option<Value>, String> {
    if !matches!(operation.as_str(), "export" | "restore") {
        return Err("未知的备份操作".into());
    }
    let shared = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let title = if operation == "export" {
            "选择存放工作区备份的父文件夹"
        } else {
            "选择此前创建的完整工作区备份文件夹"
        };
        let Some(selection) = rfd::FileDialog::new().set_title(title).pick_folder() else {
            return Ok(None);
        };
        if operation == "restore"
            && rfd::MessageDialog::new()
                .set_level(rfd::MessageLevel::Warning)
                .set_title("恢复工作区备份")
                .set_description("恢复后会切换到单独的新工作区。当前工作区将保留，本机 API Key 需要在恢复后重新绑定。继续吗？")
                .set_buttons(rfd::MessageButtons::YesNo)
                .show()
                != rfd::MessageDialogResult::Yes
        {
            return Ok(None);
        }
        let mut host = shared.0.lock().map_err(|_| "宿主状态不可用")?;
        ensure_idle(&mut host)?;
        if operation == "restore" {
            return switch_workspace(&mut host, &selection).map(Some);
        }
        quiesce(&mut host)?;
        host.stop();
        let result = run_offline(&host, "export", &selection, &host.data_dir);
        let restarted = host.start();
        match (result, restarted) {
            (Ok(mut result), Err(error)) => {
                result["restart_error"] = json!(error);
                Ok(Some(result))
            }
            (result, _) => result.map(Some),
        }
    })
    .await
    .map_err(|_| "备份工作异常结束")?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workspace_pointer_accepts_only_local_workspace_names() {
        assert!(valid_workspace_name("lite"));
        assert!(valid_workspace_name(&format!(
            "lite-restored-{}",
            Uuid::new_v4()
        )));
        assert!(!valid_workspace_name("../lite"));
        assert!(!valid_workspace_name("lite-restored-../paper"));
        assert!(!super::super::allowed(
            "POST",
            "/api/v1/maintenance/quiesce"
        ));
    }

    #[test]
    #[ignore = "requires packaged engine; run after build-engine with RGS_TEST_ENGINE_PATH"]
    fn native_host_exports_and_restores_into_a_separate_workspace() {
        let executable =
            PathBuf::from(std::env::var_os("RGS_TEST_ENGINE_PATH").expect("test engine"));
        let root = std::env::temp_dir().join(format!("rgs-backup-{}", Uuid::new_v4()));
        let original = root.join("lite");
        let target = root.join("合成工作区备份");
        fs::create_dir_all(&target).expect("test backup folder");
        let mut host = Host {
            data_dir: original.clone(),
            executable,
            ..Host::default()
        };
        host.start().expect("start original workspace");
        quiesce(&mut host).expect("idle workspace");
        host.stop();
        let result = run_offline(&host, "export", &target, &original).expect("export workspace");
        let snapshot = PathBuf::from(result["path"].as_str().expect("snapshot path"));
        assert!(snapshot.starts_with(&target));
        host.start().expect("restart original workspace");
        let result = switch_workspace(&mut host, &snapshot).expect("restore workspace");
        assert_eq!(result["previous_path"], json!(original));
        assert_ne!(host.data_dir, original);
        assert_eq!(active_workspace(&root), host.data_dir);
        assert!(original.join("researchgraph-lite.sqlite3").is_file());
        assert!(host.status().running);
        host.stop();
        let test_root = root
            .canonicalize()
            .expect("canonical isolated test directory");
        assert_eq!(
            test_root.parent(),
            Some(std::env::temp_dir().canonicalize().unwrap().as_path())
        );
        fs::remove_dir_all(test_root).expect("clean only this isolated test directory");
    }
}
