"""TTS engine interface and base types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Voice:
    """A voice offered by a TTS engine."""

    name: str
    locale: str
    gender: str
    age: str
    # Engine-specific identifier (e.g., registry key for Windows, voice ID for edge-tts)
    engine_id: str


@dataclass(frozen=True, slots=True)
class SynthesisResult:
    """Result of text-to-speech synthesis."""

    audio_path: str
    format: str  # e.g., "mp3", "wav"
    duration_seconds: float | None = None


class TTSEngine(ABC):
    """Interface for a text-to-speech engine."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine identifier (e.g., 'edge', 'windows')."""
        raise NotImplementedError

    @abstractmethod
    async def list_voices(self) -> list[Voice]:
        """Return available voices for this engine."""
        raise NotImplementedError

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str,
        rate_percent: int,
    ) -> SynthesisResult:
        """
        Synthesize text to speech.

        Args:
            text: Text to synthesize (already prepared for speech).
            voice: Voice name or engine-specific identifier.
            rate_percent: Speech rate adjustment (-50 to +50).

        Returns:
            SynthesisResult with path to audio file and format.

        Raises:
            TTSError: On synthesis failure.
        """
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Release any resources held by the engine."""
        raise NotImplementedError


class EngineFactory:
    """Factory for creating TTS engines by name."""

    _engines: dict[str, type[TTSEngine]] = {}

    @classmethod
    def register(cls, name: str, engine_cls: type[TTSEngine]) -> None:
        cls._engines[name.lower()] = engine_cls

    @classmethod
    def create(cls, name: str, **kwargs: Any) -> TTSEngine:
        engine_cls = cls._engines.get(name.lower())
        if engine_cls is None:
            from friday.voice.errors import TTSNotAvailable

            raise TTSNotAvailable(f"TTS engine '{name}' is not available")
        return engine_cls(**kwargs)

    @classmethod
    def available_engines(cls) -> list[str]:
        return list(cls._engines.keys())


__all__ = [
    "Voice",
    "SynthesisResult",
    "TTSEngine",
    "EngineFactory",
]
