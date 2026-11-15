"""Offscreen tests for memory and search UI integration."""

import time

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from friday.config.settings import MemorySettings, Settings
from friday.core.service import CoreService
from friday.gateway.base import Provider
from friday.gateway.types import EVENT_DONE, EVENT_TOKEN, StreamEvent
from friday.memory.conversations import Conversation
from friday.memory.facts import Fact
from friday.memory.search import SearchResult
from friday.ui.main_window import MainWindow
from friday.ui.memory_dialog import MemoryDialog


class RecordingProvider(Provider):
    def __init__(self) -> None:
        self.calls = []

    async def stream_chat(self, messages):
        self.calls.append(list(messages))
        yield StreamEvent(EVENT_TOKEN, "ok")
        yield StreamEvent(EVENT_DONE)


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


def _fact(fact_id: int, content: str) -> Fact:
    now = "2026-01-01T00:00:00+00:00"
    return Fact(
        id=fact_id,
        content=content,
        source="user",
        created_at=now,
        updated_at=now,
    )


def test_status_line_reports_facts_used(qt_app: QApplication) -> None:
    window = MainWindow(CoreService())
    try:
        window._on_facts_used(3)
        assert window._facts_status_label.text() == "Using 3 facts"
    finally:
        window.close()
        window.deleteLater()


def test_search_results_render_snippets_and_clearing_restores_list(
    qt_app: QApplication,
) -> None:
    window = MainWindow(CoreService())
    try:
        conversation = Conversation(
            id=7,
            title="Pets",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        window._on_conversations_loaded([conversation])
        window._search_box.setText("cats")
        window._on_search_results(
            [
                SearchResult(
                    conversation_id=7,
                    conversation_title="Pets",
                    message_id=3,
                    role="user",
                    snippet="my cats like fish",
                    created_at="2026-01-01T00:00:00+00:00",
                )
            ]
        )

        assert window._search_active
        assert window._conversation_list.count() == 1
        text = window._conversation_list.item(0).text()
        assert "Pets" in text
        assert "my cats like fish" in text
        assert (
            window._conversation_list.item(0).data(
                Qt.ItemDataRole.UserRole
            )
            == 7
        )

        window._search_box.clear()
        assert not window._search_active
        assert window._conversation_list.count() == 1
        assert "Pets" in window._conversation_list.item(0).text()
        assert "my cats like fish" not in window._conversation_list.item(0).text()
    finally:
        window.close()
        window.deleteLater()


def test_memory_dialog_shows_count_and_facts(
    qt_app: QApplication,
) -> None:
    core = CoreService()
    dialog = MemoryDialog(core, [_fact(1, "I like tea")])
    try:
        assert dialog._list.count() == 1
        assert "1 fact" in dialog._count_label.text()
        assert "I like tea" in dialog._list.item(0).text()
    finally:
        dialog.close()
        dialog.deleteLater()


def test_slash_commands_show_confirmations_without_calling_provider(
    qt_app: QApplication, tmp_path
) -> None:
    provider = RecordingProvider()
    settings = Settings(
        memory=MemorySettings(db_path=str(tmp_path / "friday.db"))
    )
    core = CoreService(provider=provider, settings=settings)
    facts_loaded = QSignalSpy(core.signals.facts_loaded)
    window = MainWindow(core)
    core.start()

    try:
        assert wait_until(lambda: facts_loaded.count() >= 1)

        window._input.setPlainText("/remember I like tea")
        window._on_send_clicked()
        assert wait_until(
            lambda: "Remembered fact 1: I like tea"
            in window._transcript.toPlainText()
        )
        assert provider.calls == []

        window._input.setPlainText("/facts")
        window._on_send_clicked()
        assert wait_until(
            lambda: "Facts (1):" in window._transcript.toPlainText()
        )
        assert provider.calls == []

        window._input.setPlainText("/forget 1")
        window._on_send_clicked()
        assert wait_until(
            lambda: "Forgot fact 1" in window._transcript.toPlainText()
        )
        assert provider.calls == []
    finally:
        core.stop()
        window.close()
        window.deleteLater()
