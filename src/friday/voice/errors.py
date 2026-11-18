"""Typed voice errors (TTS, capture and transcription) with messages."""

from __future__ import annotations

from friday.gateway.errors import GatewayError
from friday.security.redaction import redact_text

MAX_PROVIDER_MESSAGE_CHARS = 300


def sanitize_provider_message(
    text: str,
    *,
    secret: str | None = None,
    limit: int = MAX_PROVIDER_MESSAGE_CHARS,
) -> str:
    """Redact secrets and truncate a provider response body."""
    if secret:
        text = text.replace(secret, "***REDACTED***")
    text = redact_text(text).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "\u2026"
    return text


class TTSError(GatewayError):
    """Base class for every TTS failure surfaced to the UI."""

    kind = "TTSError"


class TTSNotAvailable(TTSError):
    """The requested TTS engine is not available."""

    kind = "TTSNotAvailable"


class TTSAuthError(TTSError):
    """The TTS provider rejected the request (401/403)."""

    kind = "TTSAuthError"


class TTSNetworkError(TTSError):
    """A connection to the TTS provider could not be established."""

    kind = "TTSNetworkError"


class TTSTimeout(TTSError):
    """The TTS provider did not respond within the configured timeout."""

    kind = "TTSTimeout"


class TTSBadVoice(TTSError):
    """The requested voice is not available."""

    kind = "TTSBadVoice"


class TTSEmptyText(TTSError):
    """The input text is empty after preparation."""

    kind = "TTSEmptyText"


class PlaybackNotAvailable(TTSError):
    """No audio player is attached to the UI bridge."""

    kind = "PlaybackNotAvailable"


class AudioCaptureError(Exception):
    """Base class for microphone capture failures."""

    kind = "AudioCaptureError"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NoInputDevice(AudioCaptureError):
    """No microphone input device is available."""

    kind = "NoInputDevice"


class InputDeviceNotFound(AudioCaptureError):
    """The configured microphone name did not match any device."""

    kind = "InputDeviceNotFound"


class MicPermissionOrSilent(AudioCaptureError):
    """The microphone produced only silence (permission or mute)."""

    kind = "MicPermissionOrSilent"


class RecordingTooShort(AudioCaptureError):
    """The recording was shorter than the configured minimum."""

    kind = "RecordingTooShort"


class RecordingError(AudioCaptureError):
    """The recording could not be started or decoded."""

    kind = "RecordingError"


class TranscriptionError(Exception):
    """Base class for speech-to-text failures."""

    kind = "TranscriptionError"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class TranscriptionNotAvailable(TranscriptionError):
    """The local transcription engine or its package is unavailable."""

    kind = "TranscriptionNotAvailable"


class ModelLoadError(TranscriptionError):
    """The Faster-Whisper model could not be downloaded or loaded."""

    kind = "ModelLoadError"


class EmptyAudio(TranscriptionError):
    """The supplied audio contains no samples."""

    kind = "EmptyAudio"


class UnsupportedAudioFormat(TranscriptionError):
    """The supplied audio is not 16 kHz mono 16-bit PCM."""

    kind = "UnsupportedAudioFormat"


class UnsupportedLanguage(TranscriptionError):
    """The requested language is not English or Hindi."""

    kind = "UnsupportedLanguage"


def build_tts_http_error(
    status_code: int,
    body: str,
    *,
    secret: str | None = None,
) -> TTSError:
    """Map a non-success HTTP response to the matching typed TTS error."""
    provider_message = sanitize_provider_message(body, secret=secret)

    if status_code in (401, 403):
        message = (
            "Microsoft rejected the request (403). This usually means "
            "edge-tts is outdated or your PC clock is wrong. "
            "Run pip install -U edge-tts and check the Windows time."
        )
        return TTSAuthError(
            message,
            status_code=status_code,
            provider_message=provider_message,
        )

    return TTSError(
        f"TTS provider returned HTTP {status_code}.",
        status_code=status_code,
        provider_message=provider_message,
    )


__all__ = [
    "TTSError",
    "TTSNotAvailable",
    "TTSAuthError",
    "TTSNetworkError",
    "TTSTimeout",
    "TTSBadVoice",
    "TTSEmptyText",
    "PlaybackNotAvailable",
    "AudioCaptureError",
    "NoInputDevice",
    "InputDeviceNotFound",
    "MicPermissionOrSilent",
    "RecordingTooShort",
    "RecordingError",
    "TranscriptionError",
    "TranscriptionNotAvailable",
    "ModelLoadError",
    "EmptyAudio",
    "UnsupportedAudioFormat",
    "UnsupportedLanguage",
    "build_tts_http_error",
    "sanitize_provider_message",
]
