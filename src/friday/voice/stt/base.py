"""Qt-free speech-to-text types and interfaces.

The recorder already produces 16 kHz mono int16 PCM (see
:mod:`friday.voice.audio`), so transcription engines accept those bytes
directly and never re-convert or buffer audio on disk.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from friday.voice.errors import UnsupportedLanguage

# Languages FRIDAY supports today.  Passing None (or "auto") lets the
# model detect the language instead.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "hi")
AUTO_LANGUAGE = "auto"

INPUT_SAMPLE_RATE = 16_000

# Sentinel distinguishing "caller omitted language" from an explicit None,
# which forces automatic detection.
UNSET: object = object()

# Progress phases reported to the caller.  "loading" repeats every few
# seconds while the model downloads or is read from disk.
STATUS_PREPARING = "preparing"
STATUS_LOADING = "loading"
STATUS_READY = "ready"
STATUS_TRANSCRIBING = "transcribing"
STATUS_DONE = "done"


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    """A completed transcription."""

    text: str
    language: str
    language_probability: float
    duration_seconds: float
    # How much audio survived voice-activity filtering.  ``None`` when VAD
    # was disabled, so callers can tell "no VAD" from "nothing removed".
    duration_after_vad_seconds: float | None = None
    segment_count: int = 0


@dataclass(frozen=True, slots=True)
class TranscriptionStatus:
    """A progress update emitted while loading or transcribing."""

    phase: str
    message: str
    elapsed_seconds: float = 0.0


StatusCallback = Callable[[TranscriptionStatus], None]


def normalize_language(value: str | None) -> str | None:
    """Map a config/CLI value to a Faster-Whisper ``language`` argument.

    ``None``, an empty string and ``"auto"`` mean automatic detection.
    Only English and Hindi may be requested explicitly.
    """
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned or cleaned == AUTO_LANGUAGE:
        return None
    if cleaned not in SUPPORTED_LANGUAGES:
        allowed = ", ".join(SUPPORTED_LANGUAGES)
        raise UnsupportedLanguage(
            f"Language '{value}' is not supported. Use 'auto', {allowed}."
        )
    return cleaned


class TranscriptionEngine(Protocol):
    """Interface implemented by speech-to-text engines."""

    @property
    def model_name(self) -> str:
        """Identifier of the loaded model (e.g. ``tiny``)."""
        ...

    async def load(self) -> None:
        """Download (on first use) and load the model."""
        ...

    async def transcribe(
        self,
        pcm: bytes,
        *,
        sample_rate: int = INPUT_SAMPLE_RATE,
        language: str | None | object = UNSET,
        beam_size: int | None = None,
        vad_filter: bool | None = None,
        vad_parameters: dict | None = None,
    ) -> TranscriptionResult:
        """Transcribe 16 kHz mono int16 PCM.

        ``language`` is a per-call override; ``None`` forces automatic
        detection.  Omitted, the engine's configured default is used.
        ``beam_size``, ``vad_filter`` and ``vad_parameters`` are optional
        per-call decoding overrides.
        """
        ...

    async def close(self) -> None:
        """Release the model and any resources it holds."""
        ...


__all__ = [
    "AUTO_LANGUAGE",
    "INPUT_SAMPLE_RATE",
    "STATUS_DONE",
    "STATUS_LOADING",
    "STATUS_PREPARING",
    "STATUS_READY",
    "STATUS_TRANSCRIBING",
    "SUPPORTED_LANGUAGES",
    "UNSET",
    "StatusCallback",
    "TranscriptionEngine",
    "TranscriptionResult",
    "TranscriptionStatus",
    "normalize_language",
]
