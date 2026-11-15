#!/usr/bin/env python
"""List available TTS voices for the configured engine.

Usage:
    python scripts/list_voices.py [--locale en-IN]

Manual only; never run by pytest.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from friday.config.settings import load_settings
from friday.voice import available_engines, create_engine


async def main() -> int:
    parser = argparse.ArgumentParser(description="List TTS voices")
    parser.add_argument(
        "--locale",
        help="Filter voices by locale (e.g., en-IN, en-US, en-GB)",
    )
    parser.add_argument(
        "--engine",
        choices=["edge", "windows"],
        help="Override engine from config",
    )
    args = parser.parse_args()

    try:
        settings = load_settings()
    except Exception as exc:
        print(f"ConfigError: {exc}", file=sys.stderr)
        return 1

    engine_name = args.engine or settings.voice.engine
    if engine_name not in available_engines():
        available = ", ".join(available_engines())
        msg = f"Error: Unknown engine '{engine_name}'. Available: {available}"
        print(msg, file=sys.stderr)
        return 1

    try:
        engine = create_engine(engine_name)
    except Exception as exc:
        print(f"TTSNotAvailable: {exc}", file=sys.stderr)
        return 1

    try:
        voices = await engine.list_voices()
    except Exception as exc:
        print(f"TTSError: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.close()

    if args.locale:
        voices = [v for v in voices if args.locale.lower() in v.locale.lower()]

    if not voices:
        print("No voices found.")
        return 0

    for v in voices:
        print(f"{v.name} | {v.locale} | {v.gender} | {v.age} | {v.engine_id}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
