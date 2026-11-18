"""Tests for the local Faster-Whisper transcription engine.

The real model is never downloaded here: every test injects a fake model
factory.  Audio stays in memory as a float32 array (no container and no
temporary files), and the fake records the exact decoding options.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from array import array
from types import SimpleNamespace

import numpy as np
import pytest

from friday.config.settings import STTSettings
from friday.voice.errors import (
    EmptyAudio,
    ModelLoadError,
    TranscriptionError,
    TranscriptionNotAvailable,
    UnsupportedAudioFormat,
    UnsupportedLanguage,
)
from friday.voice.stt import (
    STATUS_DONE,
    STATUS_LOADING,
    STATUS_PREPARING,
    STATUS_READY,
    STATUS_TRANSCRIBING,
    FasterWhisperEngine,
    create_transcription_engine,
    normalize_language,
)

MAIN_THREAD = threading.main_thread().name


def _pcm(seconds: float = 0.25) -> bytes:
    """Return silence as 16 kHz mono int16 PCM."""
    return bytes(2 * int(16_000 * seconds))


class FakeModel:
    """Stand-in for faster_whisper.WhisperModel."""

    def __init__(
        self,
        *,
        language: str = "en",
        probability: float = 0.97,
        duration: float = 0.25,
        after_vad: float | None = None,
        segments: tuple[str, ...] = (" Hello", " world"),
        error: Exception | None = None,
    ) -> None:
        self.language = language
        self.probability = probability
        self.duration = duration
        self.after_vad = after_vad
        self.segments = segments
        self.error = error
        self.calls: list[dict[str, object]] = []
        self.audio = None
        self.thread_name = ""

    def transcribe(self, audio, **options):
        self.calls.append(dict(options))
        self.thread_name = threading.current_thread().name
        if self.error is not None:
            raise self.error
        self.audio = audio
        info = SimpleNamespace(
            language=self.language,
            language_probability=self.probability,
            duration=self.duration,
            duration_after_vad=self.after_vad,
        )
        chunks = [SimpleNamespace(text=part) for part in self.segments]
        return iter(chunks), info


class FakeFactory:
    """Records how the engine constructs the model."""

    def __init__(
        self,
        model: FakeModel | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.model = model or FakeModel()
        self.error = error
        self.calls = 0
        self.kwargs: dict[str, object] = {}
        self.thread_name = ""

    def __call__(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        self.thread_name = threading.current_thread().name
        if self.error is not None:
            raise self.error
        return self.model


class GatedFactory(FakeFactory):
    """Blocks construction until the test releases it."""

    def __init__(self, model: FakeModel | None = None) -> None:
        super().__init__(model)
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        self.thread_name = threading.current_thread().name
        self.entered.set()
        self.release.wait(timeout=10)
        return self.model


def _engine(factory, **kwargs) -> FasterWhisperEngine:
    return FasterWhisperEngine(
        model_factory=factory, heartbeat_seconds=0.01, **kwargs
    )


def test_normalize_language() -> None:
    assert normalize_language(None) is None
    assert normalize_language("") is None
    assert normalize_language("auto") is None
    assert normalize_language("EN") == "en"
    assert normalize_language(" hi ") == "hi"
    with pytest.raises(UnsupportedLanguage):
        normalize_language("fr")


def test_english_only_model_is_rejected() -> None:
    with pytest.raises(ValueError, match="English-only"):
        FasterWhisperEngine(model="tiny.en")
    with pytest.raises(ValueError, match="English-only"):
        FasterWhisperEngine(model="base.en")


def test_multilingual_tiny_and_base_are_accepted() -> None:
    assert FasterWhisperEngine(model="tiny").model_name == "tiny"
    assert FasterWhisperEngine(model="base").model_name == "base"


def test_invalid_beam_size_is_rejected() -> None:
    with pytest.raises(ValueError, match="beam_size"):
        FasterWhisperEngine(beam_size=0)
    with pytest.raises(ValueError, match="beam_size"):
        FasterWhisperEngine(beam_size=11)


def test_invalid_vad_settings_are_rejected() -> None:
    for kwargs in (
        {"vad_threshold": 0},
        {"vad_threshold": 1},
        {"vad_min_silence_ms": -1},
        {"vad_speech_pad_ms": -1},
        {"vad_min_speech_ms": -1},
    ):
        with pytest.raises(ValueError):
            FasterWhisperEngine(**kwargs)


@pytest.mark.asyncio
async def test_load_uses_cpu_int8_and_multilingual_tiny() -> None:
    factory = FakeFactory()
    engine = _engine(factory)

    await engine.load()

    assert factory.kwargs["model_size_or_path"] == "tiny"
    assert factory.kwargs["device"] == "cpu"
    assert factory.kwargs["compute_type"] == "int8"
    assert "cpu_threads" not in factory.kwargs
    assert engine.model_name == "tiny"
    assert engine.is_loaded is True


@pytest.mark.asyncio
async def test_load_passes_cpu_threads_when_configured() -> None:
    factory = FakeFactory()
    engine = _engine(factory, cpu_threads=4)

    await engine.load()

    assert factory.kwargs["cpu_threads"] == 4


@pytest.mark.asyncio
async def test_model_loads_on_a_worker_thread() -> None:
    factory = FakeFactory()
    engine = _engine(factory)

    await engine.load()

    assert factory.thread_name != MAIN_THREAD


@pytest.mark.asyncio
async def test_transcription_runs_on_a_worker_thread() -> None:
    model = FakeModel()
    engine = _engine(FakeFactory(model))

    await engine.transcribe(_pcm())

    assert model.thread_name != MAIN_THREAD


@pytest.mark.asyncio
async def test_load_reports_download_and_heartbeat_progress() -> None:
    factory = GatedFactory()
    statuses = []
    engine = _engine(factory, on_status=statuses.append)

    task = asyncio.create_task(engine.load())
    for _ in range(500):
        if factory.entered.is_set():
            break
        await asyncio.sleep(0.005)
    assert factory.entered.is_set()

    for _ in range(500):
        loading = [s for s in statuses if s.phase == STATUS_LOADING]
        if len(loading) >= 2:
            break
        await asyncio.sleep(0.005)
    factory.release.set()
    await asyncio.wait_for(task, timeout=10)

    assert statuses[0].phase == STATUS_PREPARING
    assert "first run" in statuses[0].message.lower()
    loading = [s for s in statuses if s.phase == STATUS_LOADING]
    assert len(loading) >= 2
    assert all(s.elapsed_seconds > 0 for s in loading)
    assert "elapsed" in loading[-1].message
    assert statuses[-1].phase == STATUS_READY
    assert "ready" in statuses[-1].message.lower()


@pytest.mark.asyncio
async def test_model_load_failure_raises_model_load_error() -> None:
    engine = _engine(FakeFactory(error=OSError("disk full")))

    with pytest.raises(ModelLoadError, match="Could not download"):
        await engine.load()

    assert engine.is_loaded is False


@pytest.mark.asyncio
async def test_missing_faster_whisper_package_is_reported(
    monkeypatch,
) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    engine = FasterWhisperEngine()

    with pytest.raises(TranscriptionNotAvailable, match="not installed"):
        await engine.load()


@pytest.mark.asyncio
async def test_auto_language_is_detected() -> None:
    model = FakeModel(language="hi", probability=0.91, duration=2.5)
    engine = _engine(FakeFactory(model), language="auto")

    result = await engine.transcribe(_pcm(2.5))

    assert result.text == "Hello world"
    assert result.language == "hi"
    assert result.language_probability == pytest.approx(0.91)
    assert result.duration_seconds == pytest.approx(2.5)
    assert model.calls[-1]["language"] is None


@pytest.mark.asyncio
async def test_explicit_hindi_override_is_passed_through() -> None:
    model = FakeModel(language="hi")
    engine = _engine(FakeFactory(model), language="auto")

    await engine.transcribe(_pcm(), language="hi")

    assert model.calls[-1]["language"] == "hi"


@pytest.mark.asyncio
async def test_configured_language_is_used_when_omitted() -> None:
    model = FakeModel(language="en")
    engine = _engine(FakeFactory(model), language="en")

    await engine.transcribe(_pcm())

    assert model.calls[-1]["language"] == "en"


@pytest.mark.asyncio
async def test_explicit_none_forces_detection_over_configured_language() -> None:
    model = FakeModel(language="hi")
    engine = _engine(FakeFactory(model), language="en")

    await engine.transcribe(_pcm(), language=None)

    assert model.calls[-1]["language"] is None


@pytest.mark.asyncio
async def test_transcribe_passes_default_beam_and_safe_vad() -> None:
    model = FakeModel()
    engine = _engine(FakeFactory(model))

    await engine.transcribe(_pcm())

    options = model.calls[-1]
    assert options["beam_size"] == 5
    assert options["vad_filter"] is True
    assert options["vad_parameters"] == {
        "threshold": 0.4,
        "min_silence_duration_ms": 500,
        "speech_pad_ms": 400,
        "min_speech_duration_ms": 0,
    }
    assert engine.beam_size == 5
    assert engine.vad_filter is True


@pytest.mark.asyncio
async def test_per_call_beam_and_vad_overrides() -> None:
    model = FakeModel(after_vad=0.2)
    engine = _engine(FakeFactory(model), beam_size=5, vad_filter=False)

    result = await engine.transcribe(
        _pcm(), beam_size=1, vad_filter=True
    )

    options = model.calls[-1]
    assert options["beam_size"] == 1
    assert options["vad_filter"] is True
    assert options["vad_parameters"] == {
        "threshold": 0.4,
        "min_silence_duration_ms": 500,
        "speech_pad_ms": 400,
        "min_speech_duration_ms": 0,
    }
    assert result.duration_after_vad_seconds == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_configured_beam_and_vad_options_are_used() -> None:
    model = FakeModel(after_vad=0.25)
    engine = _engine(
        FakeFactory(model),
        beam_size=1,
        vad_filter=True,
        vad_threshold=0.3,
        vad_min_silence_ms=250,
        vad_speech_pad_ms=600,
        vad_min_speech_ms=100,
    )

    await engine.transcribe(_pcm())

    options = model.calls[-1]
    assert options["beam_size"] == 1
    assert options["vad_filter"] is True
    assert options["vad_parameters"] == {
        "threshold": 0.3,
        "min_silence_duration_ms": 250,
        "speech_pad_ms": 600,
        "min_speech_duration_ms": 100,
    }


@pytest.mark.asyncio
async def test_per_call_vad_parameters_override_engine_defaults() -> None:
    model = FakeModel(after_vad=0.2)
    engine = _engine(FakeFactory(model), vad_filter=True)

    await engine.transcribe(
        _pcm(), vad_parameters={"threshold": 0.6}
    )

    assert model.calls[-1]["vad_parameters"] == {"threshold": 0.6}


@pytest.mark.asyncio
async def test_invalid_per_call_beam_size_is_rejected() -> None:
    engine = _engine(FakeFactory())

    with pytest.raises(ValueError, match="beam_size"):
        await engine.transcribe(_pcm(), beam_size=0)


@pytest.mark.asyncio
async def test_result_records_segments_and_post_vad_duration() -> None:
    model = FakeModel(
        segments=(" one", " two", " three"), after_vad=0.2
    )
    engine = _engine(FakeFactory(model))

    result = await engine.transcribe(_pcm(), vad_filter=True)

    assert result.segment_count == 3
    assert result.duration_after_vad_seconds == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_vad_disabled_leaves_post_vad_duration_unknown() -> None:
    model = FakeModel(after_vad=0.2)
    engine = _engine(FakeFactory(model), vad_filter=False)

    result = await engine.transcribe(_pcm())

    assert result.duration_after_vad_seconds is None


@pytest.mark.asyncio
async def test_unsupported_language_is_rejected() -> None:
    engine = _engine(FakeFactory())

    with pytest.raises(UnsupportedLanguage):
        await engine.transcribe(_pcm(), language="fr")


@pytest.mark.asyncio
async def test_empty_audio_is_rejected_without_loading() -> None:
    factory = FakeFactory()
    engine = _engine(factory)

    with pytest.raises(EmptyAudio):
        await engine.transcribe(b"")
    with pytest.raises(EmptyAudio):
        await engine.transcribe(b"\x01")

    assert factory.calls == 0


@pytest.mark.asyncio
async def test_unsupported_sample_rate_is_rejected() -> None:
    engine = _engine(FakeFactory())

    with pytest.raises(UnsupportedAudioFormat, match="16000"):
        await engine.transcribe(_pcm(), sample_rate=48_000)


@pytest.mark.asyncio
async def test_audio_is_passed_as_float32_without_container() -> None:
    model = FakeModel()
    engine = _engine(FakeFactory(model))
    samples = array("h", [0, 16384, -32768, 32767])

    await engine.transcribe(samples.tobytes())

    audio = model.audio
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.shape == (4,)
    np.testing.assert_allclose(
        audio, [0.0, 0.5, -1.0, 32767 / 32768], rtol=0, atol=1e-7
    )


@pytest.mark.asyncio
async def test_odd_length_pcm_is_trimmed_not_corrupted() -> None:
    model = FakeModel()
    engine = _engine(FakeFactory(model))
    samples = array("h", [100, -100, 200, 300])
    pcm = samples.tobytes() + b"\x7f"

    await engine.transcribe(pcm)

    assert model.audio.shape == (4,)
    np.testing.assert_allclose(
        model.audio, [100 / 32768, -100 / 32768, 200 / 32768, 300 / 32768]
    )


@pytest.mark.asyncio
async def test_transcribe_loads_the_model_on_first_use() -> None:
    factory = FakeFactory()
    statuses = []
    engine = _engine(factory, on_status=statuses.append)

    await engine.transcribe(_pcm())

    assert factory.calls == 1
    phases = [status.phase for status in statuses]
    assert STATUS_PREPARING in phases
    assert STATUS_READY in phases
    assert STATUS_TRANSCRIBING in phases
    assert phases[-1] == STATUS_DONE


@pytest.mark.asyncio
async def test_recognition_text_is_not_logged(caplog) -> None:
    model = FakeModel(segments=(" secret phrase",))
    engine = _engine(FakeFactory(model))

    with caplog.at_level(logging.INFO):
        await engine.transcribe(_pcm())

    assert "stt_transcription_done" in caplog.text
    assert "secret phrase" not in caplog.text


@pytest.mark.asyncio
async def test_transcription_failure_is_wrapped_and_model_stays_loaded() -> None:
    model = FakeModel(error=RuntimeError("decoder exploded"))
    engine = _engine(FakeFactory(model))

    with pytest.raises(TranscriptionError, match="decoder exploded"):
        await engine.transcribe(_pcm())

    assert engine.is_loaded is True


@pytest.mark.asyncio
async def test_model_is_loaded_once_and_can_be_released() -> None:
    first = FakeModel()
    factory = FakeFactory(first)
    engine = _engine(factory)

    await engine.load()
    await engine.load()
    assert factory.calls == 1

    await engine.close()
    assert engine.is_loaded is False

    second = FakeModel()
    factory.model = second
    await engine.load()
    assert factory.calls == 2
    assert engine.is_loaded is True


@pytest.mark.asyncio
async def test_status_callback_errors_do_not_break_transcription() -> None:
    def boom(_status) -> None:
        raise RuntimeError("ui is gone")

    engine = _engine(FakeFactory(), on_status=boom)

    result = await engine.transcribe(_pcm())

    assert result.text == "Hello world"


def test_create_transcription_engine_uses_settings() -> None:
    settings = STTSettings(
        model="small",
        cpu_threads=3,
        language="hi",
        beam_size=1,
        vad_filter=True,
        vad_threshold=0.3,
        vad_min_silence_ms=250,
        vad_speech_pad_ms=600,
        vad_min_speech_ms=100,
    )

    engine = create_transcription_engine(settings=settings)

    assert isinstance(engine, FasterWhisperEngine)
    assert engine.model_name == "small"
    assert engine.language == "hi"
    assert engine.beam_size == 1
    assert engine.vad_filter is True
    assert engine._vad_options() == {
        "threshold": 0.3,
        "min_silence_duration_ms": 250,
        "speech_pad_ms": 600,
        "min_speech_duration_ms": 100,
    }


def test_create_transcription_engine_maps_auto_language_to_none() -> None:
    engine = create_transcription_engine(settings=STTSettings())

    assert engine.model_name == "tiny"
    assert engine.language is None
