#!/usr/bin/env python
"""Standalone Faster-Whisper accuracy/speed benchmark (never run by pytest).

This does not touch the UI, the conversation pipeline or microphone capture.
It loads one model at a time, reuses the production STT engine and audio
helpers, and writes a JSON report that includes the recognised text.

Recognised speech is deliberately kept out of the application logs; the JSON
report is a local benchmark artefact and is git-ignored.

Typical use on the 8 GB laptop:

    .\\venv\\Scripts\\python.exe scripts\\stt_benchmark.py

    # one model, both beam sizes, every VAD profile
    .\\venv\\Scripts\\python.exe scripts\\stt_benchmark.py --models base

The known-distorted capture is excluded by default; its text is never
collected.  To include it anyway, pass ``--wav`` for it and an ``--exclude``
name that matches nothing (for example ``--exclude none``).
"""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import gc
import json
import os
import re
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from friday.voice.audio import to_mono_16k  # noqa: E402
from friday.voice.errors import TranscriptionError  # noqa: E402
from friday.voice.stt import (  # noqa: E402
    FasterWhisperEngine,
    TranscriptionStatus,
)

DEFAULT_TMP_DIR = (
    Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Friday" / "tmp" / "tts"
)

# The 1.8 s Bluetooth capture is heavily distorted.  It is excluded so its
# text never enters the report (earlier runs must not be quoted either).
DEFAULT_EXCLUDES = ("friday_mic_1794936990098.wav",)

DEVANAGARI = re.compile(r"[\u0900-\u097F]")

# Named VAD profiles.  ``safe`` keeps the padding and only removes clear
# silence; ``default`` mirrors Faster-Whisper's own aggressive defaults and
# is expected to be riskier for quiet sentence endings.
VAD_PROFILES: dict[str, dict[str, float | int] | None] = {
    "off": None,
    "safe": {
        "threshold": 0.4,
        "min_silence_duration_ms": 500,
        "speech_pad_ms": 400,
        "min_speech_duration_ms": 0,
    },
    "default": {
        "threshold": 0.5,
        "min_silence_duration_ms": 2000,
        "speech_pad_ms": 400,
        "min_speech_duration_ms": 0,
    },
}


class _ProcessMemoryCounters(ctypes.Structure):
    """PROCESS_MEMORY_COUNTERS from psapi.h."""

    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _memory_snapshot() -> dict[str, float] | None:
    """Return process working-set figures in MiB (Windows only)."""
    if sys.platform != "win32":
        return None
    from ctypes import wintypes

    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        ok = psapi.GetProcessMemoryInfo(
            kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
    except (AttributeError, OSError):
        return None
    if not ok:
        return None
    mib = 1024 * 1024
    return {
        "working_set_mib": round(counters.WorkingSetSize / mib, 1),
        "peak_working_set_mib": round(
            counters.PeakWorkingSetSize / mib, 1
        ),
        "pagefile_mib": round(counters.PagefileUsage / mib, 1),
    }


def _load_pcm(path: Path) -> bytes:
    """Read a WAV file and convert it with the production audio helper."""
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        rate = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError(f"Expected 16-bit samples, got {width * 8}-bit")
    return to_mono_16k(raw, rate, channels, width)


def _script(text: str) -> str:
    """Classify the output script so Hindi can be checked at a glance."""
    if not text.strip():
        return "empty"
    return "devanagari" if DEVANAGARI.search(text) else "latin"


def _discover(args: argparse.Namespace) -> list[Path]:
    """Return the recordings to benchmark, newest last."""
    if args.wav:
        files = [Path(item) for item in args.wav]
    else:
        files = sorted(DEFAULT_TMP_DIR.glob("*.wav"))
    excluded = {name.casefold() for name in args.exclude}
    selected = [
        path
        for path in files
        if path.is_file() and path.name.casefold() not in excluded
    ]
    return selected


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark Faster-Whisper models on local WAV files"
    )
    parser.add_argument(
        "--wav",
        action="append",
        default=[],
        help="Explicit WAV path (repeatable). Defaults to the Friday tmp dir.",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=["tiny", "base"],
        choices=["tiny", "base"],
        help="Multilingual models to compare (default: tiny base)",
    )
    parser.add_argument(
        "--beams",
        nargs="+",
        type=int,
        default=[1, 5],
        help="Beam sizes to compare (default: 1 5)",
    )
    parser.add_argument(
        "--vad",
        nargs="+",
        default=["off", "safe", "default"],
        choices=list(VAD_PROFILES),
        help="VAD profiles to compare (default: off safe default)",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=0,
        help="cpu_threads passed to Faster-Whisper (0 = library default)",
    )
    parser.add_argument(
        "--exclude",
        nargs="+",
        default=list(DEFAULT_EXCLUDES),
        help="File names to skip (default: the distorted capture)",
    )
    parser.add_argument(
        "--no-overrides",
        action="store_true",
        help="Skip explicit en/hi runs",
    )
    parser.add_argument(
        "--override-beam",
        type=int,
        default=5,
        help="Beam size for the explicit en/hi runs (default: 5)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON report path (default: benchmark_reports/...)",
    )
    return parser


def _default_output() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        Path(__file__).parent.parent
        / "benchmark_reports"
        / f"stt_benchmark_{stamp}.json"
    )


def _status_printer(model: str):
    def _print(status: TranscriptionStatus) -> None:
        print(f"[{model}] {status.phase}: {status.message}", flush=True)

    return _print


async def _run_once(
    engine: FasterWhisperEngine,
    pcm: bytes,
    *,
    model: str,
    beam_size: int,
    vad_profile: str,
    language: str,
) -> dict[str, object]:
    """Transcribe once and return one report row."""
    vad_parameters = VAD_PROFILES[vad_profile]
    started = time.perf_counter()
    try:
        result = await engine.transcribe(
            pcm,
            language=language,
            beam_size=beam_size,
            vad_filter=vad_parameters is not None,
            vad_parameters=vad_parameters,
        )
    except TranscriptionError as exc:
        elapsed = time.perf_counter() - started
        return {
            "model": model,
            "beam_size": beam_size,
            "vad_profile": vad_profile,
            "language_requested": language,
            "error": f"{exc.kind}: {exc.message}",
            "processing_seconds": round(elapsed, 3),
        }

    elapsed = time.perf_counter() - started
    after_vad = result.duration_after_vad_seconds
    removed = (
        None
        if after_vad is None
        else max(0.0, result.duration_seconds - after_vad)
    )
    audio_seconds = result.duration_seconds or 0.0
    return {
        "model": model,
        "beam_size": beam_size,
        "vad_profile": vad_profile,
        "vad_parameters": vad_parameters,
        "language_requested": language,
        "detected_language": result.language,
        "language_probability": round(result.language_probability, 4),
        "audio_seconds": round(audio_seconds, 3),
        "duration_after_vad_seconds": (
            None if after_vad is None else round(after_vad, 3)
        ),
        "speech_removed_seconds": (
            None if removed is None else round(removed, 3)
        ),
        "processing_seconds": round(elapsed, 3),
        "realtime_factor": (
            round(elapsed / audio_seconds, 3) if audio_seconds else None
        ),
        "segment_count": result.segment_count,
        "text_chars": len(result.text),
        "script": _script(result.text),
        "text": result.text,
    }


def _print_row(row: dict[str, object]) -> None:
    if "error" in row:
        print(
            f"  {row['model']:>5} beam={row['beam_size']} "
            f"vad={row['vad_profile']:<7} lang={row['language_requested']:<4} "
            f"ERROR {row['error']}",
            flush=True,
        )
        return
    print(
        f"  {row['model']:>5} beam={row['beam_size']} "
        f"vad={row['vad_profile']:<7} req={row['language_requested']:<4} "
        f"det={row['detected_language']}({row['language_probability']:.2f}) "
        f"audio={row['audio_seconds']:.2f}s proc={row['processing_seconds']:.2f}s "
        f"rtf={row['realtime_factor']} chars={row['text_chars']} "
        f"script={row['script']} removed={row['speech_removed_seconds']}",
        flush=True,
    )
    if row["text"]:
        print(f"       text: {str(row['text'])[:160]}", flush=True)


async def _benchmark(args: argparse.Namespace) -> int:
    files = _discover(args)
    if not files:
        print("No WAV files found to benchmark.", file=sys.stderr)
        return 1

    pcm_by_file: dict[str, bytes] = {}
    file_meta: list[dict[str, object]] = []
    for path in files:
        try:
            pcm = _load_pcm(path)
        except (OSError, ValueError, wave.Error) as exc:
            print(f"Skipping {path.name}: {exc}", file=sys.stderr)
            continue
        pcm_by_file[path.name] = pcm
        file_meta.append(
            {
                "name": path.name,
                "path": str(path),
                "bytes": path.stat().st_size,
                "pcm_seconds": round(len(pcm) / 2 / 16_000, 3),
            }
        )
    if not pcm_by_file:
        print("Every WAV file failed to load.", file=sys.stderr)
        return 1

    report: dict[str, object] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "device": "cpu",
        "compute_type": "int8",
        "cpu_threads": args.threads,
        "models": args.models,
        "beams": args.beams,
        "vad_profiles": args.vad,
        "vad_profile_definitions": VAD_PROFILES,
        "excluded": args.exclude,
        "files": file_meta,
        "runs": [],
        "memory": {},
        "notes": (
            "Text is stored only in this local report. The distorted capture "
            "is excluded by default. Ground-truth transcripts were not "
            "available, so accuracy is judged from the text and script."
        ),
    }
    runs: list[dict[str, object]] = report["runs"]  # type: ignore[assignment]
    memories: dict[str, object] = report["memory"]  # type: ignore[assignment]

    for model in args.models:
        print(f"\n=== Loading {model} ===", flush=True)
        engine = FasterWhisperEngine(
            model=model,
            cpu_threads=args.threads,
            language="auto",
            on_status=_status_printer(model),
        )
        load_started = time.perf_counter()
        try:
            await engine.load()
        except TranscriptionError as exc:
            print(f"{model}: {exc.kind}: {exc.message}", file=sys.stderr)
            continue
        load_seconds = time.perf_counter() - load_started
        memories[f"{model}_after_load"] = _memory_snapshot()
        print(f"{model} loaded in {load_seconds:.2f}s", flush=True)

        # Warm the lazy decoder paths so the first measured run is fair.
        await engine.transcribe(
            bytes(2 * 16_000),
            language=None,
            beam_size=1,
            vad_filter=False,
        )

        for vad_profile in args.vad:
            for beam_size in args.beams:
                print(
                    f"\n--- {model} beam={beam_size} vad={vad_profile} ---",
                    flush=True,
                )
                for name, pcm in pcm_by_file.items():
                    row = await _run_once(
                        engine,
                        pcm,
                        model=model,
                        beam_size=beam_size,
                        vad_profile=vad_profile,
                        language="auto",
                    )
                    row["file"] = name
                    row["load_seconds"] = round(load_seconds, 3)
                    runs.append(row)
                    _print_row(row)

        if not args.no_overrides:
            print(
                f"\n--- {model} explicit en/hi overrides "
                f"(beam={args.override_beam}, vad=off) ---",
                flush=True,
            )
            for name, pcm in pcm_by_file.items():
                for language in ("en", "hi"):
                    row = await _run_once(
                        engine,
                        pcm,
                        model=model,
                        beam_size=args.override_beam,
                        vad_profile="off",
                        language=language,
                    )
                    row["file"] = name
                    row["load_seconds"] = round(load_seconds, 3)
                    runs.append(row)
                    _print_row(row)

        memories[f"{model}_after_runs"] = _memory_snapshot()
        await engine.close()
        del engine
        gc.collect()

    output = args.output or _default_output()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nReport written to {output}", flush=True)
    print(f"Runs recorded: {len(runs)}", flush=True)
    for label, snapshot in memories.items():
        if snapshot is None:
            print(f"memory {label}: not measurable on this platform")
        else:
            print(
                f"memory {label}: working_set="
                f"{snapshot['working_set_mib']} MiB peak="
                f"{snapshot['peak_working_set_mib']} MiB"
            )
    return 0


def main() -> int:
    # Devanagari output must never crash a cp1252 console.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    args = _build_parser().parse_args()
    if args.threads < 0:
        print("--threads must be zero or positive", file=sys.stderr)
        return 2
    if any(beam < 1 for beam in args.beams):
        print("--beams values must be positive", file=sys.stderr)
        return 2
    return asyncio.run(_benchmark(args))


if __name__ == "__main__":
    raise SystemExit(main())
