"""UI-thread microphone recorder using QAudioSource.

Lives in ``friday.ui`` like :mod:`friday.ui.audio_player`: Qt multimedia
objects must be created and used on the UI thread.  All PCM decoding and
conversion is delegated to the Qt-free :mod:`friday.voice.audio` helpers.

Captured audio is never written to disk here and never logged.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDevice,
    QAudioFormat,
    QAudioSource,
    QMediaDevices,
)

from friday.core.logging import get_logger
from friday.voice.audio import (
    INPUT_RATE,
    choose_input_device,
    pcm_stats,
    to_mono_16k,
)
from friday.voice.errors import (
    AudioCaptureError,
    InputDeviceNotFound,
    MicPermissionOrSilent,
    RecordingError,
    RecordingTooShort,
)

logger = get_logger(__name__)

LEVEL_INTERVAL_MS = 100


class AudioRecorder(QObject):
    """Record from a microphone on the UI thread.

    Signals:
        recording_started()
        level(float)                       # peak, 0..1, about 10 Hz
        recording_finished(bytes, float, float, float)
            # 16 kHz mono int16 PCM, duration_s, peak, rms_dbfs
        recording_error(kind, message)

    The device is released before any terminal signal is emitted.
    """

    recording_started = Signal()
    level = Signal(float)
    recording_finished = Signal(bytes, float, float, float)
    recording_error = Signal(str, str)

    def __init__(
        self,
        *,
        input_device: str = "",
        max_record_seconds: float = 30.0,
        min_record_seconds: float = 0.3,
        silence_peak_threshold: float = 0.01,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._input_device = input_device
        self._max_record_seconds = max(0.05, float(max_record_seconds))
        self._min_record_seconds = max(0.0, float(min_record_seconds))
        self._silence_peak_threshold = float(silence_peak_threshold)

        self._source: QAudioSource | None = None
        self._io_device = None
        self._signal_connected = False
        self._source_started = False
        self._pcm = bytearray()
        self._level_pcm = bytearray()
        self._state = "idle"

        self._device_name = ""
        self._sample_rate = 0
        self._channels = 0
        self._sample_width = 0
        self._float_samples = False
        self._last_raw_bytes = 0

        self._level_timer = QTimer(self)
        self._level_timer.setInterval(LEVEL_INTERVAL_MS)
        self._level_timer.timeout.connect(self._emit_level)

        self._max_timer = QTimer(self)
        self._max_timer.setSingleShot(True)
        self._max_timer.timeout.connect(self._on_max_duration)

    # ------------------------------------------------------------------
    # Device discovery / selection
    # ------------------------------------------------------------------
    @staticmethod
    def list_devices() -> list[tuple[str, bool]]:
        """Return ``(name, is_default)`` for every input device."""
        devices = QMediaDevices()
        default = devices.defaultAudioInput()
        default_name = default.description() if default is not None else ""
        return [
            (device.description(), device.description() == default_name)
            for device in devices.audioInputs()
        ]

    def _resolve_device(self, name: str) -> QAudioDevice:
        for device in QMediaDevices().audioInputs():
            if device.description() == name:
                return device
        raise InputDeviceNotFound(
            f"No microphone matching '{name}' was found."
        )

    @staticmethod
    def _negotiate_format(device: QAudioDevice) -> QAudioFormat:
        requested = QAudioFormat()
        requested.setSampleRate(INPUT_RATE)
        requested.setChannelCount(1)
        requested.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if device.isFormatSupported(requested):
            return requested
        return device.preferredFormat()

    @staticmethod
    def _format_details(
        audio_format: QAudioFormat,
    ) -> tuple[int, int, int, bool]:
        """Return (sample_rate, channels, sample_width, is_float)."""
        sample_format = audio_format.sampleFormat()
        if sample_format == QAudioFormat.SampleFormat.UInt8:
            width, is_float = 1, False
        elif sample_format == QAudioFormat.SampleFormat.Int32:
            width, is_float = 4, False
        elif sample_format == QAudioFormat.SampleFormat.Float:
            width, is_float = 4, True
        elif sample_format == QAudioFormat.SampleFormat.Int16:
            width, is_float = 2, False
        else:
            raise RecordingError(
                "The microphone reported an unsupported sample format."
            )
        return (
            audio_format.sampleRate(),
            max(1, audio_format.channelCount()),
            width,
            is_float,
        )

    # ------------------------------------------------------------------
    # Capture lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start recording; failures are reported via ``recording_error``."""
        if self._state == "recording":
            logger.info("recording_start_ignored: already recording")
            return

        self._state = "starting"
        try:
            devices = self.list_devices()
            name, _ = choose_input_device(devices, self._input_device)
            device = self._resolve_device(name)
            audio_format = self._negotiate_format(device)
            (
                self._sample_rate,
                self._channels,
                self._sample_width,
                self._float_samples,
            ) = self._format_details(audio_format)
            self._device_name = name

            source = QAudioSource(device, audio_format, self)
            self._source = source
            io_device = source.start()
            self._source_started = io_device is not None
            if io_device is None:
                raise RecordingError(
                    "The microphone could not be started."
                )
            self._io_device = io_device

            # Qt may adjust the format; trust the source's actual format.
            actual_format = source.format()
            if actual_format.isValid():
                (
                    self._sample_rate,
                    self._channels,
                    self._sample_width,
                    self._float_samples,
                ) = self._format_details(actual_format)

            error = source.error()
            if error.value != QAudio.Error.NoError.value:
                raise RecordingError(
                    f"The microphone could not be started: {error.name}."
                )

            self._io_device.readyRead.connect(self._read_ready)
            self._signal_connected = True
            self._pcm.clear()
            self._level_pcm.clear()
            self._last_raw_bytes = 0
            self._state = "recording"

            self._level_timer.start()
            self._max_timer.start(int(self._max_record_seconds * 1000))
            logger.info(
                "recording_started: device=%s sample_rate=%d channels=%d "
                "sample_width=%d max_seconds=%.1f",
                name,
                self._sample_rate,
                self._channels,
                self._sample_width,
                self._max_record_seconds,
            )
            self.recording_started.emit()
        except AudioCaptureError as exc:
            self._fail(exc)
        except Exception as exc:
            self._fail(RecordingError(f"Recording failed: {exc}"))

    def stop(self) -> None:
        """Stop and emit exactly one terminal signal (idempotent)."""
        if self._state != "recording":
            return
        self._state = "stopping"
        self._level_timer.stop()
        self._max_timer.stop()

        # Drain whatever the source has already buffered.
        self._read_ready()
        raw = bytes(self._pcm)
        self._pcm.clear()
        self._level_pcm.clear()
        self._last_raw_bytes = len(raw)
        frame_bytes = max(1, self._channels * self._sample_width)
        raw_duration = len(raw) / (self._sample_rate * frame_bytes)
        self._release_source()

        if raw_duration < self._min_record_seconds:
            self._state = "idle"
            self._fail(
                RecordingTooShort(
                    f"Recording too short ({raw_duration:.2f}s); "
                    f"minimum is {self._min_record_seconds:.2f}s."
                ),
            )
            return

        try:
            converted = to_mono_16k(
                raw,
                self._sample_rate,
                self._channels,
                self._sample_width,
                float_samples=self._float_samples,
            )
            duration, peak, rms_dbfs = pcm_stats(converted, INPUT_RATE)
        except Exception as exc:
            self._state = "idle"
            self._fail(RecordingError(f"Recording could not be decoded: {exc}"))
            return

        logger.info(
            "recording_finished: device=%s raw_bytes=%d converted_bytes=%d "
            "duration_s=%.2f peak=%.4f rms_dbfs=%.1f",
            self._device_name,
            len(raw),
            len(converted),
            duration,
            peak,
            rms_dbfs,
        )

        self._state = "idle"
        if peak < self._silence_peak_threshold:
            logger.info(
                "recording_silent: device=%s duration_s=%.2f peak=%.5f",
                self._device_name,
                duration,
                peak,
            )
            self.recording_error.emit(
                MicPermissionOrSilent.kind,
                "No microphone audio was captured. Check Windows Settings "
                "> Privacy & security > Microphone, turn on \"Let desktop "
                "apps access your microphone\", and make sure the device "
                "is not muted.",
            )
            return

        self.recording_finished.emit(converted, duration, peak, rms_dbfs)

    def cancel(self) -> None:
        """Stop recording and discard audio without emitting a signal."""
        if self._state != "recording":
            return
        self._state = "idle"
        self._level_timer.stop()
        self._max_timer.stop()
        raw_bytes = len(self._pcm)
        self._pcm.clear()
        self._level_pcm.clear()
        self._release_source()
        logger.info(
            "recording_cancelled: device=%s raw_bytes=%d",
            self._device_name,
            raw_bytes,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _read_ready(self) -> None:
        if self._io_device is None:
            return
        try:
            data = self._io_device.readAll()
        except Exception:
            logger.debug("microphone read failed", exc_info=True)
            return
        if not data:
            return
        chunk = bytes(data)
        self._pcm.extend(chunk)
        self._level_pcm.extend(chunk)

    def _emit_level(self) -> None:
        if not self._level_pcm:
            self.level.emit(0.0)
            return
        chunk = bytes(self._level_pcm)
        self._level_pcm.clear()
        try:
            converted = to_mono_16k(
                chunk,
                self._sample_rate,
                self._channels,
                self._sample_width,
                float_samples=self._float_samples,
            )
            _, peak, _ = pcm_stats(converted, INPUT_RATE)
        except Exception:
            logger.debug("microphone level computation failed", exc_info=True)
            return
        self.level.emit(peak)

    def _on_max_duration(self) -> None:
        if self._state != "recording":
            return
        logger.info(
            "recording_auto_stop: device=%s max_seconds=%.1f",
            self._device_name,
            self._max_record_seconds,
        )
        self.stop()

    def _release_source(self) -> None:
        io_device = self._io_device
        self._io_device = None
        if io_device is not None and self._signal_connected:
            self._signal_connected = False
            io_device.readyRead.disconnect(self._read_ready)

        source = self._source
        self._source = None
        if source is not None:
            if self._source_started:
                self._source_started = False
                source.stop()
            source.deleteLater()

    def _fail(self, exc: AudioCaptureError) -> None:
        raw_bytes = len(self._pcm)
        self._release_source()
        self._pcm.clear()
        self._level_pcm.clear()
        logger.info(
            "recording_error: kind=%s device=%s raw_bytes=%d",
            exc.kind,
            self._device_name,
            raw_bytes,
        )
        self._state = "idle"
        self.recording_error.emit(exc.kind, exc.message)

    @property
    def format_description(self) -> str:
        """Human-readable negotiated format for the manual smoke script."""
        kind = "float" if self._float_samples else "int"
        return (
            f"{self._sample_rate} Hz, {self._channels} ch, "
            f"{self._sample_width * 8}-bit {kind}"
        )

    @property
    def device_name(self) -> str:
        """Name of the selected input device."""
        return self._device_name

    @property
    def last_raw_bytes(self) -> int:
        """Byte count captured during the most recent recording."""
        return self._last_raw_bytes

    def __del__(self) -> None:
        # QObject parenting releases the source on normal destruction; this
        # only covers garbage collection while the C++ objects are alive.
        try:
            self._release_source()
        except RuntimeError:
            pass


__all__ = ["AudioRecorder"]
