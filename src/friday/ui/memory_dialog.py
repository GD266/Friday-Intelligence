"""Memory facts dialog. Storage calls go through the core service."""

from __future__ import annotations

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from friday.memory.facts import MAX_FACTS, Fact


class MemoryDialog(QDialog):
    """List, add, edit, and delete user facts."""

    def __init__(self, core_service, facts: list[Fact], parent=None) -> None:
        super().__init__(parent)
        self._core = core_service
        self._facts: list[Fact] = []
        self._setup_ui()
        self.set_facts(facts)
        self._core.signals.memory_error.connect(self._on_memory_error)

    def _setup_ui(self) -> None:
        self.setWindowTitle("Memory")
        self.resize(560, 380)

        layout = QVBoxLayout(self)
        self._count_label = QLabel()
        layout.addWidget(self._count_label)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._on_edit)
        self._list.currentItemChanged.connect(self._update_buttons)
        layout.addWidget(self._list, 1)

        button_row = QHBoxLayout()
        self._add_button = QPushButton("Add")
        self._add_button.clicked.connect(self._on_add)
        button_row.addWidget(self._add_button)

        self._edit_button = QPushButton("Edit")
        self._edit_button.clicked.connect(self._on_edit)
        button_row.addWidget(self._edit_button)

        self._delete_button = QPushButton("Delete")
        self._delete_button.clicked.connect(self._on_delete)
        button_row.addWidget(self._delete_button)

        button_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)
        self._update_buttons()

    def set_facts(self, facts: list[Fact]) -> None:
        """Replace the displayed fact list."""
        selected_id = None
        current = self._list.currentItem()
        if current is not None:
            selected_id = current.data(Qt.ItemDataRole.UserRole)

        self._facts = list(facts)
        self._list.clear()
        for fact in self._facts:
            item = QListWidgetItem(f"{fact.id}. {fact.content}")
            item.setData(Qt.ItemDataRole.UserRole, fact.id)
            item.setToolTip(fact.content)
            self._list.addItem(item)
            if fact.id == selected_id:
                self._list.setCurrentItem(item)

        count = len(self._facts)
        if count == 0:
            self._count_label.setText(
                f"No facts saved (maximum {MAX_FACTS})"
            )
        else:
            noun = "fact" if count == 1 else "facts"
            self._count_label.setText(
                f"{count} {noun} (maximum {MAX_FACTS})"
            )
        self._update_buttons()

    def _selected_fact(self) -> Fact | None:
        item = self._list.currentItem()
        if item is None:
            return None
        fact_id = item.data(Qt.ItemDataRole.UserRole)
        return next(
            (fact for fact in self._facts if fact.id == fact_id), None
        )

    @Slot()
    def _update_buttons(self) -> None:
        has_selection = self._selected_fact() is not None
        self._edit_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)

    @Slot()
    def _on_add(self) -> None:
        text, accepted = QInputDialog.getText(
            self,
            "Add fact",
            "Fact:",
            QLineEdit.EchoMode.Normal,
            "",
        )
        if accepted:
            self._core.add_fact(text)

    @Slot()
    def _on_edit(self) -> None:
        fact = self._selected_fact()
        if fact is None:
            return
        text, accepted = QInputDialog.getText(
            self,
            "Edit fact",
            "Fact:",
            QLineEdit.EchoMode.Normal,
            fact.content,
        )
        if accepted:
            self._core.update_fact(fact.id, text)

    @Slot()
    def _on_delete(self) -> None:
        fact = self._selected_fact()
        if fact is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete fact",
            f"Delete this fact?\n\n{fact.content}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._core.delete_fact(fact.id)

    @Slot(str, str)
    def _on_memory_error(self, kind: str, message: str) -> None:
        QMessageBox.warning(self, "Memory error", f"{kind}: {message}")
