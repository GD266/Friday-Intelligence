use enigo::{Direction, Enigo, Key, Keyboard, Settings};
use serde::Serialize;
use std::path::Path;
use std::process::Command;
use std::time::Duration;
use tauri::{AppHandle, Manager};

#[derive(Serialize)]
pub struct AutomationResult {
    pub success: bool,
    pub message: String,
    pub action: String,
}

fn launched(program: &str, args: &[&str]) -> Result<(), String> {
    Command::new(program)
        .args(args)
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("could not launch {program}: {error}"))
}

fn start_target(target: &str) -> Result<(), String> {
    launched("cmd.exe", &["/C", "start", "", target])
}

fn open_url(url: &str) -> Result<(), String> {
    let valid = (url.starts_with("https://") || url.starts_with("http://"))
        && !url
            .chars()
            .any(|character| character.is_control() || character.is_whitespace());

    if !valid {
        return Err("only http and https URLs are supported".to_string());
    }

    launched("rundll32.exe", &["url.dll,FileProtocolHandler", url])
}

fn user_folder(name: &str) -> Result<String, String> {
    let profile = std::env::var("USERPROFILE")
        .map_err(|_| "could not locate the user profile".to_string())?;
    Ok(format!("{profile}\\{name}"))
}

fn open_folder(name: &str) -> Result<(), String> {
    let path = user_folder(name)?;
    if !Path::new(&path).is_dir() {
        return Err(format!("{name} is not available on this system"));
    }
    launched("explorer.exe", &[&path])
}

fn press_key(key: Key) -> Result<(), String> {
    let mut enigo = Enigo::new(&Settings::default())
        .map_err(|error| format!("input engine unavailable: {error}"))?;
    enigo
        .key(key, Direction::Click)
        .map_err(|error| format!("input action failed: {error}"))
}

fn press_combo(modifier: Key, key: Key) -> Result<(), String> {
    let mut enigo = Enigo::new(&Settings::default())
        .map_err(|error| format!("input engine unavailable: {error}"))?;

    enigo
        .key(modifier, Direction::Press)
        .map_err(|error| format!("input action failed: {error}"))?;

    let result = enigo
        .key(key, Direction::Click)
        .map_err(|error| format!("input action failed: {error}"));

    let _ = enigo.key(modifier, Direction::Release);
    result
}

fn type_text(app: &AppHandle, text: &str) -> Result<(), String> {
    if text.trim().is_empty() {
        return Err("there is no text to type".to_string());
    }

    if text.chars().count() > 500 {
        return Err("typed text is limited to 500 characters".to_string());
    }

    let window = app.get_webview_window("main");
    if let Some(window) = &window {
        window
            .hide()
            .map_err(|error| format!("could not hide the FRIDAY window: {error}"))?;
    }

    std::thread::sleep(Duration::from_millis(450));

    let result = (|| {
        let mut enigo = Enigo::new(&Settings::default())
            .map_err(|error| format!("input engine unavailable: {error}"))?;
        enigo
            .text(text)
            .map_err(|error| format!("could not type the requested text: {error}"))
    })();

    std::thread::sleep(Duration::from_millis(250));

    if let Some(window) = &window {
        let _ = window.show();
        let _ = window.set_focus();
    }

    result
}

fn take_screenshot() -> Result<String, String> {
    let folder = format!(
        "{}\\Pictures\\FRIDAY",
        std::env::var("USERPROFILE").map_err(|_| "could not locate the user profile".to_string())?
    );
    std::fs::create_dir_all(&folder)
        .map_err(|error| format!("could not create the screenshot folder: {error}"))?;

    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    let path = format!("{folder}\\friday-{stamp}.png");
    let escaped_path = path.replace('\'', "''");

    let script = format!(
        "Add-Type -AssemblyName System.Windows.Forms; \
         Add-Type -AssemblyName System.Drawing; \
         $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; \
         $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height; \
         $graphics = [System.Drawing.Graphics]::FromImage($bitmap); \
         $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size); \
         $bitmap.Save('{escaped_path}', [System.Drawing.Imaging.ImageFormat]::Png); \
         $graphics.Dispose(); $bitmap.Dispose()"
    );

    let status = Command::new("powershell.exe")
        .args([
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            &script,
        ])
        .status()
        .map_err(|error| format!("could not start the screenshot service: {error}"))?;

    if !status.success() {
        return Err("the screenshot service did not complete successfully".to_string());
    }

    Ok(path)
}

fn encode_query(input: &str) -> String {
    let mut encoded = String::new();
    for byte in input.trim().as_bytes() {
        match byte {
            b'a'..=b'z' | b'A'..=b'Z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                encoded.push(*byte as char)
            }
            b' ' => encoded.push('+'),
            _ => encoded.push_str(&format!("%{byte:02X}")),
        }
    }
    encoded
}

fn run_action(app: &AppHandle, action: &str, argument: Option<&str>) -> Result<String, String> {
    match action {
        "open_notepad" => launched("notepad.exe", &[]).map(|_| "Notepad is opening.".to_string()),
        "open_calculator" => {
            launched("calc.exe", &[]).map(|_| "Calculator is opening.".to_string())
        }
        "open_explorer" => {
            launched("explorer.exe", &[]).map(|_| "File Explorer is opening.".to_string())
        }
        "open_terminal" => Command::new("wt.exe")
            .spawn()
            .or_else(|_| Command::new("cmd.exe").spawn())
            .map(|_| "The terminal is opening.".to_string())
            .map_err(|error| format!("could not open a terminal: {error}")),
        "open_settings" => {
            start_target("ms-settings:").map(|_| "Windows Settings is opening.".to_string())
        }
        "open_browser" => {
            open_url("https://www.google.com").map(|_| "The browser is opening.".to_string())
        }
        "open_task_manager" => {
            launched("taskmgr.exe", &[]).map(|_| "Task Manager is opening.".to_string())
        }
        "open_paint" => launched("mspaint.exe", &[]).map(|_| "Paint is opening.".to_string()),
        "open_desktop" => open_folder("Desktop").map(|_| "Opening your desktop.".to_string()),
        "open_downloads" => open_folder("Downloads").map(|_| "Opening Downloads.".to_string()),
        "open_documents" => open_folder("Documents").map(|_| "Opening Documents.".to_string()),
        "open_folder" => {
            let path = argument.ok_or_else(|| "a folder path is required".to_string())?;
            if !Path::new(path).is_dir() {
                return Err("that folder does not exist".to_string());
            }
            launched("explorer.exe", &[path]).map(|_| "The folder is opening.".to_string())
        }
        "lock_workstation" => launched("rundll32.exe", &["user32.dll,LockWorkStation"])
            .map(|_| "Locking the workstation now.".to_string()),
        "volume_up" => press_key(Key::VolumeUp).map(|_| "Volume increased.".to_string()),
        "volume_down" => press_key(Key::VolumeDown).map(|_| "Volume decreased.".to_string()),
        "volume_mute" => press_key(Key::VolumeMute).map(|_| "Volume muted.".to_string()),
        "media_play_pause" => {
            press_key(Key::MediaPlayPause).map(|_| "Media playback toggled.".to_string())
        }
        "media_next" => press_key(Key::MediaNextTrack).map(|_| "Skipping forward.".to_string()),
        "media_previous" => press_key(Key::MediaPrevTrack).map(|_| "Skipping back.".to_string()),
        "media_stop" => press_key(Key::MediaStop).map(|_| "Media stopped.".to_string()),
        "window_minimize" => {
            press_combo(Key::Meta, Key::DownArrow).map(|_| "Window minimized.".to_string())
        }
        "window_maximize" => {
            press_combo(Key::Meta, Key::UpArrow).map(|_| "Window maximized.".to_string())
        }
        "window_close" => {
            press_combo(Key::Alt, Key::F4).map(|_| "The active window has been closed.".to_string())
        }
        "type_text" => {
            let text = argument.ok_or_else(|| "text is required".to_string())?;
            type_text(app, text).map(|_| "The text has been typed.".to_string())
        }
        "search_web" => {
            let query = argument.ok_or_else(|| "a search query is required".to_string())?;
            let url = format!("https://www.google.com/search?q={}", encode_query(query));
            open_url(&url).map(|_| format!("Searching the web for \"{query}\"."))
        }
        "open_url" => {
            let url = argument.ok_or_else(|| "a URL is required".to_string())?;
            open_url(url).map(|_| "Opening the link.".to_string())
        }
        "screenshot" => take_screenshot().map(|path| format!("Screenshot saved to {path}.")),
        "empty_recycle_bin" => Command::new("powershell.exe")
            .args([
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-Command",
                "Clear-RecycleBin -Force -ErrorAction SilentlyContinue",
            ])
            .status()
            .map_err(|error| format!("could not empty the recycle bin: {error}"))
            .and_then(|status| {
                if status.success() {
                    Ok("The recycle bin has been emptied.".to_string())
                } else {
                    Err("the recycle bin could not be emptied".to_string())
                }
            }),
        _ => Err(format!("unknown automation action: {action}")),
    }
}

#[tauri::command]
pub fn run_automation(
    app: AppHandle,
    action: String,
    argument: Option<String>,
) -> Result<AutomationResult, String> {
    let message = run_action(&app, &action, argument.as_deref())?;

    Ok(AutomationResult {
        success: true,
        message,
        action,
    })
}
