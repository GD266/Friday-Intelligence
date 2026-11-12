//! Neural text-to-speech through the Microsoft Edge read-aloud voices.
//!
//! This is the free, key-less "human voice" provider: the same Azure neural
//! voices that Edge reads pages with. Audio is generated in Rust and handed to
//! the webview as base64 MP3, mirroring the ElevenLabs path so the frontend has
//! one playback pipeline.

use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use msedge_tts::tts::client::connect;
use msedge_tts::tts::SpeechConfig;
use msedge_tts::voice::{get_voices_list, Voice};
use serde::{Deserialize, Serialize};

/// 24 kHz 48 kbit/s mono MP3 plays in every WebView2 build.
const AUDIO_FORMAT: &str = "audio-24khz-48kbitrate-mono-mp3";
const MAX_TEXT_CHARS: usize = 5_000;

/// The voices FRIDAY ships with first. Ordered by how well they fit the
/// "calm, confident, intelligent female assistant" brief.
const PREFERRED: [&str; 6] = [
    "en-IN-NeerjaExpressiveNeural",
    "en-GB-SoniaNeural",
    "en-US-AvaNeural",
    "en-US-EmmaNeural",
    "en-GB-LibbyNeural",
    "en-IN-NeerjaNeural",
];

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EdgeVoice {
    pub short_name: String,
    pub locale: String,
    pub gender: String,
    pub friendly_name: String,
    /// True for the curated voices shown at the top of the picker.
    pub recommended: bool,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EdgeSpeakRequest {
    pub text: String,
    #[serde(default)]
    pub voice: Option<String>,
    /// Percentage adjustment, -50..50, matching the Speech SDK convention.
    #[serde(default)]
    pub rate: Option<i32>,
    #[serde(default)]
    pub pitch: Option<i32>,
    #[serde(default)]
    pub volume: Option<i32>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EdgeAudio {
    pub audio_base64: String,
    pub mime_type: String,
    pub voice: String,
}

const DEFAULT_VOICE: &str = "en-IN-NeerjaExpressiveNeural";

/// Azure voice names look like `en-GB-SoniaNeural`; anything else is rejected
/// so the value cannot be smuggled into the SSML that we send upstream.
fn validate_voice(name: &str) -> Result<String, String> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Ok(DEFAULT_VOICE.to_string());
    }

    let valid = trimmed.len() <= 64
        && trimmed.ends_with("Neural")
        && trimmed.split('-').count() >= 3
        && trimmed
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '-');

    if !valid {
        return Err("That voice name is not valid.".to_string());
    }

    Ok(trimmed.to_string())
}

fn clamp_percent(value: Option<i32>) -> i32 {
    value.unwrap_or(0).clamp(-50, 50)
}

/// Strips characters that break SSML and collapses runs of blank lines so the
/// reader does not insert long pauses mid-sentence.
fn prepare_text(text: &str) -> String {
    let cleaned: String = text
        .chars()
        .filter(|character| {
            !character.is_control() || *character == '\n' || *character == '\t'
        })
        .collect();

    let collapsed = cleaned
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect::<Vec<_>>()
        .join("\n");

    collapsed.chars().take(MAX_TEXT_CHARS).collect()
}

fn to_voice(voice: &Voice) -> Option<EdgeVoice> {
    let short_name = voice.name.clone();
    let locale = voice.locale.clone().unwrap_or_default();
    if !locale.starts_with("en") {
        return None;
    }

    Some(EdgeVoice {
        recommended: PREFERRED.contains(&short_name.as_str()),
        friendly_name: voice
            .friendly_name
            .clone()
            .unwrap_or_else(|| short_name.clone()),
        gender: voice.gender.clone().unwrap_or_else(|| "Female".to_string()),
        locale,
        short_name,
    })
}

fn sort_voices(mut voices: Vec<EdgeVoice>) -> Vec<EdgeVoice> {
    voices.sort_by_key(|voice| {
        let rank = PREFERRED
            .iter()
            .position(|name| *name == voice.short_name)
            .map(|index| index as u32)
            .unwrap_or(u32::MAX / 2);
        // Female voices first, then the curated order, then locale.
        (voice.gender != "Female", rank, voice.locale.clone())
    });
    voices
}

#[tauri::command]
pub async fn edge_voices() -> Result<Vec<EdgeVoice>, String> {
    tauri::async_runtime::spawn_blocking(move || -> Result<Vec<EdgeVoice>, String> {
        let voices = get_voices_list()
            .map_err(|error| format!("Could not reach the neural voice catalog: {error}"))?;

        let english: Vec<EdgeVoice> = voices.iter().filter_map(to_voice).collect();
        if english.is_empty() {
            return Err("No English neural voices were returned.".to_string());
        }

        Ok(sort_voices(english))
    })
    .await
    .map_err(|_| "The voice catalog stopped unexpectedly.".to_string())?
}

#[tauri::command]
pub async fn edge_speak(request: EdgeSpeakRequest) -> Result<EdgeAudio, String> {
    let text = prepare_text(&request.text);
    if text.trim().is_empty() {
        return Err("There is nothing to speak.".to_string());
    }

    let voice = validate_voice(request.voice.as_deref().unwrap_or(DEFAULT_VOICE))?;
    let config = SpeechConfig {
        voice_name: voice.clone(),
        audio_format: AUDIO_FORMAT.to_string(),
        rate: clamp_percent(request.rate),
        pitch: clamp_percent(request.pitch),
        volume: clamp_percent(request.volume),
    };

    tauri::async_runtime::spawn_blocking(move || -> Result<EdgeAudio, String> {
        let mut client = connect()
            .map_err(|error| format!("Could not open the neural voice stream: {error}"))?;

        let audio = client
            .synthesize(&text, &config)
            .map_err(|error| format!("Neural voice synthesis failed: {error}"))?;

        if audio.audio_bytes.is_empty() {
            return Err("The neural voice returned no audio. Try again.".to_string());
        }

        let mime_type = if audio.audio_format.contains("mp3") {
            "audio/mpeg"
        } else {
            "audio/wav"
        };

        Ok(EdgeAudio {
            audio_base64: BASE64.encode(audio.audio_bytes),
            mime_type: mime_type.to_string(),
            voice,
        })
    })
    .await
    .map_err(|_| "The voice engine stopped unexpectedly.".to_string())?
}

/// Short, fixed sentence used by the Settings preview button.
#[tauri::command]
pub async fn edge_preview(voice: Option<String>) -> Result<EdgeAudio, String> {
    edge_speak(EdgeSpeakRequest {
        text: "Good evening. FRIDAY is online and standing by.".to_string(),
        voice,
        rate: Some(0),
        pitch: Some(0),
        volume: Some(0),
    })
    .await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_azure_voice_names() {
        assert_eq!(
            validate_voice("en-IN-NeerjaExpressiveNeural").unwrap(),
            "en-IN-NeerjaExpressiveNeural"
        );
        assert_eq!(
            validate_voice("  en-GB-SoniaNeural  ").unwrap(),
            "en-GB-SoniaNeural"
        );
    }

    #[test]
    fn falls_back_to_the_default_voice() {
        assert_eq!(validate_voice("").unwrap(), DEFAULT_VOICE);
        assert_eq!(validate_voice("   ").unwrap(), DEFAULT_VOICE);
    }

    #[test]
    fn rejects_injected_voice_names() {
        assert!(validate_voice("en-GB-SoniaNeural\"><speak>").is_err());
        assert!(validate_voice("http://example.com").is_err());
        assert!(validate_voice("Sonia").is_err());
    }

    #[test]
    fn clamps_speech_adjustments() {
        assert_eq!(clamp_percent(Some(500)), 50);
        assert_eq!(clamp_percent(Some(-500)), -50);
        assert_eq!(clamp_percent(None), 0);
    }

    #[test]
    fn strips_control_characters_and_blank_lines() {
        let prepared = prepare_text("Hello\u{0007} there\n\n\nGeneral Kenobi");
        assert_eq!(prepared, "Hello there\nGeneral Kenobi");
    }

    #[test]
    fn caps_very_long_text() {
        let prepared = prepare_text(&"a".repeat(9_000));
        assert_eq!(prepared.chars().count(), MAX_TEXT_CHARS);
    }

    #[test]
    fn keeps_only_english_voices() {
        let voice = Voice {
            name: "hi-IN-SwaraNeural".to_string(),
            locale: Some("hi-IN".to_string()),
            gender: Some("Female".to_string()),
            friendly_name: None,
            suggested_codec: None,
        };
        assert!(to_voice(&voice).is_none());
    }

    #[test]
    fn marks_curated_voices_as_recommended() {
        let voice = Voice {
            name: "en-GB-SoniaNeural".to_string(),
            locale: Some("en-GB".to_string()),
            gender: Some("Female".to_string()),
            friendly_name: Some("Microsoft Sonia Online".to_string()),
            suggested_codec: None,
        };
        let mapped = to_voice(&voice).unwrap();
        assert!(mapped.recommended);
        assert_eq!(mapped.friendly_name, "Microsoft Sonia Online");
    }
}
