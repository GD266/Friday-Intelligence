"""Full-text search over complete messages."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from friday.memory.db import (
    Database,
    translate_database_error,
)
from friday.memory.fts import fts_match_query, normalize_limit

_SNIPPET_TOKENS = 16


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One matching conversation with its best matching message."""

    conversation_id: int
    conversation_title: str
    message_id: int
    role: str
    snippet: str
    created_at: str


class SearchService:
    """Search complete messages, one result per conversation.

    All calls are synchronous and must run on the core thread that owns the
    database connection.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    @property
    def database(self) -> Database:
        return self._db

    def search_messages(
        self, query: str, limit: int = 20
    ) -> list[SearchResult]:
        """Return conversations whose complete messages match *query*.

        ``query`` is sanitized before it reaches FTS5. Hostile or empty input
        returns an empty list rather than raising a syntax error.
        """
        match = fts_match_query(query)
        conversation_limit = normalize_limit(limit)
        if not match or conversation_limit == 0:
            return []

        row_limit = min(conversation_limit * 10, 1000)
        try:
            rows = self._db.connection.execute(
                """
                SELECT
                    m.id AS message_id,
                    m.conversation_id AS conversation_id,
                    m.role AS role,
                    m.created_at AS created_at,
                    c.title AS conversation_title,
                    snippet(messages_fts, 0, '', '', '\u2026', ?) AS snippet,
                    bm25(messages_fts) AS rank
                FROM messages_fts
                JOIN messages AS m ON m.id = messages_fts.rowid
                JOIN conversations AS c ON c.id = m.conversation_id
                WHERE messages_fts MATCH ?
                ORDER BY rank ASC, m.id DESC
                LIMIT ?
                """,
                (_SNIPPET_TOKENS, match, row_limit),
            ).fetchall()
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc

        results: list[SearchResult] = []
        seen: set[int] = set()
        for row in rows:
            conversation_id = int(row["conversation_id"])
            if conversation_id in seen:
                continue
            seen.add(conversation_id)
            results.append(
                SearchResult(
                    conversation_id=conversation_id,
                    conversation_title=str(row["conversation_title"]),
                    message_id=int(row["message_id"]),
                    role=str(row["role"]),
                    snippet=str(row["snippet"] or ""),
                    created_at=str(row["created_at"]),
                )
            )
            if len(results) >= conversation_limit:
                break
        return results
