"""Main window for FRIDAY 2.0."""

import sys
from datetime import datetime, timezone

from PySide6.QtCore import QPoint, Qt, QTimer, Signal, Slot
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
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from friday.core.service import CoreService, parse_command
from friday.core.ui_bridge import QtUIBridge
from friday.memory.conversations import (
    STATUS_INCOMPLETE,
    Conversation,
    StoredMessage,
)
from friday.memory.facts import Fact
from friday.memory.search import SearchResult
from friday.ui.audio_player import AudioPlayer
from friday.ui.audio_recorder import AudioRecorder
from friday.ui.confirm_dialog import ConfirmDialog
from friday.ui.memory_dialog import MemoryDialog
from friday.ui.tools_dialog import ToolsDialog
from friday.ui.voice_input import (
    VOICE_COMPLETED,
    VOICE_ERROR,
    VOICE_IDLE,
    VOICE_PROCESSING,
    VOICE_RECORDING,
    VoiceInputController,
    VoiceInputResult,
)


def _speech_tooltip(engine: str) -> str:
    """Tooltip for the session-only speech checkbox."""
    suffix = (
        "Session setting: edit config.toml to change the default."
    )
    if engine == "windows":
        return f"Spoken offline on this PC. {suffix}"
    return f"Reply text is sent to Microsoft to create the voice. {suffix}"


def _relative_time(timestamp: str) -> str:
    """Format an ISO-8601 UTC timestamp for the conversation list."""
    try:
        then = datetime.fromisoformat(timestamp)
    except ValueError:
        return ""
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)

    seconds = int((datetime.now(timezone.utc) - then).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 7 * 86400:
        return f"{seconds // 86400}d ago"
    return then.astimezone().strftime("%b %d")


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
        self._conversations: dict[int, Conversation] = {}
        self._facts: list[Fact] = []
        self._search_results: list[SearchResult] = []
        self._search_active = False
        self._facts_list_pending = 0
        self._memory_dialog: MemoryDialog | None = None
        self._tools_dialog: ToolsDialog | None = None
        self._confirm_dialog: ConfirmDialog | None = None
        self._tool_lines: list[tuple[str, int]] = []
        self._current_conversation_id = 0
        self._ui_bridge = QtUIBridge(
            self._core.signals.confirm_requested, self
        )
        self._core.set_ui_bridge(self._ui_bridge)
        self._ui_bridge.clipboard_requested.connect(
            self._on_clipboard_requested
        )
        # Create AudioPlayer and connect bridge signals
        self._audio_player = AudioPlayer(self)
        self._ui_bridge.play_audio_requested.connect(self._on_play_audio_requested)
        self._ui_bridge.stop_audio_requested.connect(self._audio_player.stop)
        self._audio_player.play_finished.connect(self._ui_bridge.resolve_audio)
        self._audio_player.play_error.connect(
            lambda req_id, kind, msg: self._ui_bridge.resolve_audio(req_id, kind, msg)
        )
        self._setup_ui()
        self._voice_input = VoiceInputController(
            self._core,
            recorder_factory=self._create_recorder,
            before_record=self._before_voice_record,
            after_record=self._after_voice_record,
            parent=self,
        )
        self._voice_input.state_changed.connect(self._on_voice_state_changed)
        self._voice_input.result_ready.connect(self._on_voice_result)
        self._voice_input.failed.connect(self._on_voice_failed)
        self._voice_input.progress.connect(self._on_voice_progress)
        self._voice_input.notice.connect(self._on_voice_notice)
        self._voice_input.level_changed.connect(self._on_voice_level)
        self._on_voice_state_changed(VOICE_IDLE)
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("FRIDAY 2.0")
        self.resize(780, 640)

        central = QWidget()
        self.setCentralWidget(central)

        outer_layout = QHBoxLayout(central)
        outer_layout.setSpacing(12)
        outer_layout.setContentsMargins(12, 12, 12, 12)

        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(6)

        sidebar_title = QLabel("Conversations")
        sidebar_title.setStyleSheet(
            "font-size: 14px; font-weight: bold;"
        )
        sidebar_layout.addWidget(sidebar_title)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search chats...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_search_text_changed)
        sidebar_layout.addWidget(self._search_box)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self._run_search)

        self._conversation_list = QListWidget()
        self._conversation_list.setMinimumWidth(200)
        self._conversation_list.setMaximumWidth(260)
        self._conversation_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._conversation_list.customContextMenuRequested.connect(
            self._on_conversation_context_menu
        )
        self._conversation_list.itemClicked.connect(
            self._on_conversation_clicked
        )
        sidebar_layout.addWidget(self._conversation_list, 1)
        outer_layout.addWidget(sidebar)

        chat_panel = QWidget()
        layout = QVBoxLayout(chat_panel)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(chat_panel, 1)

        status_row = QHBoxLayout()
        self._status_label = QLabel("Core: running | Idle")
        self._status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        status_row.addWidget(self._status_label)

        self._facts_status_label = QLabel("Using 0 facts")
        status_row.addWidget(self._facts_status_label)
        status_row.addStretch(1)
        self._memory_button = QPushButton("Memory")
        self._memory_button.clicked.connect(self._on_memory_clicked)
        status_row.addWidget(self._memory_button)
        self._tools_button = QPushButton("Tools")
        self._tools_button.clicked.connect(self._on_tools_clicked)
        status_row.addWidget(self._tools_button)
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

        self._speak_checkbox = QCheckBox("Speak replies")
        self._speak_checkbox.setChecked(self._core.speech_enabled)
        self._speak_checkbox.setToolTip(
            _speech_tooltip(self._core.speech_engine)
        )
        self._speak_checkbox.toggled.connect(self._on_speak_toggled)
        button_row.addWidget(self._speak_checkbox)

        self._stop_speaking_button = QPushButton("Stop speaking")
        self._stop_speaking_button.setEnabled(False)
        self._stop_speaking_button.clicked.connect(
            self._on_stop_speaking_clicked
        )
        button_row.addWidget(self._stop_speaking_button)

        self._voice_button = QPushButton("Record voice")
        self._voice_button.setToolTip(
            "Record speech and insert the recognized text into the message "
            "box. Review and edit it before sending."
        )
        self._voice_button.clicked.connect(self._on_voice_clicked)
        button_row.addWidget(self._voice_button)

        self._voice_status_label = QLabel("Voice: idle")
        self._voice_status_label.setToolTip(
            "Voice input only fills the message box; it never sends or runs "
            "commands automatically."
        )
        button_row.addWidget(self._voice_status_label)

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
        self._core.signals.conversations_loaded.connect(
            self._on_conversations_loaded
        )
        self._core.signals.conversation_opened.connect(
            self._on_conversation_opened
        )
        self._core.signals.conversation_created.connect(
            self._on_conversation_created
        )
        self._core.signals.conversation_deleted.connect(
            self._on_conversation_deleted
        )
        self._core.signals.memory_error.connect(self._on_memory_error)
        self._core.signals.facts_used.connect(self._on_facts_used)
        self._core.signals.facts_loaded.connect(self._on_facts_loaded)
        self._core.signals.memory_notice.connect(self._on_memory_notice)
        self._core.signals.search_results.connect(self._on_search_results)
        self._core.signals.tool_started.connect(self._on_tool_started)
        self._core.signals.tool_finished.connect(self._on_tool_finished)
        self._core.signals.confirm_requested.connect(
            self._on_confirm_requested
        )
        # Speech signals
        self._core.signals.speech_started.connect(self._on_speech_started)
        self._core.signals.speech_finished.connect(self._on_speech_finished)
        self._core.signals.speech_error.connect(self._on_speech_error)
        self._core.signals.speech_notice.connect(self._on_speech_notice)

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

    def _tool_color(self) -> QColor:
        return self._palette_color(QPalette.ColorRole.Link)

    def _append_tool_started(self, name: str, args_summary: str) -> None:
        """Append a tool activity line and remember its cursor position."""
        if self._assistant_open:
            self._assistant_open = False
            self._assistant_has_tokens = False
        cursor = self._cursor_at_end()
        self._start_block(cursor)
        label = QTextCharFormat()
        label.setForeground(self._tool_color())
        label.setFontWeight(QFont.Weight.Bold)
        cursor.insertText("Tool: ", label)
        body = QTextCharFormat()
        body.setForeground(self._tool_color())
        cursor.insertText(f"{name}({args_summary})", body)
        position = cursor.position()
        self._commit(cursor)
        self._tool_lines.append((name, position))

    def _finish_tool_line(
        self, name: str, status: str, summary: str
    ) -> None:
        """Insert the real status after the matching tool activity line."""
        position = None
        for index in range(len(self._tool_lines) - 1, -1, -1):
            line_name, line_position = self._tool_lines[index]
            if line_name == name:
                position = line_position
                self._tool_lines.pop(index)
                break

        if position is None:
            cursor = self._cursor_at_end()
            self._start_block(cursor)
            status_format = QTextCharFormat()
            status_format.setForeground(
                self._error_color()
                if status in ("error", "denied")
                else self._tool_color()
            )
            status_format.setFontWeight(QFont.Weight.Bold)
            cursor.insertText(
                f"Tool: {name} -> {status}", status_format
            )
            if summary:
                cursor.insertText(f": {summary}", self._body_format())
            self._commit(cursor)
            return

        cursor = QTextCursor(self._transcript.document())
        cursor.setPosition(position)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        status_format = QTextCharFormat()
        status_format.setForeground(
            self._error_color()
            if status in ("error", "denied")
            else self._tool_color()
        )
        status_format.setFontWeight(QFont.Weight.Bold)
        cursor.insertText(f" -> {status}", status_format)
        if summary:
            cursor.insertText(f": {summary}", self._body_format())
        self._commit(self._cursor_at_end())

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

    def _append_notice(self, text: str) -> None:
        """Append a memory/command confirmation line."""
        cursor = self._cursor_at_end()
        self._start_block(cursor)
        label = QTextCharFormat()
        label.setForeground(self._palette_color(QPalette.ColorRole.Link))
        label.setFontWeight(QFont.Weight.Bold)
        cursor.insertText("Memory: ", label)
        cursor.insertText(text, self._body_format())
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

        command = parse_command(text)
        if command is not None:
            name, _ = command
            if name == "/facts":
                self._facts_list_pending += 1
            try:
                self._core.send_command(text)
            except Exception as exc:
                if name == "/facts" and self._facts_list_pending:
                    self._facts_list_pending -= 1
                self._append_error(exc.__class__.__name__, str(exc))
            return

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
        if self._streaming:
            self._output_label.setText(
                "Stop the current reply before starting a new chat."
            )
            return
        try:
            self._core.new_conversation()
        except Exception as exc:
            self._append_error(exc.__class__.__name__, str(exc))
            self._set_streaming(False)

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
        self._close_confirm_dialog()
        if self._assistant_open and self._assistant_has_tokens:
            self._insert_marker(" [incomplete]", self._error_color())
        self._assistant_open = False
        self._assistant_has_tokens = False
        self._tool_lines.clear()
        self._append_error(kind, message)
        self._set_streaming(False)
        self._output_label.setText(f"Request failed: {kind}")

    @Slot()
    def _on_chat_cancelled(self) -> None:
        self._close_confirm_dialog()
        if self._assistant_open:
            marker = " [cancelled]"
            if not self._assistant_has_tokens:
                marker = " [cancelled before any output]"
            self._insert_marker(marker, self._cancelled_color())
        self._assistant_open = False
        self._assistant_has_tokens = False
        self._tool_lines.clear()
        self._set_streaming(False)
        self._output_label.setText("Reply cancelled")

    # ------------------------------------------------------------------
    # Tool slots
    # ------------------------------------------------------------------
    @Slot(str, str)
    def _on_tool_started(self, name: str, args_summary: str) -> None:
        self._append_tool_started(name, args_summary)
        self._status_label.setText("Core: running | Running tool…")
        self._output_label.setText("Running tool…")

    @Slot(str, str, str)
    def _on_tool_finished(
        self, name: str, status: str, summary: str
    ) -> None:
        self._finish_tool_line(name, status, summary)
        state = "Streaming..." if self._streaming else "Idle"
        self._status_label.setText(f"Core: running | {state}")
        detail = f": {summary}" if summary else ""
        self._output_label.setText(f"Tool {name} -> {status}{detail}")

    @Slot(str, str, str, str)
    def _on_confirm_requested(
        self,
        request_id: str,
        tool: str,
        description: str,
        args_summary: str,
    ) -> None:
        self._output_label.setText(f"Waiting for approval: {tool}")
        dialog = ConfirmDialog(
            tool, description, args_summary, self
        )
        self._confirm_dialog = dialog
        try:
            approved = dialog.exec() == QDialog.DialogCode.Accepted
        finally:
            self._confirm_dialog = None
            dialog.deleteLater()
        self._core.confirm_response(request_id, approved)

    @Slot(str)
    def _on_clipboard_requested(self, request_id: str) -> None:
        """Read the clipboard on the UI thread and resolve the bridge."""
        text: str | None = None
        try:
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                mime_data = clipboard.mimeData()
                if mime_data is not None and mime_data.hasText():
                    text = clipboard.text()
        except Exception:
            text = None
        self._ui_bridge.resolve_clipboard(request_id, text)

    @Slot(str, str)
    def _on_play_audio_requested(self, request_id: str, path: str) -> None:
        """Handle play audio request from the bridge."""
        if self._core.is_microphone_active:
            # A request queued just before the gate opened must not play
            # into the microphone; resolve it without touching the player.
            self._ui_bridge.resolve_audio(request_id)
            return
        self._audio_player.play(path, request_id)

    @Slot()
    def _on_speech_started(self) -> None:
        """Speech playback started."""
        self._status_label.setText("Core: running | Speaking…")
        self._stop_speaking_button.setEnabled(True)

    def _clear_speaking_status(self) -> None:
        """Restore the normal status line after speech ended."""
        state = "Streaming…" if self._streaming else "Idle"
        self._status_label.setText(f"Core: running | {state}")

    @Slot()
    def _on_speech_finished(self) -> None:
        """Speech playback finished."""
        self._stop_speaking_button.setEnabled(False)
        self._clear_speaking_status()

    @Slot(str, str)
    def _on_speech_error(self, kind: str, message: str) -> None:
        """Speech playback error."""
        self._stop_speaking_button.setEnabled(False)
        self._clear_speaking_status()
        self._append_error(kind, message)
        self._output_label.setText(f"Speech error: {kind}")

    @Slot(bool)
    def _on_speak_toggled(self, checked: bool) -> None:
        """Apply the session speech setting to the core service."""
        self._core.set_speech_enabled_sync(checked)

    @Slot()
    def _on_stop_speaking_clicked(self) -> None:
        """Stop the current speech from the UI thread."""
        self._stop_speaking_button.setEnabled(False)
        self._core.stop_speaking()

    @Slot(str)
    def _on_speech_notice(self, message: str) -> None:
        """Speech notice (e.g., privacy skip)."""
        self._append_notice(message)
        self._output_label.setText(message)

    # ------------------------------------------------------------------
    # Voice-input slots
    # ------------------------------------------------------------------
    def _create_recorder(self) -> AudioRecorder:
        """Build the UI-thread recorder from the configured voice options."""
        return AudioRecorder(**self._core.recording_options)

    def _before_voice_record(self) -> None:
        """Close Aria's mouth before the microphone opens (UI thread)."""
        self._core.set_microphone_active(True)
        self._core.stop_speaking()
        self._audio_player.stop()

    def _after_voice_record(self) -> None:
        """Reopen speech once the microphone is closed."""
        self._core.set_microphone_active(False)

    @Slot()
    def _on_voice_clicked(self) -> None:
        """Start, stop, or cancel voice input depending on the state."""
        try:
            self._voice_input.toggle()
        except Exception as exc:
            self._append_error(exc.__class__.__name__, str(exc))
            self._output_label.setText("Voice input failed")

    @Slot(str)
    def _on_voice_state_changed(self, state: str) -> None:
        labels = {
            VOICE_IDLE: "Voice: idle",
            VOICE_RECORDING: "Voice: listening...",
            VOICE_PROCESSING: "Voice: transcribing...",
            VOICE_COMPLETED: "Voice: ready - edit and send",
            VOICE_ERROR: "Voice: error - try again",
        }
        buttons = {
            VOICE_IDLE: "Record voice",
            VOICE_RECORDING: "Stop & transcribe",
            VOICE_PROCESSING: "Cancel transcription",
            VOICE_COMPLETED: "Record again",
            VOICE_ERROR: "Try again",
        }
        self._voice_status_label.setText(labels.get(state, "Voice"))
        self._voice_button.setText(buttons.get(state, "Record voice"))
        self._voice_button.setEnabled(self._core.is_running)
        if state == VOICE_RECORDING:
            self._output_label.setText(
                "Listening... click the microphone button again to stop."
            )
        elif state == VOICE_PROCESSING:
            self._output_label.setText("Transcribing speech...")

    @Slot(object)
    def _on_voice_result(self, result: VoiceInputResult) -> None:
        """Insert recognized text for editing; never send it automatically."""
        self._insert_voice_text(result.text)
        language = result.language or "unknown"
        self._output_label.setText(
            f"Voice ready ({language}, "
            f"{result.language_probability:.0%}): edit and send."
        )

    @Slot(str, str)
    def _on_voice_failed(self, kind: str, message: str) -> None:
        self._append_error(kind, message)
        self._output_label.setText(f"Voice input failed: {kind}")

    @Slot(str)
    def _on_voice_progress(self, message: str) -> None:
        if self._voice_input.state in (VOICE_RECORDING, VOICE_PROCESSING):
            short = message.strip()
            if len(short) > 48:
                short = short[:45].rstrip() + "..."
            self._voice_status_label.setText(f"Voice: {short}")
            self._voice_status_label.setToolTip(message)

    @Slot(str)
    def _on_voice_notice(self, message: str) -> None:
        self._output_label.setText(message)

    @Slot(float)
    def _on_voice_level(self, level: float) -> None:
        if self._voice_input.state == VOICE_RECORDING:
            self._voice_status_label.setText(
                f"Voice: listening... {int(max(0.0, min(1.0, level)) * 100)}%"
            )

    def _insert_voice_text(self, text: str) -> None:
        """Append recognized text to the chat input as editable text."""
        cleaned = text.strip()
        if not cleaned:
            return
        existing = self._input.toPlainText()
        if existing and not existing.endswith((" ", "\n", "\t")):
            cleaned = " " + cleaned
        cursor = self._input.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._input.setTextCursor(cursor)
        self._input.insertPlainText(cleaned)
        self._input.setFocus()

    def _close_confirm_dialog(self) -> None:
        dialog = self._confirm_dialog
        if dialog is not None:
            dialog.reject()

    @Slot()
    def _on_tools_clicked(self) -> None:
        if not self._core.is_running:
            self._append_error(
                "CoreNotRunning", "Tools are unavailable while core is stopped."
            )
            return
        dialog = ToolsDialog(self._core, self)
        self._tools_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._tools_dialog = None
            dialog.deleteLater()

    @Slot()
    def _on_tools_loaded(self, tools: list, rows: list) -> None:
        if self._tools_dialog is not None:
            self._tools_dialog.set_contents(tools, rows)

    # ------------------------------------------------------------------
    # Conversation slots
    # ------------------------------------------------------------------
    @Slot(list)
    def _on_conversations_loaded(
        self, conversations: list[Conversation]
    ) -> None:
        self._conversations = {
            conversation.id: conversation for conversation in conversations
        }
        if not self._search_active:
            self._render_conversations(conversations)

    def _render_conversations(
        self, conversations: list[Conversation]
    ) -> None:
        self._conversation_list.clear()
        for conversation in conversations:
            item = QListWidgetItem(
                f"{conversation.title}   "
                f"{_relative_time(conversation.updated_at)}"
            )
            item.setData(
                Qt.ItemDataRole.UserRole, conversation.id
            )
            item.setToolTip(conversation.title)
            self._conversation_list.addItem(item)
        self._select_conversation(self._current_conversation_id)

    @Slot(str)
    def _on_search_text_changed(self, text: str) -> None:
        if not text.strip():
            self._search_timer.stop()
            self._search_active = False
            self._search_results = []
            self._render_conversations(list(self._conversations.values()))
            return
        self._search_timer.start()

    @Slot()
    def _run_search(self) -> None:
        query = self._search_box.text().strip()
        if not query:
            self._search_active = False
            self._render_conversations(list(self._conversations.values()))
            return
        try:
            self._core.search_chats(query)
        except Exception as exc:
            self._search_active = False
            self._append_error(exc.__class__.__name__, str(exc))
            self._render_conversations(list(self._conversations.values()))

    @Slot(list)
    def _on_search_results(self, results: list[SearchResult]) -> None:
        if not self._search_box.text().strip():
            self._search_active = False
            self._render_conversations(list(self._conversations.values()))
            return
        self._search_active = True
        self._search_results = list(results)
        self._conversation_list.clear()
        for result in self._search_results:
            snippet = result.snippet or result.role
            item = QListWidgetItem(
                f"{result.conversation_title}\n"
                f"{snippet}   {_relative_time(result.created_at)}"
            )
            item.setData(
                Qt.ItemDataRole.UserRole, result.conversation_id
            )
            item.setToolTip(snippet)
            self._conversation_list.addItem(item)
        self._select_conversation(self._current_conversation_id)

    @Slot(int, list)
    def _on_conversation_opened(
        self, conversation_id: int, messages: list[StoredMessage]
    ) -> None:
        self._current_conversation_id = conversation_id
        self._render_messages(messages)
        self._select_conversation(conversation_id)
        if conversation_id == 0:
            self._output_label.setText("New chat")
        else:
            self._output_label.setText(
                f"Opened conversation "
                f"({len(messages)} messages)"
            )

    @Slot(int, str)
    def _on_conversation_created(
        self, conversation_id: int, title: str
    ) -> None:
        self._current_conversation_id = conversation_id
        self._select_conversation(conversation_id)

    @Slot(int)
    def _on_conversation_deleted(self, conversation_id: int) -> None:
        if conversation_id == self._current_conversation_id:
            self._current_conversation_id = 0
            self._assistant_open = False
            self._assistant_has_tokens = False
            self._transcript.clear()
            self._set_streaming(False)
        self._output_label.setText("Conversation deleted")
        if self._search_active:
            self._run_search()

    @Slot(str, str)
    def _on_memory_error(self, kind: str, message: str) -> None:
        self._facts_list_pending = 0
        self._append_error(kind, message)
        self._output_label.setText(f"Memory error: {kind}")

    @Slot(int)
    def _on_facts_used(self, count: int) -> None:
        self._facts_status_label.setText(f"Using {count} facts")

    @Slot(list)
    def _on_facts_loaded(self, facts: list[Fact]) -> None:
        self._facts = list(facts)
        if self._memory_dialog is not None:
            self._memory_dialog.set_facts(self._facts)
        if self._facts_list_pending > 0:
            self._facts_list_pending -= 1
            self._append_facts_list(self._facts)

    def _append_facts_list(self, facts: list[Fact]) -> None:
        if not facts:
            self._append_notice("No facts saved.")
            return
        lines = [f"Facts ({len(facts)}):"]
        lines.extend(f"{fact.id}. {fact.content}" for fact in facts)
        self._append_notice("\n".join(lines))

    @Slot(str)
    def _on_memory_notice(self, text: str) -> None:
        self._append_notice(text)
        self._output_label.setText(text)

    @Slot()
    def _on_memory_clicked(self) -> None:
        if not self._core.is_running:
            self._append_error(
                "CoreNotRunning", "Memory is unavailable while core is stopped."
            )
            return
        try:
            self._core.refresh_facts()
        except Exception as exc:
            self._append_error(exc.__class__.__name__, str(exc))
            return
        dialog = MemoryDialog(self._core, self._facts, self)
        self._memory_dialog = dialog
        try:
            dialog.exec()
        finally:
            self._memory_dialog = None
            dialog.deleteLater()

    def _on_conversation_clicked(self, item: QListWidgetItem) -> None:
        conversation_id = item.data(Qt.ItemDataRole.UserRole)
        if conversation_id is None:
            return
        if self._streaming:
            self._output_label.setText(
                "Stop the current reply before opening another conversation."
            )
            self._select_conversation(self._current_conversation_id)
            return
        try:
            self._core.open_conversation(int(conversation_id))
        except Exception as exc:
            self._append_error(exc.__class__.__name__, str(exc))

    @Slot(QPoint)
    def _on_conversation_context_menu(self, position) -> None:
        item = self._conversation_list.itemAt(position)
        if item is None:
            return
        conversation_id = item.data(Qt.ItemDataRole.UserRole)
        if conversation_id is None:
            return
        conversation = self._conversations.get(int(conversation_id))
        if conversation is None:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        delete_action = menu.addAction("Delete")
        chosen = menu.exec(
            self._conversation_list.viewport().mapToGlobal(position)
        )
        if chosen == rename_action:
            self._rename_conversation(conversation)
        elif chosen == delete_action:
            self._delete_conversation(conversation)

    def _rename_conversation(self, conversation: Conversation) -> None:
        title, accepted = QInputDialog.getText(
            self,
            "Rename conversation",
            "Title:",
            QLineEdit.EchoMode.Normal,
            conversation.title,
        )
        if not accepted:
            return
        title = title.strip()
        if not title:
            self._output_label.setText("Conversation title cannot be empty.")
            return
        try:
            self._core.rename_conversation(conversation.id, title)
        except Exception as exc:
            self._append_error(exc.__class__.__name__, str(exc))

    def _delete_conversation(self, conversation: Conversation) -> None:
        if self._streaming:
            self._output_label.setText(
                "Stop the current reply before deleting a conversation."
            )
            return
        answer = QMessageBox.question(
            self,
            "Delete conversation",
            f'Delete "{conversation.title}" and all of its messages?',
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._core.delete_conversation(conversation.id)
        except Exception as exc:
            self._append_error(exc.__class__.__name__, str(exc))

    def _select_conversation(self, conversation_id: int) -> None:
        for row in range(self._conversation_list.count()):
            item = self._conversation_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == conversation_id:
                self._conversation_list.setCurrentItem(item)
                return

    def _render_messages(self, messages: list[StoredMessage]) -> None:
        self._transcript.clear()
        self._assistant_open = False
        self._assistant_has_tokens = False
        for message in messages:
            if message.role == "user":
                self._append_user(message.content)
            elif message.role == "assistant":
                self._begin_assistant()
                if message.content:
                    self._append_token(message.content)
                self._assistant_open = False
                self._assistant_has_tokens = False
                if message.status == STATUS_INCOMPLETE:
                    self._insert_marker(
                        " (incomplete)", self._error_color()
                    )
        self._set_streaming(False)

    # ------------------------------------------------------------------
    # Core status / ping slots
    # ------------------------------------------------------------------
    @Slot()
    def _on_core_started(self) -> None:
        self._status_label.setText("Core: running | Idle")
        self._ping_button.setEnabled(True)
        self._voice_button.setEnabled(True)

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
        self._memory_button.setEnabled(False)
        self._tools_button.setEnabled(False)
        self._send_button.setEnabled(False)
        self._stop_button.setEnabled(False)
        self._new_chat_button.setEnabled(False)
        self._stop_speaking_button.setEnabled(False)
        self._voice_button.setEnabled(False)

    def set_core_failed(self, message: str) -> None:
        """Mark the core as failed and disable core-dependent controls."""
        self._status_label.setText(f"Core: failed - {message}")
        self._ping_button.setEnabled(False)
        self._memory_button.setEnabled(False)
        self._tools_button.setEnabled(False)
        self._send_button.setEnabled(False)
        self._stop_button.setEnabled(False)
        self._new_chat_button.setEnabled(False)
        self._conversation_list.setEnabled(False)
        self._stop_speaking_button.setEnabled(False)
        self._speak_checkbox.setEnabled(False)
        self._voice_button.setEnabled(False)

    def closeEvent(self, event) -> None:
        """Deny pending requests and stop the core on window close."""
        self._close_confirm_dialog()
        # Discard a recording and stop speech before tearing the core down.
        self._voice_input.dispose()
        self._core.stop_speaking()
        self._ui_bridge.shutdown()
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
