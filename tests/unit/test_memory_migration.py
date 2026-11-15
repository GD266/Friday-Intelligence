"""Migration and FTS5 availability tests."""

import sqlite3

import pytest

import friday.memory.db as db_module
from friday.memory.db import (
    MIGRATION_1,
    SCHEMA_VERSION,
    Database,
    FTS5UnavailableError,
    verify_fts5,
)


def _create_version_1_database(path):
    connection = sqlite3.connect(path)
    try:
        for statement in MIGRATION_1:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) "
            "VALUES (1, 'Old chat', '2026-01-01T00:00:00+00:00', "
            "'2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO messages "
            "(id, conversation_id, role, content, status, created_at) "
            "VALUES (1, 1, 'user', 'old kittens question', 'complete', "
            "'2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO messages "
            "(id, conversation_id, role, content, status, created_at) "
            "VALUES (2, 1, 'assistant', 'unfinished puppies answer', "
            "'incomplete', '2026-01-01T00:00:01+00:00')"
        )
        connection.execute("PRAGMA user_version = 1")
        connection.commit()
    finally:
        connection.close()


def test_upgrade_from_v1_preserves_data_and_backfills_complete_messages(
    tmp_path,
) -> None:
    path = tmp_path / "friday.db"
    _create_version_1_database(path)

    database = Database(path)
    try:
        connection = database.connection
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == SCHEMA_VERSION

        assert connection.execute(
            "SELECT COUNT(*) FROM conversations"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM messages"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT title FROM conversations WHERE id = 1"
        ).fetchone()[0] == "Old chat"

        kittens = connection.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH "
            "'\"kittens\"'"
        ).fetchall()
        puppies = connection.execute(
            "SELECT rowid FROM messages_fts WHERE messages_fts MATCH "
            "'\"puppies\"'"
        ).fetchall()
        assert [row[0] for row in kittens] == [1]
        assert puppies == []
        assert connection.execute(
            "SELECT COUNT(*) FROM facts_fts"
        ).fetchone()[0] == 0

        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        assert {
            "facts_fts_ai",
            "facts_fts_ad",
            "facts_fts_au",
            "messages_fts_ai",
            "messages_fts_ad",
            "messages_fts_au",
        } <= triggers
    finally:
        database.close()


def test_message_status_updates_keep_fts_in_sync(tmp_path) -> None:
    database = Database(tmp_path / "friday.db")
    try:
        connection = database.connection
        with connection:
            connection.execute(
                "INSERT INTO conversations "
                "(id, title, created_at, updated_at) "
                "VALUES (1, 'Sync', 'now', 'now')"
            )
            connection.execute(
                "INSERT INTO messages "
                "(id, conversation_id, role, content, status, created_at) "
                "VALUES (1, 1, 'assistant', 'partial zebra', 'incomplete', "
                "'now')"
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM messages_fts "
            "WHERE messages_fts MATCH '\"zebra\"'"
        ).fetchone()[0] == 0

        with connection:
            connection.execute(
                "UPDATE messages SET status = 'complete' WHERE id = 1"
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM messages_fts "
            "WHERE messages_fts MATCH '\"zebra\"'"
        ).fetchone()[0] == 1

        with connection:
            connection.execute(
                "UPDATE messages SET content = 'finished yak' WHERE id = 1"
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM messages_fts "
            "WHERE messages_fts MATCH '\"zebra\"'"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM messages_fts "
            "WHERE messages_fts MATCH '\"yak\"'"
        ).fetchone()[0] == 1

        with connection:
            connection.execute(
                "UPDATE messages SET status = 'incomplete' WHERE id = 1"
            )
        assert connection.execute(
            "SELECT COUNT(*) FROM messages_fts "
            "WHERE messages_fts MATCH '\"yak\"'"
        ).fetchone()[0] == 0
    finally:
        database.close()


def test_verify_fts5_accepts_supported_sqlite(tmp_path) -> None:
    path = tmp_path / "friday.db"
    connection = sqlite3.connect(path)
    try:
        verify_fts5(connection, path)
        check = connection.execute(
            "SELECT name FROM sqlite_temp_master "
            "WHERE name = '__friday_fts5_check'"
        ).fetchone()
        assert check is None
    finally:
        connection.close()


class _BrokenConnection:
    def execute(self, sql):
        raise sqlite3.OperationalError("no such module: fts5")


def test_verify_fts5_raises_typed_error_when_missing(tmp_path) -> None:
    path = tmp_path / "friday.db"
    with pytest.raises(FTS5UnavailableError) as exc_info:
        verify_fts5(_BrokenConnection(), path)
    message = str(exc_info.value)
    assert "FTS5" in message
    assert str(path) in message


def test_database_startup_surfaces_fts5_error(tmp_path, monkeypatch) -> None:
    path = tmp_path / "friday.db"

    def fail_verification(connection, database_path):
        raise FTS5UnavailableError("FTS5 is missing")

    monkeypatch.setattr(db_module, "verify_fts5", fail_verification)

    with pytest.raises(FTS5UnavailableError, match="FTS5 is missing"):
        Database(path)
    assert path.exists()
