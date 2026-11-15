"""Queue-based TTS playback pipeline with pipelining (no Qt dependencies)."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from friday.core.ui_bridge import UIBridge
from friday.voice.tts.base import SynthesisResult, TTSEngine


@dataclass
class SpeechTask:
    """A single speech synthesis + playback task."""

    text: str
    voice: str
    rate_percent: int
    engine_name: str


class SpeechQueue:
    """
    Queue-based TTS playback with pipelining.

    - Synthesizes sentence N+1 while sentence N plays
    - Ordered playback guaranteed
    - stop() clears queue, cancels in-flight synthesis, stops player
    - New reply replaces the queue

    Callbacks (all called on the core thread):
    - on_started(): playback started
    - on_finished(): queue fully drained
    - on_error(kind, message): synthesis or playback error
    - on_notice(message): non-error notification (e.g., privacy skip)
    """

    def __init__(
        self,
        engine_factory: Callable[[str], "TTSEngine"],
        bridge: UIBridge,
        *,
        tmp_dir: str = "",
        on_started: Callable[[], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
        on_notice: Callable[[str], None] | None = None,
    ) -> None:
        self._engine_factory = engine_factory
        self._bridge = bridge
        self._tmp_dir = (
            Path(tmp_dir) if tmp_dir else Path(tempfile.gettempdir()) / "friday_tts"
        )
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

        self._queue: asyncio.Queue[SpeechTask] = asyncio.Queue()
        self._current_task: SpeechTask | None = None
        self._next_task: SpeechTask | None = None
        self._synthesis_task: asyncio.Task | None = None
        self._playback_task: asyncio.Task | None = None
        self._stopped = False

        # Callbacks
        self._on_started = on_started
        self._on_finished = on_finished
        self._on_error = on_error
        self._on_notice = on_notice

        # Purge temp dir on startup
        self._purge_tmp_dir()

    def _purge_tmp_dir(self) -> None:
        """Delete all temp files in the TTS temp directory."""
        try:
            for f in self._tmp_dir.glob("friday_tts_*"):
                try:
                    f.unlink()
                except OSError:
                    pass
        except OSError:
            pass

    def enqueue(
        self,
        text: str,
        voice: str,
        rate_percent: int,
        engine_name: str,
    ) -> None:
        """Add a speech task to the queue. Fire-and-forget; errors via on_error."""
        task = SpeechTask(
            text=text,
            voice=voice,
            rate_percent=rate_percent,
            engine_name=engine_name,
        )
        self._queue.put_nowait(task)

    async def stop(self) -> None:
        """Stop playback, clear queue, cancel in-flight synthesis."""
        self._stopped = True
        self._clear_queue()
        await self._cancel_current()

    def _clear_queue(self) -> None:
        """Clear all pending tasks."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _cancel_current(self) -> None:
        """Cancel current synthesis and playback."""
        if self._synthesis_task and not self._synthesis_task.done():
            self._synthesis_task.cancel()
        if self._playback_task and not self._playback_task.done():
            self._playback_task.cancel()
        # Also stop the audio player on UI thread
        try:
            await self._bridge.stop_audio()
        except Exception:
            pass

    async def _process_queue(self) -> None:
        """Main queue processing loop with pipelining."""
        if self._queue.empty():
            return

        # Start synthesis of first task
        task = await self._queue.get()
        self._current_task = task
        self._synthesis_task = asyncio.create_task(self._synthesize_task(task))

        while not self._stopped:
            # Wait for synthesis to complete
            try:
                result = await self._synthesis_task
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._emit_error(type(exc).__name__, str(exc))
                self._synthesis_task = None
                if self._queue.empty():
                    break
                task = await self._queue.get()
                self._current_task = task
                self._synthesis_task = asyncio.create_task(self._synthesize_task(task))
                continue

            # Check if stopped during synthesis
            if self._stopped:
                break

            # Synthesis succeeded
            if self._on_started:
                self._on_started()

            # Start playback and next synthesis in parallel
            self._playback_task = asyncio.create_task(self._play_audio(result))
            self._synthesis_task = None

            # Start next synthesis if available
            if not self._queue.empty() and not self._stopped:
                next_task = await self._queue.get()
                self._next_task = next_task
                self._synthesis_task = asyncio.create_task(
                    self._synthesize_task(next_task)
                )

            # Wait for playback to complete
            try:
                await self._playback_task
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._emit_error(type(exc).__name__, str(exc))

            # Clean up audio file after playback
            try:
                Path(result.audio_path).unlink(missing_ok=True)
            except OSError:
                pass

            # Move to next task
            if self._synthesis_task:
                self._current_task = self._next_task
                self._next_task = None
                try:
                    result = await self._synthesis_task
                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    self._emit_error(type(exc).__name__, str(exc))
                    if self._queue.empty():
                        break
                    task = await self._queue.get()
                    self._current_task = task
                    if self._stopped:
                        break
                    self._synthesis_task = asyncio.create_task(
                        self._synthesize_task(task)
                    )
                    continue

                # Synthesis succeeded
                if self._on_started:
                    self._on_started()

                # Wait for previous playback to finish before starting next
                if self._playback_task:
                    try:
                        await self._playback_task
                    except asyncio.CancelledError:
                        break
                    except Exception as exc:
                        self._emit_error(type(exc).__name__, str(exc))

                try:
                    Path(result.audio_path).unlink(missing_ok=True)
                except OSError:
                    pass

            # Check if more tasks
            if self._queue.empty() and self._synthesis_task is None:
                break

        # All done
        if not self._stopped and self._on_finished:
            self._on_finished()

    async def _synthesize_task(self, task: SpeechTask) -> SynthesisResult:
        """Synthesize a single task's text."""
        engine = self._engine_factory(task.engine_name)
        try:
            result = await engine.synthesize(
                task.text, task.voice, task.rate_percent
            )
            return result
        finally:
            await engine.close()

    async def _play_audio(self, result: SynthesisResult) -> None:
        """Play audio file using the UI bridge."""
        await self._bridge.play_audio(result.audio_path)

    def _emit_error(self, kind: str, message: str) -> None:
        """Emit error via callback."""
        if self._on_error:
            self._on_error(kind, message)

    def _emit_notice(self, message: str) -> None:
        """Emit notice via callback."""
        if self._on_notice:
            self._on_notice(message)


__all__ = ["SpeechQueue", "SpeechTask"]
