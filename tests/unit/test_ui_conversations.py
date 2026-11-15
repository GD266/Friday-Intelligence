"""Offscreen tests for conversation rendering in the main window."""

from datetime import datetime, timezone

from PySide6.QtWidgets import QApplication

from friday.core.service import CoreService
from friday.memory.conversations import (
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    Conversation,
    StoredMessage,
)
from friday.ui.main_window import MainWindow


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def test_conversation_list_shows_title_and_relative_time(
    qt_app: QApplication,
) -> None:
    window = MainWindow(CoreService())
    try:
        conversation = Conversation(
            id=1,
            title="Shopping list",
            created_at=_timestamp(),
            updated_at=_timestamp(),
        )
        window._on_conversations_loaded([conversation])

        assert window._conversation_list.count() == 1
        text = window._conversation_list.item(0).text()
        assert "Shopping list" in text
        assert "just now" in text
    finally:
        window.close()
        window.deleteLater()


def test_opened_conversation_marks_incomplete_assistant_reply(
    qt_app: QApplication,
) -> None:
    window = MainWindow(CoreService())
    try:
        now = _timestamp()
        messages = [
            StoredMessage(
                id=1,
                conversation_id=7,
                role="user",
                content="hello",
                status=STATUS_COMPLETE,
                created_at=now,
            ),
            StoredMessage(
                id=2,
                conversation_id=7,
                role="assistant",
                content="partial answer",
                status=STATUS_INCOMPLETE,
                created_at=now,
            ),
        ]
        window._on_conversation_opened(7, messages)

        transcript = window._transcript.toPlainText()
        assert "You: hello" in transcript
        assert "FRIDAY: partial answer" in transcript
        assert "(incomplete)" in transcript
        assert window._current_conversation_id == 7
    finally:
        window.close()
        window.deleteLater()


def test_new_conversation_clears_transcript(qt_app: QApplication) -> None:
    window = MainWindow(CoreService())
    try:
        window._append_user("old message")
        window._on_conversation_opened(0, [])
        assert window._transcript.toPlainText() == ""
        assert window._current_conversation_id == 0
    finally:
        window.close()
        window.deleteLater()
