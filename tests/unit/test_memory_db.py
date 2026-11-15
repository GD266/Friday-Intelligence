"""Tests for SQLite setup and schema migrations."""

import sqlite3

import pytest

from friday.memory.db import (
    SCHEMA_VERSION,
    Database,
    DatabaseCorruptError,
    DatabaseLockedError,
    DatabaseThreadError,
    DatabaseVersionError,
    get_default_db_path,
    translate_database_error,
)


def test_migrations_create_schema_and_set_user_version(tmp_path) -> None:
    path = tmp_path / "friday.db"
    database = Database(path)
    try:
        connection = database.connection
        assert connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == SCHEMA_VERSION
        assert connection.execute(
            "PRAGMA journal_mode"
        ).fetchone()[0].lower() == "wal"
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "conversations" in tables
        assert "messages" in tables
        index = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name = 'idx_messages_conversation_id_id'"
        ).fetchone()
        assert index is not None
    finally:
        database.close()


def test_reopening_does_not_rerun_migrations(tmp_path) -> None:
    path = tmp_path / "friday.db"
    Database(path).close()

    reopened = Database(path)
    try:
        assert reopened.connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0] == SCHEMA_VERSION
    finally:
        reopened.close()


def test_newer_schema_version_is_refused(tmp_path) -> None:
    path = tmp_path / "friday.db"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA user_version = 999")
    connection.commit()
    connection.close()

    with pytest.raises(DatabaseVersionError) as exc_info:
        Database(path)

    message = str(exc_info.value)
    assert "999" in message
    assert str(path) in message
    assert "Update FRIDAY" in message
    assert path.exists()


def test_corrupt_database_is_not_replaced(tmp_path) -> None:
    path = tmp_path / "friday.db"
    original = b"this is not a sqlite database"
    path.write_bytes(original)

    with pytest.raises(DatabaseCorruptError):
        Database(path)

    assert path.read_bytes() == original


def test_connection_is_bound_to_creating_thread(tmp_path) -> None:
    database = Database(tmp_path / "friday.db")
    errors: list[Exception] = []

    def use_from_other_thread() -> None:
        try:
            database.connection.execute("SELECT 1")
        except Exception as exc:  # noqa: BLE001 - captured for assertion
            errors.append(exc)

    import threading

    thread = threading.Thread(target=use_from_other_thread)
    thread.start()
    thread.join(timeout=2.0)

    assert len(errors) == 1
    assert isinstance(errors[0], DatabaseThreadError)
    database.close()


def test_default_database_path_uses_localappdata(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert get_default_db_path() == tmp_path / "Friday" / "friday.db"


def test_lock_and_corruption_map_to_typed_errors(tmp_path) -> None:
    path = tmp_path / "friday.db"

    locked = translate_database_error(
        sqlite3.OperationalError("database is locked"), path
    )
    assert isinstance(locked, DatabaseLockedError)

    corrupt = translate_database_error(
        sqlite3.DatabaseError("file is not a database"), path
    )
    assert isinstance(corrupt, DatabaseCorruptError)
