use robius_speech::{NativeSpeechEvent, NativeSpeechOptions, NativeSpeechSession};
use serde::Serialize;
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter};

#[derive(Default)]
pub struct SpeechState {
    session: Arc<Mutex<Option<NativeSpeechSession>>>,
}

#[derive(Clone, Serialize)]
#[serde(tag = "kind", rename_all = "camelCase")]
pub enum SpeechEventPayload {
    Started,
    Transcript {
        text: String,
        #[serde(rename = "isFinal")]
        is_final: bool,
    },
    AudioLevel {
        level: f32,
    },
    Stopped,
    Error {
        message: String,
    },
}

fn emit_event(app: &AppHandle, event: SpeechEventPayload) {
    let _ = app.emit("friday://speech", event);
}

#[tauri::command]
pub fn start_dictation(app: AppHandle, state: tauri::State<'_, SpeechState>) -> Result<(), String> {
    {
        let guard = state
            .session
            .lock()
            .map_err(|_| "speech service is unavailable".to_string())?;
        if guard.is_some() {
            return Err("dictation is already active".to_string());
        }
    }

    let slot = state.session.clone();
    let app_handle = app.clone();

    let session = NativeSpeechSession::start(
        NativeSpeechOptions {
            // Use the Windows dictation language installed for the current user.
            locale: None,
            prefer_on_device: true,
        },
        move |event| {
            let payload = match &event {
                NativeSpeechEvent::Started => SpeechEventPayload::Started,
                NativeSpeechEvent::Transcript { text, is_final } => {
                    SpeechEventPayload::Transcript {
                        text: text.clone(),
                        is_final: *is_final,
                    }
                }
                NativeSpeechEvent::AudioLevel(level) => {
                    SpeechEventPayload::AudioLevel { level: *level }
                }
                NativeSpeechEvent::Stopped => SpeechEventPayload::Stopped,
                NativeSpeechEvent::Error(error) => {
                    if let Ok(mut guard) = slot.lock() {
                        guard.take();
                    }
                    SpeechEventPayload::Error {
                        message: error.to_string(),
                    }
                }
            };

            if matches!(event, NativeSpeechEvent::Stopped) {
                if let Ok(mut guard) = slot.lock() {
                    guard.take();
                }
            }

            emit_event(&app_handle, payload);
        },
    )
    .map_err(|error| format!("speech recognition is unavailable: {error}"))?;

    let mut guard = state
        .session
        .lock()
        .map_err(|_| "speech service is unavailable".to_string())?;
    *guard = Some(session);

    Ok(())
}

#[tauri::command]
pub fn stop_dictation(state: tauri::State<'_, SpeechState>) -> Result<(), String> {
    let guard = state
        .session
        .lock()
        .map_err(|_| "speech service is unavailable".to_string())?;

    if let Some(session) = guard.as_ref() {
        session.stop();
    }

    Ok(())
}

#[tauri::command]
pub fn cancel_dictation(state: tauri::State<'_, SpeechState>) -> Result<(), String> {
    let mut guard = state
        .session
        .lock()
        .map_err(|_| "speech service is unavailable".to_string())?;

    if let Some(session) = guard.take() {
        session.cancel();
    }

    Ok(())
}
