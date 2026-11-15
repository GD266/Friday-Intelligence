#!/usr/bin/env python
"""Manual smoke test for streaming tool calls.

This script uses the REAL gateway and registry schemas to verify that
tool calls are correctly streamed and assembled. It does NOT execute
any tools and NEVER prints the API key.

Run manually: python scripts/tool_stream_smoke.py

Requires FRIDAY_API_KEY environment variable and valid config.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Add src to path - must be before friday imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
# ruff: noqa: E402,I001

from friday.config.settings import ToolsSettings, load_settings
from friday.gateway.errors import GatewayError
from friday.gateway.openai_compat import OpenAICompatProvider
from friday.gateway.types import (
    EVENT_DONE,
    EVENT_TOKEN,
    EVENT_TOOL_CALLS,
    Message,
)
from friday.security.secrets import SecretManager
from friday.tools.builtin import build_builtin_registry


PROMPTS = [
    "What time is it in Tokyo?",
    "Open notepad",
    "What is 2+2?",
    "What time is it?",
    "Open the file C:\\Windows\\System32\\cmd.exe",
]


async def run_smoke_test() -> None:
    # Load settings from config (uses provider.model from config.toml)
    settings = load_settings()
    # Override only tools settings for this test
    settings.tools = ToolsSettings(enabled=True)

    if not settings.provider.model.strip():
        print("ERROR: provider.model is empty. Set it in config.toml.")
        return

    # Get API key from keyring or env
    secret_manager = SecretManager()
    api_key = secret_manager.get_secret("provider_api_key") or os.environ.get(
        "FRIDAY_API_KEY"
    )
    if not api_key:
        print("ERROR: No API key found. Set FRIDAY_API_KEY or store in keyring.")
        return

    # Build tool registry and get provider specs
    registry = build_builtin_registry(settings.tools)
    specs = registry.provider_specs()

    print("=" * 60)
    print("FRIDAY 2.0 Phase 4 - Tool Streaming Smoke Test")
    print("=" * 60)
    print(f"Model: {settings.provider.model}")
    print(f"Registered tools: {[s['function']['name'] for s in specs]}")
    print(f"Prompts to test: {len(PROMPTS)}")
    print("-" * 60)

    # Create provider
    provider = OpenAICompatProvider(settings.provider, secret_manager)

    try:
        for i, prompt in enumerate(PROMPTS, 1):
            print(f"\n[{i}/{len(PROMPTS)}] Prompt: {prompt}")
            print("-" * 60)

            messages = [Message("user", prompt)]
            tool_calls_seen = []
            text_accumulated = []

            async for event in provider.stream_chat(
                messages, tools=specs, tool_choice="auto"
            ):
                if event.type == EVENT_TOKEN:
                    if event.text:
                        text_accumulated.append(event.text)
                        print(f"  [TOKEN] {event.text!r}")
                elif event.type == EVENT_TOOL_CALLS:
                    for tc in event.tool_calls:
                        tool_calls_seen.append({
                            "id": tc.id,
                            "name": tc.name,
                            "arguments": tc.arguments,
                        })
                        print(f"  [TOOL CALL] {tc.name}({tc.arguments}) id={tc.id}")
                elif event.type == EVENT_DONE:
                    print(f"  [DONE] usage={event.usage}")
                elif event.type == "error":
                    print(f"  [ERROR] {event.error}")

            # Summary
            full_text = "".join(text_accumulated)
            # Replace non-ASCII chars for Windows console
            safe_text = full_text.encode("ascii", "replace").decode("ascii")
            print("\n  Summary:")
            print(f"    Text: {safe_text[:80]}{'...' if len(safe_text) > 80 else ''}")
            print(f"    Tool calls: {len(tool_calls_seen)}")
            for tc in tool_calls_seen:
                # Validate against registry
                tool = registry.get(tc["name"])
                if tool:
                    try:
                        parsed = json.loads(tc["arguments"])
                        tool.args_model.model_validate(parsed)
                        print(f"      OK {tc['name']}: args validated OK")
                    except Exception as e:
                        print(f"      FAIL {tc['name']}: args INVALID - {e}")
                else:
                    print(f"      ? {tc['name']}: UNKNOWN TOOL")

    finally:
        await provider.aclose()

    print("\n" + "=" * 60)
    print("Smoke test complete.")
    print("=" * 60)


def main() -> int:
    try:
        asyncio.run(run_smoke_test())
        return 0
    except GatewayError as exc:
        print(f"\n{exc.kind}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
