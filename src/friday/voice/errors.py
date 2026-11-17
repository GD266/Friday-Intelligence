"""Typed TTS errors with user-readable messages."""

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
    "build_tts_http_error",
    "sanitize_provider_message",
]
