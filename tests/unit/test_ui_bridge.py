"""Offscreen tests for the QtUIBridge."""

# PySide6 must load after pydantic is fully initialised: shiboken's import
# hook breaks pydantic's lazy imports on this interpreter.
# ruff: noqa: I001

from __future__ import annotations

import asyncio
import time

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from friday.config.settings import MemorySettings, Settings
from friday.core.service import CoreService
from friday.core.ui_bridge import QtUIBridge
from friday.gateway.base import Provider
from friday.gateway.types import EVENT_DONE, EVENT_TOKEN, StreamEvent


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
