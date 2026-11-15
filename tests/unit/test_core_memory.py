"""Core integration tests for facts, commands, and chat search."""

import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from friday.config.settings import (
    MemorySettings,
    ProviderSettings,
    Settings,
)
from friday.core.service import FACTS_HEADER, CoreService
from friday.gateway.base import Provider
from friday.gateway.types import EVENT_DONE, EVENT_TOKEN, StreamEvent
from friday.memory.conversations import (
    STATUS_COMPLETE,
    ConversationRepository,
)
from friday.memory.db import Database
from friday.memory.facts import FactRepository


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


class RecordingProvider(Provider):
    def __init__(self, reply: str = "ok") -> None:
        self._reply = reply
        self.calls = []

    async def stream_chat(self, messages):
        self.calls.append(list(messages))
        yield StreamEvent(EVENT_TOKEN, self._reply)
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


def make_settings(
    db_path,
    *,
    enabled: bool = True,
    fact_char_budget: int = 2000,
    max_facts_in_prompt: int = 20,
    system_prompt: str = "Test system prompt.",
) -> Settings:
    return Settings(
        memory=MemorySettings(
            db_path=str(db_path),
            enabled=enabled,
            fact_char_budget=fact_char_budget,
            max_facts_in_prompt=max_facts_in_prompt,
        ),
        provider=ProviderSettings(system_prompt=system_prompt),
    )


def seed_facts(db_path, contents) -> list[int]:
    database = Database(db_path)
    try:
        repository = FactRepository(database)
        return [repository.add_fact(content).id for content in contents]
    finally:
        database.close()


def test_facts_are_injected_into_system_message_and_signal(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    seed_facts(db_path, ["I like green tea."])
    provider = RecordingProvider("hello")
    core = CoreService(
        provider=provider, settings=make_settings(db_path)
    )
    facts_used = QSignalSpy(core.signals.facts_used)
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        core.chat_send("what should I drink?")
        assert wait_until(lambda: done.count() >= 1)

        system = provider.calls[0][0]
        assert system.role == "system"
        assert system.content.startswith("Test system prompt.")
        assert FACTS_HEADER in system.content
        assert "- I like green tea." in system.content
        assert facts_used.count() == 1
        assert facts_used.at(0)[0] == 1
    finally:
        core.stop()


def test_memory_disabled_injects_nothing(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    seed_facts(db_path, ["I like green tea."])
    provider = RecordingProvider()
    core = CoreService(
        provider=provider,
        settings=make_settings(db_path, enabled=False),
    )
    facts_used = QSignalSpy(core.signals.facts_used)
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        core.chat_send("hello")
        assert wait_until(lambda: done.count() >= 1)

        system_content = provider.calls[0][0].content
        assert system_content == "Test system prompt."
        assert FACTS_HEADER not in system_content
        assert "green tea" not in system_content
        assert facts_used.count() == 1
        assert facts_used.at(0)[0] == 0
    finally:
        core.stop()


def test_over_budget_facts_are_ranked_by_relevance(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    seed_facts(
        db_path,
        [
            "I dislike celery intensely.",
            "I love astronomy and telescopes.",
            "My favorite color is teal.",
        ],
    )
    provider = RecordingProvider()
    core = CoreService(
        provider=provider,
        settings=make_settings(
            db_path, fact_char_budget=120, max_facts_in_prompt=20
        ),
    )
    facts_used = QSignalSpy(core.signals.facts_used)
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        core.chat_send("tell me about astronomy")
        assert wait_until(lambda: done.count() >= 1)

        system_content = provider.calls[0][0].content
        assert "astronomy" in system_content
        assert "celery" not in system_content
        assert "teal" not in system_content
        assert facts_used.at(0)[0] == 1
        prefix = "Test system prompt.\n\n"
        assert system_content.startswith(prefix)
        assert len(system_content) - len(prefix) <= 120
    finally:
        core.stop()


def test_max_facts_in_prompt_caps_injection(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    seed_facts(db_path, ["alpha fact", "beta fact", "gamma fact"])
    provider = RecordingProvider()
    core = CoreService(
        provider=provider,
        settings=make_settings(db_path, max_facts_in_prompt=2),
    )
    facts_used = QSignalSpy(core.signals.facts_used)
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        core.chat_send("hello")
        assert wait_until(lambda: done.count() >= 1)

        system_content = provider.calls[0][0].content
        assert system_content.count("\n- ") == 2
        assert facts_used.at(0)[0] == 2
    finally:
        core.stop()


def test_no_facts_still_emits_zero(qapp, tmp_path) -> None:
    provider = RecordingProvider()
    core = CoreService(
        provider=provider, settings=make_settings(tmp_path / "friday.db")
    )
    facts_used = QSignalSpy(core.signals.facts_used)
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        core.chat_send("hello")
        assert wait_until(lambda: done.count() >= 1)
        assert facts_used.count() == 1
        assert facts_used.at(0)[0] == 0
        assert FACTS_HEADER not in provider.calls[0][0].content
    finally:
        core.stop()


def test_commands_persist_facts_without_calling_provider(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    provider = RecordingProvider()
    core = CoreService(
        provider=provider, settings=make_settings(db_path)
    )
    facts_loaded = QSignalSpy(core.signals.facts_loaded)
    notices = QSignalSpy(core.signals.memory_notice)
    core.start()

    try:
        assert wait_until(lambda: facts_loaded.count() >= 1)

        core.send_command("/remember  I like green tea.  ")
        assert wait_until(lambda: notices.count() >= 1)
        assert "Remembered fact" in notices.at(0)[0]

        core.send_command("/facts")
        assert wait_until(lambda: facts_loaded.count() >= 2)

        core.send_command("/forget 1")
        assert wait_until(lambda: notices.count() >= 2)
        assert "Forgot fact 1" in notices.at(1)[0]
        assert provider.calls == []
    finally:
        core.stop()

    database = Database(db_path)
    try:
        assert FactRepository(database).list_facts() == []
    finally:
        database.close()


def test_chat_send_treats_slash_command_as_command(qapp, tmp_path) -> None:
    provider = RecordingProvider()
    core = CoreService(
        provider=provider, settings=make_settings(tmp_path / "friday.db")
    )
    notices = QSignalSpy(core.signals.memory_notice)
    core.start()

    try:
        core.chat_send("/remember a fact")
        assert wait_until(lambda: notices.count() >= 1)
        assert provider.calls == []
    finally:
        core.stop()


def test_commands_are_not_persisted_as_chat_messages(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    provider = RecordingProvider()
    core = CoreService(
        provider=provider, settings=make_settings(db_path)
    )
    facts_loaded = QSignalSpy(core.signals.facts_loaded)
    notices = QSignalSpy(core.signals.memory_notice)
    memory_errors = QSignalSpy(core.signals.memory_error)
    core.start()

    try:
        assert wait_until(lambda: facts_loaded.count() >= 1)

        core.send_command("/remember I live in Mumbai")
        assert wait_until(lambda: notices.count() >= 1)

        core.chat_send("/remember my favorite game is Hollow Knight")
        assert wait_until(lambda: notices.count() >= 2)

        core.chat_send("/remember my key is nvapi-abc123456789")
        assert wait_until(lambda: memory_errors.count() >= 1)
        assert memory_errors.at(0)[0] == "FactValidationError"
        assert memory_errors.at(0)[1] == "Looks like a secret; not saved."

        core.send_command("/facts")
        core.send_command("/forget 1")
        assert wait_until(lambda: notices.count() >= 3)
        assert "Forgot fact 1" in notices.at(2)[0]
        assert provider.calls == []
    finally:
        core.stop()

    database = Database(db_path)
    try:
        assert ConversationRepository(database).list_conversations() == []
        message_count = database.connection.execute(
            "SELECT COUNT(*) FROM messages"
        ).fetchone()[0]
        assert message_count == 0
        facts = FactRepository(database).list_facts()
    finally:
        database.close()

    # Only the accepted command's fact remains; command text is never stored
    # as a chat message.
    assert [fact.content for fact in facts] == [
        "my favorite game is Hollow Knight"
    ]


def test_invalid_fact_surfaces_typed_memory_error(qapp, tmp_path) -> None:
    provider = RecordingProvider()
    core = CoreService(
        provider=provider, settings=make_settings(tmp_path / "friday.db")
    )
    errors = QSignalSpy(core.signals.memory_error)
    core.start()

    try:
        core.add_fact("sk-" + "a" * 32)
        assert wait_until(lambda: errors.count() >= 1)
        assert errors.at(0)[0] == "FactValidationError"
        assert errors.at(0)[1] == "Looks like a secret; not saved."
        assert provider.calls == []
    finally:
        core.stop()


def test_search_chats_emits_results(qapp, tmp_path) -> None:
    db_path = tmp_path / "friday.db"
    database = Database(db_path)
    try:
        conversations = ConversationRepository(database)
        conversation_id = conversations.create_conversation("Space talk")
        conversations.add_message(
            conversation_id,
            "user",
            "I bought a new telescope yesterday",
            STATUS_COMPLETE,
        )
    finally:
        database.close()

    provider = RecordingProvider()
    core = CoreService(
        provider=provider, settings=make_settings(db_path)
    )
    results = QSignalSpy(core.signals.search_results)
    core.start()

    try:
        core.search_chats("telescope")
        assert wait_until(lambda: results.count() >= 1)
        found = results.at(0)[0]
        assert len(found) == 1
        assert found[0].conversation_id == conversation_id
        assert found[0].conversation_title == "Space talk"
        assert "telescope" in found[0].snippet
        assert provider.calls == []
    finally:
        core.stop()
