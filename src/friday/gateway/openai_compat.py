"""OpenAI-compatible streaming provider built on httpx."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from friday.config.settings import ProviderSettings
from friday.core.logging import get_logger
from friday.gateway import errors
from friday.gateway.base import Provider
from friday.gateway.types import (
    EVENT_DONE,
    EVENT_TOKEN,
    ChatRequest,
    Message,
    StreamEvent,
    Usage,
)
from friday.security.secrets import PROVIDER_API_KEY, SecretManager

logger = get_logger(__name__)


class _ThinkTagFilter:
    """Strip ``<think...>...</think...>`` reasoning spans from streamed text."""

    _OPEN = "<think"
    _CLOSE = "</think"

    def __init__(self) -> None:
        self._buffer = ""
        self._in_think = False

    def feed(self, text: str) -> str:
        """Consume *text* and return the visible part."""
        self._buffer += text
        visible: list[str] = []

        while True:
            if self._in_think:
                close_index = self._buffer.find(self._CLOSE)
                if close_index == -1:
                    # Keep only a possible partial closing tag.
                    self._buffer = self._buffer[-(len(self._CLOSE) - 1) :]
                    return "".join(visible)
                close_end = self._buffer.find(">", close_index)
                if close_end == -1:
                    return "".join(visible)
                self._buffer = self._buffer[close_end + 1 :]
                self._in_think = False
                continue

            open_index = self._buffer.find(self._OPEN)
            if open_index == -1:
                keep = self._partial_suffix_length(self._buffer, self._OPEN)
                if keep:
                    visible.append(self._buffer[:-keep])
                    self._buffer = self._buffer[-keep:]
                else:
                    visible.append(self._buffer)
                    self._buffer = ""
                return "".join(visible)

            open_end = self._buffer.find(">", open_index)
            if open_end == -1:
                visible.append(self._buffer[:open_index])
                self._buffer = self._buffer[open_index:]
                return "".join(visible)

            visible.append(self._buffer[:open_index])
            self._buffer = self._buffer[open_end + 1 :]
            self._in_think = True

    def flush(self) -> str:
        """Return any buffered visible text at the end of a stream."""
        buffered = self._buffer
        self._buffer = ""
        if self._in_think:
            return ""
        if buffered.startswith(self._OPEN) or self._OPEN.startswith(buffered):
            # An unterminated tag is not answer text.
            return ""
        return buffered

    @staticmethod
    def _partial_suffix_length(text: str, tag: str) -> int:
        for length in range(min(len(text), len(tag) - 1), 0, -1):
            if tag.startswith(text[-length:]):
                return length
        return 0


class OpenAICompatProvider(Provider):
    """Provider for any OpenAI-compatible ``/chat/completions`` endpoint."""

    def __init__(
        self,
        settings: ProviderSettings,
        secret_manager: SecretManager | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        client: httpx.AsyncClient | None = None,
        retry_backoff: float = 0.5,
        max_retries: int = 2,
    ) -> None:
        self._settings = settings
        self._secrets = secret_manager if secret_manager is not None else (
            SecretManager()
        )
        self._owns_client = client is None
        if client is None:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=settings.connect_timeout_seconds,
                    read=settings.read_timeout_seconds,
                    write=settings.read_timeout_seconds,
                    pool=settings.connect_timeout_seconds,
                ),
                transport=transport,
            )
        self._client = client
        self._retry_backoff = retry_backoff
        self._max_retries = max_retries

    @property
    def _base_url(self) -> str:
        return self._settings.base_url.rstrip("/")

    async def aclose(self) -> None:
        """Close the HTTP client if this provider created it."""
        if self._owns_client:
            await self._client.aclose()

    async def stream_chat(
        self, messages: Sequence[Message]
    ) -> AsyncIterator[StreamEvent]:
        """Stream a chat completion from the configured provider."""
        api_key = self._require_configuration()
        request = ChatRequest(
            model=self._settings.model.strip(),
            messages=tuple(messages),
            stream=True,
        )
        url = f"{self._base_url}/chat/completions"
        attempt = 0

        try:
            while True:
                yielded_any = False
                try:
                    async with self._client.stream(
                        "POST",
                        url,
                        json=request.to_payload(),
                        headers=self._headers(api_key),
                    ) as response:
                        if response.status_code != 200:
                            body = await response.aread()
                            raise errors.build_http_error(
                                response.status_code,
                                body.decode("utf-8", "replace"),
                                secret=api_key,
                                retry_after_header=response.headers.get(
                                    "Retry-After"
                                ),
                            )

                        async for event in self._iter_events(response, api_key):
                            if event.type == EVENT_TOKEN and event.text:
                                yielded_any = True
                            yield event
                        return

                except httpx.ConnectError as exc:
                    if yielded_any or attempt >= self._max_retries:
                        raise errors.NetworkError(
                            f"Could not connect to {self._base_url}."
                        ) from exc
                    attempt += 1
                    await asyncio.sleep(
                        self._retry_backoff * (2 ** (attempt - 1))
                    )

                except errors.ServerError:
                    if yielded_any or attempt >= self._max_retries:
                        raise
                    attempt += 1
                    logger.warning(
                        "Provider server error; retrying (attempt %s of %s)",
                        attempt,
                        self._max_retries,
                    )
                    await asyncio.sleep(
                        self._retry_backoff * (2 ** (attempt - 1))
                    )

        # CancelledError and GeneratorExit intentionally propagate unchanged:
        # converting them would break async generator cleanup.
        except httpx.TimeoutException as exc:
            raise errors.TimeoutError(
                "The provider timed out while responding. "
                "Check the connection and provider.read_timeout_seconds."
            ) from exc
        except httpx.TransportError as exc:
            raise errors.NetworkError(
                "Network error while contacting the provider "
                f"({exc.__class__.__name__})."
            ) from exc

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }

    def _require_configuration(self) -> str:
        model = (self._settings.model or "").strip()
        api_key = self._secrets.get_secret(PROVIDER_API_KEY)
        missing_model = not model
        missing_key = not api_key
        if missing_model or missing_key:
            details = []
            if missing_model:
                details.append("provider.model is empty")
            if missing_key:
                details.append("no API key is stored")
            raise errors.NotConfigured(
                "AI provider is not configured ("
                + "; ".join(details)
                + ").\nFix:\n"
                "1. Store the API key: python scripts/set_key.py\n"
                "2. Find a model id: python scripts/list_models.py\n"
                "3. Set provider.model in %APPDATA%\\Friday\\config.toml"
            )
        return api_key or ""

    async def _iter_events(
        self, response: httpx.Response, api_key: str
    ) -> AsyncIterator[StreamEvent]:
        usage: Usage | None = None
        think_filter = _ThinkTagFilter()

        async for raw_line in response.aiter_lines():
            line = raw_line.strip("\r")
            if not line or line.startswith(":"):
                # Empty separators and SSE comments / keep-alives.
                continue
            if not line.startswith("data:"):
                continue

            data = line[len("data:") :].strip()
            if not data:
                continue

            if data == "[DONE]":
                tail = think_filter.flush()
                if tail:
                    yield StreamEvent(EVENT_TOKEN, tail)
                yield StreamEvent(EVENT_DONE, usage=usage)
                return

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError as exc:
                raise errors.MalformedResponse(
                    "Provider sent malformed JSON in its stream.",
                    provider_message=errors.sanitize_provider_message(
                        data, secret=api_key
                    ),
                ) from exc

            if not isinstance(chunk, dict):
                raise errors.MalformedResponse(
                    "Provider sent a non-object stream chunk."
                )

            if chunk.get("error"):
                raise errors.ServerError(
                    "Provider reported an error while streaming.",
                    provider_message=errors.sanitize_provider_message(
                        self._format_error_payload(chunk["error"]),
                        secret=api_key,
                    ),
                )

            reported_usage = self._parse_usage(chunk)
            if reported_usage is not None:
                usage = reported_usage

            choices = chunk.get("choices")
            if choices is None:
                continue
            if not isinstance(choices, list):
                raise errors.MalformedResponse(
                    "Provider sent an invalid choices field."
                )

            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if not isinstance(delta, dict):
                    continue
                content = delta.get("content")
                if content is None:
                    # Missing deltas and reasoning_content need no handling:
                    # reasoning is intentionally excluded from the answer.
                    continue
                if not isinstance(content, str):
                    raise errors.MalformedResponse(
                        "Provider sent non-text content in its stream."
                    )
                visible = think_filter.feed(content)
                if visible:
                    yield StreamEvent(EVENT_TOKEN, visible)

        tail = think_filter.flush()
        if tail:
            yield StreamEvent(EVENT_TOKEN, tail)
        yield StreamEvent(EVENT_DONE, usage=usage)

    @staticmethod
    def _format_error_payload(payload: Any) -> str:
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("detail")
            if isinstance(message, str):
                return message
            return json.dumps(payload, ensure_ascii=False)
        return str(payload)

    @staticmethod
    def _parse_usage(chunk: dict[str, Any]) -> Usage | None:
        usage = chunk.get("usage")
        if not isinstance(usage, dict):
            return None

        def as_int(value: Any) -> int | None:
            return value if isinstance(value, int) else None

        return Usage(
            prompt_tokens=as_int(usage.get("prompt_tokens")),
            completion_tokens=as_int(usage.get("completion_tokens")),
            total_tokens=as_int(usage.get("total_tokens")),
        )
