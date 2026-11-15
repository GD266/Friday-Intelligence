"""TTS engine implementations."""

from friday.voice.tts.base import (
    EngineFactory,
    SynthesisResult,
    TTSEngine,
    Voice,
)
from friday.voice.tts.edge import EdgeTTSEngine
from friday.voice.tts.windows import WindowsTTSEngine

__all__ = [
    "EngineFactory",
    "SynthesisResult",
    "TTSEngine",
    "Voice",
    "EdgeTTSEngine",
    "WindowsTTSEngine",
]
