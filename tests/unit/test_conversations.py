"""Tests for the conversation repository."""

import pytest

from friday.memory.conversations import (
    AUTO_TITLE_LIMIT,
    EMPTY_TITLE,
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    ConversationNotFound,
    ConversationRepository,
    auto_title,
)
from friday.memory.db import Database


@pytest.fixture
def repository(tmp_path):
    database = Database(tmp_path / "friday.db")
    yield ConversationRepository(database)
    database.close()


def test_auto_title_empty_and_whitespace() -> None:
    assert auto_title("") == EMPTY_TITLE
    assert auto_title("   \n\t  ") == EMPTY_TITLE


def test_auto_title_collapses_newlines() -> None:
    assert auto_title("  hello\n\n  world  ") == "hello world"


def test_auto_title_truncates_with_ellipsis() -> None:
    title = auto_title("x" * (AUTO_TITLE_LIMIT + 10))
    assert title == "x" * AUTO_TITLE_LIMIT + "\u2026"
    assert len(title) == AUTO_TITLE_LIMIT + 1


def test_auto_title_unicode() -> None:
    title = auto_title("\U0001f642" * (AUTO_TITLE_LIMIT + 5))
    assert title == "\U0001f642" * AUTO_TITLE_LIMIT + "\u2026"


def test_create_and_list_conversations_newest_updated_first(repository) -> None:
    first = repository.create_conversation("First")
    second = repository.create_conversation("Second")

    conversations = repository.list_conversations()
    assert [conversation.id for conversation in conversations] == [
        second,
        first,
    ]

    repository.add_message(first, "user", "hello", STATUS_COMPLETE)

    conversations = repository.list_conversations()
    assert [conversation.id for conversation in conversations] == [
        first,
        second,
    ]


def test_adding_to_older_conversation_updates_ordering(repository) -> None:
    first = repository.create_conversation("First")
    repository.create_conversation("Second")
    repository.add_message(first, "user", "hello", STATUS_COMPLETE)

    conversations = repository.list_conversations()
    assert conversations[0].id == first


def test_messages_are_ordered_by_id(repository) -> None:
    conversation_id = repository.create_conversation("Order")
    first = repository.add_message(
        conversation_id, "user", "one", STATUS_COMPLETE
    )
    second = repository.add_message(
        conversation_id, "assistant", "two", STATUS_COMPLETE
    )
    third = repository.add_message(
        conversation_id, "user", "three", STATUS_COMPLETE
    )

    messages = repository.get_messages(conversation_id)
    assert [message.id for message in messages] == [first, second, third]
    assert [message.content for message in messages] == [
        "one",
        "two",
        "three",
    ]


def test_get_complete_messages_filters_incomplete(repository) -> None:
    conversation_id = repository.create_conversation("Filter")
    repository.add_message(
        conversation_id, "user", "complete user", STATUS_COMPLETE
    )
    repository.add_message(
        conversation_id, "assistant", "partial", STATUS_INCOMPLETE
    )

    complete = repository.get_messages(conversation_id, complete_only=True)
    assert [message.content for message in complete] == ["complete user"]

    all_messages = repository.get_messages(conversation_id)
    assert len(all_messages) == 2


def test_delete_cascades_messages(repository) -> None:
    conversation_id = repository.create_conversation("Delete me")
    repository.add_message(
        conversation_id, "user", "hello", STATUS_COMPLETE
    )
    repository.add_message(
        conversation_id, "assistant", "hi", STATUS_COMPLETE
    )

    repository.delete(conversation_id)

    assert repository.list_conversations() == []
    assert repository.get_messages(conversation_id) == []
    count = repository.database.connection.execute(
        "SELECT COUNT(*) FROM messages"
    ).fetchone()[0]
    assert count == 0


def test_rename(repository) -> None:
    conversation_id = repository.create_conversation("Old title")
    repository.rename(conversation_id, "  New\n title  ")

    conversation = repository.get_conversation(conversation_id)
    assert conversation.title == "New title"


def test_missing_conversation_raises(repository) -> None:
    with pytest.raises(ConversationNotFound):
        repository.rename(999, "Missing")
    with pytest.raises(ConversationNotFound):
        repository.delete(999)
    with pytest.raises(ConversationNotFound):
        repository.add_message(999, "user", "hello", STATUS_COMPLETE)


def test_sql_injection_style_title_is_stored_safely(repository) -> None:
    title = "Robert'); DROP TABLE messages;--"
    conversation_id = repository.create_conversation(title)
    repository.add_message(
        conversation_id, "user", "still here", STATUS_COMPLETE
    )

    assert repository.get_conversation(conversation_id).title == title
    assert len(repository.get_messages(conversation_id)) == 1
    table_check = repository.database.connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name = 'messages'"
    ).fetchone()
    assert table_check is not None
