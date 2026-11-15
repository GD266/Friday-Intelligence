"""Typed gateway errors with user-readable messages.

Provider response bodies are truncated and passed through the log redaction
filter (plus an explicit replacement of the active API key) before they are
attached to an exception.
"""

from __future__ import annotations

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


def parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header. Only numeric deltas are supported."""
    if not value:
        return None
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        # HTTP-date form (or garbage); we simply do not report a delay.
        return None


class GatewayError(Exception):
    """Base class for every gateway failure surfaced to the UI."""

    kind = "GatewayError"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        provider_message: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.provider_message = provider_message or None

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code is not None and f"HTTP {self.status_code}" not in (
            self.message
        ):
            parts.append(f"(HTTP {self.status_code})")
        if self.provider_message:
            parts.append(f"Provider response: {self.provider_message}")
        return " ".join(parts)


class NotConfigured(GatewayError):
    """The provider model or API key is missing."""

    kind = "NotConfigured"


class AuthError(GatewayError):
    """The provider rejected the credentials (401 or 403)."""

    kind = "AuthError"


class NotFound(GatewayError):
    """The model or endpoint does not exist (404)."""

    kind = "NotFound"


class RateLimited(GatewayError):
    """The provider is rate limiting requests (429)."""

    kind = "RateLimited"

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = 429,
        provider_message: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            provider_message=provider_message,
        )
        self.retry_after = retry_after


class ServerError(GatewayError):
    """The provider failed server-side (5xx)."""

    kind = "ServerError"


class NetworkError(GatewayError):
    """A connection to the provider could not be established or broke."""

    kind = "NetworkError"


class TimeoutError(GatewayError):
    """The provider did not respond within the configured timeout."""

    kind = "TimeoutError"


class MalformedResponse(GatewayError):
    """The provider returned data that is not valid streamed chat output."""

    kind = "MalformedResponse"


class Cancelled(GatewayError):
    """The request was cancelled."""

    kind = "Cancelled"


def build_http_error(
    status_code: int,
    body: str,
    *,
    secret: str | None = None,
    retry_after_header: str | None = None,
) -> GatewayError:
    """Map a non-success HTTP response to the matching typed error."""
    provider_message = sanitize_provider_message(body, secret=secret)

    if status_code in (401, 403):
        message = f"Authentication failed (HTTP {status_code})."
        if status_code == 401:
            message += " Check the API key stored by scripts/set_key.py."
        else:
            message += (
                " The key may lack access; a 403 can also mean this model is "
                "enterprise-gated for your account."
            )
        return AuthError(
            message,
            status_code=status_code,
            provider_message=provider_message,
        )

    if status_code == 404:
        return NotFound(
            "Model or endpoint not found (HTTP 404). "
            "Check provider.model and provider.base_url.",
            status_code=status_code,
            provider_message=provider_message,
        )

    if status_code == 429:
        retry_after = parse_retry_after(retry_after_header)
        message = "Rate limited by the provider (HTTP 429)."
        if retry_after is not None:
            message += f" Retry after {retry_after:g} seconds."
        return RateLimited(
            message,
            status_code=status_code,
            provider_message=provider_message,
            retry_after=retry_after,
        )

    if 500 <= status_code <= 599:
        return ServerError(
            f"Provider server error (HTTP {status_code}).",
            status_code=status_code,
            provider_message=provider_message,
        )

    return GatewayError(
        f"Provider returned HTTP {status_code}.",
        status_code=status_code,
        provider_message=provider_message,
    )


__all__ = [
    "AuthError",
    "Cancelled",
    "GatewayError",
    "MalformedResponse",
    "NetworkError",
    "NotConfigured",
    "NotFound",
    "RateLimited",
    "ServerError",
    "TimeoutError",
    "build_http_error",
    "parse_retry_after",
    "sanitize_provider_message",
]
