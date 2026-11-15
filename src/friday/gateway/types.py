"""Value types shared by the AI gateway."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from friday.gateway.errors import GatewayError

ROLE_SYSTEM = "system"
ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

EVENT_TOKEN = "token"
EVENT_DONE = "done"
EVENT_ERROR = "error"


@dataclass(frozen=True, slots=True)
class Message:
    """A single chat message."""

    role: str
    content: str

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """A chat completion request."""

    model: str
    messages: tuple[Message, ...]
    stream: bool = True

    def to_payload(self) -> dict[str, object]:
        return {
            "model": self.model,
            "messages": [message.to_dict() for message in self.messages],
            "stream": self.stream,
        }


@dataclass(frozen=True, slots=True)
class Usage:
    """Token usage reported by the provider, when available."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """One event from a streaming chat completion.

    ``type`` is one of ``token``, ``done`` or ``error``. Token events carry
    visible answer text in ``text``; the done event may carry ``usage``.
    """

    type: str
    text: str = ""
    usage: Usage | None = None
    error: GatewayError | None = None
