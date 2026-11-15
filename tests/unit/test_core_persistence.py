"""Core integration tests for persisted conversations (no network)."""

import asyncio
import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from friday.config.settings import ChatSettings, MemorySettings, Settings
from friday.core.service import CoreService
from friday.gateway import errors
from friday.gateway.base import Provider
from friday.gateway.types import EVENT_DONE, EVENT_TOKEN, StreamEvent
from friday.memory.conversations import (
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    ConversationRepository,
)
from friday.memory.db import Database


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


class ScriptedProvider(Provider):
    """Provider with a different script for each call."""

    def __init__(self, scripts, token_delay: float = 0.0) -> None:
        self._scripts = list(scripts)
        self._token_delay = token_delay
        self.calls = []

    async def stream_chat(self, messages):
        self.calls.append(list(messages))
        events, error = self._scripts.pop(0)
        for event in events:
            yield event
            if self._token_delay and event.type == EVENT_TOKEN:
                await asyncio.sleep(self._token_delay)
        if error is not None:
            raise error


def make_settings(db_path, char_budget: int = 24000) -> Settings:
    return Settings(
        memory=MemorySettings(db_path=str(db_path)),
        chat=ChatSettings(context_char_budget=char_budget),
    )


def read_rows(db_path):
    database = Database(db_path)
    try:
        repository = ConversationRepository(database)
        conversations = repository.list_conversations()
        messages = (
            repository.get_messages(conversations[0].id)
            if conversations
            else []
        )
        return conversations, messages
    finally:
        database.close()


def test_user_message_persisted_when_provider_fails_immediately(
    qapp, tmp_path
) -> None:
    db_path = tmp_path / "friday.db"
    provider = ScriptedProvider(
        [([], errors.ServerError("boom"))]
    )
    core = CoreService(
        provider=provider, settings=make_settings(db_path)
    )
    chat_errors = QSignalSpy(core.signals.chat_error)
    core.start()

    try:
        core.chat_send("remember this")
        assert wait_until(lambda: chat_errors.count() >= 1)
    finally:
        core.stop()

    conversations, messages = read_rows(db_path)
    assert len(conversations) == 1
    assert conversations[0].title == "remember this"
    assert [(m.role, m.content, m.status) for m in messages] == [
        ("user", "remember this", STATUS_COMPLETE)
    ]


def test_partial_assistant_reply_persisted_as_incomplete(
    qapp, tmp_path
) -> None:
    db_path = tmp_path / "friday.db"
    provider = ScriptedProvider(
        [
            (
                [StreamEvent(EVENT_TOKEN, "half")],
                errors.ServerError("boom"),
            )
        ]
    )
    core = CoreService(
        provider=provider, settings=make_settings(db_path)
    )
    chat_errors = QSignalSpy(core.signals.chat_error)
    core.start()

    try:
        core.chat_send("hi")
        assert wait_until(lambda: chat_errors.count() >= 1)
    finally:
        core.stop()

    _, messages = read_rows(db_path)
    assert [(m.role, m.content, m.status) for m in messages] == [
        ("user", "hi", STATUS_COMPLETE),
        ("assistant", "half", STATUS_INCOMPLETE),
    ]


def test_incomplete_messages_are_excluded_from_context(
    qapp, tmp_path
) -> None:
    db_path = tmp_path / "friday.db"
    database = Database(db_path)
    repository = ConversationRepository(database)
    conversation_id = repository.create_conversation("Seeded")
    repository.add_message(
        conversation_id, "user", "old question", STATUS_COMPLETE
    )
    repository.add_message(
        conversation_id, "assistant", "old incomplete", STATUS_INCOMPLETE
    )
    database.close()

    provider = ScriptedProvider(
        [([StreamEvent(EVENT_TOKEN, "answer"), StreamEvent(EVENT_DONE)], None)]
    )
    core = CoreService(
        provider=provider, settings=make_settings(db_path)
    )
    opened = QSignalSpy(core.signals.conversation_opened)
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        assert wait_until(lambda: opened.count() >= 1)
        core.chat_send("new question")
        assert wait_until(lambda: done.count() >= 1)
    finally:
        core.stop()

    contents = [message.content for message in provider.calls[0]]
    assert "old question" in contents
    assert "new question" in contents
    assert "old incomplete" not in contents


def test_context_budget_drops_oldest_and_keeps_latest_user(
    qapp, tmp_path
) -> None:
    db_path = tmp_path / "friday.db"
    database = Database(db_path)
    repository = ConversationRepository(database)
    conversation_id = repository.create_conversation("Budget")
    repository.add_message(
        conversation_id, "user", "A" * 10, STATUS_COMPLETE
    )
    repository.add_message(
        conversation_id, "assistant", "B" * 10, STATUS_COMPLETE
    )
    database.close()

    provider = ScriptedProvider(
        [([StreamEvent(EVENT_TOKEN, "ok"), StreamEvent(EVENT_DONE)], None)]
    )
    core = CoreService(
        provider=provider,
        settings=make_settings(db_path, char_budget=20),
    )
    opened = QSignalSpy(core.signals.conversation_opened)
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        assert wait_until(lambda: opened.count() >= 1)
        core.chat_send("C" * 5)
        assert wait_until(lambda: done.count() >= 1)
    finally:
        core.stop()

    messages = provider.calls[0]
    assert messages[-1].content == "C" * 5
    assert all(message.content != "A" * 10 for message in messages)
    assert any(message.content == "B" * 10 for message in messages)


def test_latest_user_is_kept_when_it_exceeds_budget(
    qapp, tmp_path
) -> None:
    db_path = tmp_path / "friday.db"
    provider = ScriptedProvider(
        [([StreamEvent(EVENT_TOKEN, "ok"), StreamEvent(EVENT_DONE)], None)]
    )
    core = CoreService(
        provider=provider,
        settings=make_settings(db_path, char_budget=1),
    )
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        core.chat_send("this message is longer than the budget")
        assert wait_until(lambda: done.count() >= 1)
    finally:
        core.stop()

    assert provider.calls[0][-1].role == "user"
    assert (
        provider.calls[0][-1].content
        == "this message is longer than the budget"
    )


def test_reopening_conversation_continues_with_history(
    qapp, tmp_path
) -> None:
    db_path = tmp_path / "friday.db"
    settings = make_settings(db_path)

    first_provider = ScriptedProvider(
        [
            (
                [
                    StreamEvent(EVENT_TOKEN, "first reply"),
                    StreamEvent(EVENT_DONE),
                ],
                None,
            )
        ]
    )
    first_core = CoreService(provider=first_provider, settings=settings)
    first_done = QSignalSpy(first_core.signals.message_done)
    first_core.start()
    try:
        first_core.chat_send("first question")
        assert wait_until(lambda: first_done.count() >= 1)
    finally:
        first_core.stop()

    second_provider = ScriptedProvider(
        [
            (
                [
                    StreamEvent(EVENT_TOKEN, "second reply"),
                    StreamEvent(EVENT_DONE),
                ],
                None,
            )
        ]
    )
    second_core = CoreService(provider=second_provider, settings=settings)
    opened = QSignalSpy(second_core.signals.conversation_opened)
    second_done = QSignalSpy(second_core.signals.message_done)
    second_core.start()
    try:
        assert wait_until(lambda: opened.count() >= 1)
        assert second_core.current_conversation_id > 0
        second_core.chat_send("second question")
        assert wait_until(lambda: second_done.count() >= 1)
    finally:
        second_core.stop()

    context = second_provider.calls[0]
    assert [(m.role, m.content) for m in context] == [
        ("system", context[0].content),
        ("user", "first question"),
        ("assistant", "first reply"),
        ("user", "second question"),
    ]


def test_new_chat_does_not_create_a_row(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    core = CoreService(
        provider=ScriptedProvider([]), settings=make_settings(db_path)
    )
    opened = QSignalSpy(core.signals.conversation_opened)
    core.start()
    try:
        assert wait_until(lambda: opened.count() >= 1)
        core.new_conversation()
        assert wait_until(lambda: opened.count() >= 2)
        assert core.current_conversation_id == 0
    finally:
        core.stop()

    conversations, _ = read_rows(db_path)
    assert conversations == []


def test_opening_during_streaming_is_rejected(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    provider = ScriptedProvider(
        [
            (
                [
                    StreamEvent(EVENT_TOKEN, "token"),
                    StreamEvent(EVENT_DONE),
                ],
                None,
            )
        ],
        token_delay=5.0,
    )
    core = CoreService(
        provider=provider, settings=make_settings(db_path)
    )
    tokens = QSignalSpy(core.signals.token)
    memory_errors = QSignalSpy(core.signals.memory_error)
    cancelled = QSignalSpy(core.signals.chat_cancelled)
    core.start()

    try:
        core.chat_send("streaming")
        assert wait_until(lambda: tokens.count() >= 1)
        core.open_conversation(1)
        assert wait_until(lambda: memory_errors.count() >= 1)
        assert memory_errors.at(0)[0] == "Busy"
        assert "Stop" in memory_errors.at(0)[1]

        core.cancel_chat()
        assert wait_until(lambda: cancelled.count() >= 1)
    finally:
        core.stop()


def test_delete_conversation_removes_messages(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    database = Database(db_path)
    repository = ConversationRepository(database)
    conversation_id = repository.create_conversation("Delete me")
    repository.add_message(
        conversation_id, "user", "hello", STATUS_COMPLETE
    )
    database.close()

    core = CoreService(
        provider=ScriptedProvider([]), settings=make_settings(db_path)
    )
    opened = QSignalSpy(core.signals.conversation_opened)
    deleted = QSignalSpy(core.signals.conversation_deleted)
    core.start()
    try:
        assert wait_until(lambda: opened.count() >= 1)
        core.delete_conversation(conversation_id)
        assert wait_until(lambda: deleted.count() >= 1)
    finally:
        core.stop()

    conversations, messages = read_rows(db_path)
    assert conversations == []
    assert messages == []


def test_corrupt_database_surfaces_typed_error(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    db_path.write_bytes(b"not a database")

    core = CoreService(
        provider=ScriptedProvider([]), settings=make_settings(db_path)
    )
    memory_errors = QSignalSpy(core.signals.memory_error)
    core.start()
    try:
        assert wait_until(lambda: memory_errors.count() >= 1)
        assert memory_errors.at(0)[0] == "DatabaseCorruptError"
        assert "will not replace" in memory_errors.at(0)[1]
    finally:
        core.stop()
