"""Tool audit schema and redaction tests."""

from __future__ import annotations

import logging

from friday.memory.conversations import ConversationRepository
from friday.memory.db import Database
from friday.security.redaction import register_secret
from friday.tools.audit import ToolAuditRepository


def test_migration_creates_tool_audit_table(tmp_path) -> None:
    database = Database(tmp_path / "friday.db")
    try:
        columns = [
            row[1]
            for row in database.connection.execute(
                "PRAGMA table_info(tool_audit)"
            ).fetchall()
        ]
        assert columns == [
            "id",
            "ts",
            "conversation_id",
            "tool",
            "args_json",
            "permission",
            "decision",
            "status",
            "error_kind",
            "duration_ms",
        ]
    finally:
        database.close()


def test_audit_rows_are_redacted_and_do_not_store_results(
    tmp_path, caplog
) -> None:
    caplog.set_level(logging.INFO)
    secret = "clipboard-secret-value-Q7"
    register_secret(secret)
    database = Database(tmp_path / "friday.db")
    try:
        repository = ToolAuditRepository(database)
        repository.record(
            conversation_id=None,
            tool="read_clipboard",
            args_json=f'{{"text": "{secret}"}}',
            permission="SENSITIVE",
            decision="approved",
            status="ok",
            error_kind=None,
            duration_ms=12,
            result_chars=len(secret),
        )
        rows = repository.recent()
        assert len(rows) == 1
        row = rows[0]
        assert row.tool == "read_clipboard"
        assert row.decision == "approved"
        assert row.status == "ok"
        assert row.duration_ms == 12
        assert secret not in row.args_json
        assert "***REDACTED***" in row.args_json
        assert not hasattr(row, "result")
        assert secret not in caplog.text
        assert "tool call tool=read_clipboard" in caplog.text
        assert f"result_chars={len(secret)}" in caplog.text
    finally:
        database.close()


def test_audit_recent_returns_newest_first_and_respects_limit(
    tmp_path,
) -> None:
    database = Database(tmp_path / "friday.db")
    try:
        repository = ToolAuditRepository(database)
        for index in range(25):
            repository.record(
                conversation_id=None,
                tool=f"tool_{index}",
                args_json="{}",
                permission="SAFE",
                decision="auto",
                status="ok",
                error_kind=None,
                duration_ms=index,
            )

        rows = repository.recent()
        assert len(rows) == 20
        assert rows[0].tool == "tool_24"
        assert rows[-1].tool == "tool_5"
    finally:
        database.close()


def test_deleting_conversation_sets_audit_conversation_to_null(
    tmp_path,
) -> None:
    database = Database(tmp_path / "friday.db")
    try:
        conversations = ConversationRepository(database)
        conversation_id = conversations.create_conversation("Audit chat")
        repository = ToolAuditRepository(database)
        repository.record(
            conversation_id=conversation_id,
            tool="get_time",
            args_json="{}",
            permission="SAFE",
            decision="auto",
            status="ok",
            error_kind=None,
            duration_ms=1,
        )
        conversations.delete(conversation_id)

        rows = repository.recent()
        assert len(rows) == 1
        assert rows[0].conversation_id is None
    finally:
        database.close()
