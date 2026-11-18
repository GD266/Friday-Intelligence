"""Offscreen tests for voice-input feedback and text insertion.

Recognition only fills the editable message box; these tests assert that
the text is never submitted automatically.
"""

# PySide6 must load after pydantic is fully initialised: shiboken's import
# hook breaks pydantic's lazy imports on this interpreter.
# ruff: noqa: I001

from __future__ import annotations

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
