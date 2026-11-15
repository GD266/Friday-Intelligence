"""Voice module for FRIDAY 2.0 — Text-to-speech output."""

from __future__ import annotations

from typing import Any

from friday.voice.tts.base import EngineFactory
from friday.voice.tts.edge import EdgeTTSEngine
from friday.voice.tts.windows import WindowsTTSEngine

# Register built-in engines
EngineFactory.register("edge", EdgeTTSEngine)
EngineFactory.register("windows", WindowsTTSEngine)


def create_engine(name: str, **kwargs: Any) -> Any:
    """Create a TTS engine by name."""
    return EngineFactory.create(name, **kwargs)


def available_engines() -> list[str]:
    """Return list of available engine names."""
    return EngineFactory.available_engines()


__all__ = [
    "create_engine",
    "available_engines",
    "EdgeTTSEngine",
    "WindowsTTSEngine",
]
