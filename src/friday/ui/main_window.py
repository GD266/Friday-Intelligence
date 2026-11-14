"""Main window for FRIDAY 2.0."""

import sys

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from friday.core.service import CoreService


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, core_service: CoreService):
        super().__init__()
        self._core = core_service
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("FRIDAY 2.0")
        self.resize(600, 400)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Layout
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Status label
        self._status_label = QLabel("Core: running")
        self._status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self._status_label)

        # Ping button
        self._ping_button = QPushButton("Ping core")
        self._ping_button.setFixedHeight(40)
        self._ping_button.clicked.connect(self._on_ping_clicked)
        layout.addWidget(self._ping_button)

        # Output label
        self._output_label = QLabel("Output will appear here...")
        self._output_label.setWordWrap(True)
        self._output_label.setStyleSheet(
            "font-family: monospace; font-size: 13px; "
            "background-color: #f5f5f5; padding: 12px; border-radius: 4px;"
        )
        self._output_label.setMinimumHeight(200)
        layout.addWidget(self._output_label, 1)

    def _connect_signals(self) -> None:
        """Connect core service signals to UI slots."""
        self._core.signals.pong_received.connect(self._on_pong_received)
        self._core.signals.error_occurred.connect(self._on_error)
        self._core.signals.stopped.connect(self._on_core_stopped)

    @Slot()
    def _on_ping_clicked(self) -> None:
        """Handle ping button click."""
        try:
            self._core.send_ping("ui-ping")
            self._output_label.setText("Sent ping...")
        except Exception as e:
            self._output_label.setText(f"Error sending ping: {e}")

    @Slot(str)
    def _on_pong_received(self, message: str) -> None:
        """Handle pong from core."""
        self._output_label.setText(message)

    @Slot(str)
    def _on_error(self, error: str) -> None:
        """Handle error from core."""
        self._output_label.setText(f"Core error: {error}")
        self._status_label.setText("Core: error")

    @Slot()
    def _on_core_stopped(self) -> None:
        """Handle core stopped."""
        self._status_label.setText("Core: stopped")
        self._ping_button.setEnabled(False)

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
