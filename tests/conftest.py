"""Shared pytest fixtures."""

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
