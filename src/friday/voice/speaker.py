"""Queue-based TTS playback pipeline (no Qt dependencies)."""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from friday.core.logging import get_logger
from friday.core.ui_bridge import UIBridge
from friday.voice.tts.base import SynthesisResult, TTSEngine

logger = get_logger(__name__)

# Default playback timeout in seconds
DEFAULT_PLAYBACK_TIMEOUT = 60.0

# Maximum time stop() waits for the UI to acknowledge an audio stop.
STOP_AUDIO_TIMEOUT = 5.0


@dataclass
class SpeechTask:
    """A single speech synthesis + playback task."""

    text: str
    voice: str
    rate_percent: int
    engine_name: str
    generation: int = 0


class SpeechQueue:
    """
    Queue-based TTS playback.

    - Tasks are synthesized and played in the order they were enqueued
    - stop() clears pending tasks, cancels in-flight work, announces a new
      generation, and leaves the queue ready for the next reply
    - Tasks tagged with an older generation are dropped, never played
    - A reply that has been accepted is either played or reported through
      on_error; it is never silently abandoned

    Callbacks (all called on the core thread):
    - on_started(): playback started
    - on_finished(): queue fully drained
    - on_error(kind, message): synthesis or playback error
    - on_notice(message): non-error notification (e.g., privacy skip)
    """

    def __init__(
        self,
        engine_factory: Callable[[str], "TTSEngine"],
        get_bridge: Callable[[], "UIBridge"],
        *,
        tmp_dir: str = "",
        on_started: Callable[[], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
        on_notice: Callable[[str], None] | None = None,
        playback_timeout: float = DEFAULT_PLAYBACK_TIMEOUT,
    ) -> None:
        self._engine_factory = engine_factory
        self._get_bridge = get_bridge
        self._tmp_dir = (
            Path(tmp_dir) if tmp_dir else Path(tempfile.gettempdir()) / "friday_tts"
        )
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

        self._queue: asyncio.Queue[SpeechTask] = asyncio.Queue()
        self._process_task: asyncio.Task | None = None
        self._generation = 0
        self._playback_timeout = playback_timeout

        # Callbacks
        self._on_started = on_started
        self._on_finished = on_finished
        self._on_error = on_error
        self._on_notice = on_notice

        # Purge temp dir on startup
        self._purge_tmp_dir()

        logger.info(
            "SpeechQueue initialized: playback_timeout=%.1fs", playback_timeout
        )

    @property
    def generation(self) -> int:
        """Return the current generation tag."""
        return self._generation

    @property
    def is_running(self) -> bool:
        """Return True while the queue processor is alive."""
        return self._process_task is not None and not self._process_task.done()

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
            generation=self._generation,
        )
        self._queue.put_nowait(task)
        logger.info(
            "speech_enqueued: len=%d generation=%d queued=%d",
            len(text),
            task.generation,
            self._queue.qsize(),
        )
        try:
            self._ensure_processor()
        except RuntimeError:
            self._emit_error(
                "NoEventLoop",
                "Speech queue requires a running asyncio event loop.",
            )

    def _ensure_processor(self) -> None:
        """Start the queue processor when it is not already running."""
        if self._process_task is None or self._process_task.done():
            self._process_task = asyncio.create_task(self._process_queue())

    async def stop(self) -> None:
        """Stop playback and make the queue ready for the next reply.

        Increments the generation so work tagged with the old generation is
        dropped, clears pending tasks, cancels in-flight synthesis/playback,
        and stops the UI player. The queue stays usable afterwards.
        """
        logger.info("speech_stop_requested")
        self._generation += 1
        generation = self._generation

        pending = self._discard_pending()
        if pending:
            logger.info(
                "speech dropped: stale generation count=%d generation=%d",
                pending,
                generation,
            )

        await self._cancel_current_work()

        process_task = self._process_task
        self._process_task = None
        if process_task is not None and not process_task.done():
            process_task.cancel()
            try:
                await process_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("speech processor failed during stop")

        logger.info("speech_stop_completed: generation=%d", generation)
        # A reply may have been accepted while stop() was awaiting. It must
        # not sit in the queue without a processor.
        if not self._queue.empty():
            self._ensure_processor()

    def _discard_pending(self) -> int:
        """Drop every queued task and return how many were discarded."""
        dropped = 0
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return dropped
            else:
                dropped += 1

    async def _cancel_current_work(self) -> None:
        """Stop the UI player before cancelling the queue processor."""
        logger.info("cancelled: trigger=stop")
        try:
            bridge = self._get_bridge()
            await asyncio.wait_for(
                bridge.stop_audio(), timeout=STOP_AUDIO_TIMEOUT
            )
        except Exception:
            logger.debug("stop_audio failed or timed out", exc_info=True)

    async def wait_idle(self, timeout: float = 10.0) -> None:
        """Wait until the processor has drained the queue (tests/shutdown)."""
        process_task = self._process_task
        if process_task is None or process_task.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(process_task), timeout)
        except asyncio.TimeoutError:
            logger.warning("speech queue did not drain within %.1fs", timeout)

    async def _process_queue(self) -> None:
        """Process accepted tasks in order until the queue is empty."""
        logger.info(
            "queue_task_started: queued=%d generation=%d",
            self._queue.qsize(),
            self._generation,
        )
        try:
            while True:
                task = await self._queue.get()
                try:
                    if task.generation != self._generation:
                        logger.info(
                            "speech dropped: stale generation task=%d current=%d",
                            task.generation,
                            self._generation,
                        )
                        continue
                    await self._run_task(task)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # A bug in the pipeline must still be visible to the UI.
                    logger.exception("speech task failed")
                    self._emit_error(type(exc).__name__, str(exc))
                if self._queue.empty():
                    break
        except asyncio.CancelledError:
            logger.info("cancelled: trigger=stop processor")
            raise
        finally:
            if self._process_task is asyncio.current_task():
                self._process_task = None

        logger.info("queue_task_finished")
        if self._on_finished:
            self._on_finished()

    async def _run_task(self, task: SpeechTask) -> None:
        """Synthesize and play one task, reporting every failure."""
        try:
            result = await self._synthesize(task)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.info(
                "synthesis_error: kind=%s len=%d",
                type(exc).__name__,
                len(task.text),
            )
            self._emit_error(type(exc).__name__, str(exc))
            return

        if task.generation != self._generation:
            logger.info(
                "speech dropped: stale generation task=%d current=%d",
                task.generation,
                self._generation,
            )
            self._remove_audio(result)
            return

        try:
            await self._play(result, task)
        except asyncio.CancelledError:
            raise
        finally:
            self._remove_audio(result)

    async def _synthesize(self, task: SpeechTask) -> SynthesisResult:
        """Synthesize a single task's text."""
        logger.info(
            "synthesis_started: engine=%s len=%d generation=%d",
            task.engine_name,
            len(task.text),
            task.generation,
        )
        engine = self._engine_factory(task.engine_name)
        try:
            result = await engine.synthesize(
                task.text, task.voice, task.rate_percent
            )
        finally:
            await engine.close()
        logger.info(
            "synthesis_done: len=%d generation=%d",
            len(task.text),
            task.generation,
        )
        return result

    async def _play(self, result: SynthesisResult, task: SpeechTask) -> None:
        """Play an audio file through the UI bridge, with a timeout."""
        audio_path = Path(result.audio_path)
        bridge = self._get_bridge()
        if self._on_started:
            self._on_started()
        logger.info(
            "play_requested: generation=%d path=%s", task.generation, audio_path
        )
        try:
            await asyncio.wait_for(
                bridge.play_audio(str(audio_path)),
                timeout=self._playback_timeout,
            )
        except asyncio.CancelledError:
            logger.info("cancelled: trigger=stop playback")
            raise
        except asyncio.TimeoutError:
            logger.info(
                "play_error: kind=PlaybackTimeout timeout=%.1fs",
                self._playback_timeout,
            )
            self._emit_error(
                "PlaybackTimeout",
                f"Playback timed out after {self._playback_timeout:.1f}s",
            )
        except Exception as exc:
            logger.info("play_error: kind=%s", type(exc).__name__)
            self._emit_error(type(exc).__name__, str(exc))
        else:
            logger.info("play_finished: generation=%d", task.generation)

    @staticmethod
    def _remove_audio(result: SynthesisResult) -> None:
        """Delete the synthesized audio file after use."""
        try:
            Path(result.audio_path).unlink(missing_ok=True)
        except OSError:
            pass

    def _emit_error(self, kind: str, message: str) -> None:
        """Emit error via callback."""
        if self._on_error:
            self._on_error(kind, message)

    def _emit_notice(self, message: str) -> None:
        """Emit notice via callback."""
        if self._on_notice:
            self._on_notice(message)


__all__ = ["SpeechQueue", "SpeechTask"]
