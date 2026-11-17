"""Tests for Qt-free PCM helpers and microphone device selection."""

from __future__ import annotations

import math
from array import array
from pathlib import Path

import pytest

from friday.voice.audio import (
    choose_input_device,
    pcm_stats,
    to_mono_16k,
)
from friday.voice.errors import InputDeviceNotFound, NoInputDevice


def _sine_pcm(
    frequency: float,
    seconds: float,
    rate: int,
    *,
    amplitude: int = 32767,
    channels: int = 1,
) -> bytes:
    """Generate interleaved sine PCM with the given channel count."""
    frames = int(rate * seconds)
    samples = array("h")
    for index in range(frames):
        value = int(
            amplitude * math.sin(2 * math.pi * frequency * index / rate)
        )
        for _ in range(channels):
            samples.append(value)
    return samples.tobytes()


def _zero_crossing_frequency(pcm: bytes, rate: int) -> float:
    samples = array("h")
    samples.frombytes(pcm)
    crossings = 0
    previous = samples[0]
    for value in samples[1:]:
        if (previous < 0) != (value < 0):
            crossings += 1
        previous = value
    return crossings / 2 / (len(samples) / rate)


def test_pcm_stats_sine() -> None:
    """A full-scale sine has peak 1.0 and RMS near -3 dBFS."""
    pcm = _sine_pcm(440.0, 0.5, 16_000)
    duration, peak, rms_dbfs = pcm_stats(pcm, 16_000)

    assert duration == pytest.approx(0.5, abs=0.001)
    assert peak == pytest.approx(1.0, abs=0.01)
    assert rms_dbfs == pytest.approx(-3.01, abs=0.2)


def test_pcm_stats_silence() -> None:
    """Digital silence has zero peak and the RMS floor."""
    pcm = bytes(16_000)
    duration, peak, rms_dbfs = pcm_stats(pcm, 16_000)

    assert duration == pytest.approx(0.5)
    assert peak == 0.0
    assert rms_dbfs == -120.0


def test_pcm_stats_clipped() -> None:
    """Clipped full-scale samples stay at peak 1.0 and near 0 dBFS."""
    samples = array("h")
    for _ in range(1000):
        samples.append(32767)
        samples.append(-32768)
    duration, peak, rms_dbfs = pcm_stats(samples.tobytes(), 16_000)

    assert duration == pytest.approx(0.125)
    assert peak == pytest.approx(1.0)
    assert rms_dbfs == pytest.approx(0.0, abs=0.5)


def test_to_mono_16k_48k_stereo() -> None:
    """48 kHz stereo is mixed down and resampled to 16 kHz mono."""
    pcm = _sine_pcm(440.0, 0.25, 48_000, channels=2)
    converted = to_mono_16k(pcm, 48_000, 2, 2)

    assert len(converted) == 8_000
    duration, _, _ = pcm_stats(converted, 16_000)
    assert duration == pytest.approx(0.25, abs=0.005)
    assert _zero_crossing_frequency(converted, 16_000) == pytest.approx(
        440.0, rel=0.05
    )


def test_to_mono_16k_44k1_mono() -> None:
    """44.1 kHz mono is resampled to 16 kHz without changing pitch."""
    pcm = _sine_pcm(440.0, 0.25, 44_100)
    converted = to_mono_16k(pcm, 44_100, 1, 2)

    assert len(converted) == pytest.approx(8_000, abs=4)
    assert _zero_crossing_frequency(converted, 16_000) == pytest.approx(
        440.0, rel=0.05
    )


def test_to_mono_16k_16k_mono_is_unchanged() -> None:
    """Already-16 kHz mono audio keeps its samples."""
    pcm = _sine_pcm(440.0, 0.1, 16_000)
    assert to_mono_16k(pcm, 16_000, 1, 2) == pcm


def test_choose_input_device_by_substring() -> None:
    devices = [("Laptop Mic", False), ("USB Headset", True)]
    assert choose_input_device(devices, "head") == ("USB Headset", True)


def test_choose_input_device_uses_default() -> None:
    devices = [("Laptop Mic", False), ("USB Headset", True)]
    assert choose_input_device(devices, "") == ("USB Headset", True)
    assert choose_input_device([("Mic A", False)], "") == ("Mic A", False)


def test_choose_input_device_missing_raises() -> None:
    with pytest.raises(InputDeviceNotFound):
        choose_input_device([("Laptop Mic", True)], "usb")


def test_choose_input_device_no_devices_raises() -> None:
    with pytest.raises(NoInputDevice):
        choose_input_device([], "")


def test_voice_package_has_no_pyside6_imports() -> None:
    """Qt stays in friday.ui; friday.voice must stay Qt-free."""
    root = Path(__file__).resolve().parents[2]
    voice_dir = root / "src" / "friday" / "voice"
    for path in voice_dir.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert "PySide6" not in content, path
