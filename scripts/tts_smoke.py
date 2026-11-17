#!/usr/bin/env python
"""Manual TTS smoke test.

Usage:
    python scripts/tts_smoke.py [--play]

Manual only; never run by pytest.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from friday.config.settings import load_settings
from friday.voice import available_engines, create_engine
from friday.voice.errors import GatewayError

TEST_TEXT = "FRIDAY voice check, one two three."


async def main() -> int:
    parser = argparse.ArgumentParser(description="TTS smoke test")
    parser.add_argument(
        "--play",
        action="store_true",
        help="Play audio through Qt player",
    )
    parser.add_argument(
        "--engine",
        choices=["edge", "windows"],
        help="Override engine from config",
    )
    parser.add_argument("--voice", help="Override voice name from config")
    parser.add_argument("--rate", type=int, help="Override rate percent from config")
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

    voice_name = args.voice or settings.voice.voice_name
    rate = args.rate if args.rate is not None else settings.voice.rate_percent

    print(f"Engine: {engine_name}")
    print(f"Voice: {voice_name or '(default)'}")
    print(f"Rate: {rate}%")
    print(f"Play: {args.play}")

    if not args.play:
        # Just test synthesis to file
        engine = None
        try:
            engine = create_engine(engine_name)
            display_voice = voice_name or "(engine default)"
            print(f"Synthesis: using voice '{display_voice}'")
            start = time.perf_counter()
            result = await engine.synthesize(
                TEST_TEXT, voice_name or "", settings.voice.rate_percent
            )
            elapsed = time.perf_counter() - start
            size = os.path.getsize(result.audio_path)
            display_voice = voice_name or "(default)"
            msg = (
                f"OK: engine={engine_name} voice={display_voice} "
                f"bytes={size} time={elapsed:.2f}s format={result.format} "
                f"path={result.audio_path}"
            )
            print(msg)
            # Clean up
            try:
                os.unlink(result.audio_path)
            except OSError:
                pass
            return 0
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        finally:
            if engine:
                await engine.close()

    # Play mode - use AudioPlayer
    try:
        from PySide6.QtCore import QEventLoop, QTimer
        from PySide6.QtWidgets import QApplication

        from friday.ui.audio_player import AudioPlayer

        app = QApplication.instance() or QApplication([])
        assert app is not None

        engine = None
        try:
            engine = create_engine(engine_name)
            display_voice = voice_name or "(engine default)"
            print(f"Synthesis: using voice '{display_voice}'")
            start = time.perf_counter()
            result = await engine.synthesize(
                TEST_TEXT, voice_name or "", settings.voice.rate_percent
            )
            elapsed = time.perf_counter() - start
            size = os.path.getsize(result.audio_path)
            display_voice = voice_name or "(default)"
            msg = (
                f"OK: engine={engine_name} voice={display_voice} "
                f"bytes={size} time={elapsed:.2f}s format={result.format} "
                f"path={result.audio_path}"
            )
            print(msg)

            # Play using AudioPlayer. Qt needs its own event loop to advance
            # QMediaPlayer; the asyncio loop does not pump Qt events, so the
            # old asyncio.Event wait always timed out on a real desktop.
            player = AudioPlayer()
            request_id = "smoke-test-1"
            qt_loop = QEventLoop()
            outcome = {"finished": False, "error": "", "timeout": False}

            def on_finished(req_id: str) -> None:
                if req_id == request_id:
                    outcome["finished"] = True
                    qt_loop.quit()

            def on_error(req_id: str, kind: str, message: str) -> None:
                if req_id == request_id:
                    outcome["error"] = f"{kind}: {message}"
                    qt_loop.quit()

            def on_timeout() -> None:
                outcome["timeout"] = True
                qt_loop.quit()

            player.play_finished.connect(on_finished)
            player.play_error.connect(on_error)
            QTimer.singleShot(30_000, on_timeout)
            player.play(result.audio_path, request_id)
            qt_loop.exec()
            player.stop()

            if outcome["timeout"]:
                print("Error: Playback timed out", file=sys.stderr)
                return 1
            if outcome["error"]:
                print(
                    f"Playback error: {outcome['error']}", file=sys.stderr
                )
                return 1
            if not outcome["finished"]:
                print(
                    "Error: Playback ended without a result",
                    file=sys.stderr,
                )
                return 1

            print("OK: played 1 sentence(s)")
            return 0

        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        finally:
            if engine:
                await engine.close()

    except GatewayError as exc:
        print(f"{exc.kind}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
