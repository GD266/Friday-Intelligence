"""Local speech-to-text for FRIDAY 2.0 (Faster-Whisper, CPU/INT8)."""

from __future__ import annotations

from friday.voice.stt.base import (
    AUTO_LANGUAGE,
    INPUT_SAMPLE_RATE,
    STATUS_DONE,
    STATUS_LOADING,
    STATUS_PREPARING,
    STATUS_READY,
    STATUS_TRANSCRIBING,
    SUPPORTED_LANGUAGES,
    StatusCallback,
    TranscriptionEngine,
    TranscriptionResult,
    TranscriptionStatus,
    normalize_language,
)
from friday.voice.stt.faster_whisper import FasterWhisperEngine


def create_transcription_engine(
    *, settings=None, on_status: StatusCallback | None = None
) -> FasterWhisperEngine:
    """Build the configured transcription engine.

    ``settings`` is a ``friday.config.settings.STTSettings`` instance; when
    omitted, defaults are used.  No model is downloaded until ``load()`` or
    the first ``transcribe()`` call.
    """
    if settings is None:
        from friday.config.settings import STTSettings

        settings = STTSettings()
    return FasterWhisperEngine(
        model=settings.model,
        cpu_threads=settings.cpu_threads,
        language=settings.language,
        beam_size=settings.beam_size,
        vad_filter=settings.vad_filter,
        vad_threshold=settings.vad_threshold,
        vad_min_silence_ms=settings.vad_min_silence_ms,
        vad_speech_pad_ms=settings.vad_speech_pad_ms,
        vad_min_speech_ms=settings.vad_min_speech_ms,
        on_status=on_status,
    )


__all__ = [
    "AUTO_LANGUAGE",
    "INPUT_SAMPLE_RATE",
    "STATUS_DONE",
    "STATUS_LOADING",
    "STATUS_PREPARING",
    "STATUS_READY",
    "STATUS_TRANSCRIBING",
    "SUPPORTED_LANGUAGES",
    "FasterWhisperEngine",
    "StatusCallback",
    "TranscriptionEngine",
    "TranscriptionResult",
    "TranscriptionStatus",
    "create_transcription_engine",
    "normalize_language",
]
