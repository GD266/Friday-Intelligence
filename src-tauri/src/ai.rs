use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::path::PathBuf;
use std::time::{Duration, Instant};

const OPENCODE_BASE: &str = "https://opencode.ai/inference/openai/v1";
const NVIDIA_BASE: &str = "https://integrate.api.nvidia.com/v1";
const OPENROUTER_BASE: &str = "https://openrouter.ai/api/v1";
const ELEVENLABS_BASE: &str = "https://api.elevenlabs.io/v1";

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ChatMessage {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AIChatRequest {
    pub provider: String,
    pub model: String,
    pub messages: Vec<ChatMessage>,
    pub api_key: Option<String>,
    pub base_url: String,
    #[serde(default)]
    pub temperature: f64,
    #[serde(default)]
    pub max_tokens: u32,
    #[serde(default)]
    pub timeout_ms: u64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AIChatResponse {
    pub text: String,
    pub provider: String,
    pub model: String,
    pub latency_ms: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub usage: Option<AIUsage>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AIUsage {
    pub input: Option<u64>,
    pub output: Option<u64>,
    pub total: Option<u64>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CredentialSettings {
    #[serde(default)]
    pub open_code_api_key: String,
    #[serde(default)]
    pub nvidia_api_key: String,
    #[serde(default)]
    pub open_router_api_key: String,
    #[serde(default)]
    pub eleven_labs_api_key: String,
}

#[derive(Debug, Serialize)]
pub struct CredentialStatus {
    pub opencode: bool,
    pub nvidia: bool,
    pub openrouter: bool,
    pub elevenlabs: bool,
    pub source: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ElevenLabsSpeakRequest {
    pub text: String,
    pub api_key: Option<String>,
    pub voice_id: String,
    pub model_id: String,
    #[serde(default)]
    pub stability: f64,
    #[serde(default)]
    pub similarity: f64,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ElevenLabsAudio {
    pub audio_base64: String,
    pub mime_type: String,
    pub voice_id: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ElevenLabsVoicesRequest {
    pub api_key: Option<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ElevenLabsVoice {
    pub id: String,
    pub name: String,
    pub description: Option<String>,
    pub labels: Option<HashMap<String, String>>,
    pub preview_url: Option<String>,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DeveloperFileInput {
    pub path: String,
    pub content: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DeveloperProjectRequest {
    pub name: String,
    pub title: String,
    pub description: String,
    pub prompt: String,
    #[serde(default)]
    pub engine: String,
    #[serde(default)]
    pub model: Option<String>,
    pub files: Vec<DeveloperFileInput>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct WrittenDeveloperFile {
    pub path: String,
    pub bytes: usize,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DeveloperProjectResult {
    pub name: String,
    pub path: String,
    pub files: Vec<WrittenDeveloperFile>,
}

fn home_dir() -> Option<PathBuf> {
    std::env::var_os("USERPROFILE")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(PathBuf::from))
}

/// Reads provider credentials that the local OpenCode installation already
/// stored. Values never leave Rust except as a used request header.
fn opencode_auth() -> HashMap<String, String> {
    let Some(path) = home_dir().map(|home| home.join(".local/share/opencode/auth.json")) else {
        return HashMap::new();
    };
    let Ok(raw) = std::fs::read_to_string(path) else {
        return HashMap::new();
    };
    let Ok(value) = serde_json::from_str::<Value>(&raw) else {
        return HashMap::new();
    };
    let Some(object) = value.as_object() else {
        return HashMap::new();
    };

    let mut credentials = HashMap::new();
    for (provider, entry) in object {
        let Some(entry) = entry.as_object() else {
            continue;
        };
        for field in ["key", "access_token", "token"] {
            if let Some(key) = entry.get(field).and_then(Value::as_str) {
                if !key.trim().is_empty() {
                    credentials.insert(provider.clone(), key.trim().to_string());
                    break;
                }
            }
        }
    }

    credentials
}

fn env_credential(name: &str) -> Option<String> {
    std::env::var(name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn resolve_api_key(provider: &str, supplied: Option<String>) -> Option<String> {
    if let Some(key) = supplied.map(|value| value.trim().to_string()) {
        if !key.is_empty() {
            return Some(key);
        }
    }

    match provider {
        "opencode" => {
            env_credential("OPENCODE_API_KEY").or_else(|| opencode_auth().get("opencode").cloned())
        }
        "nvidia" => {
            env_credential("NVIDIA_API_KEY").or_else(|| opencode_auth().get("nvidia").cloned())
        }
        "openrouter" => env_credential("OPENROUTER_API_KEY")
            .or_else(|| opencode_auth().get("openrouter").cloned()),
        _ => None,
    }
}

fn validate_base_url(provider: &str, base_url: &str) -> Result<String, String> {
    let expected = match provider {
        "opencode" => OPENCODE_BASE,
        "nvidia" => NVIDIA_BASE,
        "openrouter" => OPENROUTER_BASE,
        _ => return Err(format!("Unknown intelligence provider: {provider}")),
    };

    let trimmed = base_url.trim().trim_end_matches('/');
    let url = reqwest::Url::parse(trimmed).map_err(|_| "Invalid engine base URL.".to_string())?;
    let allowed_host = match provider {
        "opencode" => "opencode.ai",
        "nvidia" => "integrate.api.nvidia.com",
        "openrouter" => "openrouter.ai",
        _ => "",
    };

    if url.scheme() != "https" || url.host_str() != Some(allowed_host) {
        return Err("The engine URL does not match an approved provider.".to_string());
    }

    Ok(if trimmed.is_empty() {
        expected.to_string()
    } else {
        trimmed.to_string()
    })
}

fn parse_content(value: &Value) -> String {
    let Some(choices) = value.get("choices").and_then(Value::as_array) else {
        return String::new();
    };
    let Some(message) = choices.first().and_then(|choice| choice.get("message")) else {
        return String::new();
    };
    let Some(content) = message.get("content") else {
        return String::new();
    };

    if let Some(text) = content.as_str() {
        return text.trim().to_string();
    }

    if let Some(parts) = content.as_array() {
        return parts
            .iter()
            .filter_map(|part| {
                part.as_str()
                    .map(str::to_string)
                    .or_else(|| part.get("text").and_then(Value::as_str).map(str::to_string))
            })
            .collect::<String>()
            .trim()
            .to_string();
    }

    String::new()
}

fn parse_usage(value: &Value) -> Option<AIUsage> {
    let usage = value.get("usage")?;
    let input = usage.get("prompt_tokens").and_then(Value::as_u64);
    let output = usage.get("completion_tokens").and_then(Value::as_u64);
    let total = usage.get("total_tokens").and_then(Value::as_u64);
    if input.is_none() && output.is_none() && total.is_none() {
        return None;
    }
    Some(AIUsage {
        input,
        output,
        total,
    })
}

#[tauri::command]
pub async fn ai_chat(request: AIChatRequest) -> Result<AIChatResponse, String> {
    let started = Instant::now();
    let base_url = validate_base_url(&request.provider, &request.base_url)?;
    let api_key = resolve_api_key(&request.provider, request.api_key).ok_or_else(|| {
        format!(
            "No credential is available for {}. Add a key in Settings or sign in with OpenCode.",
            request.provider
        )
    })?;

    if request.messages.is_empty() {
        return Err("No messages were supplied to the engine.".to_string());
    }

    let timeout = Duration::from_millis(request.timeout_ms.clamp(5_000, 300_000));
    let client = reqwest::Client::builder()
        .timeout(timeout)
        .build()
        .map_err(|error| format!("Could not start the engine client: {error}"))?;

    let body = serde_json::json!({
        "model": request.model,
        "messages": request.messages,
        "temperature": request.temperature.clamp(0.0, 2.0),
        "max_tokens": request.max_tokens.clamp(16, 16_384),
        "stream": false,
    });

    let mut builder = client
        .post(format!("{base_url}/chat/completions"))
        .header("Content-Type", "application/json")
        .header("Authorization", format!("Bearer {api_key}"))
        .json(&body);

    if request.provider == "openrouter" {
        builder = builder
            .header("HTTP-Referer", "https://friday.local")
            .header("X-Title", "FRIDAY Intelligence");
    }

    let response = builder.send().await.map_err(|error| {
        if error.is_timeout() {
            format!("The engine timed out after {}s.", timeout.as_secs())
        } else {
            format!("Engine network error: {error}")
        }
    })?;

    let status = response.status();
    let payload = response.text().await.unwrap_or_default();
    if !status.is_success() {
        return Err(format!(
            "HTTP {} from {}: {}",
            status.as_u16(),
            request.provider,
            payload.chars().take(600).collect::<String>()
        ));
    }

    let value: Value = serde_json::from_str(&payload)
        .map_err(|_| "The engine returned a response that was not valid JSON.".to_string())?;
    let text = parse_content(&value);
    if text.is_empty() {
        return Err(format!("{} returned an empty response.", request.provider));
    }

    Ok(AIChatResponse {
        text,
        provider: request.provider,
        model: request.model,
        latency_ms: started.elapsed().as_millis() as u64,
        usage: parse_usage(&value),
    })
}

#[tauri::command]
pub async fn ai_credential_status(
    settings: CredentialSettings,
) -> Result<CredentialStatus, String> {
    let stored = opencode_auth();
    let from_settings = [
        settings.open_code_api_key.trim(),
        settings.nvidia_api_key.trim(),
        settings.open_router_api_key.trim(),
        settings.eleven_labs_api_key.trim(),
    ]
    .iter()
    .any(|value| !value.is_empty());

    let from_environment = [
        env_credential("OPENCODE_API_KEY"),
        env_credential("NVIDIA_API_KEY"),
        env_credential("OPENROUTER_API_KEY"),
        env_credential("ELEVENLABS_API_KEY"),
    ]
    .iter()
    .any(Option::is_some);

    let source = if from_settings {
        "settings"
    } else if from_environment {
        "environment"
    } else if !stored.is_empty() {
        "opencode-auth"
    } else {
        "none"
    };

    Ok(CredentialStatus {
        opencode: !settings.open_code_api_key.trim().is_empty()
            || env_credential("OPENCODE_API_KEY").is_some()
            || stored.contains_key("opencode"),
        nvidia: !settings.nvidia_api_key.trim().is_empty()
            || env_credential("NVIDIA_API_KEY").is_some()
            || stored.contains_key("nvidia"),
        openrouter: !settings.open_router_api_key.trim().is_empty()
            || env_credential("OPENROUTER_API_KEY").is_some()
            || stored.contains_key("openrouter"),
        elevenlabs: !settings.eleven_labs_api_key.trim().is_empty()
            || env_credential("ELEVENLABS_API_KEY").is_some(),
        source: source.to_string(),
    })
}

fn elevenlabs_key(supplied: Option<String>) -> Result<String, String> {
    supplied
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| env_credential("ELEVENLABS_API_KEY"))
        .ok_or_else(|| "Add an ElevenLabs API key in Settings to use the studio voice.".to_string())
}

fn valid_voice_id(voice_id: &str) -> bool {
    !voice_id.is_empty()
        && voice_id.len() <= 64
        && voice_id
            .chars()
            .all(|character| character.is_ascii_alphanumeric())
}

#[tauri::command]
pub async fn elevenlabs_speak(request: ElevenLabsSpeakRequest) -> Result<ElevenLabsAudio, String> {
    let api_key = elevenlabs_key(request.api_key)?;
    if !valid_voice_id(&request.voice_id) {
        return Err("The ElevenLabs voice id is not valid.".to_string());
    }

    let text = request.text.trim();
    if text.is_empty() {
        return Err("There is nothing to speak.".to_string());
    }

    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(75))
        .build()
        .map_err(|error| format!("Could not start the voice client: {error}"))?;

    let body = serde_json::json!({
        "text": text.chars().take(5_000).collect::<String>(),
        "model_id": request.model_id,
        "voice_settings": {
            "stability": request.stability.clamp(0.0, 1.0),
            "similarity_boost": request.similarity.clamp(0.0, 1.0),
        },
    });

    let response = client
        .post(format!(
            "{ELEVENLABS_BASE}/text-to-speech/{}",
            request.voice_id
        ))
        .header("xi-api-key", api_key)
        .header("Accept", "audio/mpeg")
        .header("Content-Type", "application/json")
        .json(&body)
        .send()
        .await
        .map_err(|error| {
            if error.is_timeout() {
                "ElevenLabs timed out while generating speech.".to_string()
            } else {
                format!("ElevenLabs network error: {error}")
            }
        })?;

    let status = response.status();
    let mime_type = response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or("audio/mpeg")
        .to_string();

    let bytes = response
        .bytes()
        .await
        .map_err(|error| format!("Could not read the ElevenLabs audio: {error}"))?;

    if !status.is_success() {
        let detail = String::from_utf8_lossy(&bytes);
        return Err(format!(
            "HTTP {} from ElevenLabs: {}",
            status.as_u16(),
            detail.chars().take(400).collect::<String>()
        ));
    }

    if bytes.is_empty() {
        return Err("ElevenLabs returned empty audio.".to_string());
    }

    Ok(ElevenLabsAudio {
        audio_base64: BASE64.encode(bytes),
        mime_type,
        voice_id: request.voice_id,
    })
}

#[tauri::command]
pub async fn elevenlabs_voices(
    request: ElevenLabsVoicesRequest,
) -> Result<Vec<ElevenLabsVoice>, String> {
    let api_key = elevenlabs_key(request.api_key)?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|error| format!("Could not start the voice client: {error}"))?;

    let response = client
        .get(format!("{ELEVENLABS_BASE}/voices"))
        .header("xi-api-key", api_key)
        .send()
        .await
        .map_err(|error| format!("ElevenLabs network error: {error}"))?;

    let status = response.status();
    let payload: Value = response
        .json()
        .await
        .map_err(|_| "ElevenLabs returned an unreadable voice list.".to_string())?;

    if !status.is_success() {
        return Err(format!(
            "HTTP {} from ElevenLabs: {}",
            status.as_u16(),
            payload
                .get("detail")
                .map(|detail| detail.to_string())
                .unwrap_or_else(|| "voice list rejected".to_string())
        ));
    }

    let voices = payload
        .get("voices")
        .and_then(Value::as_array)
        .ok_or_else(|| "ElevenLabs returned no voices.".to_string())?
        .iter()
        .filter_map(|voice| {
            let id = voice.get("voice_id")?.as_str()?.to_string();
            let name = voice.get("name")?.as_str()?.to_string();
            let description = voice
                .get("description")
                .and_then(Value::as_str)
                .map(str::to_string);
            let preview_url = voice
                .get("preview_url")
                .and_then(Value::as_str)
                .map(str::to_string);
            let labels = voice
                .get("labels")
                .and_then(Value::as_object)
                .map(|labels| {
                    labels
                        .iter()
                        .filter_map(|(key, value)| {
                            value.as_str().map(|value| (key.clone(), value.to_string()))
                        })
                        .collect::<HashMap<String, String>>()
                });

            Some(ElevenLabsVoice {
                id,
                name,
                description,
                labels,
                preview_url,
            })
        })
        .collect::<Vec<_>>();

    if voices.is_empty() {
        return Err("ElevenLabs returned no usable voices.".to_string());
    }

    Ok(voices)
}

const ALLOWED_EXTENSIONS: &[&str] = &[
    "html",
    "htm",
    "css",
    "js",
    "mjs",
    "jsx",
    "ts",
    "tsx",
    "json",
    "md",
    "txt",
    "svg",
    "webmanifest",
    "csv",
    "yml",
    "yaml",
];

fn sanitize_file_path(raw: &str) -> Result<PathBuf, String> {
    let trimmed = raw.trim().replace('\\', "/");
    if trimmed.is_empty() || trimmed.len() > 180 {
        return Err("A generated file path was empty or too long.".to_string());
    }

    let path = PathBuf::from(&trimmed);
    if path.is_absolute() {
        return Err(format!("Generated file path must be relative: {raw}"));
    }

    let mut checked = PathBuf::new();
    for component in path.components() {
        use std::path::Component;
        match component {
            Component::Normal(part) => {
                let part = part.to_string_lossy();
                let lower = part.to_ascii_lowercase();
                let reserved = matches!(
                    lower.as_str(),
                    "con"
                        | "prn"
                        | "aux"
                        | "nul"
                        | "com1"
                        | "com2"
                        | "com3"
                        | "com4"
                        | "com5"
                        | "com6"
                        | "com7"
                        | "com8"
                        | "com9"
                        | "lpt1"
                        | "lpt2"
                        | "lpt3"
                        | "lpt4"
                        | "lpt5"
                        | "lpt6"
                        | "lpt7"
                        | "lpt8"
                        | "lpt9"
                );
                if reserved || part.ends_with('.') || part.ends_with(' ') {
                    return Err(format!("Generated file path is not allowed: {raw}"));
                }
                checked.push(part.as_ref());
            }
            _ => return Err(format!("Generated file path is not safe: {raw}")),
        }
    }

    let extension = checked
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| value.to_ascii_lowercase())
        .unwrap_or_default();
    if !ALLOWED_EXTENSIONS.contains(&extension.as_str()) {
        return Err(format!(
            "Generated file type .{extension} is outside the forge allowlist."
        ));
    }

    Ok(checked)
}

fn sanitize_project_name(raw: &str) -> String {
    let mut name = raw
        .trim()
        .to_ascii_lowercase()
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() {
                character
            } else {
                '-'
            }
        })
        .collect::<String>();

    while name.contains("--") {
        name = name.replace("--", "-");
    }
    let name = name.trim_matches('-').chars().take(48).collect::<String>();

    if name.is_empty() {
        "friday-project".to_string()
    } else {
        name
    }
}

fn unique_project_dir(root: &std::path::Path, name: &str) -> PathBuf {
    let mut candidate = root.join(name);
    let mut index = 2;
    while candidate.exists() && index < 200 {
        candidate = root.join(format!("{name}-{index}"));
        index += 1;
    }
    candidate
}

#[tauri::command]
pub fn developer_create_project(
    request: DeveloperProjectRequest,
) -> Result<DeveloperProjectResult, String> {
    if request.files.is_empty() {
        return Err("The forge did not receive any files to write.".to_string());
    }
    if request.files.len() > 24 {
        return Err("The forge accepts at most 24 files per project.".to_string());
    }

    let root = home_dir()
        .map(|home| home.join("Documents").join("FRIDAY Forge"))
        .ok_or_else(|| "The Documents folder could not be located.".to_string())?;
    std::fs::create_dir_all(&root)
        .map_err(|error| format!("Could not create the forge workspace: {error}"))?;

    let name = sanitize_project_name(&request.name);
    let target = unique_project_dir(&root, &name);
    std::fs::create_dir_all(&target)
        .map_err(|error| format!("Could not create the project folder: {error}"))?;

    let mut written = Vec::new();
    let mut total_bytes = 0usize;

    for file in &request.files {
        let relative = match sanitize_file_path(&file.path) {
            Ok(path) => path,
            Err(error) => {
                let _ = std::fs::remove_dir_all(&target);
                return Err(error);
            }
        };

        let size = file.content.len();
        total_bytes += size;
        if size > 400_000 || total_bytes > 3_000_000 {
            let _ = std::fs::remove_dir_all(&target);
            return Err("The generated project exceeds the forge size limit.".to_string());
        }

        let destination = target.join(&relative);
        if let Some(parent) = destination.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|error| format!("Could not create a project folder: {error}"))?;
        }

        if let Err(error) = std::fs::write(&destination, &file.content) {
            let _ = std::fs::remove_dir_all(&target);
            return Err(format!("Could not write {}: {error}", relative.display()));
        }

        written.push(WrittenDeveloperFile {
            path: relative.to_string_lossy().replace('\\', "/"),
            bytes: size,
        });
    }

    let readme = [
        format!("# {}", request.title),
        String::new(),
        request.description.clone(),
        String::new(),
        format!("> Requested: {}", request.prompt),
        String::new(),
        format!(
            "Generated by FRIDAY Forge using {}.",
            if request.model.is_some() {
                request.model.clone().unwrap_or_default()
            } else {
                request.engine.clone()
            }
        ),
        String::new(),
        "Open `index.html` in a browser, or serve this folder with any static file server."
            .to_string(),
    ]
    .join("\n");

    let _ = std::fs::write(target.join("FRIDAY.md"), readme);

    Ok(DeveloperProjectResult {
        name,
        path: target.to_string_lossy().to_string(),
        files: written,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitize_project_name_builds_safe_slugs() {
        assert_eq!(sanitize_project_name("My Flappy Game!"), "my-flappy-game");
        assert_eq!(sanitize_project_name("   "), "friday-project");
        assert_eq!(sanitize_project_name("../../evil"), "evil");
    }

    #[test]
    fn rejects_parent_directory_traversal() {
        assert!(sanitize_file_path("../secret.txt").is_err());
        assert!(sanitize_file_path("C:/Windows/evil.txt").is_err());
        assert!(sanitize_file_path("src/../../escape.txt").is_err());
    }

    #[test]
    fn rejects_executable_extensions() {
        assert!(sanitize_file_path("payload.exe").is_err());
        assert!(sanitize_file_path("run.bat").is_err());
        assert!(sanitize_file_path("index.html").is_ok());
        assert!(sanitize_file_path("src/game.js").is_ok());
    }
}
