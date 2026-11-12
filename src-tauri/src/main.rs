#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod automation;
mod speech;
mod telemetry;

fn main() {
    tauri::Builder::default()
        .manage(telemetry::TelemetryState::new())
        .manage(speech::SpeechState::default())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_tts::init())
        .invoke_handler(tauri::generate_handler![
            telemetry::get_system_snapshot,
            automation::run_automation,
            speech::start_dictation,
            speech::stop_dictation,
            speech::cancel_dictation,
        ])
        .run(tauri::generate_context!())
        .expect("error while running FRIDAY Intelligence");
}
