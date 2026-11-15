"""Tests for full-text search over complete messages."""

import pytest

from friday.memory.conversations import (
    STATUS_COMPLETE,
    STATUS_INCOMPLETE,
    ConversationRepository,
)
from friday.memory.db import Database
from friday.memory.search import SearchResult, SearchService


@pytest.fixture
def services(tmp_path):
    database = Database(tmp_path / "friday.db")
    yield ConversationRepository(database), SearchService(database), database
    database.close()


def test_search_returns_conversation_snippet_and_timestamp(services) -> None:
    conversations, search, _ = services
    conversation_id = conversations.create_conversation("Cat notes")
    message_id = conversations.add_message(
        conversation_id,
        "user",
        "I have two cats and one dog at home",
        STATUS_COMPLETE,
    )
    stored = conversations.get_messages(conversation_id)[0]

    results = search.search_messages("cats")

    assert len(results) == 1
    result = results[0]
    assert isinstance(result, SearchResult)
    assert result.conversation_id == conversation_id
    assert result.conversation_title == "Cat notes"
    assert result.message_id == message_id
    assert result.role == "user"
    assert "cats" in result.snippet.lower()
    assert result.created_at == stored.created_at
    assert len(result.snippet) <= 200


def test_search_deduplicates_by_conversation(services) -> None:
    conversations, search, _ = services
    first = conversations.create_conversation("First")
    conversations.add_message(
        first, "user", "cats like fish", STATUS_COMPLETE
    )
    conversations.add_message(
        first, "assistant", "cats also like sleep", STATUS_COMPLETE
    )
    second = conversations.create_conversation("Second")
    conversations.add_message(
        second, "user", "my cat is orange", STATUS_COMPLETE
    )

    results = search.search_messages("cat")
    assert len(results) == 2
    assert len({result.conversation_id for result in results}) == 2


def test_incomplete_messages_are_not_searchable(services) -> None:
    conversations, search, _ = services
    conversation_id = conversations.create_conversation("Partial")
    conversations.add_message(
        conversation_id,
        "assistant",
        "unfinished discussion of zebras",
        STATUS_INCOMPLETE,
    )

    assert search.search_messages("zebras") == []


def test_search_ignores_operator_words_and_prefix_matches(services) -> None:
    conversations, search, _ = services
    conversation_id = conversations.create_conversation("Pets")
    conversations.add_message(
        conversation_id,
        "user",
        "cats and dogs are friends",
        STATUS_COMPLETE,
    )

    assert search.search_messages("cats OR dogs")
    assert search.search_messages("friend")
    assert search.search_messages("cat")


def test_cascade_delete_removes_search_rows(services) -> None:
    conversations, search, database = services
    conversation_id = conversations.create_conversation("Delete")
    conversations.add_message(
        conversation_id,
        "user",
        "searchable penguins",
        STATUS_COMPLETE,
    )
    assert search.search_messages("penguins")

    conversations.delete(conversation_id)

    assert search.search_messages("penguins") == []
    count = database.connection.execute(
        "SELECT COUNT(*) FROM messages_fts"
    ).fetchone()[0]
    assert count == 0


@pytest.mark.parametrize(
    "query",
    [
        '"',
        "*",
        "OR",
        "NEAR(",
        "--",
        ";",
        "\u732b",
        "",
        "   ",
        "x" * 10000,
        'cats" OR "dogs',
        "caf\u00e9 \u4e2d\u6587 \U0001f600",
        "NEAR(cats dogs)",
        "\x00\x01",
    ],
)
def test_hostile_search_input_never_raises(services, query) -> None:
    conversations, search, _ = services
    conversation_id = conversations.create_conversation("Safe")
    conversations.add_message(
        conversation_id, "user", "cats and dogs", STATUS_COMPLETE
    )

    result = search.search_messages(query)
    assert isinstance(result, list)


def test_search_unicode(services) -> None:
    conversations, search, _ = services
    conversation_id = conversations.create_conversation("Unicode")
    conversations.add_message(
        conversation_id,
        "user",
        "na\u00efve caf\u00e9 \u4e2d\u6587",
        STATUS_COMPLETE,
    )

    results = search.search_messages("caf\u00e9")
    assert len(results) == 1
    assert "\u4e2d\u6587" in conversations.get_messages(conversation_id)[0].content


def test_search_limit(services) -> None:
    conversations, search, _ = services
    for index in range(3):
        conversation_id = conversations.create_conversation(f"C{index}")
        conversations.add_message(
            conversation_id,
            "user",
            f"shared keyword {index}",
            STATUS_COMPLETE,
        )

    assert len(search.search_messages("shared", limit=2)) == 2
    assert search.search_messages("shared", limit=0) == []
