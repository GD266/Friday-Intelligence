#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod ai;
mod automation;
mod edge_tts;
mod speech;
mod stt;
mod telemetry;

fn main() {
    tauri::Builder::default()
        .manage(telemetry::TelemetryState::new())
        .manage(speech::SpeechState::default())
        .manage(stt::SttState::default())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_tts::init())
        .invoke_handler(tauri::generate_handler![
            telemetry::get_system_snapshot,
            automation::run_automation,
            speech::start_dictation,
            speech::stop_dictation,
            speech::cancel_dictation,
            ai::ai_chat,
            ai::ai_credential_status,
            ai::elevenlabs_speak,
            ai::elevenlabs_voices,
            ai::developer_create_project,
            stt::stt_local_status,
            stt::stt_models,
            stt::stt_install_local,
            stt::stt_transcribe_local,
            stt::stt_transcribe_groq,
            edge_tts::edge_voices,
            edge_tts::edge_speak,
            edge_tts::edge_preview,
        ])
        .run(tauri::generate_context!())
        .expect("error while running FRIDAY Intelligence");
}
