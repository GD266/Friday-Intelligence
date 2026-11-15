"""Modal confirmation dialog for tool calls."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class ConfirmDialog(QDialog):
    """Ask the user to approve or deny one tool call. Deny is the default."""

    def __init__(
        self,
        tool: str,
        description: str,
        arguments: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.tool_name = tool
        self.description = description
        self.arguments = arguments
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Approve tool action")
        self.setModal(True)
        self.resize(520, 320)

        layout = QVBoxLayout(self)
        title = QLabel(f"Tool: {self.tool_name}")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel(self.description)
        description.setWordWrap(True)
        layout.addWidget(description)

        arguments_label = QLabel("Arguments")
        arguments_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(arguments_label)

        self._arguments_view = QPlainTextEdit()
        self._arguments_view.setReadOnly(True)
        self._arguments_view.setPlainText(self.arguments or "{}")
        self._arguments_view.setFixedHeight(90)
        layout.addWidget(self._arguments_view)

        layout.addStretch(1)
        button_row = QHBoxLayout()
        button_row.addStretch(1)

        self._approve_button = QPushButton("Approve")
        self._approve_button.setAutoDefault(False)
        self._approve_button.clicked.connect(self.accept)

        self._deny_button = QPushButton("Deny")
        self._deny_button.setDefault(True)
        self._deny_button.setAutoDefault(True)
        self._deny_button.clicked.connect(self.reject)

        button_row.addWidget(self._approve_button)
        button_row.addWidget(self._deny_button)
        layout.addLayout(button_row)

        self._deny_button.setFocus(Qt.FocusReason.OtherFocusReason)


__all__ = ["ConfirmDialog"]
