"""User-authored facts with validated writes and FTS5 search."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from friday.memory.conversations import utc_now_iso
from friday.memory.db import (
    Database,
    StorageError,
    translate_database_error,
)
from friday.memory.fts import (
    fts_match_query,
    fts_relevance_query,
    normalize_limit,
)
from friday.security.redaction import contains_secret

MAX_FACT_CHARS = 300
MAX_FACTS = 200
SECRET_FACT_MESSAGE = "Looks like a secret; not saved."


class FactError(StorageError):
    """Base class for fact storage failures."""


class FactValidationError(FactError):
    """A fact did not pass validation."""


class FactLimitError(FactValidationError):
    """The maximum number of stored facts has been reached."""


class FactNotFound(FactError):
    """The requested fact does not exist."""


@dataclass(frozen=True, slots=True)
class Fact:
    """A persisted user fact."""

    id: int
    content: str
    source: str
    created_at: str
    updated_at: str


def validate_fact_text(text: str) -> str:
    """Trim and validate fact text, returning the normalized value."""
    normalized = text.strip() if isinstance(text, str) else ""
    if not normalized:
        raise FactValidationError("Fact cannot be empty.")
    if len(normalized) > MAX_FACT_CHARS:
        raise FactValidationError(
            f"Fact is too long ({len(normalized)} characters); "
            f"the maximum is {MAX_FACT_CHARS}."
        )
    if contains_secret(normalized):
        raise FactValidationError(SECRET_FACT_MESSAGE)
    return normalized


def _fact_from_row(row: sqlite3.Row) -> Fact:
    return Fact(
        id=int(row["id"]),
        content=str(row["content"]),
        source=str(row["source"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class FactRepository:
    """CRUD and search for user facts.

    All calls are synchronous and must run on the core thread that owns the
    database connection.
    """

    def __init__(self, database: Database) -> None:
        self._db = database

    @property
    def database(self) -> Database:
        return self._db

    def add_fact(self, text: str) -> Fact:
        """Validate and store a fact, returning the persisted row."""
        normalized = validate_fact_text(text)
        now = utc_now_iso()
        try:
            with self._db.connection as connection:
                count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM facts"
                    ).fetchone()[0]
                )
                if count >= MAX_FACTS:
                    raise FactLimitError(
                        f"Fact limit reached ({MAX_FACTS} facts). "
                        "Delete a fact before adding another."
                    )
                cursor = connection.execute(
                    """
                    INSERT INTO facts
                        (content, source, created_at, updated_at)
                    VALUES (?, 'user', ?, ?)
                    """,
                    (normalized, now, now),
                )
                fact_id = int(cursor.lastrowid)
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc

        return self._get_fact(fact_id)

    def list_facts(self) -> list[Fact]:
        """Return every fact in creation order."""
        try:
            rows = self._db.connection.execute(
                """
                SELECT id, content, source, created_at, updated_at
                FROM facts
                ORDER BY id ASC
                """
            ).fetchall()
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc
        return [_fact_from_row(row) for row in rows]

    def update_fact(self, fact_id: int, text: str) -> Fact:
        """Replace a fact's text and return the updated row."""
        normalized = validate_fact_text(text)
        now = utc_now_iso()
        try:
            with self._db.connection as connection:
                cursor = connection.execute(
                    """
                    UPDATE facts
                    SET content = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (normalized, now, fact_id),
                )
                if cursor.rowcount == 0:
                    raise FactNotFound(f"Fact {fact_id} does not exist.")
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc

        return self._get_fact(fact_id)

    def delete_fact(self, fact_id: int) -> None:
        """Delete one fact."""
        try:
            with self._db.connection as connection:
                cursor = connection.execute(
                    "DELETE FROM facts WHERE id = ?",
                    (fact_id,),
                )
                if cursor.rowcount == 0:
                    raise FactNotFound(f"Fact {fact_id} does not exist.")
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc

    def search_facts(
        self, query: str, limit: int = 20, *, any_term: bool = False
    ) -> list[Fact]:
        """Return facts ranked by FTS relevance to *query*.

        By default every token must match. ``any_term`` ranks facts that match
        any token, which the core uses to rank the latest user message.
        """
        match = (
            fts_relevance_query(query)
            if any_term
            else fts_match_query(query)
        )
        row_limit = normalize_limit(limit)
        if not match or row_limit == 0:
            return []
        try:
            rows = self._db.connection.execute(
                """
                SELECT f.id, f.content, f.source, f.created_at, f.updated_at
                FROM facts_fts
                JOIN facts AS f ON f.id = facts_fts.rowid
                WHERE facts_fts MATCH ?
                ORDER BY bm25(facts_fts), f.id
                LIMIT ?
                """,
                (match, row_limit),
            ).fetchall()
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc
        return [_fact_from_row(row) for row in rows]

    def _get_fact(self, fact_id: int) -> Fact:
        try:
            row = self._db.connection.execute(
                """
                SELECT id, content, source, created_at, updated_at
                FROM facts
                WHERE id = ?
                """,
                (fact_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise translate_database_error(exc, self._db.path) from exc
        if row is None:
            raise FactNotFound(f"Fact {fact_id} does not exist.")
        return _fact_from_row(row)
