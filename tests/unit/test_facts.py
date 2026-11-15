"""Tests for user-authored facts and their FTS index."""

import pytest

from friday.memory.db import Database
from friday.memory.facts import (
    MAX_FACT_CHARS,
    MAX_FACTS,
    SECRET_FACT_MESSAGE,
    FactLimitError,
    FactNotFound,
    FactRepository,
    FactValidationError,
)
from friday.security.redaction import register_secret

SECRET_FACT_SAMPLES = [
    pytest.param("my key is nvapi-abc123456789", id="reported-nvidia"),
    pytest.param("my key is nvapi-" + "A1" * 10, id="nvidia"),
    pytest.param("github token ghp_" + "a1" * 12, id="github-classic"),
    pytest.param(
        "github token github_pat_" + "a1_" * 8,
        id="github-fine-grained",
    ),
    pytest.param("aws key AKIA" + "1234567890ABCDEF", id="aws-access-key"),
    pytest.param("slack token xoxb-1234567890-abcdef", id="slack"),
    pytest.param(
        "jwt eyJhbGciOiJIUzI1NiJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        id="jwt",
    ),
    pytest.param(
        "private key -----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA1234567890abcdef\n"
        "-----END RSA PRIVATE KEY-----",
        id="pem-private-key",
    ),
    pytest.param("my password is hunter2abc", id="password-value"),
    pytest.param("value " + "A1" * 12, id="high-entropy-token"),
]


@pytest.fixture
def repository(tmp_path):
    database = Database(tmp_path / "friday.db")
    yield FactRepository(database)
    database.close()


def test_fact_crud_and_fts_sync(repository) -> None:
    fact = repository.add_fact("  I like green tea.  ")
    assert fact.content == "I like green tea."
    assert fact.source == "user"
    assert [item.id for item in repository.list_facts()] == [fact.id]
    assert [item.id for item in repository.search_facts("tea")] == [fact.id]

    updated = repository.update_fact(fact.id, "I like coffee now.")
    assert updated.id == fact.id
    assert updated.content == "I like coffee now."
    assert repository.search_facts("tea") == []
    assert [item.id for item in repository.search_facts("coffee")] == [
        fact.id
    ]

    repository.delete_fact(fact.id)
    assert repository.list_facts() == []
    assert repository.search_facts("coffee") == []


def test_empty_and_whitespace_facts_are_rejected(repository) -> None:
    for value in ("", "   ", "\n\t "):
        with pytest.raises(FactValidationError, match="cannot be empty"):
            repository.add_fact(value)


def test_fact_length_limit(repository) -> None:
    maximum = repository.add_fact("x" * MAX_FACT_CHARS)
    assert len(maximum.content) == MAX_FACT_CHARS

    with pytest.raises(FactValidationError, match=str(MAX_FACT_CHARS)):
        repository.add_fact("x" * (MAX_FACT_CHARS + 1))


@pytest.mark.parametrize("text", SECRET_FACT_SAMPLES)
def test_secret_like_facts_are_rejected(repository, text) -> None:
    with pytest.raises(FactValidationError) as exc_info:
        repository.add_fact(text)
    assert str(exc_info.value) == SECRET_FACT_MESSAGE
    assert repository.list_facts() == []


def test_update_rejects_secret_like_fact(repository) -> None:
    fact = repository.add_fact("safe note")
    with pytest.raises(FactValidationError) as exc_info:
        repository.update_fact(fact.id, "Bearer " + "sk-" + "a" * 32)
    assert str(exc_info.value) == SECRET_FACT_MESSAGE


@pytest.mark.parametrize(
    "text",
    [
        "I live in Mumbai",
        "my favorite game is Hollow Knight",
    ],
)
def test_ordinary_facts_are_accepted(repository, text) -> None:
    assert repository.add_fact(text).content == text


def test_runtime_registered_secret_is_rejected(repository) -> None:
    secret = "custom-format-fact-Q7"
    register_secret(secret)

    with pytest.raises(FactValidationError) as exc_info:
        repository.add_fact(f"note {secret}")

    assert str(exc_info.value) == SECRET_FACT_MESSAGE


def test_fact_count_limit(repository) -> None:
    for index in range(MAX_FACTS):
        repository.add_fact(f"fact number {index}")

    with pytest.raises(FactLimitError, match=str(MAX_FACTS)):
        repository.add_fact("one too many")

    assert len(repository.list_facts()) == MAX_FACTS


def test_update_and_delete_missing_fact_raise(repository) -> None:
    with pytest.raises(FactNotFound):
        repository.update_fact(999, "missing")
    with pytest.raises(FactNotFound):
        repository.delete_fact(999)


def test_fact_search_sanitizes_hostile_input(repository) -> None:
    repository.add_fact("I have two cats")

    hostile = [
        '"',
        "*",
        "OR",
        "NEAR(",
        "--",
        ";",
        "\u732b",
        "",
        "x" * 10000,
        'cats" OR "dogs',
    ]
    for query in hostile:
        result = repository.search_facts(query)
        assert isinstance(result, list)


def test_fact_search_unicode(repository) -> None:
    repository.add_fact("I enjoy caf\u00e9 au lait")
    assert [fact.content for fact in repository.search_facts("caf\u00e9")] == [
        "I enjoy caf\u00e9 au lait"
    ]


def test_fact_search_respects_limit(repository) -> None:
    repository.add_fact("alpha one")
    repository.add_fact("alpha two")
    assert len(repository.search_facts("alpha", limit=1)) == 1
    assert repository.search_facts("alpha", limit=0) == []


def test_fact_relevance_search_matches_any_term(repository) -> None:
    repository.add_fact("My favorite color is teal")
    message = "what is my favorite color"
    assert repository.search_facts(message) == []
    assert [
        fact.content
        for fact in repository.search_facts(message, any_term=True)
    ] == ["My favorite color is teal"]
