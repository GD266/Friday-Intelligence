"""Tool definitions, results, and shared sanitization."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from friday.security.redaction import redact_text

if TYPE_CHECKING:
    from friday.config.settings import ToolsSettings

MAX_ARGS_SUMMARY_CHARS = 200


class Permission(str, Enum):
    """Permission level for a tool."""

    SAFE = "SAFE"
    SENSITIVE = "SENSITIVE"
    DESTRUCTIVE = "DESTRUCTIVE"


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The outcome of one tool execution."""

    ok: bool
    text: str
    error_kind: str | None = None

    @classmethod
    def success(cls, text: str) -> "ToolResult":
        return cls(True, text)

    @classmethod
    def failure(cls, text: str, kind: str = "ToolError") -> "ToolResult":
        return cls(False, text, kind)

    @property
    def status(self) -> str:
        """Return the audit/UI status for this result."""
        return "ok" if self.ok else "error"


@dataclass(slots=True)
class ToolContext:
    """Runtime dependencies made available to a tool."""

    settings: "ToolsSettings"
    ui_bridge: Any = None
    conversation_id: int | None = None


class Tool(ABC):
    """Base class for every tool the model may call."""

    name: ClassVar[str]
    description: ClassVar[str]
    args_model: type[BaseModel]
    permission: ClassVar[Permission] = Permission.SAFE
    requires_confirmation: ClassVar[bool] = False
    returns_untrusted: ClassVar[bool] = False
    pure: ClassVar[bool] = False

    @abstractmethod
    async def execute(
        self, args: BaseModel, ctx: ToolContext
    ) -> ToolResult:
        """Execute the tool with validated arguments."""
        raise NotImplementedError

    def confirmation_description(self, args: BaseModel) -> str:
        """Return a plain-English description for the confirmation dialog."""
        return f"FRIDAY wants to use the {self.name} tool."

    def result_summary(self, result: ToolResult) -> str:
        """Return a short, UI-safe summary of a result."""
        return " ".join(result.text.split())[:160]


def summarize_arguments(raw_arguments: str) -> str:
    """Redact and shorten a raw tool-arguments string for display."""
    text = (raw_arguments or "").strip() or "{}"
    text = redact_text(text)
    if len(text) > MAX_ARGS_SUMMARY_CHARS:
        text = text[: MAX_ARGS_SUMMARY_CHARS - 1] + "\u2026"
    return text


def arguments_for_audit(raw_arguments: str) -> str:
    """Return a redacted arguments string suitable for the audit table."""
    text = (raw_arguments or "").strip() or "{}"
    text = redact_text(text)
    if len(text) > 1000:
        text = text[:999] + "\u2026"
    return text


def arguments_from_json(raw_arguments: str) -> dict[str, Any]:
    """Parse a raw arguments string that must contain a JSON object."""
    text = (raw_arguments or "").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must be a JSON object")
    return parsed


def sanitize_result(result: ToolResult, max_chars: int) -> ToolResult:
    """Redact secrets and truncate a tool result before it reaches the model."""
    text = redact_text(result.text)
    limit = max(1, int(max_chars))
    if len(text) > limit:
        if limit == 1:
            text = text[:1]
        else:
            text = text[: limit - 1] + "\u2026"
    return replace(result, text=text)


def short_text(text: str, limit: int = 160) -> str:
    """Collapse whitespace and truncate text for signals and logs."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "\u2026"


def normalize_optional_string_args(
    raw_args: dict[str, Any],
    model: type[BaseModel],
) -> dict[str, Any]:
    """Normalize empty/whitespace-only strings to None for optional string fields.

    Iterates over the model's fields. For each field that:
    - has a default value (i.e., is optional)
    - is annotated as str or Optional[str]
    and the raw_args contains an empty or whitespace-only string,
    the value is replaced with None so Pydantic will use the default.

    Required fields (no default) are left untouched; Pydantic will
    reject empty strings for them as usual.

    Returns a new dict with normalized values.
    """
    from typing import get_args, get_origin

    normalized = dict(raw_args)
    for field_name, field_info in model.model_fields.items():
        # Skip if not present in raw args
        if field_name not in normalized:
            continue

        value = normalized[field_name]
        # Only process string values
        if not isinstance(value, str):
            continue

        # Check if field is optional (has a default) and is a string type
        annotation = field_info.annotation
        is_optional_str = False
        if annotation is str:
            is_optional_str = True
        else:
            # Handle Optional[str] = str | None
            if get_origin(annotation) is not None:
                args = get_args(annotation)
                if type(None) in args and all(
                    a is str or a is type(None) for a in args
                ):
                    is_optional_str = True

        if is_optional_str and field_info.default is not ...:
            # Field is optional string; normalize empty/whitespace to None
            if not value.strip():
                normalized[field_name] = None

    return normalized


__all__ = [
    "MAX_ARGS_SUMMARY_CHARS",
    "Permission",
    "Tool",
    "ToolContext",
    "ToolResult",
    "arguments_for_audit",
    "arguments_from_json",
    "sanitize_result",
    "short_text",
    "summarize_arguments",
]
