"""Value types shared by the AI gateway."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from friday.gateway.errors import GatewayError

ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"
ROLE_TOOL = "tool"

EVENT_TOKEN = "token"
EVENT_TOOL_CALLS = "tool_calls"
EVENT_DONE = "done"
EVENT_ERROR = "error"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One tool call requested by the model."""

    id: str
    name: str
    arguments: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


@dataclass(frozen=True, slots=True)
class Message:
    """A single chat message, including tool-call messages."""

    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()

    def to_dict(self) -> dict[str, object]:
        if self.role == ROLE_TOOL:
            return {
                "role": ROLE_TOOL,
                "tool_call_id": self.tool_call_id or "",
                "content": self.content,
            }
        if self.tool_calls:
            return {
                "role": self.role,
                "content": self.content,
                "tool_calls": [
                    tool_call.to_dict() for tool_call in self.tool_calls
                ],
            }
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """A chat completion request."""

    model: str
    messages: tuple[Message, ...]
    stream: bool = True
    tools: tuple[dict[str, object], ...] = ()
    tool_choice: str | None = "auto"

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [message.to_dict() for message in self.messages],
            "stream": self.stream,
        }
        if self.tools:
            payload["tools"] = list(self.tools)
            if self.tool_choice is not None:
                payload["tool_choice"] = self.tool_choice
        return payload


@dataclass(frozen=True, slots=True)
class Usage:
    """Token usage reported by the provider, when available."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One event from a streaming chat completion.

    ``type`` is one of ``token``, ``tool_calls``, ``done`` or ``error``.
    Token events carry visible answer text in ``text``; the tool-calls event
    carries fully assembled calls; the done event may carry ``usage``.
    """

    type: str
    text: str = ""
    usage: Usage | None = None
    error: GatewayError | None = None
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
