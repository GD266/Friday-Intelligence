"""Persistent, redacted audit trail for tool calls."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from friday.core.logging import get_logger
from friday.memory.db import Database, translate_database_error
from friday.security.redaction import redact_text

logger = get_logger(__name__)

RECENT_LIMIT = 20


@dataclass(frozen=True, slots=True)
class ToolAuditEntry:
    """One row from ``tool_audit``."""

    id: int
    ts: str
    conversation_id: int | None
    tool: str
    args_json: str
    permission: str
    decision: str
    status: str
    error_kind: str | None
    duration_ms: int


class ToolAuditRepository:
    """Write and read tool audit rows on the database-owning thread."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def record(
        self,
        *,
        conversation_id: int | None,
        tool: str,
        args_json: str,
        permission: str,
        decision: str,
        status: str,
        error_kind: str | None,
        duration_ms: int,
        result_chars: int | None = None,
    ) -> int:
        """Insert one audit row and write one redacted log line."""
        safe_args = redact_text(args_json or "{}")
        timestamp = datetime.now(timezone.utc).isoformat(
            timespec="microseconds"
        )
        try:
            with self._database.connection:
                cursor = self._database.connection.execute(
                    """
                    INSERT INTO tool_audit (
                        ts, conversation_id, tool, args_json, permission,
                        decision, status, error_kind, duration_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        timestamp,
                        conversation_id,
                        tool,
                        safe_args,
                        permission,
                        decision,
                        status,
                        error_kind,
                        int(duration_ms),
                    ),
                )
                row_id = int(cursor.lastrowid or 0)
        except sqlite3.Error as exc:
            raise translate_database_error(
                exc, self._database.path
            ) from exc

        logger.info(
            "tool call tool=%s permission=%s decision=%s status=%s "
            "error_kind=%s duration_ms=%d result_chars=%s args=%s",
            tool,
            permission,
            decision,
            status,
            error_kind or "-",
            int(duration_ms),
            "-" if result_chars is None else result_chars,
            safe_args,
        )
        return row_id

    def recent(self, limit: int = RECENT_LIMIT) -> list[ToolAuditEntry]:
        """Return the newest audit rows first."""
        safe_limit = max(1, min(int(limit), RECENT_LIMIT))
        try:
            rows = self._database.connection.execute(
                """
                SELECT id, ts, conversation_id, tool, args_json, permission,
                       decision, status, error_kind, duration_ms
                FROM tool_audit
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise translate_database_error(
                exc, self._database.path
            ) from exc
        return [
            ToolAuditEntry(
                id=row["id"],
                ts=row["ts"],
                conversation_id=row["conversation_id"],
                tool=row["tool"],
                args_json=row["args_json"],
                permission=row["permission"],
                decision=row["decision"],
                status=row["status"],
                error_kind=row["error_kind"],
                duration_ms=row["duration_ms"],
            )
            for row in rows
        ]


__all__ = ["RECENT_LIMIT", "ToolAuditEntry", "ToolAuditRepository"]
