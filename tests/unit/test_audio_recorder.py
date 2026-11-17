"""AudioRecorder tests with fake Qt multimedia objects (no real microphone)."""

# PySide6 must load after pydantic is fully initialised: shiboken's import
# hook breaks pydantic's lazy imports on this interpreter.
# ruff: noqa: I001

from __future__ import annotations

import logging
import math
import time
import warnings
from array import array

import pytest
from PySide6.QtCore import QCoreApplication, QIODevice
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDevice,
    QAudioFormat,
    QAudioSource,
    QMediaDevices,
)
from PySide6.QtWidgets import QApplication

from friday.ui import audio_recorder as recorder_module
from friday.ui.audio_recorder import AudioRecorder


def wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


class _FakeSignal:
    """Minimal Qt-like signal that enforces connect-before-disconnect."""

    def __init__(self) -> None:
        self._slots: list = []

    def connect(self, slot) -> None:
        self._slots.append(slot)

    def disconnect(self, slot) -> None:
        if slot not in self._slots:
            raise AssertionError("disconnect() before connect()")
        self._slots.remove(slot)

    def emit(self) -> None:
        for slot in list(self._slots):
            slot()


class _FakeIODevice:
    """Buffers fed bytes and returns them from readAll()."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self.readyRead = _FakeSignal()

    def feed(self, data: bytes) -> None:
        self._chunks.append(data)
        self.readyRead.emit()

    def readAll(self) -> bytes:
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


class _FakeAudioDevice:
    def __init__(
        self,
        name: str,
        *,
        supports: bool = True,
        preferred: QAudioFormat | None = None,
    ) -> None:
        self._name = name
        self._supports = supports
        self._preferred = preferred

    def description(self) -> str:
        return self._name

    def isFormatSupported(self, audio_format: QAudioFormat) -> bool:
        return self._supports

    def preferredFormat(self) -> QAudioFormat | None:
        return self._preferred


class _FakeMediaDevices:
    devices: list[_FakeAudioDevice] = []
    default: _FakeAudioDevice | None = None

    def defaultAudioInput(self):
        return type(self).default

    def audioInputs(self):
        return list(type(self).devices)


class _FakeAudioSource:
    """Stand-in for QAudioSource exposing only real QAudioSource API."""

    instances: list[_FakeAudioSource] = []
    next_error = QAudio.Error.NoError

    def __init__(self, device, audio_format, parent=None) -> None:
        self.device = device
        self.audio_format = audio_format
        self.io = _FakeIODevice()
        self.error_value = type(self).next_error
        type(self).next_error = QAudio.Error.NoError
        self.stop_calls = 0
        self.deleted = False
        type(self).instances.append(self)

    def start(self):
        return self.io

    def error(self):
        return self.error_value

    def format(self):
        return self.audio_format

    def stop(self) -> None:
        self.stop_calls += 1

    def deleteLater(self) -> None:
        self.deleted = True


def _install_audio_fakes(monkeypatch) -> None:
    _FakeMediaDevices.devices = []
    _FakeMediaDevices.default = None
    _FakeAudioSource.instances = []
    _FakeAudioSource.next_error = QAudio.Error.NoError
    monkeypatch.setattr(recorder_module, "QMediaDevices", _FakeMediaDevices)
    monkeypatch.setattr(recorder_module, "QAudioSource", _FakeAudioSource)


def _standard_fakes(monkeypatch) -> _FakeAudioDevice:
    _install_audio_fakes(monkeypatch)
    default = _FakeAudioDevice("Fake Mic")
    _FakeMediaDevices.devices = [default]
    _FakeMediaDevices.default = default
    return default


def _sine_bytes(
    seconds: float = 0.5,
    rate: int = 16_000,
    channels: int = 1,
    frequency: float = 440.0,
) -> bytes:
    samples = array("h")
    for index in range(int(rate * seconds)):
        value = int(
            32767 * math.sin(2 * math.pi * frequency * index / rate)
        )
        for _ in range(channels):
            samples.append(value)
    return samples.tobytes()


def _connect_spies(recorder: AudioRecorder):
    started: list = []
    levels: list = []
    finished: list = []
    errors: list = []
    recorder.recording_started.connect(lambda: started.append(True))
    recorder.level.connect(lambda value: levels.append(value))
    recorder.recording_finished.connect(
        lambda *args: finished.append(args)
    )
    recorder.recording_error.connect(
        lambda kind, message: errors.append((kind, message))
    )
    return started, levels, finished, errors


def test_recorder_start_emits_level_and_finishes(
    qt_app: QApplication, monkeypatch
) -> None:
    """Start, emit level updates, then finish with 16 kHz mono stats."""
    _standard_fakes(monkeypatch)
    recorder = AudioRecorder(min_record_seconds=0.3)
    started, levels, finished, errors = _connect_spies(recorder)

    recorder.start()
    assert started == [True]
    assert len(_FakeAudioSource.instances) == 1
    source = _FakeAudioSource.instances[0]
    source.io.feed(_sine_bytes(0.5))

    assert wait_until(lambda: bool(levels), timeout=2.0)
    assert 0.9 <= levels[0] <= 1.0

    recorder.stop()

    assert errors == []
    assert len(finished) == 1
    pcm, duration, peak, rms_dbfs = finished[0]
    assert len(pcm) == 16_000
    assert duration == pytest.approx(0.5, abs=0.01)
    assert peak == pytest.approx(1.0, abs=0.01)
    assert rms_dbfs == pytest.approx(-3.01, abs=0.3)
    assert source.stop_calls == 1
    assert source.deleted is True


def test_recorder_auto_stops_at_max_seconds(
    qt_app: QApplication, monkeypatch
) -> None:
    """Reaching max_record_seconds emits finished, not an error."""
    _standard_fakes(monkeypatch)
    recorder = AudioRecorder(
        max_record_seconds=0.2, min_record_seconds=0.1
    )
    _, _, finished, errors = _connect_spies(recorder)

    recorder.start()
    _FakeAudioSource.instances[0].io.feed(_sine_bytes(0.3))

    assert wait_until(lambda: bool(finished), timeout=3.0)
    assert errors == []
    pcm, duration, _, _ = finished[0]
    assert len(pcm) == 9_600
    assert duration == pytest.approx(0.3, abs=0.01)


def test_recorder_stop_is_idempotent(
    qt_app: QApplication, monkeypatch
) -> None:
    """Calling stop() twice emits a single terminal result."""
    _standard_fakes(monkeypatch)
    recorder = AudioRecorder(min_record_seconds=0.1)
    _, _, finished, errors = _connect_spies(recorder)

    recorder.start()
    _FakeAudioSource.instances[0].io.feed(_sine_bytes(0.3))
    recorder.stop()
    recorder.stop()

    assert errors == []
    assert len(finished) == 1
    assert _FakeAudioSource.instances[0].stop_calls == 1


def test_recorder_cancel_emits_nothing_and_drops_audio(
    qt_app: QApplication, monkeypatch
) -> None:
    """cancel() is silent and releases the device."""
    _standard_fakes(monkeypatch)
    recorder = AudioRecorder(min_record_seconds=0.1)
    _, _, finished, errors = _connect_spies(recorder)

    recorder.start()
    _FakeAudioSource.instances[0].io.feed(_sine_bytes(0.5))
    recorder.cancel()

    assert finished == []
    assert errors == []
    assert recorder._pcm == bytearray()
    source = _FakeAudioSource.instances[0]
    assert source.stop_calls == 1
    assert source.deleted is True


def test_recorder_too_short_emits_error(
    qt_app: QApplication, monkeypatch
) -> None:
    """Audio shorter than min_record_seconds is rejected."""
    _standard_fakes(monkeypatch)
    recorder = AudioRecorder(min_record_seconds=0.3)
    _, _, finished, errors = _connect_spies(recorder)

    recorder.start()
    _FakeAudioSource.instances[0].io.feed(_sine_bytes(0.05))
    recorder.stop()

    assert finished == []
    assert len(errors) == 1
    kind, message = errors[0]
    assert kind == "RecordingTooShort"
    assert "too short" in message.lower()
    source = _FakeAudioSource.instances[0]
    assert source.stop_calls == 1
    assert source.deleted is True


def test_recorder_silence_emits_permission_error(
    qt_app: QApplication, monkeypatch
) -> None:
    """Silent capture reports the Windows privacy/mute guidance."""
    _standard_fakes(monkeypatch)
    recorder = AudioRecorder(
        min_record_seconds=0.3, silence_peak_threshold=0.01
    )
    _, _, finished, errors = _connect_spies(recorder)

    recorder.start()
    _FakeAudioSource.instances[0].io.feed(bytes(16_000))
    recorder.stop()

    assert finished == []
    assert len(errors) == 1
    kind, message = errors[0]
    assert kind == "MicPermissionOrSilent"
    assert "Windows Settings" in message
    assert "Privacy & security > Microphone" in message
    assert "Let desktop apps access your microphone" in message
    assert "not muted" in message
    source = _FakeAudioSource.instances[0]
    assert source.stop_calls == 1
    assert source.deleted is True


def test_recorder_start_while_recording_is_ignored(
    qt_app: QApplication, monkeypatch, caplog
) -> None:
    """A second start() logs and keeps the current recording."""
    caplog.set_level(logging.INFO)
    _standard_fakes(monkeypatch)
    recorder = AudioRecorder(min_record_seconds=0.1)
    started, _, _, _ = _connect_spies(recorder)

    recorder.start()
    recorder.start()
    recorder.cancel()

    assert started == [True]
    assert len(_FakeAudioSource.instances) == 1
    assert "recording_start_ignored" in caplog.text


def test_recorder_no_input_device_emits_error(
    qt_app: QApplication, monkeypatch
) -> None:
    """No devices at all reports NoInputDevice without creating a source."""
    _install_audio_fakes(monkeypatch)
    recorder = AudioRecorder()
    _, _, _, errors = _connect_spies(recorder)

    recorder.start()

    assert len(errors) == 1
    assert errors[0][0] == "NoInputDevice"
    assert _FakeAudioSource.instances == []


def test_recorder_unknown_device_emits_error(
    qt_app: QApplication, monkeypatch
) -> None:
    """A configured name with no match reports InputDeviceNotFound."""
    _install_audio_fakes(monkeypatch)
    default = _FakeAudioDevice("Laptop Mic")
    _FakeMediaDevices.devices = [default]
    _FakeMediaDevices.default = default
    recorder = AudioRecorder(input_device="usb headset")
    _, _, _, errors = _connect_spies(recorder)

    recorder.start()

    assert len(errors) == 1
    kind, message = errors[0]
    assert kind == "InputDeviceNotFound"
    assert "usb headset" in message
    assert _FakeAudioSource.instances == []


def test_recorder_converts_preferred_format(
    qt_app: QApplication, monkeypatch
) -> None:
    """48 kHz stereo preferred formats are converted to 16 kHz mono."""
    preferred = QAudioFormat()
    preferred.setSampleRate(48_000)
    preferred.setChannelCount(2)
    preferred.setSampleFormat(QAudioFormat.SampleFormat.Int16)

    _install_audio_fakes(monkeypatch)
    device = _FakeAudioDevice(
        "Stereo Mic", supports=False, preferred=preferred
    )
    _FakeMediaDevices.devices = [device]
    _FakeMediaDevices.default = device
    recorder = AudioRecorder(min_record_seconds=0.1)
    _, _, finished, errors = _connect_spies(recorder)

    recorder.start()
    _FakeAudioSource.instances[0].io.feed(
        _sine_bytes(0.25, rate=48_000, channels=2)
    )
    recorder.stop()

    assert errors == []
    assert len(finished) == 1
    pcm, duration, peak, _ = finished[0]
    assert len(pcm) == pytest.approx(8_000, abs=8)
    assert duration == pytest.approx(0.25, abs=0.01)
    assert peak == pytest.approx(1.0, abs=0.05)
    assert "48000 Hz, 2 ch" in recorder.format_description


def test_recorder_logs_stats_without_audio(
    qt_app: QApplication, monkeypatch, caplog
) -> None:
    """Logs carry device, duration and levels, never PCM bytes."""
    caplog.set_level(logging.INFO)
    _standard_fakes(monkeypatch)
    recorder = AudioRecorder(min_record_seconds=0.1)
    _, _, finished, _ = _connect_spies(recorder)

    chunk = _sine_bytes(0.5)
    recorder.start()
    _FakeAudioSource.instances[0].io.feed(chunk)
    recorder.stop()

    assert len(finished) == 1
    text = caplog.text
    assert "device=Fake Mic" in text
    assert "duration_s=" in text
    assert "peak=" in text
    assert "rms_dbfs=" in text
    assert chunk.hex() not in text
    assert "\\x" not in text


def test_fake_audio_classes_mirror_real_qt_api() -> None:
    """Fakes only stand in for attributes the real Qt classes expose."""
    for attr in ("start", "stop", "error", "format", "deleteLater"):
        assert hasattr(QAudioSource, attr), attr
    for attr in ("description", "isFormatSupported", "preferredFormat"):
        assert hasattr(QAudioDevice, attr), attr
    for attr in ("defaultAudioInput", "audioInputs"):
        assert hasattr(QMediaDevices, attr), attr
    for attr in ("readAll", "readyRead"):
        assert hasattr(QIODevice, attr), attr
    assert hasattr(QAudio, "Error")
    assert not hasattr(QAudioSource, "Error")
    assert not hasattr(_FakeAudioSource, "Error")


def test_recorder_start_error_before_connect_has_no_warning(
    qt_app: QApplication, monkeypatch
) -> None:
    """A failure before signal connection leaks nothing and is reusable."""
    _standard_fakes(monkeypatch)
    _FakeAudioSource.next_error = QAudio.Error.OpenError
    recorder = AudioRecorder(min_record_seconds=0.1)
    _, _, finished, errors = _connect_spies(recorder)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        recorder.start()

    assert len(errors) == 1
    kind, message = errors[0]
    assert kind == "RecordingError"
    assert "OpenError" in message
    source = _FakeAudioSource.instances[0]
    assert source.stop_calls == 1
    assert source.deleted is True

    # The same recorder can start again after the failure.
    recorder.start()
    assert len(_FakeAudioSource.instances) == 2
    _FakeAudioSource.instances[1].io.feed(_sine_bytes(0.3))
    recorder.stop()

    assert len(finished) == 1
    assert errors[0][0] == "RecordingError"


def test_recorder_release_is_idempotent(
    qt_app: QApplication, monkeypatch
) -> None:
    """Releasing an already released source emits no warnings."""
    _standard_fakes(monkeypatch)
    recorder = AudioRecorder(min_record_seconds=0.1)

    recorder.start()
    _FakeAudioSource.instances[0].io.feed(_sine_bytes(0.2))
    recorder.stop()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        recorder._release_source()
        recorder._release_source()

    assert _FakeAudioSource.instances[0].stop_calls == 1
