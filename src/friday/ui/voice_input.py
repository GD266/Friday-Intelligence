"""Voice-input orchestration between the recorder and speech-to-text.

The :class:`AudioRecorder` must live on the Qt UI thread, while model
loading and transcription run on the core asyncio thread (see
:mod:`friday.core.service`).  This controller owns the small state machine
that joins the two and exposes it to the UI through Qt signals:

    idle -> recording -> processing -> completed
                              \\-> error

Recording failures, transcription failures and cancellation all return to
``idle`` or ``error`` with no partial audio or stale result left behind.
Recognized text is delivered to the UI for editing; this module never
submits it to the chat pipeline.  Audio and recognized text are never
logged here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from PySide6.QtCore import QObject, Signal

from friday.core.logging import get_logger
from friday.ui.audio_recorder import AudioRecorder
from friday.voice.stt.base import TranscriptionResult

logger = get_logger(__name__)

VOICE_IDLE = "idle"
VOICE_RECORDING = "recording"
VOICE_PROCESSING = "processing"
VOICE_COMPLETED = "completed"
VOICE_ERROR = "error"

VOICE_STATES = (
    VOICE_IDLE,
    VOICE_RECORDING,
    VOICE_PROCESSING,
    VOICE_COMPLETED,
    VOICE_ERROR,
)

EMPTY_TRANSCRIPT_KIND = "EmptyTranscript"
CORE_NOT_RUNNING_KIND = "CoreNotRunning"


@dataclass(frozen=True, slots=True)
class VoiceInputResult:
    """Recognized text plus transcription and capture metadata."""

    text: str
    language: str
    language_probability: float
    duration_seconds: float
    duration_after_vad_seconds: float | None
    segment_count: int
    captured_seconds: float
    peak: float
    rms_dbfs: float

    @classmethod
    def from_transcription(
        cls,
        result: TranscriptionResult,
        *,
        captured_seconds: float,
        peak: float,
        rms_dbfs: float,
    ) -> "VoiceInputResult":
        return cls(
            text=result.text,
            language=result.language,
            language_probability=result.language_probability,
            duration_seconds=result.duration_seconds,
            duration_after_vad_seconds=result.duration_after_vad_seconds,
            segment_count=result.segment_count,
            captured_seconds=captured_seconds,
            peak=peak,
            rms_dbfs=rms_dbfs,
        )


class RecorderLike(Protocol):
    """The recorder surface the controller consumes."""

    recording_started: Any
    level: Any
    recording_finished: Any
    recording_error: Any

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    def cancel(self) -> None:
        ...


class VoiceCoreLike(Protocol):
    """The core-service surface the controller consumes."""

    @property
    def is_running(self) -> bool:
        ...

    @property
    def signals(self) -> Any:
        ...

    def transcribe_voice(self, pcm: bytes) -> None:
        ...

    def cancel_voice_input(self) -> None:
        ...


def _noop() -> None:
    """Default recording hook."""


class VoiceInputController(QObject):
    """Drive one recording/transcription attempt at a time.

    Signals:
        state_changed(str): one of ``VOICE_STATES``.
        result_ready(object): a :class:`VoiceInputResult` on success.
        failed(str, str): typed error kind and a user-facing message.
        progress(str): model-loading/transcription progress while busy.
        notice(str): non-error status such as cancellation.
        level_changed(float): microphone peak while recording, 0..1.
    """

    state_changed = Signal(str)
    result_ready = Signal(object)
    failed = Signal(str, str)
    progress = Signal(str)
    notice = Signal(str)
    level_changed = Signal(float)

    def __init__(
        self,
        core: VoiceCoreLike,
        *,
        recorder_factory: Callable[[], RecorderLike] | None = None,
        before_record: Callable[[], None] | None = None,
        after_record: Callable[[], None] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._core = core
        self._recorder_factory = recorder_factory or AudioRecorder
        self._before_record = before_record or _noop
        self._after_record = after_record or _noop
        self._record_hook_active = False
        self._recorder: RecorderLike | None = None
        self._state = VOICE_IDLE
        self._capture_meta: tuple[float, float, float] | None = None

        signals = core.signals
        signals.voice_result.connect(self._on_transcription_result)
        signals.voice_error.connect(self._on_transcription_error)
        signals.voice_cancelled.connect(self._on_transcription_cancelled)
        signals.voice_progress.connect(self._on_transcription_progress)

    @property
    def state(self) -> str:
        """Return the current voice-input state."""
        return self._state

    @property
    def is_busy(self) -> bool:
        """Return True while recording or transcribing."""
        return self._state in (VOICE_RECORDING, VOICE_PROCESSING)

    def start(self) -> bool:
        """Start a new recording; ignored while one is already active."""
        if self._state in (VOICE_RECORDING, VOICE_PROCESSING):
            return False
        if not self._core.is_running:
            self._fail(
                CORE_NOT_RUNNING_KIND,
                "Voice input is unavailable while FRIDAY is stopped.",
            )
            return False

        self._capture_meta = None
        recorder = self._ensure_recorder()
        # Capture this before the gate closes speech so the log records what
        # Aria was doing when Record was pressed.
        speech_active = bool(getattr(self._core, "speech_active", False))
        self._set_state(VOICE_RECORDING)
        self._record_hook_active = True
        try:
            self._before_record()
        except Exception:
            logger.exception("before_record hook failed")
        try:
            recorder.start()
        except Exception as exc:
            logger.info(
                "record_start: speech_active=%s result=failed",
                "true" if speech_active else "false",
            )
            self._fail(type(exc).__name__, str(exc))
            return False
        logger.info(
            "record_start: speech_active=%s",
            "true" if speech_active else "false",
        )
        return self._state == VOICE_RECORDING

    def stop(self) -> None:
        """Stop recording and hand the audio to the core for transcription."""
        if self._state != VOICE_RECORDING:
            return
        recorder = self._recorder
        if recorder is None:  # pragma: no cover - start() creates it
            self._fail("RecordingError", "The recorder is not available.")
            return
        try:
            recorder.stop()
        except Exception as exc:
            self._fail(type(exc).__name__, str(exc))
            return
        # The recorder closes the device synchronously before returning, so
        # the gate must not stay closed if no terminal signal arrives.
        self._notify_after_record()

    def toggle(self) -> None:
        """Handle the single microphone button."""
        if self._state == VOICE_RECORDING:
            self.stop()
        elif self._state == VOICE_PROCESSING:
            self.cancel()
        else:
            self.start()

    def cancel(self) -> None:
        """Discard a recording or abandon an in-flight transcription."""
        if self._state == VOICE_RECORDING:
            recorder = self._recorder
            if recorder is not None:
                try:
                    recorder.cancel()
                except Exception:
                    logger.debug("recording cancel failed", exc_info=True)
            self._capture_meta = None
            self._notify_after_record()
            self._set_state(VOICE_IDLE)
            self.notice.emit("Voice recording discarded.")
            return

        if self._state == VOICE_PROCESSING:
            # Move to idle first: a late result/error/cancel signal from the
            # core must not revive a cancelled attempt.
            self._capture_meta = None
            self._set_state(VOICE_IDLE)
            try:
                self._core.cancel_voice_input()
            except Exception:
                logger.debug("voice transcription cancel failed", exc_info=True)
            self.notice.emit("Voice transcription cancelled.")
            return

        if self._state in (VOICE_COMPLETED, VOICE_ERROR):
            self._set_state(VOICE_IDLE)

    def dispose(self) -> None:
        """Release the recorder on window close without emitting results."""
        recorder = self._recorder
        if self._state == VOICE_RECORDING and recorder is not None:
            try:
                recorder.cancel()
            except Exception:
                logger.debug("recording dispose failed", exc_info=True)
        self._capture_meta = None
        self._notify_after_record()
        self._state = VOICE_IDLE

    # ------------------------------------------------------------------
    # Recorder callbacks (UI thread)
    # ------------------------------------------------------------------
    def _ensure_recorder(self) -> RecorderLike:
        if self._recorder is not None:
            return self._recorder
        recorder = self._recorder_factory()
        recorder.recording_started.connect(self._on_recording_started)
        recorder.level.connect(self._on_level)
        recorder.recording_finished.connect(self._on_recording_finished)
        recorder.recording_error.connect(self._on_recording_error)
        self._recorder = recorder
        return recorder

    def _on_recording_started(self) -> None:
        if self._state == VOICE_RECORDING:
            self.progress.emit("Listening...")

    def _on_level(self, level: float) -> None:
        if self._state == VOICE_RECORDING:
            self.level_changed.emit(float(level))

    def _on_recording_finished(
        self,
        pcm: bytes,
        duration_seconds: float,
        peak: float,
        rms_dbfs: float,
    ) -> None:
        if self._state != VOICE_RECORDING:
            return
        if not pcm:
            self._fail(
                "EmptyAudio",
                "The recording is empty; nothing was captured.",
            )
            return

        self._capture_meta = (duration_seconds, peak, rms_dbfs)
        self._notify_after_record()
        self._set_state(VOICE_PROCESSING)
        self.progress.emit("Transcribing speech...")
        try:
            self._core.transcribe_voice(pcm)
        except Exception as exc:
            self._fail(type(exc).__name__, str(exc))

    def _on_recording_error(self, kind: str, message: str) -> None:
        if self._state != VOICE_RECORDING:
            return
        self._fail(kind, message)

    # ------------------------------------------------------------------
    # Core transcription callbacks (delivered through Qt signals)
    # ------------------------------------------------------------------
    def _on_transcription_result(self, result: object) -> None:
        if self._state != VOICE_PROCESSING:
            return
        if not isinstance(result, TranscriptionResult):
            self._fail(
                "MalformedTranscription",
                "The transcription service returned an unexpected result.",
            )
            return
        text = result.text.strip()
        if not text:
            self._fail(
                EMPTY_TRANSCRIPT_KIND,
                "No speech was recognized. Try again and speak clearly.",
            )
            return

        captured, peak, rms_dbfs = self._capture_meta or (0.0, 0.0, 0.0)
        voice_result = VoiceInputResult.from_transcription(
            result,
            captured_seconds=captured,
            peak=peak,
            rms_dbfs=rms_dbfs,
        )
        self._capture_meta = None
        self._set_state(VOICE_COMPLETED)
        self.result_ready.emit(voice_result)
        logger.info(
            "voice_input_result: language=%s language_prob=%.3f "
            "audio_s=%.2f captured_s=%.2f chars=%d segments=%d",
            result.language or "-",
            result.language_probability,
            result.duration_seconds,
            captured,
            len(text),
            result.segment_count,
        )

    def _on_transcription_error(self, kind: str, message: str) -> None:
        if self._state != VOICE_PROCESSING:
            return
        self._fail(kind, message)

    def _on_transcription_cancelled(self) -> None:
        if self._state != VOICE_PROCESSING:
            return
        self._capture_meta = None
        self._set_state(VOICE_IDLE)
        self.notice.emit("Voice transcription cancelled.")

    def _on_transcription_progress(self, message: str) -> None:
        if self._state == VOICE_PROCESSING:
            self.progress.emit(message)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def _set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self.state_changed.emit(state)

    def _notify_after_record(self) -> None:
        """Close the microphone gate once per started recording."""
        if not self._record_hook_active:
            return
        self._record_hook_active = False
        try:
            self._after_record()
        except Exception:
            logger.exception("after_record hook failed")

    def _fail(self, kind: str, message: str) -> None:
        self._capture_meta = None
        self._notify_after_record()
        self._set_state(VOICE_ERROR)
        self.failed.emit(kind, message)


__all__ = [
    "EMPTY_TRANSCRIPT_KIND",
    "VOICE_COMPLETED",
    "VOICE_ERROR",
    "VOICE_IDLE",
    "VOICE_PROCESSING",
    "VOICE_RECORDING",
    "VOICE_STATES",
    "VoiceInputController",
    "VoiceInputResult",
]
