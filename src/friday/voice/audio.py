"""Qt-free PCM helpers for microphone capture.

Captured audio is always 16-bit PCM on Windows; these helpers convert it to
16 kHz mono int16 and compute simple level statistics.  No audioop (removed
in Python 3.13), no third-party packages.

Nothing here writes audio to disk or logs sample data.
"""

from __future__ import annotations

import math
import sys
from array import array
from collections.abc import Iterable, Sequence

from friday.voice.errors import InputDeviceNotFound, NoInputDevice

INPUT_RATE = 16_000
SILENCE_RMS_FLOOR_DBFS = -120.0


def _decode_samples(
    pcm: bytes, sample_width: int, *, float_samples: bool = False
) -> list[float]:
    """Decode interleaved PCM into signed values scaled like int16."""
    usable = len(pcm) - (len(pcm) % sample_width)
    pcm = pcm[:usable]

    if float_samples:
        if sample_width != 4:
            raise ValueError("float samples require a 4-byte width")
        values = array("f")
        values.frombytes(pcm)
        if sys.byteorder == "big":
            values.byteswap()
        return [value * 32768.0 for value in values]

    if sample_width == 1:
        # 8-bit PCM is unsigned with a 128 bias.
        return [(value - 128) * 256.0 for value in pcm]

    if sample_width == 2:
        values = array("h")
        values.frombytes(pcm)
        if sys.byteorder == "big":
            values.byteswap()
        return [float(value) for value in values]

    if sample_width == 3:
        decoded: list[float] = []
        for index in range(0, usable, 3):
            value = (
                pcm[index]
                | (pcm[index + 1] << 8)
                | (pcm[index + 2] << 16)
            )
            if value & 0x800000:
                value -= 0x1000000
            decoded.append(float(value >> 8))
        return decoded

    if sample_width == 4:
        values = array("i")
        values.frombytes(pcm)
        if sys.byteorder == "big":
            values.byteswap()
        return [float(value >> 16) for value in values]

    raise ValueError(f"Unsupported sample width: {sample_width}")


def _resample_linear(samples: list[float], out_length: int) -> list[float]:
    """Linearly resample to ``out_length`` frames."""
    count = len(samples)
    if count == 0:
        return []
    if out_length <= 1:
        return [samples[0]]
    step = (count - 1) / (out_length - 1)
    output: list[float] = []
    for index in range(out_length):
        position = index * step
        left = int(position)
        fraction = position - left
        if left + 1 < count:
            value = samples[left] * (1.0 - fraction) + samples[left + 1] * fraction
        else:
            value = samples[left]
        output.append(value)
    return output


def _to_int16_bytes(samples: Iterable[float]) -> bytes:
    encoded = array(
        "h",
        (
            max(-32768, min(32767, int(round(value))))
            for value in samples
        ),
    )
    if sys.byteorder == "big":
        encoded.byteswap()
    return encoded.tobytes()


def to_mono_16k(
    pcm: bytes,
    rate: int,
    channels: int,
    sample_width: int,
    *,
    float_samples: bool = False,
) -> bytes:
    """Convert interleaved PCM to 16 kHz mono int16 bytes.

    Args:
        pcm: Raw interleaved PCM.
        rate: Source sample rate (e.g. 48000).
        channels: Source channel count.
        sample_width: Bytes per sample (1, 2, 3 or 4).
        float_samples: Treat 4-byte samples as float32 instead of int32.
    """
    if rate <= 0:
        raise ValueError("rate must be positive")
    if channels <= 0:
        raise ValueError("channels must be positive")
    if sample_width <= 0:
        raise ValueError("sample_width must be positive")

    decoded = _decode_samples(
        pcm, sample_width, float_samples=float_samples
    )
    frames = len(decoded) // channels
    if frames == 0:
        return b""

    if channels == 1:
        mono = decoded[:frames]
    else:
        mono = [
            sum(decoded[frame * channels : (frame + 1) * channels])
            / channels
            for frame in range(frames)
        ]

    if rate != INPUT_RATE:
        out_length = max(1, int(round(frames * INPUT_RATE / rate)))
        mono = _resample_linear(mono, out_length)

    return _to_int16_bytes(mono)


def pcm_stats(pcm: bytes, sample_rate: int) -> tuple[float, float, float]:
    """Return (duration_seconds, peak, rms_dbfs) for mono int16 PCM.

    ``peak`` is normalised to 0..1.  ``rms_dbfs`` is capped at -120 dBFS.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    usable = len(pcm) - (len(pcm) % 2)
    samples = array("h")
    samples.frombytes(pcm[:usable])
    if sys.byteorder == "big":
        samples.byteswap()

    count = len(samples)
    duration = count / sample_rate
    if count == 0:
        return 0.0, 0.0, SILENCE_RMS_FLOOR_DBFS

    peak_value = max(abs(value) for value in samples)
    peak = min(1.0, peak_value / 32768.0)
    mean_square = sum(value * value for value in samples) / count
    if mean_square <= 0.0:
        return duration, peak, SILENCE_RMS_FLOOR_DBFS
    rms = math.sqrt(mean_square) / 32768.0
    rms_dbfs = max(
        SILENCE_RMS_FLOOR_DBFS, 20.0 * math.log10(max(rms, 1e-12))
    )
    return duration, peak, rms_dbfs


def choose_input_device(
    devices: Sequence[tuple[str, bool]], wanted: str
) -> tuple[str, bool]:
    """Pick an input device by name substring, or the system default.

    ``devices`` holds ``(name, is_default)`` pairs.  An empty ``wanted``
    selects the default device (or the first one).  Raises typed errors so
    callers never guess why selection failed.
    """
    if not devices:
        raise NoInputDevice(
            "No microphone input device was found. "
            "Connect a microphone and try again."
        )

    needle = wanted.strip().lower()
    if not needle:
        for name, is_default in devices:
            if is_default:
                return name, is_default
        return devices[0]

    for name, is_default in devices:
        if needle in name.lower():
            return name, is_default

    raise InputDeviceNotFound(
        f"No microphone matching '{wanted.strip()}' was found."
    )


__all__ = [
    "INPUT_RATE",
    "SILENCE_RMS_FLOOR_DBFS",
    "choose_input_device",
    "pcm_stats",
    "to_mono_16k",
]
