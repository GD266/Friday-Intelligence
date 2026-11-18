"""Offscreen tests for voice-input feedback and text insertion.

Recognition only fills the editable message box; these tests assert that
the text is never submitted automatically.
"""

# PySide6 must load after pydantic is fully initialised: shiboken's import
# hook breaks pydantic's lazy imports on this interpreter.
# ruff: noqa: I001

from __future__ import annotations

import inspect

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from friday.core.service import CoreService
from friday.ui.main_window import MainWindow
from friday.ui.voice_input import (
    VOICE_COMPLETED,
    VOICE_ERROR,
    VOICE_IDLE,
    VOICE_PROCESSING,
    VOICE_RECORDING,
    VoiceInputResult,
)


def _result(text: str = "Hello Friday") -> VoiceInputResult:
    return VoiceInputResult(
        text=text,
        language="en",
        language_probability=0.93,
        duration_seconds=1.5,
        duration_after_vad_seconds=1.4,
        segment_count=1,
        captured_seconds=1.6,
        peak=0.5,
        rms_dbfs=-18.0,
    )


def _window() -> MainWindow:
    return MainWindow(CoreService())


def test_voice_result_fills_input_without_sending(
    qt_app: QApplication,
) -> None:
    window = _window()
    try:
        sent: list[str] = []
        window._core.chat_send = lambda text: sent.append(text)

        window._on_voice_result(_result())

        assert window._input.toPlainText() == "Hello Friday"
        assert sent == []
        assert "edit and send" in window._output_label.text()
    finally:
        window.close()
        window.deleteLater()


def test_voice_result_appends_to_existing_text(
    qt_app: QApplication,
) -> None:
    window = _window()
    try:
        window._input.setPlainText("Draft message")

        window._on_voice_result(_result("and more words"))

        assert window._input.toPlainText() == "Draft message and more words"
    finally:
        window.close()
        window.deleteLater()


def test_voice_state_updates_visible_feedback(
    qt_app: QApplication,
) -> None:
    window = _window()
    try:
        window._on_voice_state_changed(VOICE_RECORDING)
        assert "listening" in window._voice_status_label.text()
        assert window._voice_button.text() == "Stop & transcribe"

        window._on_voice_state_changed(VOICE_PROCESSING)
        assert "transcribing" in window._voice_status_label.text()
        assert window._voice_button.text() == "Cancel transcription"

        window._on_voice_state_changed(VOICE_COMPLETED)
        assert "ready" in window._voice_status_label.text()

        window._on_voice_state_changed(VOICE_ERROR)
        assert "error" in window._voice_status_label.text()

        window._on_voice_state_changed(VOICE_IDLE)
        assert window._voice_status_label.text() == "Voice: idle"
        assert window._voice_button.text() == "Record voice"
    finally:
        window.close()
        window.deleteLater()


def test_voice_failure_is_visible_and_keeps_input_untouched(
    qt_app: QApplication,
) -> None:
    window = _window()
    try:
        window._input.setPlainText("keep me")

        window._on_voice_failed("ModelLoadError", "The model is unavailable.")

        assert window._input.toPlainText() == "keep me"
        transcript = window._transcript.toPlainText()
        assert "Error [ModelLoadError]" in transcript
        assert "model is unavailable" in transcript
    finally:
        window.close()
        window.deleteLater()


def test_microphone_button_waits_for_the_core(
    qt_app: QApplication,
) -> None:
    window = _window()
    try:
        assert window._voice_button.isEnabled() is False
        window._on_core_started()
        assert window._voice_button.isEnabled() is True
    finally:
        window.close()
        window.deleteLater()


class _WindowRecorder(QObject):
    """Recorder stand-in that records the order of the start sequence."""

    recording_started = Signal()
    level = Signal(float)
    recording_finished = Signal(bytes, float, float, float)
    recording_error = Signal(str, str)

    def __init__(self, order: list[str]) -> None:
        super().__init__()
        self._order = order
        self.start_calls = 0
        self.cancel_calls = 0

    def start(self) -> None:
        self.start_calls += 1
        self._order.append("recorder.start")

    def stop(self) -> None:
        pass

    def cancel(self) -> None:
        self.cancel_calls += 1


def test_record_click_silences_speech_in_order(
    qt_app: QApplication,
) -> None:
    window = _window()
    try:
        order: list[str] = []
        recorder = _WindowRecorder(order)
        window._voice_input._recorder = recorder
        window._core._running = True
        window._core.set_microphone_active = (
            lambda active: order.append(f"gate:{active}")
        )
        window._core.stop_speaking = lambda: order.append("stop_speaking")
        window._audio_player.stop = lambda: order.append("player.stop")
        window._speak_checkbox.setChecked(True)

        window._on_voice_clicked()

        assert order == [
            "gate:True",
            "stop_speaking",
            "player.stop",
            "recorder.start",
        ]
        assert recorder.start_calls == 1
        assert window._speak_checkbox.isChecked() is True
    finally:
        window._voice_input.cancel()
        window.close()
        window.deleteLater()


def test_voice_result_cancel_and_error_never_send(
    qt_app: QApplication,
) -> None:
    window = _window()
    try:
        sent: list[str] = []
        send_clicks: list[int] = []
        window._core.chat_send = lambda text: sent.append(text)
        window._on_send_clicked = lambda: send_clicks.append(1)

        window._on_voice_result(_result())
        assert window._input.toPlainText() == "Hello Friday"

        recorder = _WindowRecorder([])
        window._voice_input._recorder = recorder
        window._core._running = True
        window._voice_input.start()
        window._voice_input.cancel()

        window._on_voice_failed("ModelLoadError", "The model is unavailable.")

        assert sent == []
        assert send_clicks == []
    finally:
        window._voice_input.dispose()
        window.close()
        window.deleteLater()


def test_voice_insertion_source_has_no_send_symbol() -> None:
    source = inspect.getsource(MainWindow._on_voice_result)
    source += inspect.getsource(MainWindow._insert_voice_text)

    assert "chat_send" not in source
    assert "_on_send_clicked" not in source
    assert "send_button" not in source


@pytest.mark.parametrize(
    "end_state",
    [VOICE_PROCESSING, VOICE_IDLE, VOICE_COMPLETED, VOICE_ERROR],
)
def test_level_label_has_no_stale_listening_after_ending(
    qt_app: QApplication, end_state: str
) -> None:
    window = _window()
    try:
        window._voice_input._set_state(VOICE_RECORDING)
        window._on_voice_level(0.42)
        assert "42%" in window._voice_status_label.text()

        window._voice_input._set_state(end_state)

        after_ending = window._voice_status_label.text()

        window._on_voice_level(0.77)

        assert window._voice_status_label.text() == after_ending
        assert "listening" not in window._voice_status_label.text().lower()
        assert "77%" not in window._voice_status_label.text()
    finally:
        window.close()
        window.deleteLater()
