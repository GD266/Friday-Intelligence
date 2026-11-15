"""UI-thread audio player using QMediaPlayer + QAudioOutput."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class AudioPlayer(QObject):
    """Audio player that lives on the UI thread.

    - play(path, request_id): start playback
    - stop(): stop current playback
    Signals: play_finished(request_id), play_error(request_id, kind, message)
    """

    play_finished = Signal(str)
    play_error = Signal(str, str, str)  # request_id, kind, message

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player: QMediaPlayer | None = None
        self._audio_output: QAudioOutput | None = None
        self._current_request_id: str | None = None
        self._pending_delete: Path | None = None

    def play(self, path: str, request_id: str) -> None:
        """Start playback of an audio file."""
        self.stop()
        self._current_request_id = request_id
        self._pending_delete = Path(path)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)
        self._player.setSource(QUrl.fromLocalFile(path))

        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(self._on_error)

        self._player.play()

    def stop(self) -> None:
        """Stop current playback and clean up."""
        if self._player:
            self._player.stop()
            self._player.deleteLater()
            self._player = None
        if self._audio_output:
            self._audio_output.deleteLater()
            self._audio_output = None

        # Delete temp file if it exists
        if self._pending_delete:
            try:
                self._pending_delete.unlink(missing_ok=True)
            except OSError:
                pass
            self._pending_delete = None

        self._current_request_id = None

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            request_id = self._current_request_id
            self._cleanup_after_playback()
            if request_id:
                self.play_finished.emit(request_id)

    def _on_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        kind = error.name if hasattr(error, "name") else "PlaybackError"
        request_id = self._current_request_id
        self._cleanup_after_playback()
        if request_id:
            self.play_error.emit(request_id, kind, error_string)

    def _cleanup_after_playback(self) -> None:
        if self._player:
            self._player.stop()
            self._player.deleteLater()
            self._player = None
        if self._audio_output:
            self._audio_output.deleteLater()
            self._audio_output = None

        if self._pending_delete:
            try:
                self._pending_delete.unlink(missing_ok=True)
            except OSError:
                pass
            self._pending_delete = None

        self._current_request_id = None
