#!/usr/bin/env python
"""Manual microphone smoke test (never run by pytest).

Usage:
    python scripts/mic_smoke.py --list
    python scripts/mic_smoke.py [--seconds 3] [--device NAME]

Records 16 kHz mono audio, prints level statistics, and saves a WAV under
voice.tmp_dir so it can be played back and deleted manually.
"""

from __future__ import annotations

import argparse
import sys
import time
import wave
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from friday.config.settings import get_default_voice_tmp_dir, load_settings
from friday.ui.audio_recorder import AudioRecorder


class _StopAfterStart:
    """Arm one stop timer only after recording has actually started."""

    def __init__(
        self,
        *,
        seconds: float,
        stop: Callable[[], None],
        schedule: Callable[[int, Callable[[], None]], None],
    ) -> None:
        self._delay_ms = max(0, int(seconds * 1000))
        self._stop = stop
        self._schedule = schedule
        self._armed = False
        self._stopped = False

    def on_recording_started(self) -> None:
        if self._armed:
            return
        self._armed = True
        self._schedule(self._delay_ms, self._stop_once)

    def _stop_once(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._stop()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Microphone smoke test")
    parser.add_argument(
        "--list", action="store_true", help="List input devices and exit"
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=3.0,
        help="Recording length in seconds (default: 3)",
    )
    parser.add_argument(
        "--device",
        metavar="NAME",
        default="",
        help="Input device name substring (overrides voice.input_device)",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    app = QApplication.instance() or QApplication([])
    assert app is not None

    if args.list:
        devices = AudioRecorder.list_devices()
        if not devices:
            print("NoInputDevice: no microphone input devices were found.")
            return 1
        for index, (name, is_default) in enumerate(devices):
            marker = " (default)" if is_default else ""
            print(f"{index}: {name}{marker}")
        return 0

    try:
        settings = load_settings()
    except Exception as exc:
        print(f"ConfigError: {exc}", file=sys.stderr)
        return 1

    voice = settings.voice
    seconds = max(0.1, min(args.seconds, float(voice.max_record_seconds)))
    recorder = AudioRecorder(
        input_device=args.device or voice.input_device,
        max_record_seconds=float(voice.max_record_seconds),
        min_record_seconds=float(voice.min_record_seconds),
        silence_peak_threshold=float(voice.silence_peak_threshold),
    )

    loop = QEventLoop()
    outcome: dict[str, object] = {
        "finished": False,
        "error_kind": "",
        "error_message": "",
        "timed_out": False,
    }

    def on_finished(
        pcm: bytes, duration: float, peak: float, rms_dbfs: float
    ) -> None:
        outcome["finished"] = True
        outcome["pcm"] = pcm
        outcome["duration"] = duration
        outcome["peak"] = peak
        outcome["rms_dbfs"] = rms_dbfs
        loop.quit()

    def on_error(kind: str, message: str) -> None:
        outcome["error_kind"] = kind
        outcome["error_message"] = message
        loop.quit()

    def on_timeout() -> None:
        outcome["timed_out"] = True
        loop.quit()

    stop_after_start = _StopAfterStart(
        seconds=seconds,
        stop=recorder.stop,
        schedule=QTimer.singleShot,
    )
    recorder.recording_finished.connect(on_finished)
    recorder.recording_error.connect(on_error)
    recorder.recording_started.connect(
        stop_after_start.on_recording_started
    )

    QTimer.singleShot(0, recorder.start)
    QTimer.singleShot(int((seconds + 10) * 1000), on_timeout)
    loop.exec()

    if outcome["timed_out"]:
        print(
            "RecordingError: timed out waiting for the microphone.",
            file=sys.stderr,
        )
        recorder.cancel()
        return 1
    if outcome["error_kind"]:
        print(
            f"{outcome['error_kind']}: {outcome['error_message']}",
            file=sys.stderr,
        )
        recorder.cancel()
        return 1
    if not outcome["finished"]:
        print("RecordingError: no audio result.", file=sys.stderr)
        recorder.cancel()
        return 1

    pcm = outcome["pcm"]
    assert isinstance(pcm, bytes)
    tmp_dir = (
        Path(voice.tmp_dir)
        if voice.tmp_dir
        else Path(get_default_voice_tmp_dir())
    )
    tmp_dir.mkdir(parents=True, exist_ok=True)
    wav_path = tmp_dir / f"friday_mic_{int(time.time() * 1000)}.wav"
    with wave.open(str(wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16_000)
        wav_file.writeframes(pcm)

    print(
        f"device: {recorder.device_name}\n"
        f"format: {recorder.format_description}\n"
        f"raw bytes: {recorder.last_raw_bytes}\n"
        f"duration: {outcome['duration']:.2f} s\n"
        f"peak: {outcome['peak']:.4f}\n"
        f"rms_dbfs: {outcome['rms_dbfs']:.1f}\n"
        f"converted bytes: {len(pcm)}\n"
        f"wav: {wav_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
