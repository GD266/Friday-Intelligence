"""Read-only Tools overview: registered tools and recent audit rows."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from friday.tools.audit import ToolAuditEntry
from friday.tools.registry import ToolInfo


def _short_time(timestamp: str) -> str:
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return timestamp
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


class ToolsDialog(QDialog):
    """Show registered tools and the last 20 audit rows."""

    def __init__(self, core_service, parent=None) -> None:
        super().__init__(parent)
        self._core = core_service
        self._setup_ui()
        self._core.signals.tools_loaded.connect(self.set_contents)
        try:
            self._core.refresh_tools()
        except Exception as exc:
            self._status_label.setText(f"Could not load tools: {exc}")

    def _setup_ui(self) -> None:
        self.setWindowTitle("Tools")
        self.resize(720, 480)
        layout = QVBoxLayout(self)

        self._status_label = QLabel("Registered tools")
        self._status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._status_label)

        self._tools_list = QListWidget()
        layout.addWidget(self._tools_list, 1)

        audit_label = QLabel("Recent tool calls (last 20)")
        audit_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(audit_label)

        self._audit_table = QTableWidget(0, 4)
        self._audit_table.setHorizontalHeaderLabels(
            ["Time", "Tool", "Decision", "Status"]
        )
        self._audit_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._audit_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._audit_table, 2)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

    @Slot(list, list)
    def set_contents(
        self,
        tools: list[ToolInfo],
        rows: list[ToolAuditEntry],
    ) -> None:
        """Replace the displayed tool and audit lists."""
        self._tools_list.clear()
        for tool in tools:
            confirmation = (
                "confirmation required"
                if tool.requires_confirmation
                else "no confirmation"
            )
            item = QListWidgetItem(
                f"{tool.name} — {tool.permission} — {confirmation}"
            )
            item.setToolTip(tool.description)
            self._tools_list.addItem(item)
        self._status_label.setText(
            f"Registered tools ({len(tools)})"
        )

        self._audit_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                _short_time(row.ts),
                row.tool,
                row.decision,
                row.status,
            ]
            for column, value in enumerate(values):
                self._audit_table.setItem(
                    row_index, column, QTableWidgetItem(value)
                )
        self._audit_table.resizeColumnsToContents()


__all__ = ["ToolsDialog"]
