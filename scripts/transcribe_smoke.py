#!/usr/bin/env python
"""Manual Faster-Whisper smoke test (never run by pytest).

Usage:
    python scripts/transcribe_smoke.py path\\to\\recording.wav
    python scripts/transcribe_smoke.py path.wav --language hi

The first run downloads the multilingual tiny model (~75 MB).  Progress
is printed while the model loads so the console never appears frozen.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from friday.config.settings import load_settings  # noqa: E402
from friday.voice.audio import to_mono_16k  # noqa: E402
from friday.voice.errors import TranscriptionError  # noqa: E402
from friday.voice.stt import (  # noqa: E402
    TranscriptionStatus,
    create_transcription_engine,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Faster-Whisper smoke test")
    parser.add_argument("wav", type=Path, help="Path to a WAV file")
    parser.add_argument(
        "--language",
        default="",
        help="Override language: auto (default), en or hi",
    )
    return parser


def _load_pcm(path: Path) -> bytes:
    """Read a WAV file and convert it to 16 kHz mono int16."""
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())

    if width != 2:
        raise ValueError(f"Expected 16-bit samples, got {width * 8}-bit")
    return to_mono_16k(raw, rate, channels, width)


def _print_status(status: TranscriptionStatus) -> None:
    print(f"[{status.phase}] {status.message}", flush=True)


async def _run(args: argparse.Namespace) -> int:
    if not args.wav.is_file():
        print(f"FileNotFoundError: {args.wav}", file=sys.stderr)
        return 1

    try:
        pcm = _load_pcm(args.wav)
    except (OSError, ValueError, wave.Error) as exc:
        print(f"AudioError: {exc}", file=sys.stderr)
        return 1

    settings = load_settings()
    engine = create_transcription_engine(
        settings=settings.stt, on_status=_print_status
    )
    language: str | None = args.language.strip() or None
    if language is None:
        language = settings.stt.language

    started = time.perf_counter()
    try:
        result = await engine.transcribe(pcm, language=language)
    except TranscriptionError as exc:
        print(f"{exc.kind}: {exc.message}", file=sys.stderr)
        return 1
    finally:
        await engine.close()

    elapsed = time.perf_counter() - started
    print(f"model: {engine.model_name}")
    print(f"language: {result.language or 'unknown'}")
    print(f"language_probability: {result.language_probability:.3f}")
    print(f"audio_seconds: {result.duration_seconds:.2f}")
    print(f"elapsed_seconds: {elapsed:.2f}")
    print(f"text: {result.text}")
    return 0


def main() -> int:
    args = _build_parser().parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
