"""Contract tests against the installed Faster-Whisper API.

These tests never download a model.  They fail if the installed
``faster_whisper`` signatures drift away from what the engine passes.
"""

from __future__ import annotations

import inspect

import pytest

pytest.importorskip("faster_whisper")

from faster_whisper import WhisperModel  # noqa: E402
from faster_whisper.transcribe import TranscriptionInfo  # noqa: E402

from friday.voice.stt import FasterWhisperEngine  # noqa: E402


def test_whisper_model_accepts_the_engine_kwargs() -> None:
    params = inspect.signature(WhisperModel.__init__).parameters
    engine = FasterWhisperEngine(cpu_threads=2, download_root="cache")

    engine_kwargs = engine._model_kwargs()

    assert set(engine_kwargs) <= set(params)
    assert engine_kwargs["device"] == "cpu"
    assert engine_kwargs["compute_type"] == "int8"
    assert engine_kwargs["model_size_or_path"] == "tiny"


def test_transcribe_accepts_audio_and_language() -> None:
    params = inspect.signature(WhisperModel.transcribe).parameters

    assert "audio" in params
    assert "language" in params


def test_transcribe_accepts_decoding_and_vad_options() -> None:
    params = inspect.signature(WhisperModel.transcribe).parameters

    assert {"beam_size", "vad_filter", "vad_parameters"} <= set(params)


def test_engine_vad_dict_matches_vad_options() -> None:
    from faster_whisper.vad import VadOptions

    engine = FasterWhisperEngine(vad_filter=True)
    options = VadOptions(**engine._vad_options())

    assert options.threshold == 0.4
    assert options.min_silence_duration_ms == 500
    assert options.speech_pad_ms == 400
    assert options.min_speech_duration_ms == 0


def test_info_exposes_the_result_fields() -> None:
    fields = getattr(
        TranscriptionInfo,
        "_fields",
        getattr(TranscriptionInfo, "__annotations__", {}),
    )

    assert {"language", "language_probability", "duration"} <= set(fields)


def test_engine_never_defaults_to_an_english_only_model() -> None:
    assert FasterWhisperEngine().model_name == "tiny"
    assert not FasterWhisperEngine().model_name.endswith(".en")
