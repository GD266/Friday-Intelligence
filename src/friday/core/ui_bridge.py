"""Thread-safe bridge between the asyncio core and Qt UI actions."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Protocol
from uuid import uuid4

from PySide6.QtCore import QObject, Signal


class UIBridge(Protocol):
    """The UI operations the core may await."""

    async def confirm(
        self, tool: str, description: str, args: str
    ) -> bool:
        """Ask the user to approve one tool call."""
        ...

    async def read_clipboard_text(self) -> str | None:
        """Read clipboard text on the UI thread, or None when unavailable."""
        ...

    def deny_pending(self) -> None:
        """Resolve every pending confirmation to Deny."""
        ...


class DenyingUIBridge:
    """Safe fallback when no UI bridge has been attached."""

    async def confirm(
        self, tool: str, description: str, args: str
    ) -> bool:
        return False

    async def read_clipboard_text(self) -> str | None:
        return None

    def deny_pending(self) -> None:
        """No-op: this bridge never has pending requests."""
        return None


class QtUIBridge(QObject):
    """Qt bridge that never touches widgets or the clipboard off-thread.

    Confirmation requests use the core's ``confirm_requested`` signal.  The
    clipboard request is emitted on this object; the main window connects it
    to a slot that reads ``QApplication.clipboard()`` on the UI thread.
    Both responses return to the waiting asyncio loop through
    ``loop.call_soon_threadsafe``.
    """

    clipboard_requested = Signal(str)

    def __init__(
        self,
        confirm_requested_signal: Any,
        parent: QObject | None = None,
        *,
        clipboard_timeout_seconds: float = 5.0,
    ) -> None:
        super().__init__(parent)
        self._confirm_signal = confirm_requested_signal
        self._confirm_pending: dict[
            str, tuple[asyncio.AbstractEventLoop, asyncio.Future[bool]]
        ] = {}
        self._clipboard_pending: dict[
            str, tuple[asyncio.AbstractEventLoop, asyncio.Future[str | None]]
        ] = {}
        self._lock = threading.Lock()
        self._closing = False
        self._clipboard_timeout_seconds = clipboard_timeout_seconds

    async def confirm(
        self, tool: str, description: str, args: str
    ) -> bool:
        """Emit a confirmation request and await the UI response."""
        if self._closing:
            return False
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        request_id = uuid4().hex
        with self._lock:
            self._confirm_pending[request_id] = (loop, future)
        try:
            self._confirm_signal.emit(
                request_id, tool, description, args
            )
            return bool(await future)
        finally:
            with self._lock:
                self._confirm_pending.pop(request_id, None)

    async def read_clipboard_text(self) -> str | None:
        """Ask the UI thread for clipboard text and await the result."""
        if self._closing:
            return None
        loop = asyncio.get_running_loop()
        future: asyncio.Future[str | None] = loop.create_future()
        request_id = uuid4().hex
        with self._lock:
            self._clipboard_pending[request_id] = (loop, future)
        try:
            self.clipboard_requested.emit(request_id)
            try:
                return await asyncio.wait_for(
                    future, timeout=self._clipboard_timeout_seconds
                )
            except asyncio.TimeoutError:
                return None
        finally:
            with self._lock:
                self._clipboard_pending.pop(request_id, None)

    def resolve_confirm(self, request_id: str, approved: bool) -> None:
        """Resolve a pending confirmation from the UI thread."""
        with self._lock:
            pending = self._confirm_pending.pop(request_id, None)
        if pending is None:
            return
        loop, future = pending
        self._set_result(loop, future, approved)

    def resolve_clipboard(
        self, request_id: str, text: str | None
    ) -> None:
        """Resolve a pending clipboard read from the UI thread."""
        with self._lock:
            pending = self._clipboard_pending.pop(request_id, None)
        if pending is None:
            return
        loop, future = pending
        self._set_result(loop, future, text)

    def deny_pending(self) -> None:
        """Deny every pending confirmation request."""
        with self._lock:
            confirm_pending = list(self._confirm_pending.values())
            self._confirm_pending.clear()
        for loop, future in confirm_pending:
            self._set_result(loop, future, False)

    def cancel_pending(self) -> None:
        """Deny confirmations and resolve clipboard reads to None."""
        with self._lock:
            confirm_pending = list(self._confirm_pending.values())
            clipboard_pending = list(self._clipboard_pending.values())
            self._confirm_pending.clear()
            self._clipboard_pending.clear()
        for loop, future in confirm_pending:
            self._set_result(loop, future, False)
        for loop, future in clipboard_pending:
            self._set_result(loop, future, None)

    def shutdown(self) -> None:
        """Deny or cancel everything and refuse new bridge requests."""
        self._closing = True
        self.cancel_pending()

    @staticmethod
    def _set_result(
        loop: asyncio.AbstractEventLoop,
        future: asyncio.Future[Any],
        value: Any,
    ) -> None:
        def apply() -> None:
            if not future.done():
                future.set_result(value)

        try:
            loop.call_soon_threadsafe(apply)
        except RuntimeError:
            # The core loop is already closed.
            return


__all__ = [
    "DenyingUIBridge",
    "QtUIBridge",
    "UIBridge",
]
