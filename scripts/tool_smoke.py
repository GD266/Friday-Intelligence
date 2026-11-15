#!/usr/bin/env python3
"""Manual non-streaming tool-calling smoke test for the configured provider.

MANUAL ONLY: this script performs real network requests and must never be run
by pytest.
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from friday.config.settings import (  # noqa: E402
    ProviderSettings,
    load_settings,
)
from friday.gateway import errors  # noqa: E402
from friday.security.secrets import (  # noqa: E402
    PROVIDER_API_KEY,
    SecretManager,
)

RUNS = 5
USER_MESSAGE = "What time is it in Tokyo?"
TOOL_NAME = "get_time"
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": "Return the current time in an IANA timezone.",
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": (
                        "IANA timezone name, for example Asia/Tokyo."
                    ),
                }
            },
            "required": ["timezone"],
            "additionalProperties": False,
        },
    },
}


@dataclass(frozen=True)
class RunResult:
    """Outcome of one provider request."""

    has_tool_calls: bool
    tool_name: str
    raw_arguments: str
    schema_valid: bool
    schema_reason: str
    reply: str
    elapsed_seconds: float


def _validate_arguments(raw_arguments: str) -> tuple[bool, str]:
    """Validate get_time arguments against the advertised JSON schema."""
    try:
        parsed = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        return False, f"invalid JSON ({exc})"
    if not isinstance(parsed, dict):
        return False, "arguments must be a JSON object"
    unexpected = sorted(set(parsed) - {"timezone"})
    if unexpected:
        return False, f"unexpected field(s): {', '.join(unexpected)}"
    if "timezone" not in parsed:
        return False, "missing required field: timezone"
    if not isinstance(parsed["timezone"], str):
        return False, "timezone must be a string"
    return True, "matches schema"


def _extract_message(payload: Any) -> dict[str, Any]:
    """Return the first response message or raise a typed gateway error."""
    if not isinstance(payload, dict):
        raise errors.MalformedResponse(
            "The provider returned a non-object response."
        )
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise errors.MalformedResponse(
            "The provider returned no choices."
        )
    choice = choices[0]
    if not isinstance(choice, dict):
        raise errors.MalformedResponse(
            "The provider returned a malformed choice."
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise errors.MalformedResponse(
            "The provider returned a malformed message."
        )
    return message


def _extract_tool_call(
    message: dict[str, Any],
) -> tuple[str, str] | None:
    """Return the first raw (name, arguments) pair, if present."""
    tool_calls = message.get("tool_calls")
    if tool_calls is None:
        return None
    if not isinstance(tool_calls, list):
        raise errors.MalformedResponse(
            "The provider returned a malformed tool_calls field."
        )
    if not tool_calls:
        return None

    first = tool_calls[0]
    if not isinstance(first, dict):
        raise errors.MalformedResponse(
            "The provider returned a malformed tool call."
        )
    function = first.get("function")
    if not isinstance(function, dict):
        raise errors.MalformedResponse(
            "The provider returned a malformed tool function."
        )

    name = function.get("name")
    arguments = function.get("arguments")
    raw_name = name if isinstance(name, str) else ""
    if isinstance(arguments, str):
        raw_arguments = arguments
    elif arguments is None:
        raw_arguments = ""
    else:
        raw_arguments = json.dumps(arguments, ensure_ascii=False)
    return raw_name, raw_arguments


async def _request_once(
    client: httpx.AsyncClient,
    provider: ProviderSettings,
    api_key: str,
) -> RunResult:
    """Send one non-streaming chat/completions request with a tool."""
    url = f"{provider.base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": provider.model.strip(),
        "messages": [{"role": "user", "content": USER_MESSAGE}],
        "tools": [TOOL_DEFINITION],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    started = time.perf_counter()
    try:
        response = await client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise errors.TimeoutError(
            "The provider timed out while handling the tool request."
        ) from exc
    except httpx.TransportError as exc:
        raise errors.NetworkError(
            "Network error while contacting the provider "
            f"({exc.__class__.__name__})."
        ) from exc
    elapsed = time.perf_counter() - started

    if response.status_code != 200:
        raise errors.build_http_error(
            response.status_code,
            response.text,
            secret=api_key,
            retry_after_header=response.headers.get("Retry-After"),
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise errors.MalformedResponse(
            "The provider returned a non-JSON response."
        ) from exc

    message = _extract_message(data)
    tool_call = _extract_tool_call(message)
    if tool_call is None:
        content = message.get("content")
        reply = content if isinstance(content, str) else ""
        return RunResult(
            has_tool_calls=False,
            tool_name="",
            raw_arguments="",
            schema_valid=False,
            schema_reason="no tool call",
            reply=reply,
            elapsed_seconds=elapsed,
        )

    raw_name, raw_arguments = tool_call
    schema_valid, schema_reason = _validate_arguments(raw_arguments)
    return RunResult(
        has_tool_calls=True,
        tool_name=raw_name,
        raw_arguments=raw_arguments,
        schema_valid=schema_valid,
        schema_reason=schema_reason,
        reply="",
        elapsed_seconds=elapsed,
    )


async def run_smoke() -> int:
    """Run five requests and print a tool-call summary."""
    settings = load_settings()
    provider = settings.provider
    model = provider.model.strip()
    if not model:
        raise errors.NotConfigured(
            "provider.model is empty. Set it in "
            "%APPDATA%\\Friday\\config.toml."
        )

    api_key = SecretManager().get_secret(PROVIDER_API_KEY)
    if not api_key:
        raise errors.NotConfigured(
            "No API key is stored.\nRun: python scripts/set_key.py"
        )

    timeout = httpx.Timeout(
        connect=provider.connect_timeout_seconds,
        read=provider.read_timeout_seconds,
        write=provider.read_timeout_seconds,
        pool=provider.connect_timeout_seconds,
    )

    valid_tool_calls = 0
    invalid_json = 0
    no_tool_call = 0

    print(f"Model: {model}")
    async with httpx.AsyncClient(timeout=timeout) as client:
        for run in range(1, RUNS + 1):
            result = await _request_once(client, provider, api_key)

            print(f"\nRun {run}/{RUNS}")
            print(
                "  tool_calls: "
                + ("yes" if result.has_tool_calls else "no")
            )
            if result.has_tool_calls:
                print(f"  tool name: {result.tool_name}")
                print(f"  arguments: {result.raw_arguments}")
                print(
                    "  schema valid: "
                    + ("yes" if result.schema_valid else "no")
                )
                if result.tool_name != TOOL_NAME:
                    print(f"  reason: expected tool {TOOL_NAME}")
                elif not result.schema_valid:
                    print(f"  reason: {result.schema_reason}")

                if result.tool_name == TOOL_NAME and result.schema_valid:
                    valid_tool_calls += 1
                else:
                    invalid_json += 1
            else:
                no_tool_call += 1
                reply = result.reply.strip()
                print(f"  reply: {reply or '(empty)'}")

            print(f"  total time: {result.elapsed_seconds:.2f}s")

    print()
    print(
        f"Summary: valid tool calls {valid_tool_calls}/{RUNS}, "
        f"invalid JSON {invalid_json}/{RUNS}, "
        f"no tool call {no_tool_call}/{RUNS}"
    )
    return 0


def main() -> int:
    """Run the tool smoke test, reporting typed errors without secrets."""
    try:
        return asyncio.run(run_smoke())
    except errors.GatewayError as exc:
        print(f"\n{exc.kind}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
