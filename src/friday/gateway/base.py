"""Abstract AI provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from friday.gateway.types import Message, StreamEvent


class Provider(ABC):
    """A streaming chat completion provider."""

    @abstractmethod
    def stream_chat(
        self, messages: Sequence[Message]
    ) -> AsyncIterator[StreamEvent]:
        """Stream the assistant reply for *messages*.

        Implementations yield ``StreamEvent`` objects and raise typed
        :mod:`friday.gateway.errors` exceptions on failure.
        """
        raise NotImplementedError
