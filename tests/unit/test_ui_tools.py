"""Offscreen tests for the Tools dialog."""

from __future__ import annotations

import time

from PySide6.QtWidgets import QApplication

from friday.core.service import CoreService
from friday.gateway.base import Provider
from friday.gateway.types import EVENT_DONE, EVENT_TOKEN, StreamEvent
from friday.tools.audit import ToolAuditEntry
from friday.tools.registry import ToolInfo
from friday.ui.tools_dialog import ToolsDialog


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return predicate()


class DummyProvider(Provider):
    async def stream_chat(self, messages):
        yield StreamEvent(EVENT_TOKEN, "ok")
        yield StreamEvent(EVENT_DONE)


def test_tools_dialog_lists_registered_tools(qt_app: QApplication) -> None:
    core = CoreService(provider=DummyProvider())
    core.start()

    try:
        dialog = ToolsDialog(core)
        wait_until(lambda: dialog._tools_list.count() == 3)
        names = [dialog._tools_list.item(i).text() for i in range(3)]
        assert "get_time" in names[0]
        assert "open_app" in names[1]
        assert "read_clipboard" in names[2]
    finally:
        core.stop()


def test_tools_dialog_shows_recent_audit_rows(qt_app: QApplication) -> None:
    core = CoreService(provider=DummyProvider())
    core.start()

    try:
        # Add audit rows via the core thread
        def add_rows():
            from friday.tools.audit import ToolAuditRepository

            repo = ToolAuditRepository(core._database)
            repo.record(
                conversation_id=None,
                tool="get_time",
                args_json="{}",
                permission="SAFE",
                decision="auto",
                status="ok",
                error_kind=None,
                duration_ms=5,
            )
            repo.record(
                conversation_id=1,
                tool="read_clipboard",
                args_json="{}",
                permission="SENSITIVE",
                decision="approved",
                status="ok",
                error_kind=None,
                duration_ms=12,
            )

        core._loop.call_soon_threadsafe(add_rows)

        dialog = ToolsDialog(core)
        wait_until(lambda: dialog._audit_table.rowCount() == 2)

        row_0_tool = dialog._audit_table.item(0, 1).text()
        row_1_tool = dialog._audit_table.item(1, 1).text()
        # Newest first
        assert row_0_tool == "read_clipboard"
        assert row_1_tool == "get_time"
    finally:
        core.stop()


def test_tools_dialog_updates_when_tools_loaded_signal_emitted(
    qt_app: QApplication,
) -> None:
    core = CoreService(provider=DummyProvider())
    core.start()

    try:
        dialog = ToolsDialog(core)
        wait_until(lambda: dialog._tools_list.count() == 3)

        # Simulate tools_loaded signal with custom data
        custom_tools = [
            ToolInfo("custom", "desc", "SAFE", False, False),
        ]
        custom_rows = [
            ToolAuditEntry(1, "2026-01-01T00:00:00+00:00", None, "custom", "{}",
                          "SAFE", "auto", "ok", None, 1),
        ]
        core.signals.tools_loaded.emit(custom_tools, custom_rows)
        wait_until(lambda: dialog._tools_list.count() == 1)
        assert "custom" in dialog._tools_list.item(0).text()
    finally:
        core.stop()
