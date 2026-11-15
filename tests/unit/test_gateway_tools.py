"""Streaming tool-call assembly and payload tests (no real network)."""

from __future__ import annotations

import json

import httpx
import pytest

from friday.config.settings import ProviderSettings
from friday.gateway import errors
from friday.gateway.openai_compat import OpenAICompatProvider
from friday.gateway.types import (
    EVENT_DONE,
    EVENT_TOKEN,
    EVENT_TOOL_CALLS,
    ChatRequest,
    Message,
    ToolCall,
)
from friday.security.secrets import PROVIDER_API_KEY

KEY = "test-secret-key-abc123"


class FakeSecrets:
    """In-memory secret store used only by tests."""

    def __init__(self, value: str | None = KEY):
        self.value = value

    def get_secret(self, key: str) -> str | None:
        assert key == PROVIDER_API_KEY
        return self.value


def make_provider(handler) -> OpenAICompatProvider:
    return OpenAICompatProvider(
        ProviderSettings(model="test-model"),
        FakeSecrets(),
        transport=httpx.MockTransport(handler),
        retry_backoff=0.0,
        max_retries=0,
    )


def sse_response(chunks: list[str]) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text="".join(chunks),
    )


def data_chunk(delta: dict) -> str:
    return f"data: {json.dumps({'choices': [{'delta': delta}]})}\n\n"


def tool_fragment(
    index: int,
    *,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> str:
    call: dict[str, object] = {"index": index}
    function: dict[str, object] = {}
    if call_id is not None:
        call["id"] = call_id
    if name is not None:
        function["name"] = name
    if arguments is not None:
        function["arguments"] = arguments
    if function:
        call["function"] = function
    return data_chunk({"tool_calls": [call]})


async def collect(
    provider: OpenAICompatProvider,
    *,
    tools: tuple[dict[str, object], ...] = (),
    tool_choice: str | None = "auto",
) -> list:
    try:
        return [
            event
            async for event in provider.stream_chat(
                [Message("user", "hi")],
                tools=tools,
                tool_choice=tool_choice,
            )
        ]
    finally:
        await provider.aclose()


def event_of(events: list, kind: str):
    matches = [event for event in events if event.type == kind]
    assert len(matches) == 1
    return matches[0]


async def test_split_argument_fragments_are_accumulated_by_index() -> None:
    chunks = [
        tool_fragment(
            0,
            call_id="call_1",
            name="get_time",
            arguments='{"timezone": "Asia/',
        ),
        tool_fragment(0, arguments='Tokyo"}'),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    calls = event_of(events, EVENT_TOOL_CALLS).tool_calls
    assert calls == (
        ToolCall(
            id="call_1",
            name="get_time",
            arguments='{"timezone": "Asia/Tokyo"}',
        ),
    )
    assert events[-1].type == EVENT_DONE


async def test_multiple_indexes_are_assembled_in_index_order() -> None:
    chunks = [
        tool_fragment(
            1,
            call_id="call_b",
            name="open_app",
            arguments='{"name":',
        ),
        tool_fragment(
            0,
            call_id="call_a",
            name="get_time",
            arguments="{}",
        ),
        tool_fragment(1, arguments=' "paint"}'),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    calls = event_of(events, EVENT_TOOL_CALLS).tool_calls
    assert [call.name for call in calls] == ["get_time", "open_app"]
    assert calls[0].arguments == "{}"
    assert calls[1].arguments == '{"name": "paint"}'


async def test_text_and_tool_calls_can_be_mixed() -> None:
    chunks = [
        data_chunk({"content": "Checking "}),
        tool_fragment(0, call_id="call_1", name="get_time"),
        data_chunk({"content": "now."}),
        tool_fragment(0, arguments="{}"),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    tokens = [event.text for event in events if event.type == EVENT_TOKEN]
    assert "".join(tokens) == "Checking now."
    calls = event_of(events, EVENT_TOOL_CALLS).tool_calls
    assert calls[0].name == "get_time"
    assert calls[0].arguments == "{}"


async def test_calls_are_finalized_without_done_marker() -> None:
    chunks = [
        tool_fragment(
            0, call_id="call_1", name="read_clipboard", arguments="{}"
        )
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    calls = event_of(events, EVENT_TOOL_CALLS).tool_calls
    assert calls == (
        ToolCall(id="call_1", name="read_clipboard", arguments="{}"),
    )
    assert events[-1].type == EVENT_DONE


async def test_empty_name_fragments_are_dropped() -> None:
    chunks = [
        tool_fragment(0, call_id="orphan", arguments="{}"),
        tool_fragment(1, call_id="call_1", name="get_time", arguments="{}"),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    events = await collect(provider)

    calls = event_of(events, EVENT_TOOL_CALLS).tool_calls
    assert [call.name for call in calls] == ["get_time"]


async def test_malformed_json_discards_partial_calls() -> None:
    chunks = [
        tool_fragment(
            0,
            call_id="call_1",
            name="get_time",
            arguments='{"timezone":',
        ),
        "data: {not json}\n\n",
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    with pytest.raises(errors.MalformedResponse):
        await collect(provider)


async def test_invalid_tool_fragment_shape_is_rejected() -> None:
    chunks = [
        data_chunk({"tool_calls": [{"function": {"name": "get_time"}}]}),
        "data: [DONE]\n\n",
    ]
    provider = make_provider(lambda request: sse_response(chunks))

    with pytest.raises(errors.MalformedResponse):
        await collect(provider)


async def test_payload_contains_tool_messages_and_tools() -> None:
    call = ToolCall(id="call_1", name="get_time", arguments="{}")
    request = ChatRequest(
        model="test-model",
        messages=(
            Message("system", "rules"),
            Message("user", "what time is it?"),
            Message("assistant", "", tool_calls=(call,)),
            Message("tool", "noon", tool_call_id="call_1"),
        ),
        tools=(
            {
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "time",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ),
    )

    payload = request.to_payload()

    assert payload["tools"] == list(request.tools)
    assert payload["tool_choice"] == "auto"
    messages = payload["messages"]
    assert messages[2] == {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_time", "arguments": "{}"},
            }
        ],
    }
    assert messages[3] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "noon",
    }


async def test_payload_omits_tools_when_none_are_supplied() -> None:
    request = ChatRequest(
        model="test-model",
        messages=(Message("user", "hi"),),
    )

    payload = request.to_payload()

    assert "tools" not in payload
    assert "tool_choice" not in payload


async def test_request_includes_tools_and_auto_choice_on_the_wire() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return sse_response(["data: [DONE]\n\n"])

    provider = make_provider(handler)
    tools = (
        {
            "type": "function",
            "function": {
                "name": "get_time",
                "description": "time",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    )

    await collect(provider, tools=tools)

    assert captured["tools"] == list(tools)
    assert captured["tool_choice"] == "auto"
