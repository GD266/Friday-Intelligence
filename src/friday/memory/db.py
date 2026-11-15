"""SQLite database setup and schema migrations for FRIDAY memory.

The connection is created on the core thread and every operation checks that it
is used from that same thread.  SQLite connections must not be shared between
threads.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 4

MIGRATION_1 = (
    """
    CREATE TABLE conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL
            REFERENCES conversations(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        content TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('complete', 'incomplete')),
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX idx_messages_conversation_id_id
        ON messages(conversation_id, id)
    """,
)

MIGRATION_2 = (
    """
    CREATE TABLE facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        source TEXT NOT NULL DEFAULT 'user'
            CHECK (source IN ('user')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE VIRTUAL TABLE facts_fts USING fts5(
        content,
        content='facts',
        content_rowid='id'
    )
    """,
    """
    CREATE TRIGGER facts_fts_ai AFTER INSERT ON facts BEGIN
        INSERT INTO facts_fts(rowid, content)
        VALUES (new.id, new.content);
    END
    """,
    """
    CREATE TRIGGER facts_fts_ad AFTER DELETE ON facts BEGIN
        INSERT INTO facts_fts(facts_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
    END
    """,
    """
    CREATE TRIGGER facts_fts_au AFTER UPDATE ON facts BEGIN
        INSERT INTO facts_fts(facts_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
        INSERT INTO facts_fts(rowid, content)
        VALUES (new.id, new.content);
    END
    """,
    """
    CREATE VIRTUAL TABLE messages_fts USING fts5(
        content,
        content='messages',
        content_rowid='id'
    )
    """,
    """
    CREATE TRIGGER messages_fts_ai AFTER INSERT ON messages
    WHEN new.status = 'complete'
    BEGIN
        INSERT INTO messages_fts(rowid, content)
        VALUES (new.id, new.content);
    END
    """,
    """
    CREATE TRIGGER messages_fts_ad AFTER DELETE ON messages
    WHEN old.status = 'complete'
    BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content)
        VALUES ('delete', old.id, old.content);
    END
    """,
    """
    CREATE TRIGGER messages_fts_au AFTER UPDATE ON messages BEGIN
        INSERT INTO messages_fts(messages_fts, rowid, content)
        SELECT 'delete', old.id, old.content
        WHERE old.status = 'complete';
        INSERT INTO messages_fts(rowid, content)
        SELECT new.id, new.content
        WHERE new.status = 'complete';
    END
    """,
    """
    INSERT INTO messages_fts(rowid, content)
    SELECT id, content
    FROM messages
    WHERE status = 'complete'
    """,
)

MIGRATION_3 = (
    """
    CREATE TABLE tool_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        conversation_id INTEGER
            REFERENCES conversations(id) ON DELETE SET NULL,
        tool TEXT NOT NULL,
        args_json TEXT NOT NULL,
        permission TEXT NOT NULL,
        decision TEXT NOT NULL
            CHECK (decision IN ('auto', 'approved', 'denied', 'timeout')),
        status TEXT NOT NULL
            CHECK (status IN ('ok', 'error', 'denied', 'skipped')),
        error_kind TEXT,
        duration_ms INTEGER NOT NULL
    )
    """,
    """
    CREATE INDEX idx_tool_audit_conversation_id
        ON tool_audit(conversation_id)
    """,
)

MIGRATION_4 = (
    """
    ALTER TABLE tool_audit RENAME TO tool_audit_old
    """,
    """
    CREATE TABLE tool_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        conversation_id INTEGER
            REFERENCES conversations(id) ON DELETE SET NULL,
        tool TEXT NOT NULL,
        args_json TEXT NOT NULL,
        permission TEXT NOT NULL,
        decision TEXT NOT NULL
            CHECK (decision IN ('auto', 'approved', 'denied', 'timeout')),
        status TEXT NOT NULL
            CHECK (status IN ('ok', 'error', 'denied', 'skipped')),
        error_kind TEXT,
        duration_ms INTEGER NOT NULL
    )
    """,
    """
    DROP INDEX IF EXISTS idx_tool_audit_conversation_id
    """,
    """
    CREATE INDEX idx_tool_audit_conversation_id
        ON tool_audit(conversation_id)
    """,
    """
    INSERT INTO tool_audit
    SELECT id, ts, conversation_id, tool, args_json, permission, decision,
           status, error_kind, duration_ms
    FROM tool_audit_old
    """,
    """
    DROP TABLE tool_audit_old
    """,
)

MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: MIGRATION_1,
    2: MIGRATION_2,
    3: MIGRATION_3,
    4: MIGRATION_4,
}


class StorageError(Exception):
    """Base class for memory storage failures."""


class DatabaseError(StorageError):
    """A SQLite database operation failed."""


class DatabaseVersionError(DatabaseError):
    """The database schema is newer than this version of FRIDAY supports."""


class DatabaseCorruptError(DatabaseError):
    """The database file is corrupt or is not a SQLite database."""


class DatabaseLockedError(DatabaseError):
    """The database is locked by another connection."""


class DatabaseClosedError(DatabaseError):
    """The database connection has already been closed."""


class DatabaseThreadError(DatabaseError):
    """The database was used from a thread other than its owning thread."""


class FTS5UnavailableError(DatabaseError):
    """The SQLite build does not provide FTS5 full-text search."""


def verify_fts5(connection: sqlite3.Connection, path: Path) -> None:
    """Verify that this SQLite build can create FTS5 tables.

    The check creates and drops a temporary table so it has no effect on the
    application schema.
    """
    try:
        connection.execute(
            "CREATE VIRTUAL TABLE temp.__friday_fts5_check "
            "USING fts5(content)"
        )
        connection.execute("DROP TABLE temp.__friday_fts5_check")
    except sqlite3.Error as exc:
        raise FTS5UnavailableError(
            "SQLite FTS5 full-text search is not available for "
            f"{path}: {exc}. FRIDAY requires a Python/SQLite build with "
            "FTS5 support enabled."
        ) from exc


def get_data_dir() -> Path:
    """Get the application data directory (``%LOCALAPPDATA%\\Friday``)."""
    localappdata = os.environ.get("LOCALAPPDATA")
    if not localappdata:
        raise DatabaseError("LOCALAPPDATA environment variable not set")
    data_dir = Path(localappdata) / "Friday"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DatabaseError(
            f"Could not create the FRIDAY data directory at {data_dir}: {exc}"
        ) from exc
    return data_dir


def get_default_db_path() -> Path:
    """Get the default SQLite database path."""
    return get_data_dir() / "friday.db"


def get_db_path(configured_path: str | None = None) -> Path:
    """Return the configured database path or the default path."""
    return resolve_db_path(configured_path)


def resolve_db_path(configured_path: str | None = None) -> Path:
    """Resolve the configured database path, falling back to LOCALAPPDATA."""
    if configured_path and configured_path.strip():
        return Path(configured_path).expanduser()
    return get_default_db_path()


def translate_database_error(
    error: sqlite3.Error, path: Path
) -> DatabaseError:
    """Convert a raw sqlite3 error into a typed storage error."""
    message = str(error)
    lowered = message.lower()
    if "locked" in lowered or "busy" in lowered:
        return DatabaseLockedError(
            f"The conversation database is locked ({path}). "
            "Close any other FRIDAY window and try again."
        )
    if (
        "not a database" in lowered
        or "malformed" in lowered
        or "encrypted" in lowered
    ):
        return DatabaseCorruptError(
            f"The conversation database at {path} is corrupt or unreadable. "
            "FRIDAY will not replace it automatically."
        )
    return DatabaseError(f"SQLite error in {path}: {message}")


class Database:
    """A thread-bound SQLite connection with versioned migrations."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._thread_id = threading.get_ident()
        self._connection: sqlite3.Connection | None = None
        self._connection = self._open()

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the connection after validating thread and open state."""
        self._check_usable()
        assert self._connection is not None
        return self._connection

    def close(self) -> None:
        """Close the connection on its owning thread."""
        self._check_thread()
        connection = self._connection
        self._connection = None
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error as exc:
                raise translate_database_error(exc, self.path) from exc

    def _check_thread(self) -> None:
        if threading.get_ident() != self._thread_id:
            raise DatabaseThreadError(
                "The conversation database was accessed from a different "
                "thread than the one that opened it."
            )

    def _check_usable(self) -> None:
        self._check_thread()
        if self._connection is None:
            raise DatabaseClosedError(
                f"The conversation database at {self.path} is closed."
            )

    def _open(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.path, timeout=5.0)
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self.path) from exc

        try:
            connection.row_factory = sqlite3.Row
            current_version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )
            if current_version > SCHEMA_VERSION:
                raise DatabaseVersionError(
                    f"The conversation database at {self.path} uses schema "
                    f"version {current_version}, but this version of FRIDAY "
                    f"supports up to version {SCHEMA_VERSION}. "
                    "Update FRIDAY before opening this database."
                )

            journal_mode = connection.execute(
                "PRAGMA journal_mode=WAL"
            ).fetchone()[0]
            if str(journal_mode).lower() != "wal":
                raise DatabaseError(
                    f"Could not enable WAL mode for {self.path} "
                    f"(journal_mode={journal_mode})."
                )

            connection.execute("PRAGMA foreign_keys=ON")
            foreign_keys = connection.execute(
                "PRAGMA foreign_keys"
            ).fetchone()[0]
            if int(foreign_keys) != 1:
                raise DatabaseError(
                    f"Could not enable foreign keys for {self.path}."
                )

            verify_fts5(connection, self.path)
            self._migrate(connection)
        except StorageError:
            connection.close()
            raise
        except sqlite3.Error as exc:
            connection.close()
            raise translate_database_error(exc, self.path) from exc

        return connection

    def _migrate(self, connection: sqlite3.Connection) -> None:
        try:
            current_version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self.path) from exc

        if current_version > SCHEMA_VERSION:
            raise DatabaseVersionError(
                f"The conversation database at {self.path} uses schema "
                f"version {current_version}, but this version of FRIDAY "
                f"supports up to version {SCHEMA_VERSION}. "
                "Update FRIDAY before opening this database."
            )

        for target_version in range(current_version + 1, SCHEMA_VERSION + 1):
            try:
                connection.execute("BEGIN")
                for statement in MIGRATIONS[target_version]:
                    connection.execute(statement)
                connection.execute(
                    f"PRAGMA user_version = {target_version}"
                )
                connection.commit()
            except sqlite3.Error as exc:
                connection.rollback()
                raise translate_database_error(exc, self.path) from exc


def execute(
    database: Database, sql: str, parameters: tuple[Any, ...] = ()
) -> sqlite3.Cursor:
    """Execute one short parameterized statement."""
    try:
        return database.connection.execute(sql, parameters)
    except sqlite3.Error as exc:
        raise translate_database_error(exc, database.path) from exc
