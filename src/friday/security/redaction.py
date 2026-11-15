"""Central secret detection, redaction, and runtime secret registry.

Every consumer that needs to recognise or mask secrets imports from this
module: the logging redaction filter, provider error sanitization, and fact
validation.  Keeping the patterns here prevents the three paths from drifting
apart.

The registry stores secret *values* returned by the secret manager.  Log
messages and provider error bodies are scanned for exact occurrences of those
values in addition to the fixed patterns, so keys that do not match any known
format are still masked.  Registry contents are never logged.
"""

from __future__ import annotations

import re
import threading

REDACTED = "***REDACTED***"
PRIVATE_KEY_REDACTED = "***REDACTED PRIVATE KEY***"

# Patterns for common secret formats.  Order matters: more specific formats
# must be replaced before their generic fallbacks.
PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # PEM private keys (redact the whole block, including the body).
    (
        re.compile(
            r"-----BEGIN[ A-Z0-9]*PRIVATE KEY-----"
            r".*?(?:-----END[ A-Z0-9]*PRIVATE KEY-----|\Z)",
            re.DOTALL,
        ),
        PRIVATE_KEY_REDACTED,
    ),
    # Anthropic API keys (sk-ant-...)
    (re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}"), "sk-ant-***REDACTED***"),
    # GitHub classic personal access tokens (ghp_...)
    (re.compile(r"ghp_[a-zA-Z0-9]{20,}"), "ghp_***REDACTED***"),
    # GitHub fine-grained personal access tokens (github_pat_...)
    (
        re.compile(r"github_pat_[a-zA-Z0-9_]{20,}"),
        "github_pat_***REDACTED***",
    ),
    # AWS access key ids (AKIA...)
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA***REDACTED***"),
    # Slack tokens (xoxb-, xoxa-, xoxp-, xoxr-, xoxs-)
    (re.compile(r"xox[baprs]-[a-zA-Z0-9-]{10,}"), "xox-***REDACTED***"),
    # NVIDIA API keys (nvapi-...).  Real keys have 16+ suffix characters;
    # 12+ also masks the short key-shaped value from the original report.
    (re.compile(r"nvapi-[a-zA-Z0-9_-]{12,}"), "nvapi-***REDACTED***"),
    # Google API keys (AIza...)
    (re.compile(r"AIza[a-zA-Z0-9_-]{35,}"), "AIza***REDACTED***"),
    # gsk_... keys (Groq)
    (re.compile(r"gsk_[a-zA-Z0-9]{20,}"), "gsk_***REDACTED***"),
    # Generic Bearer tokens
    (
        re.compile(r"Bearer\s+[a-zA-Z0-9._~+/=-]+"),
        "Bearer ***REDACTED***",
    ),
    # JWT-shaped tokens: three base64url parts joined by dots.
    (
        re.compile(
            r"[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}"
        ),
        "***REDACTED-JWT***",
    ),
    # OpenAI API keys (sk-... 48 chars)
    (re.compile(r"sk-[a-zA-Z0-9]{48}"), "sk-***REDACTED***"),
    # Generic sk-... keys (fallback)
    (re.compile(r"sk-[a-zA-Z0-9_-]{20,}"), "sk-***REDACTED***"),
)

# Fact-only guards.  These do not have a fixed replacement because the value
# is not a known-format secret; they only decide whether the text must be
# rejected.  "key" alone is included so phrases such as "my key is ..." are
# caught even when the value uses an unknown format.
_KEYWORD_PATTERN = re.compile(
    r"\b(?:password|passwd|secret|api[ _-]?key|key|token|private[ _-]?key)\b"
    r".{0,20}?(?P<value>\S{8,})",
    re.IGNORECASE | re.DOTALL,
)
_ENTROPY_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_\-+/=]{24,}")

_REGISTERED_SECRETS: set[str] = set()
_REGISTRY_LOCK = threading.Lock()


def register_secret(value: str | None) -> None:
    """Remember a secret value so exact occurrences can be masked later."""
    if not isinstance(value, str) or not value.strip():
        return
    with _REGISTRY_LOCK:
        _REGISTERED_SECRETS.add(value)


def _registered_snapshot() -> tuple[str, ...]:
    with _REGISTRY_LOCK:
        return tuple(sorted(_REGISTERED_SECRETS, key=len, reverse=True))


def _redact_registered(text: str) -> str:
    for value in _registered_snapshot():
        if value in text:
            text = text.replace(value, REDACTED)
    return text


def redact_text(text: str) -> str:
    """Return *text* with known and registered secrets masked."""
    if not isinstance(text, str) or not text:
        return text
    text = _redact_registered(text)
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _has_secret_keyword_value(text: str) -> bool:
    for match in _KEYWORD_PATTERN.finditer(text):
        value = match.group("value")
        if any(character.isdigit() for character in value):
            return True
    return False


def _has_high_entropy_token(text: str) -> bool:
    for match in _ENTROPY_TOKEN_PATTERN.finditer(text):
        token = match.group(0)
        has_letter = any(character.isalpha() for character in token)
        has_digit = any(character.isdigit() for character in token)
        if has_letter and has_digit:
            return True
    return False


def contains_secret(text: str) -> bool:
    """Return True when *text* looks like or contains a secret."""
    if not isinstance(text, str) or not text:
        return False
    if redact_text(text) != text:
        return True
    return _has_secret_keyword_value(text) or _has_high_entropy_token(text)


__all__ = [
    "PATTERNS",
    "PRIVATE_KEY_REDACTED",
    "REDACTED",
    "contains_secret",
    "redact_text",
    "register_secret",
]
