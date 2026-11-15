"""Tests for core chat orchestration (fake provider, no network)."""

import asyncio
import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from friday.config.settings import MemorySettings, Settings
from friday.core.service import CoreService
from friday.gateway import errors
from friday.gateway.base import Provider
from friday.gateway.types import EVENT_DONE, EVENT_TOKEN, StreamEvent


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


@pytest.fixture
def test_settings(tmp_path):
    return Settings(
        memory=MemorySettings(db_path=str(tmp_path / "friday.db"))
    )


class FakeProvider(Provider):
    """Test double that yields scripted events."""

    def __init__(
        self,
        events: list[StreamEvent] | None = None,
        *,
        error: Exception | None = None,
        token_delay: float = 0.0,
    ) -> None:
        self._events = events or []
        self._error = error
        self._token_delay = token_delay
        self.seen_messages = []

    async def stream_chat(self, messages):
        self.seen_messages = list(messages)
        for event in self._events:
            if self._token_delay:
                await asyncio.sleep(self._token_delay)
            yield event
        if self._error is not None:
            raise self._error


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


def test_successful_chat_updates_history(qapp, test_settings) -> None:
    provider = FakeProvider(
        [
            StreamEvent(EVENT_TOKEN, "Hello"),
            StreamEvent(EVENT_TOKEN, " world"),
            StreamEvent(EVENT_DONE),
        ]
    )
    core = CoreService(provider=provider, settings=test_settings)
    tokens = QSignalSpy(core.signals.token)
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        core.chat_send("hi")

        assert wait_until(lambda: tokens.count() >= 2)
        assert wait_until(lambda: done.count() >= 1)
        assert tokens.at(0)[0] == "Hello"
        assert done.at(0)[0] == "Hello world"

        history = core.history
        assert [message.role for message in history] == ["user", "assistant"]
        assert history[0].content == "hi"
        assert history[1].content == "Hello world"

        assert provider.seen_messages[0].role == "system"
        assert provider.seen_messages[-1].content == "hi"
    finally:
        core.stop()


def test_second_turn_includes_previous_messages(qapp, test_settings) -> None:
    provider = FakeProvider(
        [StreamEvent(EVENT_TOKEN, "ok"), StreamEvent(EVENT_DONE)]
    )
    core = CoreService(provider=provider, settings=test_settings)
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        core.chat_send("first")
        assert wait_until(lambda: done.count() >= 1)

        core.chat_send("second")
        assert wait_until(lambda: done.count() >= 2)

        roles = [message.role for message in provider.seen_messages]
        assert roles == ["system", "user", "assistant", "user"]
        assert provider.seen_messages[-1].content == "second"
    finally:
        core.stop()


def test_failed_stream_keeps_partial_but_not_history(qapp, test_settings) -> None:
    provider = FakeProvider(
        [StreamEvent(EVENT_TOKEN, "partial")],
        error=errors.ServerError("boom"),
    )
    core = CoreService(provider=provider, settings=test_settings)
    tokens = QSignalSpy(core.signals.token)
    chat_errors = QSignalSpy(core.signals.chat_error)
    core.start()

    try:
        core.chat_send("hi")

        assert wait_until(lambda: tokens.count() >= 1)
        assert wait_until(lambda: chat_errors.count() >= 1)
        assert chat_errors.at(0)[0] == "ServerError"
        assert "boom" in chat_errors.at(0)[1]
        assert core.history == ()
    finally:
        core.stop()


def test_concurrent_send_is_rejected(qapp, test_settings) -> None:
    provider = FakeProvider(
        [StreamEvent(EVENT_TOKEN, str(index)) for index in range(10)],
        token_delay=0.05,
    )
    core = CoreService(provider=provider, settings=test_settings)
    tokens = QSignalSpy(core.signals.token)
    chat_errors = QSignalSpy(core.signals.chat_error)
    cancelled = QSignalSpy(core.signals.chat_cancelled)
    core.start()

    try:
        core.chat_send("first")
        assert wait_until(lambda: tokens.count() >= 1)

        core.chat_send("second")
        assert wait_until(lambda: chat_errors.count() >= 1)
        assert chat_errors.at(0)[0] == "Busy"
        assert "already streaming" in chat_errors.at(0)[1]

        core.cancel_chat()
        assert wait_until(lambda: cancelled.count() >= 1)
        assert core.history == ()
    finally:
        core.stop()


def test_clear_chat_empties_history(qapp, test_settings) -> None:
    provider = FakeProvider(
        [StreamEvent(EVENT_TOKEN, "ok"), StreamEvent(EVENT_DONE)]
    )
    core = CoreService(provider=provider, settings=test_settings)
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        core.chat_send("hi")
        assert wait_until(lambda: done.count() >= 1)
        assert len(core.history) == 2

        core.clear_chat()
        assert wait_until(lambda: core.history == ())
    finally:
        core.stop()
