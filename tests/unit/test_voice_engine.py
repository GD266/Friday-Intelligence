"""Tests for TTS engines (fake, no network)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from friday.voice import available_engines, create_engine
from friday.voice.errors import TTSError, TTSNotAvailable
from friday.voice.tts.base import SynthesisResult, TTSEngine, Voice
from friday.voice.tts.edge import EdgeTTSEngine
from friday.voice.tts.windows import WindowsTTSEngine


class MockEdgeEngine(TTSEngine):
    """Mock Edge TTS engine for testing."""

    def __init__(
        self, *, should_fail: bool = False, error: Exception | None = None
    ) -> None:
        self._should_fail = should_fail
        self._error = error
        self.list_voices_called = False
        self.synthesize_calls = []

    @property
    def name(self) -> str:
        return "edge"

    async def list_voices(self) -> list:
        self.list_voices_called = True
        return [
            Voice(
                name="Microsoft David",
                locale="en-US",
                gender="Male",
                age="Adult",
                engine_id="en-US-DavidNeural",
            ),
            Voice(
                name="Microsoft Zira",
                locale="en-US",
                gender="Female",
                age="Adult",
                engine_id="en-US-ZiraNeural",
            ),
        ]

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate_percent: int,
    ) -> SynthesisResult:
        self.synthesize_calls.append((text, voice, rate_percent))
        if not text or not text.strip():
            from friday.voice.errors import TTSEmptyText

            raise TTSEmptyText("Text is empty after preparation")
        if voice not in [v.engine_id for v in await self.list_voices()]:
            from friday.voice.errors import TTSBadVoice

            raise TTSBadVoice(f"Voice '{voice}' not found in Edge TTS voices")
        if self._should_fail:
            raise self._error or TTSError("Synthesis failed")
        return SynthesisResult(audio_path="/tmp/test.mp3", format="mp3")

    async def close(self) -> None:
        pass


class MockWindowsEngine(TTSEngine):
    """Mock Windows TTS engine for testing."""

    def __init__(
        self, *, should_fail: bool = False, error: Exception | None = None
    ) -> None:
        self._should_fail = should_fail
        self._error = error
        self.list_voices_called = False
        self.synthesize_calls = []

    @property
    def name(self) -> str:
        return "windows"

    async def list_voices(self) -> list:
        self.list_voices_called = True
        return [
            Voice(
                name="Microsoft David",
                locale="en-US",
                gender="Male",
                age="Adult",
                engine_id="Microsoft David",
            ),
            Voice(
                name="Microsoft Zira",
                locale="en-US",
                gender="Female",
                age="Adult",
                engine_id="Microsoft Zira",
            ),
        ]

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate_percent: int,
    ) -> SynthesisResult:
        self.synthesize_calls.append((text, voice, rate_percent))
        if not text or not text.strip():
            from friday.voice.errors import TTSEmptyText

            raise TTSEmptyText("Text is empty after preparation")
        if voice not in [v.engine_id for v in await self.list_voices()]:
            from friday.voice.errors import TTSBadVoice

            raise TTSBadVoice(f"Voice '{voice}' not found in Windows TTS voices")
        if self._should_fail:
            from friday.voice.errors import TTSError

            raise self._error or TTSError("Synthesis failed")
        return SynthesisResult(audio_path="/tmp/test.wav", format="wav")

    async def close(self) -> None:
        pass


def test_available_engines() -> None:
    engines = available_engines()
    assert "edge" in engines
    assert "windows" in engines


def test_create_engine_edge() -> None:
    engine = create_engine("edge")
    assert isinstance(engine, EdgeTTSEngine)
    assert engine.name == "edge"


def test_create_engine_windows() -> None:
    engine = create_engine("windows")
    assert isinstance(engine, WindowsTTSEngine)
    assert engine.name == "windows"


def test_create_engine_unknown_raises() -> None:
    with pytest.raises(TTSNotAvailable):
        create_engine("unknown")


@pytest.mark.asyncio
async def test_edge_list_voices() -> None:
    engine = MockEdgeEngine()
    voices = await engine.list_voices()
    assert len(voices) >= 2
    assert any(v.engine_id == "en-US-DavidNeural" for v in voices)


@pytest.mark.asyncio
async def test_edge_synthesize_valid() -> None:
    engine = MockEdgeEngine()
    result = await engine.synthesize("Hello world", "en-US-DavidNeural", 0)
    assert result.audio_path == "/tmp/test.mp3"
    assert result.format == "mp3"
    assert engine.synthesize_calls == [("Hello world", "en-US-DavidNeural", 0)]


@pytest.mark.asyncio
async def test_edge_synthesize_empty_text_raises() -> None:
    engine = MockEdgeEngine()
    with pytest.raises(Exception) as exc_info:
        await engine.synthesize("", "en-US-DavidNeural", 0)
    assert "empty" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_edge_synthesize_invalid_voice_raises() -> None:
    engine = MockEdgeEngine()
    with pytest.raises(Exception) as exc_info:
        await engine.synthesize("Hello", "invalid-voice", 0)
    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_edge_synthesize_error_handling() -> None:
    engine = MockEdgeEngine(should_fail=True, error=Exception("Network error"))
    with pytest.raises(Exception):
        await engine.synthesize("Hello", "voice", 0)


@pytest.mark.asyncio
async def test_windows_list_voices() -> None:
    engine = MockWindowsEngine()
    voices = await engine.list_voices()
    assert len(voices) >= 2
    assert any(v.engine_id == "Microsoft David" for v in voices)


@pytest.mark.asyncio
async def test_windows_synthesize_valid() -> None:
    engine = MockWindowsEngine()
    result = await engine.synthesize("Hello world", "Microsoft David", 0)
    assert result.audio_path == "/tmp/test.wav"
    assert result.format == "wav"
    assert engine.synthesize_calls == [("Hello world", "Microsoft David", 0)]


@pytest.mark.asyncio
async def test_windows_synthesize_empty_text_raises() -> None:
    engine = MockWindowsEngine()
    with pytest.raises(Exception) as exc_info:
        await engine.synthesize("", "Microsoft David", 0)
    assert "empty" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_windows_synthesize_invalid_voice_raises() -> None:
    engine = MockWindowsEngine()
    with pytest.raises(Exception) as exc_info:
        await engine.synthesize("Hello", "Invalid Voice", 0)
    assert "not found" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_windows_synthesize_error_handling() -> None:
    engine = MockWindowsEngine(should_fail=True, error=Exception("SAPI error"))
    with pytest.raises(Exception):
        await engine.synthesize("Hello", "Microsoft David", 0)


def test_engine_factory_registry() -> None:
    from friday.voice.tts.base import EngineFactory

    # EngineFactory should have both engines registered
    engines = EngineFactory.available_engines()
    assert "edge" in engines
    assert "windows" in engines


@pytest.mark.asyncio
async def test_edge_synthesize_voice_parameter_passed_through() -> None:
    """Verify the voice parameter is correctly passed to edge_tts.Communicate."""

    # Create a real EdgeTTSEngine but mock the edge_tts internals
    engine = EdgeTTSEngine()

    # Mock list_voices to return known voices
    mock_voices = [
        Voice(
            name="Test Voice",
            locale="en-US",
            gender="Female",
            age="Adult",
            engine_id="en-US-AriaNeural",
        ),
        Voice(
            name="Test Voice 2",
            locale="en-US",
            gender="Male",
            age="Adult",
            engine_id="en-US-GuyNeural",
        ),
    ]

    with patch.object(engine, "list_voices", return_value=mock_voices):
        with patch("edge_tts.Communicate") as mock_communicate_class:
            mock_communicate = AsyncMock()
            mock_communicate.save = AsyncMock()
            mock_communicate_class.return_value = mock_communicate

            # Mock tempfile to avoid actual file creation
            with patch("tempfile.mkstemp", return_value=(3, "/tmp/test.mp3")):
                with patch("os.close"):
                    with patch("pathlib.Path.exists", return_value=True):
                        with patch("pathlib.Path.stat") as mock_stat:
                            mock_stat.return_value.st_size = 1000
                            await engine.synthesize("Test text", "en-US-AriaNeural", 0)

    # Verify the voice was passed correctly to Communicate
    mock_communicate_class.assert_called_once()
    call_kwargs = mock_communicate_class.call_args[1]
    assert call_kwargs["voice"] == "en-US-AriaNeural"
    assert call_kwargs["text"] == "Test text"
    assert call_kwargs["rate"] == "+0%"


@pytest.mark.asyncio
async def test_edge_synthesize_default_voice_when_empty() -> None:
    """Verify default voice is used when voice parameter is empty."""

    engine = EdgeTTSEngine()

    mock_voices = [
        Voice(
            name="Test Voice",
            locale="en-US",
            gender="Female",
            age="Adult",
            engine_id="en-US-AriaNeural",
        ),
        Voice(
            name="Test Voice 2",
            locale="en-GB",
            gender="Male",
            age="Adult",
            engine_id="en-GB-RyanNeural",
        ),
    ]

    with patch.object(engine, "list_voices", return_value=mock_voices):
        with patch("edge_tts.Communicate") as mock_communicate_class:
            mock_communicate = AsyncMock()
            mock_communicate.save = AsyncMock()
            mock_communicate_class.return_value = mock_communicate

            with patch("tempfile.mkstemp", return_value=(3, "/tmp/test.mp3")):
                with patch("os.close"):
                    with patch("pathlib.Path.exists", return_value=True):
                        with patch("pathlib.Path.stat") as mock_stat:
                            mock_stat.return_value.st_size = 1000
                            await engine.synthesize("Test text", "", 0)

    # Should use the first en- voice as default
    mock_communicate_class.assert_called_once()
    call_kwargs = mock_communicate_class.call_args[1]
    assert call_kwargs["voice"] == "en-US-AriaNeural"
