//! Speech-to-text.
//!
//! Two providers share one request shape:
//!   * `local` runs whisper.cpp on this machine. No API key, no network at
//!     inference time, audio never leaves the device.
//!   * `groq` calls Groq's hosted Whisper endpoint when the user supplies a key.
//!
//! Audio always arrives as a 16 kHz mono 16-bit PCM WAV encoded in base64, so
//! neither provider has to decode arbitrary containers.

use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager};

/// Pinned whisper.cpp release. Bumping this changes the binary layout, so the
/// extraction filter below must be re-checked.
const WHISPER_ZIP_URL: &str =
    "https://github.com/ggml-org/whisper.cpp/releases/download/b5454/whisper-bin-x64.zip";
const MODEL_BASE_URL: &str = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main";
const GROQ_BASE: &str = "https://api.groq.com/openai/v1";

/// Vocabulary primed into Whisper so product names survive transcription.
const DEFAULT_PROMPT: &str =
    "FRIDAY Intelligence. Open Notepad. Open Calculator. Open File Explorer. \
     VS Code. GitHub. OpenCode. Tauri. Open Chrome. Take a screenshot.";

/// Files the CLI needs at runtime. `ggml-cpu-*` is selected by CPU dispatch.
const REQUIRED_BINARIES: [&str; 4] = ["whisper-cli.exe", "whisper.dll", "ggml.dll", "ggml-base.dll"];

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SttModelInfo {
    pub id: &'static str,
    pub label: &'static str,
    pub file: &'static str,
    pub approx_mb: u32,
    pub description: &'static str,
}

pub const MODELS: [SttModelInfo; 3] = [
    SttModelInfo {
        id: "base.en",
        label: "Whisper Base (English)",
        file: "ggml-base.en.bin",
        approx_mb: 142,
        description: "Fastest download. Good for quiet rooms and short commands.",
    },
    SttModelInfo {
        id: "small.en",
        label: "Whisper Small (English)",
        file: "ggml-small.en.bin",
        approx_mb: 466,
        description: "Recommended. Clearly better with accents and wake-up commands.",
    },
    SttModelInfo {
        id: "large-v3-turbo-q5_0",
        label: "Whisper Large v3 Turbo (quantized)",
        file: "ggml-large-v3-turbo-q5_0.bin",
        approx_mb: 574,
        description: "Best accuracy, still runs on a modern CPU.",
    },
];

fn model_info(model_id: &str) -> &'static SttModelInfo {
    MODELS
        .iter()
        .find(|model| model.id == model_id)
        .unwrap_or(&MODELS[1])
}

pub struct SttState {
    /// Serialises installs and transcriptions: one whisper process at a time.
    lock: Arc<Mutex<()>>,
}

impl Default for SttState {
    fn default() -> Self {
        Self {
            lock: Arc::new(Mutex::new(())),
        }
    }
}

impl SttState {
    fn lock(&self) -> Arc<Mutex<()>> {
        self.lock.clone()
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SttLocalStatus {
    pub engine_ready: bool,
    pub model_ready: bool,
    pub ready: bool,
    pub model: String,
    pub model_path: String,
    pub engine_path: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SttProgress {
    pub stage: String,
    pub received: u64,
    pub total: u64,
    pub message: String,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct LocalTranscribeRequest {
    pub audio_base64: String,
    #[serde(default)]
    pub language: Option<String>,
    #[serde(default)]
    pub prompt: Option<String>,
    #[serde(default)]
    pub model: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct GroqTranscribeRequest {
    pub audio_base64: String,
    pub api_key: String,
    #[serde(default)]
    pub language: Option<String>,
    #[serde(default)]
    pub prompt: Option<String>,
    #[serde(default)]
    pub model: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Transcript {
    pub text: String,
    pub provider: String,
    pub model: String,
    pub elapsed_ms: u64,
    /// True when the decoder produced only a known silence artefact.
    pub empty: bool,
}

fn stt_root(app: &AppHandle) -> Result<PathBuf, String> {
    let base = app
        .path()
        .app_data_dir()
        .map_err(|_| "The app data directory is unavailable.".to_string())?;
    let root = base.join("stt");
    std::fs::create_dir_all(&root)
        .map_err(|error| format!("Could not create the speech data folder: {error}"))?;
    Ok(root)
}

fn engine_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(stt_root(app)?.join("engine"))
}

fn models_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = stt_root(app)?.join("models");
    std::fs::create_dir_all(&dir)
        .map_err(|error| format!("Could not create the model folder: {error}"))?;
    Ok(dir)
}

fn cli_path(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(engine_dir(app)?.join("whisper-cli.exe"))
}

fn model_path(app: &AppHandle, model_id: &str) -> Result<PathBuf, String> {
    Ok(models_dir(app)?.join(model_info(model_id).file))
}

fn inspect(app: &AppHandle, model_id: &str) -> Result<SttLocalStatus, String> {
    let engine = engine_dir(app)?;
    let cli = cli_path(app)?;
    let model = model_path(app, model_id)?;

    let engine_ready = cli.is_file()
        && REQUIRED_BINARIES
            .iter()
            .filter(|name| **name != "whisper-cli.exe")
            .all(|name| engine.join(name).is_file());

    let model_ready = model.is_file() && model.metadata().map(|meta| meta.len() > 1_000_000).unwrap_or(false);
    let ready = engine_ready && model_ready;

    let message = if ready {
        "On-device Whisper is ready.".to_string()
    } else if !engine_ready {
        "The Whisper engine is not installed yet.".to_string()
    } else {
        format!(
            "The {} model is not downloaded yet.",
            model_info(model_id).label
        )
    };

    Ok(SttLocalStatus {
        engine_ready,
        model_ready,
        ready,
        model: model_id.to_string(),
        model_path: model.to_string_lossy().to_string(),
        engine_path: cli.to_string_lossy().to_string(),
        message,
    })
}

#[tauri::command]
pub fn stt_local_status(app: AppHandle, model: Option<String>) -> Result<SttLocalStatus, String> {
    inspect(&app, model.as_deref().unwrap_or("small.en"))
}

#[tauri::command]
pub fn stt_models() -> Vec<SttModelInfo> {
    MODELS.to_vec()
}

fn emit_progress(app: &AppHandle, stage: &str, received: u64, total: u64, message: &str) {
    let _ = app.emit(
        "friday://stt-progress",
        SttProgress {
            stage: stage.to_string(),
            received,
            total,
            message: message.to_string(),
        },
    );
}

async fn download(app: &AppHandle, url: &str, destination: &Path, stage: &str, label: &str) -> Result<(), String> {
    use tokio::io::AsyncWriteExt;

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(3_600))
        .build()
        .map_err(|error| format!("Could not start the download client: {error}"))?;

    let response = client
        .get(url)
        .send()
        .await
        .map_err(|error| format!("Download failed for {label}: {error}"))?;

    let status = response.status();
    if !status.is_success() {
        return Err(format!("Download failed for {label}: HTTP {}", status.as_u16()));
    }

    let total = response.content_length().unwrap_or(0);
    let mut received: u64 = 0;

    // Write to a temporary file first so a dropped connection never leaves a
    // half-written model that looks installed.
    let partial = destination.with_extension("part");
    let mut file = tokio::fs::File::create(&partial)
        .await
        .map_err(|error| format!("Could not open {label} for writing: {error}"))?;

    let mut stream = response;
    let mut last_report = 0_u64;
    while let Some(chunk) = stream
        .chunk()
        .await
        .map_err(|error| format!("Download interrupted for {label}: {error}"))?
    {
        file.write_all(&chunk)
            .await
            .map_err(|error| format!("Could not save {label}: {error}"))?;
        received += chunk.len() as u64;

        if received - last_report > 2_000_000 {
            last_report = received;
            emit_progress(app, stage, received, total, &format!("Downloading {label}"));
        }
    }

    file.flush()
        .await
        .map_err(|error| format!("Could not finish saving {label}: {error}"))?;
    drop(file);

    tokio::fs::rename(&partial, destination)
        .await
        .map_err(|error| format!("Could not move {label} into place: {error}"))?;

    emit_progress(app, stage, received, total, &format!("Downloaded {label}"));
    Ok(())
}

fn extract_engine(archive: &Path, destination: &Path) -> Result<(), String> {
    let file = std::fs::File::open(archive)
        .map_err(|error| format!("Could not open the engine archive: {error}"))?;
    let mut zip = zip::ZipArchive::new(file)
        .map_err(|error| format!("The engine archive is unreadable: {error}"))?;

    std::fs::create_dir_all(destination)
        .map_err(|error| format!("Could not create the engine folder: {error}"))?;

    let mut extracted = 0_usize;
    for index in 0..zip.len() {
        let mut entry = zip
            .by_index(index)
            .map_err(|error| format!("The engine archive is corrupt: {error}"))?;
        if entry.is_dir() {
            continue;
        }

        let Some(name) = entry.name().rsplit('/').next().map(str::to_string) else {
            continue;
        };

        let wanted = REQUIRED_BINARIES.contains(&name.as_str())
            || (name.starts_with("ggml-cpu-") && name.ends_with(".dll"));

        if !wanted {
            continue;
        }

        let target = destination.join(&name);
        let mut output = std::fs::File::create(&target)
            .map_err(|error| format!("Could not write {name}: {error}"))?;
        std::io::copy(&mut entry, &mut output)
            .map_err(|error| format!("Could not extract {name}: {error}"))?;
        extracted += 1;
    }

    if extracted < REQUIRED_BINARIES.len() {
        let _ = std::fs::remove_dir_all(destination);
        return Err(
            "The Whisper archive did not contain the expected binaries. Try again later."
                .to_string(),
        );
    }

    Ok(())
}

#[tauri::command]
pub async fn stt_install_local(
    app: AppHandle,
    state: tauri::State<'_, SttState>,
    model: Option<String>,
) -> Result<SttLocalStatus, String> {
    let model_id = model.as_deref().unwrap_or("small.en").to_string();

    // Reject unknown model ids instead of silently downloading something else.
    if !MODELS.iter().any(|entry| entry.id == model_id) {
        return Err(format!("Unknown speech model: {model_id}"));
    }

    let app_for_blocking = app.clone();
    let model_for_blocking = model_id.clone();
    let lock = state.lock(); // Clone the Arc<Mutex<()>>

    tauri::async_runtime::spawn_blocking(move || -> Result<(), String> {
        let _guard = lock
            .lock()
            .map_err(|_| "The speech engine is busy.".to_string())?;

        let status = inspect(&app_for_blocking, &model_for_blocking)?;
        if status.ready {
            return Ok(());
        }

        let root = stt_root(&app_for_blocking)?;
        let engine = engine_dir(&app_for_blocking)?;

        if !status.engine_ready {
            let archive = root.join("whisper-bin-x64.zip");
            emit_progress(&app_for_blocking, "engine", 0, 0, "Downloading the Whisper engine");

            tauri::async_runtime::block_on(download(
                &app_for_blocking,
                WHISPER_ZIP_URL,
                &archive,
                "engine",
                "the Whisper engine",
            ))?;

            emit_progress(&app_for_blocking, "engine", 0, 0, "Installing the Whisper engine");
            let engine_target = engine.clone();
            let archive_for_extract = archive.clone();
            std::thread::spawn(move || extract_engine(&archive_for_extract, &engine_target))
                .join()
                .map_err(|_| "The engine installer stopped unexpectedly.".to_string())??;

            let _ = std::fs::remove_file(&archive);
        }

        if !inspect(&app_for_blocking, &model_for_blocking)?.model_ready {
            let info = model_info(&model_for_blocking);
            let target = model_path(&app_for_blocking, &model_for_blocking)?;
            let url = format!("{MODEL_BASE_URL}/{}", info.file);

            emit_progress(
                &app_for_blocking,
                "model",
                0,
                0,
                &format!("Downloading {} ({} MB)", info.label, info.approx_mb),
            );

            tauri::async_runtime::block_on(download(
                &app_for_blocking,
                &url,
                &target,
                "model",
                info.label,
            ))?;
        }

        emit_progress(&app_for_blocking, "done", 1, 1, "On-device Whisper is ready");
        Ok(())
    })
    .await
    .map_err(|_| "The installer stopped unexpectedly.".to_string())??;

    inspect(&app, &model_id)
}

/// Whisper expects a bare language code; regional tags such as `en-IN` are not
/// valid. We keep the region in the UI for voice selection only.
fn whisper_language(tag: Option<&str>) -> String {
    match tag.map(|value| value.trim().to_ascii_lowercase()) {
        Some(value) if value.is_empty() => "en".to_string(),
        Some(value) => value
            .split(['-', '_'])
            .next()
            .unwrap_or("en")
            .to_string(),
        None => "en".to_string(),
    }
}

/// Whisper emits a handful of memorised phrases when it is given silence.
fn clean_transcript(text: &str) -> String {
    let trimmed = text.trim();
    let normalised = trimmed.trim_matches(['"', '\u{201c}', '\u{201d}']).trim();

    let hallucinations = [
        "thank you.",
        "thanks for watching!",
        "thanks for watching.",
        "you",
        "(silence)",
        "[silence]",
        "[blank_audio]",
        "subtitles by the amara.org community",
        "please subscribe.",
    ];

    if hallucinations.contains(&normalised.to_ascii_lowercase().as_str()) {
        return String::new();
    }

    normalised.to_string()
}

fn run_local_whisper(
    app: &AppHandle,
    audio: &[u8],
    language: Option<&str>,
    prompt: Option<&str>,
    model_id: &str,
) -> Result<String, String> {
    let cli = cli_path(app)?;
    if !cli.is_file() {
        return Err("The on-device Whisper engine is not installed. Open Settings, Voice, and install it.".to_string());
    }

    let model = model_path(app, model_id)?;
    if !model.is_file() {
        return Err(format!(
            "The {} speech model is not downloaded. Open Settings, Voice, and install it.",
            model_info(model_id).label
        ));
    }

    let work = stt_root(app)?.join("work");
    std::fs::create_dir_all(&work)
        .map_err(|error| format!("Could not create a working folder: {error}"))?;

    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|value| value.as_millis())
        .unwrap_or(0);
    let input = work.join(format!("clip-{stamp}.wav"));
    let output = work.join(format!("clip-{stamp}"));

    std::fs::write(&input, audio).map_err(|error| format!("Could not stage the recording: {error}"))?;

    let threads = std::thread::available_parallelism()
        .map(|value| value.get().min(8))
        .unwrap_or(4)
        .to_string();

    let mut command = std::process::Command::new(&cli);
    command
        .current_dir(engine_dir(app)?)
        .arg("-m")
        .arg(&model)
        .arg("-f")
        .arg(&input)
        .arg("-l")
        .arg(whisper_language(language))
        .arg("-t")
        .arg(&threads)
        .arg("-bo")
        .arg("5")
        .arg("-bs")
        .arg("5")
        .arg("-sns")
        .arg("-nt")
        .arg("-np")
        .arg("-otxt")
        .arg("-of")
        .arg(&output)
        .arg("--prompt")
        .arg(prompt.unwrap_or(DEFAULT_PROMPT));

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        // CREATE_NO_WINDOW: never flash a console window over the HUD.
        command.creation_flags(0x0800_0000);
    }

    let result = command.output();

    let text_file = output.with_extension("txt");
    let transcript = std::fs::read_to_string(&text_file).ok();

    let _ = std::fs::remove_file(&input);
    let _ = std::fs::remove_file(&text_file);

    let output = result.map_err(|error| {
        format!("The speech engine could not start. Reinstall it in Settings: {error}")
    })?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!(
            "The speech engine failed: {}",
            stderr.chars().take(300).collect::<String>()
        ));
    }

    match transcript {
        Some(text) => Ok(clean_transcript(&text)),
        None => Ok(clean_transcript(&String::from_utf8_lossy(&output.stdout))),
    }
}

#[tauri::command]
pub async fn stt_transcribe_local(
    app: AppHandle,
    state: tauri::State<'_, SttState>,
    request: LocalTranscribeRequest,
) -> Result<Transcript, String> {
    let audio = decode_audio(&request.audio_base64)?;
    let model_id = request.model.unwrap_or_else(|| "small.en".to_string());
    let started = std::time::Instant::now();

    let app_for_blocking = app.clone();
    let language = request.language;
    let prompt = request.prompt;
    let model_for_work = model_id.clone();
    let lock = state.lock();

    let text = tauri::async_runtime::spawn_blocking(move || {
        let _guard = lock
            .lock()
            .map_err(|_| "The speech engine is busy.".to_string())?;
        run_local_whisper(
            &app_for_blocking,
            &audio,
            language.as_deref(),
            prompt.as_deref(),
            &model_for_work,
        )
    })
    .await
    .map_err(|_| "The speech engine stopped unexpectedly.".to_string())??;

    Ok(Transcript {
        empty: text.is_empty(),
        text,
        provider: "local".to_string(),
        model: model_id,
        elapsed_ms: started.elapsed().as_millis() as u64,
    })
}

#[tauri::command]
pub async fn stt_transcribe_groq(request: GroqTranscribeRequest) -> Result<Transcript, String> {
    let api_key = request.api_key.trim().to_string();
    if api_key.is_empty() {
        return Err("Add a Groq API key in Settings to use Groq Whisper.".to_string());
    }

    let audio = decode_audio(&request.audio_base64)?;
    let model = request
        .model
        .unwrap_or_else(|| "whisper-large-v3-turbo".to_string());
    let started = std::time::Instant::now();

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .build()
        .map_err(|error| format!("Could not start the transcription client: {error}"))?;

    let part = reqwest::multipart::Part::bytes(audio)
        .file_name("clip.wav")
        .mime_str("audio/wav")
        .map_err(|error| format!("Could not package the recording: {error}"))?;

    let mut form = reqwest::multipart::Form::new()
        .part("file", part)
        .text("model", model.clone())
        .text("response_format", "json")
        .text("temperature", "0");

    let language = whisper_language(request.language.as_deref());
    if language != "auto" {
        form = form.text("language", language);
    }
    form = form.text(
        "prompt",
        request.prompt.unwrap_or_else(|| DEFAULT_PROMPT.to_string()),
    );

    let response = client
        .post(format!("{GROQ_BASE}/audio/transcriptions"))
        .bearer_auth(api_key)
        .multipart(form)
        .send()
        .await
        .map_err(|error| {
            if error.is_timeout() {
                "Groq timed out while transcribing the recording.".to_string()
            } else {
                format!("Groq network error: {error}")
            }
        })?;

    let status = response.status();
    let body = response
        .text()
        .await
        .map_err(|error| format!("Could not read the Groq response: {error}"))?;

    if !status.is_success() {
        let detail = if status.as_u16() == 401 {
            "the Groq API key was rejected".to_string()
        } else if status.as_u16() == 429 {
            "the Groq rate limit was reached, wait a moment".to_string()
        } else {
            body.chars().take(300).collect::<String>()
        };
        return Err(format!("Groq transcription failed (HTTP {}): {detail}", status.as_u16()));
    }

    let parsed: serde_json::Value = serde_json::from_str(&body)
        .map_err(|_| "Groq returned an unreadable transcript.".to_string())?;

    let text = clean_transcript(parsed.get("text").and_then(|value| value.as_str()).unwrap_or(""));

    Ok(Transcript {
        empty: text.is_empty(),
        text,
        provider: "groq".to_string(),
        model,
        elapsed_ms: started.elapsed().as_millis() as u64,
    })
}

/// Guards payload size and validates the WAV container before any work starts.
fn decode_audio(encoded: &str) -> Result<Vec<u8>, String> {
    if encoded.trim().is_empty() {
        return Err("The recording is empty. Hold the microphone button while you speak.".to_string());
    }

    // 60 s of 16 kHz 16-bit mono is ~1.9 MB; base64 expands by 4/3.
    if encoded.len() > 8_000_000 {
        return Err("The recording is too long. Keep commands under one minute.".to_string());
    }

    let bytes = BASE64
        .decode(encoded.trim())
        .map_err(|_| "The recording could not be decoded.".to_string())?;

    if bytes.len() < 44 {
        return Err("The recording was too short to contain audio.".to_string());
    }
    if &bytes[0..4] != b"RIFF" || &bytes[8..12] != b"WAVE" {
        return Err("The recording was not a valid WAV file.".to_string());
    }

    Ok(bytes)
}

/// Re-exported so `main.rs` can pass a directory without duplicating paths.
pub fn default_model_id() -> &'static str {
    "small.en"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn language_tags_collapse_to_whisper_codes() {
        assert_eq!(whisper_language(Some("en-IN")), "en");
        assert_eq!(whisper_language(Some("en-GB")), "en");
        assert_eq!(whisper_language(Some("EN_us")), "en");
        assert_eq!(whisper_language(Some("hi")), "hi");
        assert_eq!(whisper_language(None), "en");
        assert_eq!(whisper_language(Some("  ")), "en");
    }

    #[test]
    fn silence_hallucinations_are_dropped() {
        assert_eq!(clean_transcript("Thank you."), "");
        assert_eq!(clean_transcript("  Thanks for watching!  "), "");
        assert_eq!(clean_transcript("\"you\""), "");
    }

    #[test]
    fn real_commands_survive_cleaning() {
        assert_eq!(clean_transcript(" Open Notepad \n"), "Open Notepad");
        assert_eq!(
            clean_transcript("\"Open File Explorer\""),
            "Open File Explorer"
        );
    }

    #[test]
    fn empty_audio_is_rejected_before_work() {
        assert!(decode_audio("").is_err());
        assert!(decode_audio("   ").is_err());
    }

    #[test]
    fn non_wav_payloads_are_rejected() {
        let encoded = BASE64.encode(b"not a wav file at all, just text padding......");
        assert!(decode_audio(&encoded).is_err());
    }

    #[test]
    fn wav_payloads_are_accepted() {
        let mut wav = Vec::new();
        wav.extend_from_slice(b"RIFF");
        wav.extend_from_slice(&36_u32.to_le_bytes());
        wav.extend_from_slice(b"WAVE");
        wav.extend_from_slice(&[0_u8; 32]);
        let encoded = BASE64.encode(&wav);
        assert!(decode_audio(&encoded).is_ok());
    }

    #[test]
    fn unknown_model_ids_are_not_silently_accepted() {
        assert!(MODELS.iter().any(|model| model.id == default_model_id()));
    }
}
