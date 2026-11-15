"""Tests for the OpenAI-compatible streaming gateway (no real network)."""

import asyncio
import json
import logging

import httpx
import pytest

from friday.config.settings import ProviderSettings
from friday.gateway import errors
from friday.gateway.openai_compat import OpenAICompatProvider
from friday.gateway.types import EVENT_DONE, EVENT_TOKEN, Message
from friday.security.secrets import PROVIDER_API_KEY

KEY = "test-secret-key-abc123"


class FakeSecrets:
    """In-memory secret store used only by tests."""

    def __init__(self, value: str | None = KEY):
        self.value = value

    def get_secret(self, key: str) -> str | None:
        assert key == PROVIDER_API_KEY
        return self.value


def make_provider(
    handler,
    *,
    model: str = "test-model",
    secrets: FakeSecrets | None = None,
    retry_backoff: float = 0.0,
    max_retries: int = 2,
) -> OpenAICompatProvider:
    settings = ProviderSettings(model=model)
    return OpenAICompatProvider(
        settings,
        secrets if secrets is not None else FakeSecrets(),
        transport=httpx.MockTransport(handler),
        retry_backoff=retry_backoff,
        max_retries=max_retries,
    )


def sse_response(
    chunks: list[str],
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response_headers = {"content-type": "text/event-stream"}
    if headers:
        response_headers.update(headers)
    return httpx.Response(
        status_code,
        headers=response_headers,
        text="".join(chunks),
    )


def data_chunk(delta: dict) -> str:
    return f"data: {json.dumps({'choices': [{'delta': delta}]})}\n\n"


async def collect(provider: OpenAICompatProvider) -> list:
    try:
        return [
            event
            async for event in provider.stream_chat([Message("user", "hi")])
        ]
    finally:
        await provider.aclose()


class BlockingStream(httpx.AsyncByteStream):
    """Yields one SSE token, then blocks until cancelled."""

    def __init__(self) -> None:
        self.closed = False

    async def __aiter__(self):
        yield b'data: {"choices":[{"delta":{"content":"one"}}]}\n\n'
        await asyncio.Event().wait()
        yield b"data: [DONE]\n\n"

    async def aclose(self) -> None:
        self.closed = True


async def test_multi_chunk_stream_is_assembled() -> None:
    chunks = [
        data_chunk({"role": "assistant"}),
        data_chunk({"content": "Hel"}),
        data_chunk({"content": "lo"}),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    assert [event.text for event in events if event.type == EVENT_TOKEN] == [
        "Hel",
        "lo",
    ]
    assert events[-1].type == EVENT_DONE


async def test_done_stops_processing() -> None:
    chunks = [
        data_chunk({"content": "kept"}),
        "data: [DONE]\n\n",
        data_chunk({"content": "ignored"}),
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    tokens = [event.text for event in events if event.type == EVENT_TOKEN]
    assert tokens == ["kept"]


async def test_empty_and_keepalive_lines_are_ignored() -> None:
    chunks = [
        ": keep-alive\n\n",
        "\n",
        "event: message\n\n",
        "data:\n\n",
        data_chunk({}),
        data_chunk({"content": "ok"}),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    assert [event.text for event in events if event.type == EVENT_TOKEN] == ["ok"]


async def test_reasoning_content_is_excluded() -> None:
    chunks = [
        data_chunk({"reasoning_content": "secret chain of thought"}),
        data_chunk({"content": "Answer"}),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    assert [event.text for event in events if event.type == EVENT_TOKEN] == [
        "Answer"
    ]


async def test_think_text_is_excluded() -> None:
    chunks = [
        data_chunk({"content": "Before "}),
        data_chunk(
            {"content": "<think hidden reasoning>secret</think >After"}
        ),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    answer = "".join(
        event.text for event in events if event.type == EVENT_TOKEN
    )
    assert answer == "Before After"


async def test_think_tag_split_across_chunks_is_excluded() -> None:
    chunks = [
        data_chunk({"content": "<thi"}),
        data_chunk({"content": "nk>hidden</thi"}),
        data_chunk({"content": "nk>visible"}),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    answer = "".join(
        event.text for event in events if event.type == EVENT_TOKEN
    )
    assert answer == "visible"


async def test_usage_is_reported_on_done() -> None:
    chunks = [
        data_chunk({"content": "hi"}),
        "data: "
        + json.dumps(
            {
                "choices": [],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            }
        )
        + "\n\n",
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    assert events[-1].type == EVENT_DONE
    assert events[-1].usage is not None
    assert events[-1].usage.total_tokens == 5


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, errors.AuthError),
        (403, errors.AuthError),
        (404, errors.NotFound),
        (500, errors.ServerError),
    ],
)
async def test_http_status_maps_to_typed_error(
    status_code: int, error_type: type[errors.GatewayError]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text='{"error": "nope"}')

    provider = make_provider(handler)

    with pytest.raises(error_type) as exc_info:
        await collect(provider)

    assert exc_info.value.status_code == status_code
    await provider.aclose()


async def test_403_mentions_enterprise_gating() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="forbidden")

    provider = make_provider(handler)

    with pytest.raises(errors.AuthError) as exc_info:
        await collect(provider)

    assert "enterprise" in str(exc_info.value).lower()
    await provider.aclose()


async def test_429_with_retry_after() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            429,
            headers={"Retry-After": "7"},
            text="slow down",
        )

    provider = make_provider(handler)

    with pytest.raises(errors.RateLimited) as exc_info:
        await collect(provider)

    assert exc_info.value.retry_after == 7.0
    assert len(calls) == 1, "429 must never be retried"
    await provider.aclose()


async def test_429_without_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    provider = make_provider(handler)

    with pytest.raises(errors.RateLimited) as exc_info:
        await collect(provider)

    assert exc_info.value.retry_after is None
    await provider.aclose()


async def test_5xx_is_retried_then_succeeds() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(500, text="boom")
        return sse_response([data_chunk({"content": "recovered"})])

    provider = make_provider(handler)

    events = await collect(provider)

    assert [event.text for event in events if event.type == EVENT_TOKEN] == [
        "recovered"
    ]
    assert len(calls) == 2


async def test_5xx_is_not_retried_after_first_token() -> None:
    calls = []
    chunks = [
        data_chunk({"content": "Hi"}),
        'data: {"error": {"message": "server exploded"}}\n\n',
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return sse_response(chunks)

    provider = make_provider(handler)
    received = []
    try:
        with pytest.raises(errors.ServerError):
            async for event in provider.stream_chat([Message("user", "hi")]):
                received.append(event)
    finally:
        await provider.aclose()

    assert [event.text for event in received if event.type == EVENT_TOKEN] == [
        "Hi"
    ]
    assert len(calls) == 1, "must not retry after a token was yielded"


async def test_timeout_maps_to_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = make_provider(handler)

    with pytest.raises(errors.TimeoutError):
        await collect(provider)

    await provider.aclose()


async def test_connection_error_retries_then_reports_network_error() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("refused", request=request)

    provider = make_provider(handler)

    with pytest.raises(errors.NetworkError):
        await collect(provider)

    assert len(calls) == 3, "connection errors get two retries"
    await provider.aclose()


async def test_malformed_json_chunk() -> None:
    provider = make_provider(
        lambda request: sse_response(["data: {not json}\n\n"])
    )

    with pytest.raises(errors.MalformedResponse):
        await collect(provider)

    await provider.aclose()


async def test_stream_closes_cleanly_after_full_consumption() -> None:
    chunks = [
        data_chunk({"content": "one"}),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))
    stream = provider.stream_chat([Message("user", "hi")])

    try:
        events = [event async for event in stream]
        assert events[-1].type == EVENT_DONE
        await stream.aclose()
    finally:
        await provider.aclose()


async def test_stream_aclose_after_early_break_raises_nothing() -> None:
    http_stream = BlockingStream()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=http_stream,
        )

    provider = make_provider(handler)
    stream = provider.stream_chat([Message("user", "hi")])

    try:
        async for event in stream:
            if event.type == EVENT_TOKEN:
                break
        await stream.aclose()
        assert http_stream.closed
    finally:
        await provider.aclose()


def test_script_style_early_break_has_no_unhandled_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    http_stream = BlockingStream()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=http_stream,
        )

    async def scenario() -> None:
        provider = make_provider(handler)
        try:
            async for event in provider.stream_chat([Message("user", "hi")]):
                if event.type == EVENT_TOKEN:
                    break
        finally:
            await provider.aclose()

    asyncio.run(scenario())

    captured = capsys.readouterr()
    assert "unhandled exception" not in captured.err.lower()
    assert "Traceback" not in captured.err
    assert "The response was cancelled" not in captured.err


async def test_cancellation_mid_stream_propagates_and_closes_stream() -> None:
    stream = BlockingStream()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=stream,
        )

    provider = make_provider(handler)
    received = []

    async def consume() -> None:
        async for event in provider.stream_chat([Message("user", "hi")]):
            received.append(event)

    task = asyncio.create_task(consume())
    while not received:
        await asyncio.sleep(0.01)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert stream.closed
    await provider.aclose()


async def test_not_configured_when_model_missing() -> None:
    provider = make_provider(
        lambda request: sse_response([data_chunk({"content": "never"})]),
        model="",
    )

    with pytest.raises(errors.NotConfigured) as exc_info:
        await collect(provider)

    message = str(exc_info.value)
    assert "scripts/set_key.py" in message
    assert "scripts/list_models.py" in message
    assert "config.toml" in message
    await provider.aclose()


async def test_not_configured_when_key_missing() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return sse_response([data_chunk({"content": "never"})])

    provider = make_provider(handler, secrets=FakeSecrets(None))

    with pytest.raises(errors.NotConfigured):
        await collect(provider)

    assert calls == []
    await provider.aclose()


async def test_api_key_never_appears_in_exception_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "plain-secret-abc"
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text=f'{{"error": "invalid key {secret}"}}',
        )

    provider = make_provider(handler, secrets=FakeSecrets(secret))

    with pytest.raises(errors.AuthError) as exc_info:
        await collect(provider)

    assert secret not in str(exc_info.value)
    assert secret not in caplog.text
    assert "***REDACTED***" in str(exc_info.value)
    await provider.aclose()


async def test_provider_body_is_redacted_and_truncated() -> None:
    secret = "plain-secret-abc"
    long_key_like = "sk-" + "a" * 48
    body = f"{secret} {long_key_like} " + ("x" * 500)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=body)

    provider = make_provider(
        handler,
        secrets=FakeSecrets(secret),
        max_retries=0,
    )

    with pytest.raises(errors.ServerError) as exc_info:
        await collect(provider)

    text = str(exc_info.value)
    assert secret not in text
    assert "sk-aaaa" not in text
    assert len(exc_info.value.provider_message) <= 300
    await provider.aclose()
