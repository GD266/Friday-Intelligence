"""Main window for FRIDAY 2.0."""

import sys

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QPalette,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from friday.core.service import CoreService


class ChatInput(QPlainTextEdit):
    """Multi-line input: Enter sends, Shift+Enter inserts a newline."""

    submit = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        is_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if is_enter and not shift:
            self.submit.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, core_service: CoreService):
        super().__init__()
        self._core = core_service
        self._streaming = False
        self._assistant_open = False
        self._assistant_has_tokens = False
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("FRIDAY 2.0")
        self.resize(780, 640)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        status_row = QHBoxLayout()
        self._status_label = QLabel("Core: running | Idle")
        self._status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        status_row.addWidget(self._status_label)
        status_row.addStretch(1)
        self._ping_button = QPushButton("Ping core")
        self._ping_button.clicked.connect(self._on_ping_clicked)
        status_row.addWidget(self._ping_button)
        layout.addLayout(status_row)

        self._output_label = QLabel("Output will appear here...")
        self._output_label.setWordWrap(True)
        self._output_label.setStyleSheet(
            "font-family: monospace; font-size: 12px;"
        )
        layout.addWidget(self._output_label)

        self._transcript = QTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setStyleSheet(
            "QTextEdit { border: 1px solid palette(mid); "
            "border-radius: 4px; padding: 8px; }"
        )
        layout.addWidget(self._transcript, 1)

        self._input = ChatInput()
        self._input.setPlaceholderText(
            "Type a message... (Enter sends, Shift+Enter adds a newline)"
        )
        self._input.setFixedHeight(80)
        self._input.submit.connect(self._on_send_clicked)
        layout.addWidget(self._input)

        button_row = QHBoxLayout()
        self._send_button = QPushButton("Send")
        self._send_button.clicked.connect(self._on_send_clicked)
        button_row.addWidget(self._send_button)

        self._stop_button = QPushButton("Stop")
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._on_stop_clicked)
        button_row.addWidget(self._stop_button)

        self._new_chat_button = QPushButton("New chat")
        self._new_chat_button.clicked.connect(self._on_new_chat_clicked)
        button_row.addWidget(self._new_chat_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)

    def _connect_signals(self) -> None:
        """Connect core service signals to UI slots."""
        self._core.signals.started.connect(self._on_core_started)
        self._core.signals.stopped.connect(self._on_core_stopped)
        self._core.signals.pong_received.connect(self._on_pong_received)
        self._core.signals.error_occurred.connect(self._on_error)
        self._core.signals.token.connect(self._on_token)
        self._core.signals.message_done.connect(self._on_message_done)
        self._core.signals.chat_error.connect(self._on_chat_error)
        self._core.signals.chat_cancelled.connect(self._on_chat_cancelled)

    # ------------------------------------------------------------------
    # Transcript helpers
    # ------------------------------------------------------------------
    def _cursor_at_end(self) -> QTextCursor:
        cursor = self._transcript.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        return cursor

    def _start_block(self, cursor: QTextCursor) -> None:
        if not self._transcript.document().isEmpty():
            cursor.insertBlock()

    def _commit(self, cursor: QTextCursor) -> None:
        self._transcript.setTextCursor(cursor)
        self._transcript.ensureCursorVisible()

    def _palette_color(self, role: QPalette.ColorRole) -> QColor:
        return self.palette().color(role)

    def _body_format(self) -> QTextCharFormat:
        text_format = QTextCharFormat()
        text_format.setForeground(
            self._palette_color(QPalette.ColorRole.Text)
        )
        return text_format

    def _is_dark_theme(self) -> bool:
        return (
            self._palette_color(QPalette.ColorRole.Base).lightness() < 128
        )

    def _error_color(self) -> QColor:
        if self._is_dark_theme():
            return QColor("#ff7b72")
        return QColor("#b00020")

    def _cancelled_color(self) -> QColor:
        if self._is_dark_theme():
            return QColor("#e6b450")
        return QColor("#8a6d00")

    def _append_user(self, text: str) -> None:
        cursor = self._cursor_at_end()
        self._start_block(cursor)
        label = QTextCharFormat()
        label.setForeground(self._palette_color(QPalette.ColorRole.Link))
        label.setFontWeight(QFont.Weight.Bold)
        cursor.insertText("You: ", label)
        cursor.insertText(text, self._body_format())
        self._commit(cursor)

    def _begin_assistant(self) -> None:
        cursor = self._cursor_at_end()
        self._start_block(cursor)
        label = QTextCharFormat()
        label.setForeground(self._palette_color(QPalette.ColorRole.Text))
        label.setFontWeight(QFont.Weight.Bold)
        cursor.insertText("FRIDAY: ", label)
        cursor.setCharFormat(self._body_format())
        self._commit(cursor)
        self._assistant_open = True
        self._assistant_has_tokens = False

    def _append_token(self, text: str) -> None:
        if not self._assistant_open:
            self._begin_assistant()
        cursor = self._cursor_at_end()
        cursor.insertText(text, self._body_format())
        self._commit(cursor)
        self._assistant_has_tokens = True

    def _insert_marker(self, text: str, color: QColor) -> None:
        cursor = self._cursor_at_end()
        marker = QTextCharFormat()
        marker.setForeground(color)
        marker.setFontItalic(True)
        cursor.insertText(text, marker)
        self._commit(cursor)

    def _append_error(self, kind: str, message: str) -> None:
        cursor = self._cursor_at_end()
        self._start_block(cursor)
        error_color = self._error_color()
        label = QTextCharFormat()
        label.setForeground(error_color)
        label.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(f"Error [{kind}]: ", label)
        body = QTextCharFormat()
        body.setForeground(error_color)
        cursor.insertText(message, body)
        self._commit(cursor)

    # ------------------------------------------------------------------
    # Streaming state
    # ------------------------------------------------------------------
    def _set_streaming(self, streaming: bool) -> None:
        self._streaming = streaming
        self._send_button.setEnabled(not streaming)
        self._stop_button.setEnabled(streaming)
        if self._core.is_running:
            state = "Streaming..." if streaming else "Idle"
            self._status_label.setText(f"Core: running | {state}")

    # ------------------------------------------------------------------
    # Chat slots
    # ------------------------------------------------------------------
    @Slot()
    def _on_send_clicked(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return

        self._input.clear()
        self._append_user(text)
        self._begin_assistant()
        self._set_streaming(True)

        try:
            self._core.chat_send(text)
        except Exception as exc:
            self._assistant_open = False
            self._append_error(exc.__class__.__name__, str(exc))
            self._set_streaming(False)

    @Slot()
    def _on_stop_clicked(self) -> None:
        self._output_label.setText("Cancelling...")
        self._core.cancel_chat()

    @Slot()
    def _on_new_chat_clicked(self) -> None:
        self._core.clear_chat()
        self._transcript.clear()
        self._assistant_open = False
        self._assistant_has_tokens = False
        self._set_streaming(False)
        self._output_label.setText("New chat")

    @Slot(str)
    def _on_token(self, text: str) -> None:
        self._append_token(text)

    @Slot(str)
    def _on_message_done(self, full_text: str) -> None:
        self._assistant_open = False
        self._set_streaming(False)
        self._output_label.setText(
            f"Reply complete ({len(full_text)} characters)"
        )

    @Slot(str, str)
    def _on_chat_error(self, kind: str, message: str) -> None:
        if self._assistant_open and self._assistant_has_tokens:
            self._insert_marker(" [incomplete]", self._error_color())
        self._assistant_open = False
        self._assistant_has_tokens = False
        self._append_error(kind, message)
        self._set_streaming(False)
        self._output_label.setText(f"Request failed: {kind}")

    @Slot()
    def _on_chat_cancelled(self) -> None:
        if self._assistant_open:
            marker = " [cancelled]"
            if not self._assistant_has_tokens:
                marker = " [cancelled before any output]"
            self._insert_marker(marker, self._cancelled_color())
        self._assistant_open = False
        self._assistant_has_tokens = False
        self._set_streaming(False)
        self._output_label.setText("Reply cancelled")

    # ------------------------------------------------------------------
    # Core status / ping slots
    # ------------------------------------------------------------------
    @Slot()
    def _on_core_started(self) -> None:
        self._status_label.setText("Core: running | Idle")
        self._ping_button.setEnabled(True)

    @Slot()
    def _on_ping_clicked(self) -> None:
        try:
            self._core.send_ping("ui-ping")
            self._output_label.setText("Sent ping...")
        except Exception as e:
            self._output_label.setText(f"Error sending ping: {e}")

    @Slot(str)
    def _on_pong_received(self, message: str) -> None:
        self._output_label.setText(message)

    @Slot(str)
    def _on_error(self, error: str) -> None:
        self._append_error("CoreError", error)
        self._status_label.setText("Core: error")

    @Slot()
    def _on_core_stopped(self) -> None:
        self._status_label.setText("Core: stopped")
        self._ping_button.setEnabled(False)
        self._send_button.setEnabled(False)
        self._stop_button.setEnabled(False)

    def set_core_failed(self, message: str) -> None:
        """Mark the core as failed and disable core-dependent controls."""
        self._status_label.setText(f"Core: failed - {message}")
        self._ping_button.setEnabled(False)
        self._send_button.setEnabled(False)
        self._stop_button.setEnabled(False)

    def closeEvent(self, event) -> None:
        """Handle window close event."""
        self._core.stop()
        event.accept()


def create_application() -> QApplication:
    """Create and configure the QApplication."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("FRIDAY 2.0")
    app.setApplicationVersion("0.1.0")
    return app
