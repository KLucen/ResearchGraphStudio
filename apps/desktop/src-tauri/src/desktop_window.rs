use rfd::{AsyncMessageDialog, MessageButtons, MessageDialogResult, MessageLevel};
use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::{Path, PathBuf},
    sync::Mutex,
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent},
    App, AppHandle, Emitter, Manager, State, Window, WindowEvent,
};

const TRAY_ID: &str = "desktop-window";
const OPEN_MENU_ID: &str = "desktop-window-open";
const EXIT_MENU_ID: &str = "desktop-window-exit";
const HIDE_LABEL: &str = "隐藏到任务栏托盘";
const EXIT_LABEL: &str = "退出主程序";
const CHANGED_EVENT: &str = "desktop-close-behavior-changed";

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CloseBehavior {
    HideToTray,
    Exit,
}

pub struct ClosePreference {
    path: PathBuf,
    behavior: Option<CloseBehavior>,
    prompt_open: bool,
}

impl ClosePreference {
    fn load(path: PathBuf) -> Self {
        let behavior = fs::read(&path)
            .ok()
            .and_then(|bytes| serde_json::from_slice(&bytes).ok());
        Self {
            path,
            behavior,
            prompt_open: false,
        }
    }

    fn save(&mut self, behavior: CloseBehavior) -> Result<CloseBehavior, &'static str> {
        let directory = self.path.parent().ok_or("无法定位桌面设置目录")?;
        fs::create_dir_all(directory).map_err(|_| "无法创建桌面设置目录")?;
        let payload = serde_json::to_vec(&behavior).map_err(|_| "无法编码窗口关闭设置")?;
        let temporary = directory.join(format!(".desktop-close-{}.tmp", uuid::Uuid::new_v4()));
        if fs::write(&temporary, payload)
            .and_then(|()| fs::rename(&temporary, &self.path))
            .is_err()
        {
            let _ = fs::remove_file(&temporary);
            return Err("无法保存窗口关闭设置");
        }
        self.behavior = Some(behavior);
        Ok(behavior)
    }
}

pub fn setup(app: &App, directory: &Path) {
    app.manage(Mutex::new(ClosePreference::load(
        directory.join("desktop-window-close.json"),
    )));
}

#[tauri::command]
pub fn desktop_close_behavior(
    state: State<'_, Mutex<ClosePreference>>,
) -> Result<Option<CloseBehavior>, &'static str> {
    Ok(state.lock().map_err(|_| "窗口设置不可用")?.behavior)
}

#[tauri::command]
pub fn set_desktop_close_behavior(
    state: State<'_, Mutex<ClosePreference>>,
    behavior: CloseBehavior,
) -> Result<CloseBehavior, &'static str> {
    state.lock().map_err(|_| "窗口设置不可用")?.save(behavior)
}

pub fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.show().is_err() {
            return;
        }
        let _ = window.unminimize();
        let _ = window.set_focus();
        if let Some(tray) = app.tray_by_id(TRAY_ID) {
            let _ = tray.set_visible(false);
        }
    }
}

fn show_tray(app: &AppHandle) -> tauri::Result<TrayIcon> {
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        tray.set_visible(true)?;
        return Ok(tray);
    }
    let open = MenuItem::with_id(app, OPEN_MENU_ID, "打开主窗口", true, None::<&str>)?;
    let exit = MenuItem::with_id(app, EXIT_MENU_ID, EXIT_LABEL, true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &exit])?;
    let mut builder = TrayIconBuilder::with_id(TRAY_ID)
        .menu(&menu)
        .tooltip("ResearchGraph Studio")
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            OPEN_MENU_ID => show_main_window(app),
            EXIT_MENU_ID => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if matches!(
                event,
                TrayIconEvent::Click {
                    button: MouseButton::Left,
                    button_state: MouseButtonState::Up,
                    ..
                }
            ) {
                show_main_window(tray.app_handle());
            }
        });
    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }
    builder.build(app)
}

fn report_error(window: &Window, message: &'static str) {
    let dialog = AsyncMessageDialog::new()
        .set_parent(window)
        .set_title("关闭窗口")
        .set_level(MessageLevel::Error)
        .set_description(message);
    tauri::async_runtime::spawn(async move { dialog.show().await });
}

fn hide_main_window(window: &Window) {
    match show_tray(window.app_handle()) {
        Ok(tray) => {
            if window.hide().is_err() {
                let _ = tray.set_visible(false);
                report_error(window, "无法隐藏窗口，请重试或在设置中选择退出主程序。");
            }
        }
        Err(_) => report_error(
            window,
            "无法显示任务栏托盘图标，请重试或在设置中选择退出主程序。",
        ),
    }
}

fn finish_prompt(window: &Window, result: MessageDialogResult) {
    let behavior = match result {
        MessageDialogResult::Custom(label) if label == HIDE_LABEL => {
            Some(CloseBehavior::HideToTray)
        }
        MessageDialogResult::Custom(label) if label == EXIT_LABEL => Some(CloseBehavior::Exit),
        _ => None,
    };
    let state = window.state::<Mutex<ClosePreference>>();
    let saved = state
        .lock()
        .map_err(|_| "窗口设置不可用")
        .and_then(|mut preference| {
            preference.prompt_open = false;
            behavior
                .map(|behavior| preference.save(behavior))
                .transpose()
        });
    match saved {
        Ok(Some(behavior)) => {
            let _ = window.emit(CHANGED_EVENT, behavior);
            match behavior {
                CloseBehavior::HideToTray => hide_main_window(window),
                CloseBehavior::Exit => window.app_handle().exit(0),
            }
        }
        Ok(None) => {}
        Err(message) => report_error(window, message),
    }
}

pub fn on_window_event(window: &Window, event: &WindowEvent) {
    let WindowEvent::CloseRequested { api, .. } = event else {
        return;
    };
    if window.label() != "main" {
        return;
    }
    let state = window.state::<Mutex<ClosePreference>>();
    let Ok(mut preference) = state.lock() else {
        api.prevent_close();
        report_error(window, "窗口设置不可用");
        return;
    };
    match preference.behavior {
        Some(CloseBehavior::Exit) => {}
        Some(CloseBehavior::HideToTray) => {
            api.prevent_close();
            drop(preference);
            hide_main_window(window);
        }
        None => {
            api.prevent_close();
            if preference.prompt_open {
                return;
            }
            preference.prompt_open = true;
            let window = window.clone();
            tauri::async_runtime::spawn(async move {
                let result = AsyncMessageDialog::new()
                    .set_parent(&window)
                    .set_title("关闭窗口")
                    .set_description("选择以后关闭窗口时的操作。你可以在设置与诊断中更改。")
                    .set_buttons(MessageButtons::YesNoCancelCustom(
                        HIDE_LABEL.into(),
                        EXIT_LABEL.into(),
                        "取消".into(),
                    ))
                    .show()
                    .await;
                let parent = window.clone();
                let _ = window.run_on_main_thread(move || finish_prompt(&parent, result));
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn first_run_has_no_choice_and_changes_survive_restart() {
        let directory = std::env::temp_dir().join(format!("rgs-close-{}", uuid::Uuid::new_v4()));
        let path = directory.join("desktop-window-close.json");
        let mut preference = ClosePreference::load(path.clone());
        assert_eq!(preference.behavior, None);
        assert!(!path.exists());

        preference.save(CloseBehavior::HideToTray).unwrap();
        assert_eq!(
            ClosePreference::load(path.clone()).behavior,
            Some(CloseBehavior::HideToTray)
        );
        preference.save(CloseBehavior::Exit).unwrap();
        assert_eq!(
            ClosePreference::load(path.clone()).behavior,
            Some(CloseBehavior::Exit)
        );

        fs::write(&path, b"invalid").unwrap();
        assert_eq!(ClosePreference::load(path.clone()).behavior, None);
        fs::remove_file(path).unwrap();
        fs::remove_dir(directory).unwrap();
    }
}
