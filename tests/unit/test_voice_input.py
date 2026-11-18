"""Voice-input orchestration tests with fake recorder and core.

The fake recorder mirrors ``AudioRecorder``'s signals; the fake core mirrors
the ``CoreService`` voice methods and signals.  No microphone or model is
touched, and recognized text never enters the chat pipeline.
"""

# PySide6 must load after pydantic is fully initialised: shiboken's import
# hook breaks pydantic's lazy imports on this interpreter.
# ruff: noqa: I001

from __future__ import annotations

import logging

import pytest
from PySide6.QtCore import QObject, Signal

from friday.ui.voice_input import (
    EMPTY_TRANSCRIPT_KIND,
    VOICE_COMPLETED,
    VOICE_ERROR,
    VOICE_IDLE,
    VOICE_PROCESSING,
    VOICE_RECORDING,
    VOICE_STATES,
    VoiceInputController,
    VoiceInputResult,
)
from friday.voice.stt.base import TranscriptionResult

PCM = b"\x00\x01" * 800


class FakeCoreSignals(QObject):
    voice_result = Signal(object)
    voice_error = Signal(str, str)
    voice_cancelled = Signal()
    voice_progress = Signal(str)


class FakeCore:
    """Records requests; the test emits the core signals itself."""

    def __init__(self, *, running: bool = True) -> None:
        self.signals = FakeCoreSignals()
        self.is_running = running
        self.pcm: list[bytes] = []
        self.cancel_calls = 0

    def transcribe_voice(self, pcm: bytes) -> None:
        self.pcm.append(bytes(pcm))

    def cancel_voice_input(self) -> None:
        self.cancel_calls += 1


class FakeRecorder(QObject):
    """Signal-compatible stand-in for :class:`AudioRecorder`."""

    recording_started = Signal()
    level = Signal(float)
    recording_finished = Signal(bytes, float, float, float)
    recording_error = Signal(str, str)

    def __init__(
        self,
        *,
        pcm: bytes = PCM,
        error_on_start: tuple[str, str] | None = None,
        error_on_stop: tuple[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.pcm = pcm
        self.error_on_start = error_on_start
        self.error_on_stop = error_on_stop
        self.start_calls = 0
        self.stop_calls = 0
        self.cancel_calls = 0

    def start(self) -> None:
        self.start_calls += 1
        if self.error_on_start is not None:
            self.recording_error.emit(*self.error_on_start)
            return
        self.recording_started.emit()

    def stop(self) -> None:
        self.stop_calls += 1
        if self.error_on_stop is not None:
            self.recording_error.emit(*self.error_on_stop)
            return
        self.recording_finished.emit(self.pcm, 1.25, 0.5, -18.0)

    def cancel(self) -> None:
        self.cancel_calls += 1


def _result(
    text: str = "Hello Friday",
    *,
    language: str = "en",
    probability: float = 0.93,
) -> TranscriptionResult:
    return TranscriptionResult(
        text=text,
        language=language,
        language_probability=probability,
        duration_seconds=1.25,
        duration_after_vad_seconds=1.1,
        segment_count=2,
    )


def _controller(
    *,
    running: bool = True,
    recorder: FakeRecorder | None = None,
) -> tuple[VoiceInputController, FakeCore, FakeRecorder]:
    core = FakeCore(running=running)
    rec = recorder or FakeRecorder()
    controller = VoiceInputController(
        core, recorder_factory=lambda: rec
    )
    return controller, core, rec


def test_public_state_names_are_stable() -> None:
    assert VOICE_STATES == (
        "idle",
        "recording",
        "processing",
        "completed",
        "error",
    )


def test_start_records_and_ignores_overlapping_start() -> None:
    controller, core, recorder = _controller()
    states: list[str] = []
    controller.state_changed.connect(states.append)

    assert controller.start() is True
    assert controller.start() is False

    assert states == [VOICE_RECORDING]
    assert recorder.start_calls == 1
    assert core.pcm == []


def test_stop_transcribes_then_delivers_metadata() -> None:
    controller, core, recorder = _controller()
    states: list[str] = []
    levels: list[float] = []
    results: list[VoiceInputResult] = []
    controller.state_changed.connect(states.append)
    controller.level_changed.connect(levels.append)
    controller.result_ready.connect(results.append)

    controller.start()
    recorder.level.emit(0.25)
    controller.stop()

    assert core.pcm == [PCM]
    assert states == [VOICE_RECORDING, VOICE_PROCESSING]
    assert levels == [0.25]

    core.signals.voice_result.emit(_result())

    assert states[-1] == VOICE_COMPLETED
    assert len(results) == 1
    result = results[0]
    assert result.text == "Hello Friday"
    assert result.language == "en"
    assert result.language_probability == 0.93
    assert result.duration_seconds == 1.25
    assert result.duration_after_vad_seconds == 1.1
    assert result.segment_count == 2
    assert result.captured_seconds == 1.25
    assert result.peak == 0.5
    assert result.rms_dbfs == -18.0


def test_start_while_not_recording_is_ignored() -> None:
    controller, core, recorder = _controller()
    controller.stop()
    assert recorder.stop_calls == 0
    assert core.pcm == []
    assert controller.state == VOICE_IDLE


def test_recording_start_error_enters_error_and_allows_retry() -> None:
    recorder = FakeRecorder(
        error_on_start=("NoInputDevice", "No microphone was found.")
    )
    controller, core, recorder = _controller(recorder=recorder)
    states: list[str] = []
    failures: list[tuple[str, str]] = []
    controller.state_changed.connect(states.append)
    controller.failed.connect(lambda kind, msg: failures.append((kind, msg)))

    assert controller.start() is False
    assert states == [VOICE_RECORDING, VOICE_ERROR]
    assert failures == [("NoInputDevice", "No microphone was found.")]
    assert core.pcm == []

    recorder.error_on_start = None
    assert controller.start() is True
    assert controller.state == VOICE_RECORDING
    assert recorder.start_calls == 2


def test_stop_error_reports_and_never_transcribes() -> None:
    recorder = FakeRecorder(
        error_on_stop=("RecordingTooShort", "Recording too short.")
    )
    controller, core, _ = _controller(recorder=recorder)
    failures: list[tuple[str, str]] = []
    controller.failed.connect(lambda kind, msg: failures.append((kind, msg)))

    controller.start()
    controller.stop()

    assert controller.state == VOICE_ERROR
    assert failures == [("RecordingTooShort", "Recording too short.")]
    assert core.pcm == []


def test_empty_audio_never_reaches_the_core() -> None:
    recorder = FakeRecorder(pcm=b"")
    controller, core, _ = _controller(recorder=recorder)
    failures: list[tuple[str, str]] = []
    controller.failed.connect(lambda kind, msg: failures.append((kind, msg)))

    controller.start()
    controller.stop()

    assert controller.state == VOICE_ERROR
    assert failures[0][0] == "EmptyAudio"
    assert core.pcm == []


def test_transcription_error_enters_error() -> None:
    controller, core, _ = _controller()
    failures: list[tuple[str, str]] = []
    controller.failed.connect(lambda kind, msg: failures.append((kind, msg)))

    controller.start()
    controller.stop()
    core.signals.voice_error.emit("ModelLoadError", "Could not load model.")

    assert controller.state == VOICE_ERROR
    assert failures == [("ModelLoadError", "Could not load model.")]


def test_empty_transcript_is_an_error_not_an_insertion() -> None:
    controller, core, _ = _controller()
    results: list[VoiceInputResult] = []
    failures: list[tuple[str, str]] = []
    controller.result_ready.connect(results.append)
    controller.failed.connect(lambda kind, msg: failures.append((kind, msg)))

    controller.start()
    controller.stop()
    core.signals.voice_result.emit(_result("   "))

    assert controller.state == VOICE_ERROR
    assert failures[0][0] == EMPTY_TRANSCRIPT_KIND
    assert results == []


def test_cancel_while_recording_discards_without_transcribing() -> None:
    controller, core, recorder = _controller()
    notices: list[str] = []
    controller.notice.connect(notices.append)

    controller.start()
    controller.cancel()

    assert recorder.cancel_calls == 1
    assert controller.state == VOICE_IDLE
    assert core.pcm == []
    assert notices == ["Voice recording discarded."]


def test_cancel_while_processing_ignores_late_result() -> None:
    controller, core, _ = _controller()
    results: list[VoiceInputResult] = []
    notices: list[str] = []
    controller.result_ready.connect(results.append)
    controller.notice.connect(notices.append)

    controller.start()
    controller.stop()
    controller.cancel()

    assert core.cancel_calls == 1
    assert controller.state == VOICE_IDLE

    core.signals.voice_result.emit(_result("too late"))
    core.signals.voice_error.emit("LateError", "too late")

    assert controller.state == VOICE_IDLE
    assert results == []
    assert notices == ["Voice transcription cancelled."]


def test_core_cancellation_returns_to_idle() -> None:
    controller, core, _ = _controller()
    notices: list[str] = []
    controller.notice.connect(notices.append)

    controller.start()
    controller.stop()
    core.signals.voice_cancelled.emit()

    assert controller.state == VOICE_IDLE
    assert notices == ["Voice transcription cancelled."]


def test_repeated_attempts_reset_cleanly() -> None:
    controller, core, recorder = _controller()
    states: list[str] = []
    results: list[VoiceInputResult] = []
    controller.state_changed.connect(states.append)
    controller.result_ready.connect(results.append)

    for index in range(2):
        controller.start()
        controller.stop()
        core.signals.voice_result.emit(_result(f"attempt {index}"))

    assert recorder.start_calls == 2
    assert len(core.pcm) == 2
    assert [item.text for item in results] == ["attempt 0", "attempt 1"]
    assert states == [
        VOICE_RECORDING,
        VOICE_PROCESSING,
        VOICE_COMPLETED,
        VOICE_RECORDING,
        VOICE_PROCESSING,
        VOICE_COMPLETED,
    ]


def test_busy_start_while_processing_is_ignored() -> None:
    controller, core, recorder = _controller()
    controller.start()
    controller.stop()

    assert controller.start() is False
    assert recorder.start_calls == 1
    assert len(core.pcm) == 1
    assert controller.state == VOICE_PROCESSING


def test_core_not_running_is_a_visible_error() -> None:
    controller, _, recorder = _controller(running=False)
    failures: list[tuple[str, str]] = []
    controller.failed.connect(lambda kind, msg: failures.append((kind, msg)))

    assert controller.start() is False
    assert recorder.start_calls == 0
    assert controller.state == VOICE_ERROR
    assert failures[0][0] == "CoreNotRunning"


def test_progress_only_forwards_while_active() -> None:
    controller, core, _ = _controller()
    progress: list[str] = []
    controller.progress.connect(progress.append)

    core.signals.voice_progress.emit("ignored while idle")
    assert progress == []

    controller.start()
    controller.stop()
    core.signals.voice_progress.emit("Loading model...")

    assert progress[-1] == "Loading model..."


def test_dispose_while_recording_cancels_without_terminal_signals() -> None:
    controller, core, recorder = _controller()
    results: list[VoiceInputResult] = []
    failures: list[tuple[str, str]] = []
    controller.result_ready.connect(results.append)
    controller.failed.connect(lambda kind, msg: failures.append((kind, msg)))

    controller.start()
    controller.dispose()

    assert recorder.cancel_calls == 1
    assert controller.state == VOICE_IDLE
    assert results == []
    assert failures == []
    assert core.pcm == []


class _OrderRecorder(FakeRecorder):
    """Recorder that records when its start() actually runs."""

    def __init__(self, order: list[str], **kwargs) -> None:
        super().__init__(**kwargs)
        self._order = order

    def start(self) -> None:
        self._order.append("recorder.start")
        super().start()


def test_start_calls_before_record_once_before_recorder_start() -> None:
    order: list[str] = []
    recorder = _OrderRecorder(order)
    controller = VoiceInputController(
        FakeCore(),
        recorder_factory=lambda: recorder,
        before_record=lambda: order.append("before_record"),
    )

    assert controller.start() is True

    assert order == ["before_record", "recorder.start"]
    assert controller.state == VOICE_RECORDING


def test_before_record_is_not_called_twice_or_while_busy() -> None:
    calls: list[int] = []
    controller = VoiceInputController(
        FakeCore(),
        recorder_factory=FakeRecorder,
        before_record=lambda: calls.append(1),
    )

    assert controller.start() is True
    assert controller.start() is False
    assert calls == [1]

    controller.stop()
    assert controller.start() is False
    assert calls == [1]


def test_before_record_is_not_called_when_core_is_stopped() -> None:
    calls: list[int] = []
    recorder = FakeRecorder()
    controller = VoiceInputController(
        FakeCore(running=False),
        recorder_factory=lambda: recorder,
        before_record=lambda: calls.append(1),
    )

    assert controller.start() is False
    assert calls == []
    assert recorder.start_calls == 0


def test_before_record_failure_still_starts_recording() -> None:
    recorder = FakeRecorder()
    controller = VoiceInputController(
        FakeCore(),
        recorder_factory=lambda: recorder,
        before_record=lambda: (_ for _ in ()).throw(RuntimeError("hook boom")),
    )

    assert controller.start() is True
    assert recorder.start_calls == 1
    assert controller.state == VOICE_RECORDING


@pytest.mark.parametrize(
    "ending",
    ["finished", "empty", "cancel", "error", "dispose"],
)
def test_after_record_closes_the_gate_on_every_ending(ending: str) -> None:
    gate = {"active": False}
    after_calls: list[int] = []

    def _open_gate() -> None:
        gate["active"] = True

    def _close_gate() -> None:
        gate["active"] = False
        after_calls.append(1)

    recorder = FakeRecorder(
        pcm=b"" if ending == "empty" else PCM,
        error_on_stop=(
            ("RecordingTooShort", "Recording too short.")
            if ending == "error"
            else None
        ),
    )
    controller = VoiceInputController(
        FakeCore(),
        recorder_factory=lambda: recorder,
        before_record=_open_gate,
        after_record=_close_gate,
    )

    controller.start()
    assert gate["active"] is True

    if ending in ("finished", "empty", "error"):
        controller.stop()
    elif ending == "cancel":
        controller.cancel()
    else:
        controller.dispose()

    assert gate["active"] is False
    assert after_calls == [1]


def test_after_record_is_not_called_when_recording_never_started() -> None:
    after_calls: list[int] = []
    controller = VoiceInputController(
        FakeCore(running=False),
        recorder_factory=FakeRecorder,
        after_record=lambda: after_calls.append(1),
    )

    assert controller.start() is False
    controller.cancel()
    controller.dispose()

    assert after_calls == []


def test_late_level_after_stop_is_ignored() -> None:
    controller, core, recorder = _controller()
    levels: list[float] = []
    controller.level_changed.connect(levels.append)

    controller.start()
    recorder.level.emit(0.3)
    controller.stop()
    recorder.level.emit(0.9)

    assert levels == [0.3]


def test_record_start_logs_speech_active_without_text(caplog) -> None:
    core = FakeCore()
    core.speech_active = True
    recorder = FakeRecorder()
    controller = VoiceInputController(
        core,
        recorder_factory=lambda: recorder,
    )

    with caplog.at_level(logging.INFO, logger="friday.ui.voice_input"):
        controller.start()

    assert "record_start: speech_active=true" in caplog.text
    assert "Hello Friday" not in caplog.text

