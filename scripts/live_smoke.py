#!/usr/bin/env python3
"""Manual live streaming smoke test for the configured provider.

MANUAL ONLY: this script performs a real network request and must never be
run by pytest.
"""

import asyncio
import os
import sys
import time
from contextlib import aclosing

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from friday.config.settings import load_settings  # noqa: E402
from friday.gateway.errors import GatewayError  # noqa: E402
from friday.gateway.openai_compat import OpenAICompatProvider  # noqa: E402
from friday.gateway.types import (  # noqa: E402
    EVENT_DONE,
    EVENT_TOKEN,
    ROLE_SYSTEM,
    ROLE_USER,
    Message,
)
from friday.security.secrets import SecretManager  # noqa: E402

PROMPT = "Reply with the single word: pong"


async def run_smoke() -> int:
    """Stream the smoke-test prompt and print the reply with timings."""
    settings = load_settings()
    provider = OpenAICompatProvider(settings.provider, SecretManager())
    messages = [
        Message(ROLE_SYSTEM, settings.provider.system_prompt),
        Message(ROLE_USER, PROMPT),
    ]

    started = time.perf_counter()
    first_token_at: float | None = None
    try:
        async with aclosing(provider.stream_chat(messages)) as stream:
            async for event in stream:
                if event.type == EVENT_TOKEN and event.text:
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                    print(event.text, end="", flush=True)
                elif event.type == EVENT_DONE:
                    break
    finally:
        await provider.aclose()

    elapsed = time.perf_counter() - started
    print()
    if first_token_at is not None:
        print(f"First token: {first_token_at - started:.2f}s")
    print(f"Total: {elapsed:.2f}s")
    return 0


def main() -> int:
    """Run the smoke test, reporting typed errors without secrets."""
    try:
        return asyncio.run(run_smoke())
    except GatewayError as exc:
        print(f"\n{exc.kind}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\n{exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
