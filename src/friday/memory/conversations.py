"""Conversation repository backed by the FRIDAY SQLite database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from friday.memory.db import (
    Database,
    StorageError,
    translate_database_error,
)

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

STATUS_COMPLETE = "complete"
STATUS_INCOMPLETE = "incomplete"

VALID_ROLES = (ROLE_USER, ROLE_ASSISTANT)
VALID_STATUSES = (STATUS_COMPLETE, STATUS_INCOMPLETE)

AUTO_TITLE_LIMIT = 40
EMPTY_TITLE = "New conversation"


class ConversationNotFound(StorageError):
    """The requested conversation does not exist."""


@dataclass(frozen=True, slots=True)
class Conversation:
    """A persisted conversation row."""

    id: int
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class StoredMessage:
    """A persisted message row."""

    id: int
    conversation_id: int
    role: str
    content: str
    status: str
    created_at: str


def utc_now_iso() -> str:
    """Return the current UTC timestamp as ISO-8601."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def auto_title(first_user_text: str) -> str:
    """Build a short conversation title from the first user message."""
    normalized = " ".join(first_user_text.split())
    if not normalized:
        return EMPTY_TITLE
    if len(normalized) > AUTO_TITLE_LIMIT:
        return normalized[:AUTO_TITLE_LIMIT] + "\u2026"
    return normalized


def _normalize_title(title: str) -> str:
    normalized = " ".join(title.split())
    if not normalized:
        raise ValueError("Conversation title cannot be empty.")
    return normalized


class ConversationRepository:
    """CRUD operations for conversations and messages.

    All calls are synchronous and must run on the core thread that owns the
    database connection.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    @property
    def database(self) -> Database:
        return self._db

    @staticmethod
    def auto_title(first_user_text: str) -> str:
        """Build a short conversation title from the first user message."""
        return auto_title(first_user_text)

    def create_conversation(self, title: str = EMPTY_TITLE) -> int:
        """Create a conversation and return its id."""
        normalized = _normalize_title(title)
        now = utc_now_iso()
        try:
            with self._db.connection as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO conversations (title, created_at, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (normalized, now, now),
                )
                return int(cursor.lastrowid)
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc

    def list_conversations(self) -> list[Conversation]:
        """Return conversations ordered by most recently updated first."""
        try:
            rows = self._db.connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc
        return [
            Conversation(
                id=int(row["id"]),
                title=str(row["title"]),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    def get_conversation(self, conversation_id: int) -> Conversation:
        """Return one conversation or raise :class:`ConversationNotFound`."""
        try:
            row = self._db.connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                WHERE id = ?
                """,
                (conversation_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc
        if row is None:
            raise ConversationNotFound(
                f"Conversation {conversation_id} does not exist."
            )
        return Conversation(
            id=int(row["id"]),
            title=str(row["title"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def get_messages(
        self, conversation_id: int, *, complete_only: bool = False
    ) -> list[StoredMessage]:
        """Return the conversation's messages in insertion order."""
        sql = """
            SELECT id, conversation_id, role, content, status, created_at
            FROM messages
            WHERE conversation_id = ?
        """
        parameters: tuple[object, ...] = (conversation_id,)
        if complete_only:
            sql += " AND status = ?"
            parameters = (conversation_id, STATUS_COMPLETE)
        sql += " ORDER BY id ASC"

        try:
            rows = self._db.connection.execute(sql, parameters).fetchall()
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc
        return [
            StoredMessage(
                id=int(row["id"]),
                conversation_id=int(row["conversation_id"]),
                role=str(row["role"]),
                content=str(row["content"]),
                status=str(row["status"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        status: str = STATUS_COMPLETE,
    ) -> int:
        """Append a message and touch the conversation's updated_at."""
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid message role: {role!r}")
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid message status: {status!r}")

        now = utc_now_iso()
        try:
            with self._db.connection as connection:
                conversation = connection.execute(
                    "SELECT id FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).fetchone()
                if conversation is None:
                    raise ConversationNotFound(
                        f"Conversation {conversation_id} does not exist."
                    )

                cursor = connection.execute(
                    """
                    INSERT INTO messages
                        (conversation_id, role, content, status, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (conversation_id, role, content, status, now),
                )
                connection.execute(
                    """
                    UPDATE conversations
                    SET updated_at = ?
                    WHERE id = ?
                    """,
                    (now, conversation_id),
                )
                return int(cursor.lastrowid)
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc

    def rename(self, conversation_id: int, title: str) -> None:
        """Rename a conversation."""
        normalized = _normalize_title(title)
        try:
            with self._db.connection as connection:
                cursor = connection.execute(
                    """
                    UPDATE conversations
                    SET title = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (normalized, utc_now_iso(), conversation_id),
                )
                if cursor.rowcount == 0:
                    raise ConversationNotFound(
                        f"Conversation {conversation_id} does not exist."
                    )
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc

    def delete(self, conversation_id: int) -> None:
        """Delete a conversation; messages cascade."""
        try:
            with self._db.connection as connection:
                cursor = connection.execute(
                    "DELETE FROM conversations WHERE id = ?",
                    (conversation_id,),
                )
                if cursor.rowcount == 0:
                    raise ConversationNotFound(
                        f"Conversation {conversation_id} does not exist."
                    )
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc
