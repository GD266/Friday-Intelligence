"""Queue-based TTS playback pipeline with bounded synthesis prefetch."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from friday.config.settings import get_default_voice_tmp_dir
from friday.core.logging import get_logger
from friday.core.ui_bridge import UIBridge
from friday.voice.tts.base import SynthesisResult, TTSEngine

logger = get_logger(__name__)

# Default playback timeout in seconds
DEFAULT_PLAYBACK_TIMEOUT = 60.0

# Maximum time stop() waits for the UI to acknowledge an audio stop.
STOP_AUDIO_TIMEOUT = 5.0

# Bounded prefetch: clips synthesized but not yet played.
DEFAULT_PREFETCH_SENTENCES = 2
MAX_PREFETCH_SENTENCES = 4

# Sentinels passed from the producer to the consumer over ``_ready``.
_PRODUCER_DONE = object()
_PRODUCER_FAILED = object()


def default_tmp_dir() -> Path:
    """Return the spec TTS temp directory (%LOCALAPPDATA%\\Friday\\tmp\\tts)."""
    return Path(get_default_voice_tmp_dir())


@dataclass
class SpeechTask:
    """A single speech synthesis + playback task."""

    text: str
    voice: str
    rate_percent: int
    engine_name: str
    generation: int = 0
    enqueued_at: float = 0.0


class SpeechQueue:
    """
    Queue-based TTS playback with bounded synthesis prefetch.

    - A synthesis producer runs ahead of a playback consumer
    - Playback stays in enqueue order
    - At most ``prefetch_sentences`` clips are synthesized but not yet played
    - stop() clears pending tasks, cancels producer and consumer, deletes
      unplayed audio files, announces a new generation, and leaves the queue
      ready for the next reply
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
        prefetch_sentences: int = DEFAULT_PREFETCH_SENTENCES,
        on_started: Callable[[], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
        on_notice: Callable[[str], None] | None = None,
        playback_timeout: float = DEFAULT_PLAYBACK_TIMEOUT,
        is_microphone_active: Callable[[], bool] | None = None,
    ) -> None:
        self._engine_factory = engine_factory
        self._get_bridge = get_bridge
        self._is_microphone_active = is_microphone_active or (lambda: False)
        self._tmp_dir = Path(tmp_dir) if tmp_dir else default_tmp_dir()
        self._tmp_dir.mkdir(parents=True, exist_ok=True)

        self._queue: asyncio.Queue[SpeechTask] = asyncio.Queue()
        # Snapshot of the reply currently being processed. Tasks enqueued
        # while it plays (the next reply) stay in ``_queue``.
        self._batch: asyncio.Queue[SpeechTask] = asyncio.Queue()
        self._ready: asyncio.Queue[object] = asyncio.Queue()
        self._slots: asyncio.Semaphore = asyncio.Semaphore(
            self._clamp_prefetch(prefetch_sentences)
        )
        self._prefetch = self._clamp_prefetch(prefetch_sentences)
        self._process_task: asyncio.Task | None = None
        self._producer_task: asyncio.Task | None = None
        self._consumer_task: asyncio.Task | None = None
        self._generation = 0
        self._playback_timeout = playback_timeout
        self._prev_play_finished_at: float | None = None
        self._first_audio_logged = False
        self._reply_failed = False
        self._terminal_emitted = False
        self._episode_active = False

        # Callbacks
        self._on_started = on_started
        self._on_finished = on_finished
        self._on_error = on_error
        self._on_notice = on_notice

        # Purge temp dir on startup
        self._purge_tmp_dir()

        logger.info(
            "SpeechQueue initialized: playback_timeout=%.1fs prefetch=%d",
            playback_timeout,
            self._prefetch,
        )

    @staticmethod
    def _clamp_prefetch(value: int) -> int:
        return max(1, min(MAX_PREFETCH_SENTENCES, int(value)))

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
            enqueued_at=time.perf_counter(),
        )
        self._queue.put_nowait(task)
        if not self._episode_active:
            self._episode_active = True
            self._terminal_emitted = False
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
        dropped, clears pending tasks, cancels the producer and the consumer,
        deletes any synthesized-but-unplayed files, and stops the UI player.
        The queue stays usable afterwards.
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

        await self._cancel_pipeline()
        self._delete_ready_files()
        await self._stop_audio()
        # Every ending path must produce exactly one terminal signal. A stop
        # during playback would otherwise leave the UI stuck on "Speaking…".
        self._emit_finished()

        logger.info("speech_stop_completed: generation=%d", generation)
        # A reply may have been accepted while stop() was awaiting. It must
        # not sit in the queue without a processor.
        if not self._queue.empty():
            self._ensure_processor()

    async def shutdown(self) -> None:
        """Stop work and purge the TTS temp directory (called at exit)."""
        await self.stop()
        self._purge_tmp_dir()

    def _discard_pending(self) -> int:
        """Drop every queued task and return how many were discarded."""
        dropped = 0
        for queue in (self._queue, self._batch):
            while True:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    dropped += 1
        return dropped

    def _delete_ready_files(self) -> None:
        """Delete audio files that were synthesized but never played."""
        deleted = 0
        while True:
            try:
                item = self._ready.get_nowait()
            except asyncio.QueueEmpty:
                break
            if isinstance(item, tuple):
                self._remove_audio(item[1])
                deleted += 1
        if deleted:
            logger.info("speech deleted: unplayed files=%d", deleted)

    async def _cancel_pipeline(self) -> None:
        """Cancel the producer and consumer, then the supervisor."""
        producer = self._producer_task
        consumer = self._consumer_task
        supervisor = self._process_task
        self._producer_task = None
        self._consumer_task = None
        self._process_task = None

        tasks = [
            task
            for task in (producer, consumer, supervisor)
            if task is not None
        ]
        for task in tasks:
            if not task.done():
                task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("speech task failed during stop")

    async def _stop_audio(self) -> None:
        """Tell the UI player to stop (bounded wait)."""
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
        """Supervise one producer/consumer pass per reply batch."""
        logger.info(
            "queue_task_started: queued=%d generation=%d",
            self._queue.qsize(),
            self._generation,
        )
        try:
            while True:
                if self._queue.empty():
                    break
                # Take the reply as it was queued: this task's whole reply is
                # enqueued synchronously, so anything added later belongs to
                # the next reply and must survive a failure here.
                while True:
                    try:
                        self._batch.put_nowait(self._queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                self._ready = asyncio.Queue()
                self._slots = asyncio.Semaphore(self._prefetch)
                self._prev_play_finished_at = None
                self._first_audio_logged = False
                self._reply_failed = False
                self._terminal_emitted = False
                self._episode_active = True
                self._producer_task = asyncio.create_task(self._producer())
                self._consumer_task = asyncio.create_task(self._consumer())
                try:
                    await asyncio.gather(
                        self._producer_task, self._consumer_task
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.exception("speech pipeline failed")
                    self._delete_ready_files()
                    self._emit_error(type(exc).__name__, str(exc))
                finally:
                    self._producer_task = None
                    self._consumer_task = None
                if self._reply_failed:
                    # One terminal signal (speech_error) was already emitted;
                    # the rest of this reply was discarded. The queue stays
                    # usable for the next reply.
                    self._delete_ready_files()
                    logger.info(
                        "speech_reply_stopped: reason=failure remaining=%d",
                        self._queue.qsize(),
                    )
                    break
        except asyncio.CancelledError:
            logger.info("cancelled: trigger=stop processor")
            raise
        finally:
            self._producer_task = None
            self._consumer_task = None
            if self._process_task is asyncio.current_task():
                self._process_task = None

        logger.info("queue_task_finished")
        if not self._queue.empty():
            # Work arrived while the pass was finishing; keep it moving.
            self._ensure_processor()
            return
        self._emit_finished()

    async def _producer(self) -> None:
        """Synthesize ahead of playback, bounded by ``prefetch_sentences``."""
        try:
            while True:
                if self._reply_failed:
                    break
                try:
                    task = self._batch.get_nowait()
                except asyncio.QueueEmpty:
                    break

                if task.generation != self._generation:
                    logger.info(
                        "speech dropped: stale generation task=%d current=%d",
                        task.generation,
                        self._generation,
                    )
                    continue

                await self._slots.acquire()
                if task.generation != self._generation:
                    self._slots.release()
                    logger.info(
                        "speech dropped: stale generation task=%d current=%d",
                        task.generation,
                        self._generation,
                    )
                    continue

                try:
                    result = await self._synthesize(task)
                except asyncio.CancelledError:
                    self._slots.release()
                    raise
                except Exception:
                    self._slots.release()
                    self._delete_ready_files()
                    # One error per failed reply; later sentences are not
                    # synthesized and unplayed files are removed.
                    self._reply_failed = True
                    while True:
                        try:
                            self._batch.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    await self._ready.put(_PRODUCER_FAILED)
                    return

                if task.generation != self._generation:
                    self._slots.release()
                    self._remove_audio(result)
                    logger.info(
                        "speech dropped: stale generation task=%d current=%d",
                        task.generation,
                        self._generation,
                    )
                    continue

                if self._reply_failed:
                    self._slots.release()
                    self._remove_audio(result)
                    break
                await self._ready.put((task, result))

            await self._ready.put(_PRODUCER_DONE)
        except asyncio.CancelledError:
            raise

    async def _consumer(self) -> None:
        """Play synthesized clips in order."""
        try:
            while True:
                item = await self._ready.get()
                if item is _PRODUCER_DONE:
                    break
                if item is _PRODUCER_FAILED:
                    self._delete_ready_files()
                    break
                task, result = item
                # This clip is now playing, so it no longer counts as
                # synthesized-but-unplayed; let the producer advance.
                self._slots.release()

                if task.generation != self._generation:
                    self._remove_audio(result)
                    logger.info(
                        "speech dropped: stale generation task=%d current=%d",
                        task.generation,
                        self._generation,
                    )
                    continue

                await self._play(result, task)
                if self._reply_failed:
                    # Playback failed; later clips must not play.
                    while True:
                        try:
                            self._batch.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    self._delete_ready_files()
                    break
        except asyncio.CancelledError:
            logger.info("cancelled: trigger=stop consumer")
            raise

    async def _synthesize(self, task: SpeechTask) -> SynthesisResult:
        """Synthesize a single task's text and log its duration."""
        logger.info(
            "synthesis_started: engine=%s len=%d generation=%d",
            task.engine_name,
            len(task.text),
            task.generation,
        )
        started = time.perf_counter()
        engine: TTSEngine | None = None
        try:
            engine = self._engine_factory(task.engine_name)
            result = await engine.synthesize(
                task.text, task.voice, task.rate_percent
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            synth_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "synthesis_error: kind=%s len=%d synth_ms=%.1f",
                type(exc).__name__,
                len(task.text),
                synth_ms,
            )
            self._emit_error(type(exc).__name__, str(exc))
            raise
        finally:
            if engine is not None:
                await engine.close()
        synth_ms = (time.perf_counter() - started) * 1000.0
        logger.info(
            "synthesis_done: len=%d generation=%d synth_ms=%.1f",
            len(task.text),
            task.generation,
            synth_ms,
        )
        return result

    async def _play(self, result: SynthesisResult, task: SpeechTask) -> bool:
        """Play one clip; return False when playback failed.

        The microphone gate is checked here, immediately before every play
        request, so a clip synthesized before the microphone opened can never
        start playing into it. The clip is dropped without failing the reply
        and its temp file is removed.
        """
        audio_path = Path(result.audio_path)
        if self._is_microphone_active():
            self._remove_audio(result)
            logger.info(
                "speech dropped: microphone active len=%d",
                len(task.text),
            )
            return True
        bridge = self._get_bridge()
        now = time.perf_counter()
        gap_ms = (
            0.0
            if self._prev_play_finished_at is None
            else (now - self._prev_play_finished_at) * 1000.0
        )
        first_audio_ms: float | None = None
        if not self._first_audio_logged:
            first_audio_ms = (now - task.enqueued_at) * 1000.0
            self._first_audio_logged = True

        if self._on_started:
            self._on_started()
        logger.info(
            "play_requested: generation=%d path=%s", task.generation, audio_path
        )
        if first_audio_ms is not None:
            logger.info("first_audio: first_audio_ms=%.1f", first_audio_ms)

        started = time.perf_counter()
        ok = True
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
            ok = False
        except Exception as exc:
            logger.info("play_error: kind=%s", type(exc).__name__)
            self._emit_error(type(exc).__name__, str(exc))
            ok = False
        else:
            logger.info("play_finished: generation=%d", task.generation)
        finally:
            play_ms = (time.perf_counter() - started) * 1000.0
            self._prev_play_finished_at = time.perf_counter()
            logger.info(
                "play_timing: gap_ms=%.1f play_ms=%.1f", gap_ms, play_ms
            )
            self._remove_audio(result)
        if not ok:
            self._reply_failed = True
        return ok

    @staticmethod
    def _remove_audio(result: SynthesisResult) -> None:
        """Delete the synthesized audio file after use."""
        try:
            Path(result.audio_path).unlink(missing_ok=True)
        except OSError:
            pass

    def _emit_error(self, kind: str, message: str) -> None:
        """Emit the single terminal error signal for this speech episode."""
        if self._terminal_emitted or not self._episode_active:
            return
        self._terminal_emitted = True
        self._episode_active = False
        if self._on_error:
            self._on_error(kind, message)

    def _emit_finished(self) -> None:
        """Emit the single terminal finished signal for this speech episode."""
        if self._terminal_emitted or not self._episode_active:
            return
        self._terminal_emitted = True
        self._episode_active = False
        if self._on_finished:
            self._on_finished()

    def _emit_notice(self, message: str) -> None:
        """Emit notice via callback."""
        if self._on_notice:
            self._on_notice(message)


__all__ = ["SpeechQueue", "SpeechTask", "default_tmp_dir"]
