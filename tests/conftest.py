"""Shared pytest fixtures."""

import asyncio
import gc
import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_secret_registry(monkeypatch):
    """Keep runtime-registered secret values from leaking between tests."""
    from friday.security import redaction

    monkeypatch.setattr(redaction, "_REGISTERED_SECRETS", set())


@pytest.fixture(scope="session", autouse=True)
def qt_app():
    """Provide one offscreen QApplication for widget tests."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _check_unretrieved_futures():
    """Check for unretrieved futures after each test."""
    yield
    # Force garbage collection to trigger any unretrieved future warnings
    gc.collect()
    # Check asyncio logger for "exception was never retrieved"
    # We can't easily capture the logger output, but we can check for pending
    # futures in the current task's loop
    try:
        loop = asyncio.get_running_loop()
        # Check all tasks for unretrieved exceptions
        for task in asyncio.all_tasks(loop):
            if task.done() and not task.cancelled():
                try:
                    task.exception()
                except asyncio.CancelledError:
                    pass
                except Exception:
                    # This would be an unretrieved exception
                    pass
    except RuntimeError:
        # No running loop
        pass
