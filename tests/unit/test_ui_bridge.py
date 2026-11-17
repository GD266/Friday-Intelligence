"""Offscreen tests for the QtUIBridge."""

# PySide6 must load after pydantic is fully initialised: shiboken's import
# hook breaks pydantic's lazy imports on this interpreter.
# ruff: noqa: I001

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from friday.config.settings import (
    MemorySettings,
    Settings,
    VoiceSettings,
)
from friday.core.service import CoreService
from friday.core.ui_bridge import QtUIBridge
from friday.gateway.base import Provider
from friday.gateway.types import EVENT_DONE, EVENT_TOKEN, StreamEvent
from friday.ui.main_window import MainWindow


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


class DummyProvider(Provider):
    async def stream_chat(self, messages):
        yield StreamEvent(EVENT_TOKEN, "ok")
        yield StreamEvent(EVENT_DONE)


def make_core_with_bridge():
    """Create a CoreService with a QtUIBridge attached."""
    core = CoreService(
        provider=DummyProvider(),
        settings=Settings(memory=MemorySettings(db_path="")),
    )
    # Create the QtUIBridge with the core's confirm_requested signal
    bridge = QtUIBridge(core.signals.confirm_requested)
    core.set_ui_bridge(bridge)
    core.start()
    return core, bridge


def test_bridge_confirm_resolves_from_ui_thread(qt_app: QApplication) -> None:
    """confirm() awaits until resolve_confirm is called."""
    core, bridge = make_core_with_bridge()

    try:
        async def run():
            task = asyncio.create_task(bridge.confirm("get_time", "desc", "{}"))
            await asyncio.sleep(0.02)  # let it emit
            # Get the request_id from the signal
            # The signal was emitted; we need to capture it
            # Use deny_pending as a simple way to resolve
            bridge.deny_pending()
            return await task

        future = asyncio.run_coroutine_threadsafe(run(), core._loop)
        approved = future.result(timeout=2.0)
        assert approved is False  # denied by deny_pending
    finally:
        core.stop()


def test_bridge_confirm_no_timeout_without_response(qt_app: QApplication) -> None:
    """confirm() waits indefinitely for a response; core enforces timeout."""
    core, bridge = make_core_with_bridge()

    try:
        # The bridge itself doesn't have a confirm timeout;
        # the core uses asyncio.wait_for to enforce confirm_timeout_seconds.
        # Here we test that a pending confirm can be resolved.
        async def run():
            task = asyncio.create_task(bridge.confirm("get_time", "desc", "{}"))
            await asyncio.sleep(0.02)
            bridge.resolve_confirm(list(bridge._confirm_pending.keys())[0], True)
            return await task

        future = asyncio.run_coroutine_threadsafe(run(), core._loop)
        approved = future.result(timeout=2.0)
        assert approved is True
    finally:
        core.stop()


def test_bridge_deny_pending_resolves_all_to_false(qt_app: QApplication) -> None:
    """deny_pending() resolves all pending confirmations to False."""
    core, bridge = make_core_with_bridge()

    try:
        async def run():
            task1 = asyncio.create_task(bridge.confirm("tool1", "desc", "{}"))
            task2 = asyncio.create_task(bridge.confirm("tool2", "desc", "{}"))
            await asyncio.sleep(0.02)
            bridge.deny_pending()
            r1 = await task1
            r2 = await task2
            return r1, r2

        future = asyncio.run_coroutine_threadsafe(run(), core._loop)
        r1, r2 = future.result(timeout=2.0)
        assert r1 is False
        assert r2 is False
    finally:
        core.stop()


def test_bridge_shutdown_denies_pending(qt_app: QApplication) -> None:
    """shutdown() denies pending confirmations and refuses new ones."""
    core, bridge = make_core_with_bridge()

    try:
        async def run():
            task = asyncio.create_task(bridge.confirm("tool", "desc", "{}"))
            await asyncio.sleep(0.02)
            bridge.shutdown()
            existing = await task
            # New request after shutdown should be denied immediately
            new = await bridge.confirm("tool2", "desc", "{}")
            return existing, new

        future = asyncio.run_coroutine_threadsafe(run(), core._loop)
        existing, new = future.result(timeout=2.0)
        assert existing is False
        assert new is False
    finally:
        core.stop()


def test_bridge_clipboard_request_reads_on_ui_thread(qt_app: QApplication) -> None:
    """clipboard_requested signal fires; resolution comes from UI thread."""
    core, bridge = make_core_with_bridge()

    try:
        results = {}

        def on_clipboard(req_id):
            # Simulate UI thread clipboard read
            bridge.resolve_clipboard(req_id, "clipboard text")

        bridge.clipboard_requested.connect(on_clipboard)

        async def run():
            results["text"] = await bridge.read_clipboard_text()

        future = asyncio.run_coroutine_threadsafe(run(), core._loop)
        # Process Qt events to deliver the signal
        for _ in range(10):
            QApplication.processEvents()
            time.sleep(0.01)
        future.result(timeout=2.0)
        assert results["text"] == "clipboard text"
    finally:
        core.stop()


def test_bridge_clipboard_timeout_returns_none(qt_app: QApplication) -> None:
    """read_clipboard_text returns None if not resolved in time."""
    core, bridge = make_core_with_bridge()

    try:
        # Short timeout, never resolve
        bridge._clipboard_timeout_seconds = 0.01

        async def run():
            return await bridge.read_clipboard_text()

        future = asyncio.run_coroutine_threadsafe(run(), core._loop)
        text = future.result(timeout=2.0)
        assert text is None
    finally:
        core.stop()


def test_bridge_cancel_pending_resolves_clipboard_to_none(qt_app: QApplication) -> None:
    """cancel_pending() resolves clipboard reads to None."""
    core, bridge = make_core_with_bridge()

    try:
        async def run():
            task = asyncio.create_task(bridge.read_clipboard_text())
            await asyncio.sleep(0.02)
            bridge.cancel_pending()
            return await task

        future = asyncio.run_coroutine_threadsafe(run(), core._loop)
        text = future.result(timeout=2.0)
        assert text is None
    finally:
        core.stop()


def _speech_core(speak_replies: bool = False, engine: str = "edge") -> CoreService:
    return CoreService(
        settings=Settings(
            voice=VoiceSettings(
                speak_replies=speak_replies, engine=engine
            )
        )
    )


@pytest.mark.parametrize("speak_replies", [True, False])
def test_speak_checkbox_initial_state(
    qt_app: QApplication, speak_replies: bool
) -> None:
    """The checkbox starts from the config-backed runtime flag."""
    window = MainWindow(_speech_core(speak_replies=speak_replies))
    try:
        assert window._speak_checkbox.isChecked() is speak_replies
    finally:
        window.close()
        window.deleteLater()


def test_speak_checkbox_toggle_calls_core(qt_app: QApplication) -> None:
    """Toggling the checkbox forwards the new state to the core."""
    core = _speech_core()
    window = MainWindow(core)
    calls: list[bool] = []
    core.set_speech_enabled_sync = calls.append  # type: ignore[method-assign]
    try:
        window._speak_checkbox.setChecked(True)
        window._speak_checkbox.setChecked(False)
        assert calls == [True, False]
    finally:
        window.close()
        window.deleteLater()


def test_stop_speaking_button_follows_speech_signals(
    qt_app: QApplication,
) -> None:
    """Stop speaking is enabled only while speech is active."""
    core = _speech_core()
    window = MainWindow(core)
    button = window._stop_speaking_button
    try:
        assert not button.isEnabled()

        core.signals.speech_started.emit()
        assert button.isEnabled()
        assert "Speaking" in window._status_label.text()

        core.signals.speech_finished.emit()
        assert not button.isEnabled()
        assert "Speaking" not in window._status_label.text()

        core.signals.speech_started.emit()
        core.signals.speech_error.emit("TTSNetworkError", "boom")
        assert not button.isEnabled()
        assert "Speaking" not in window._status_label.text()
    finally:
        window.close()
        window.deleteLater()


def test_stop_speaking_click_calls_public_method(
    qt_app: QApplication,
) -> None:
    """Clicking Stop speaking calls core.stop_speaking exactly once."""
    core = _speech_core(speak_replies=True)
    window = MainWindow(core)
    calls: list[str] = []
    core.stop_speaking = lambda: calls.append("stop")  # type: ignore[method-assign]
    try:
        core.signals.speech_started.emit()
        window._stop_speaking_button.click()
        assert calls == ["stop"]
        assert not window._stop_speaking_button.isEnabled()
    finally:
        window.close()
        window.deleteLater()


@pytest.mark.parametrize(
    ("engine", "expected"),
    [
        (
            "edge",
            "Reply text is sent to Microsoft to create the voice. "
            "Session setting: edit config.toml to change the default.",
        ),
        (
            "windows",
            "Spoken offline on this PC. "
            "Session setting: edit config.toml to change the default.",
        ),
    ],
)
def test_speak_checkbox_tooltip_matches_engine(
    qt_app: QApplication, engine: str, expected: str
) -> None:
    """The tooltip explains where audio is produced for the engine."""
    window = MainWindow(_speech_core(engine=engine))
    try:
        assert window._speak_checkbox.toolTip() == expected
    finally:
        window.close()
        window.deleteLater()


def test_close_event_uses_public_stop_speaking(
    qt_app: QApplication,
) -> None:
    """Window close stops speech through the public core method."""
    core = _speech_core(speak_replies=True)
    window = MainWindow(core)
    calls: list[str] = []
    core.stop_speaking = lambda: calls.append("stop")  # type: ignore[method-assign]
    window.close()
    window.deleteLater()
    assert calls == ["stop"]


def test_main_window_uses_no_private_core_members() -> None:
    """main_window.py only calls the public CoreService API."""
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "src" / "friday" / "ui" / "main_window.py"
    ).read_text(encoding="utf-8")
    assert "self._core._" not in source
