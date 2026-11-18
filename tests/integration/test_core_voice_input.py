"""CoreService voice-input integration tests (real core loop, fake engine).

The engine is faked so no model is downloaded, but the real CoreService
thread, scheduling, cancellation and signal delivery are exercised.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from friday.config.settings import MemorySettings, Settings
from friday.core.service import CoreService
from friday.voice.errors import ModelLoadError
from friday.voice.stt.base import TranscriptionResult

PCM = b"\x00\x01" * 1600
CORE_THREAD = "friday-core"


class FakeTranscriptionEngine:
    """Signal-free engine that records its calls and thread."""

    def __init__(
        self,
        *,
        text: str = "Hello Friday",
        language: str = "en",
        fail: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self.result = TranscriptionResult(
            text=text,
            language=language,
            language_probability=0.91,
            duration_seconds=2.0,
            duration_after_vad_seconds=1.8,
            segment_count=3,
        )
        self.fail = fail
        self.delay = delay
        self.calls: list[bytes] = []
        self.threads: list[str] = []
        self.entered = threading.Event()
        self.closed = False

    @property
    def model_name(self) -> str:
        return "fake"

    async def load(self) -> None:
        return None

    async def transcribe(self, pcm: bytes, **kwargs) -> TranscriptionResult:
        self.calls.append(bytes(pcm))
        self.threads.append(threading.current_thread().name)
        self.entered.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        return self.result

    async def close(self) -> None:
        self.closed = True


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


def settle(seconds: float = 0.15) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    QCoreApplication.processEvents()


def _settings(tmp_path) -> Settings:
    return Settings(
        memory=MemorySettings(db_path=str(tmp_path / "friday.db"))
    )


def _core(tmp_path) -> CoreService:
    return CoreService(settings=_settings(tmp_path))


@pytest.fixture
def engine(monkeypatch) -> FakeTranscriptionEngine:
    fake = FakeTranscriptionEngine()
    monkeypatch.setattr(
        "friday.voice.stt.create_transcription_engine",
        lambda **kwargs: fake,
    )
    return fake


def test_transcription_runs_on_the_core_thread_and_emits_result(
    qt_app, tmp_path, engine
) -> None:
    core = _core(tmp_path)
    results = QSignalSpy(core.signals.voice_result)
    errors = QSignalSpy(core.signals.voice_error)
    core.start()

    try:
        core.transcribe_voice(PCM)
        assert wait_until(lambda: results.count() == 1)
        settle()

        result = results.at(0)[0]
        assert result.text == "Hello Friday"
        assert result.language == "en"
        assert result.duration_after_vad_seconds == 1.8
        assert engine.calls == [PCM]
        assert engine.threads == [CORE_THREAD]
        assert threading.current_thread().name != engine.threads[0]
        assert errors.count() == 0
    finally:
        core.stop()

    assert engine.closed is True


def test_repeated_transcriptions_are_allowed_after_completion(
    qt_app, tmp_path, engine
) -> None:
    core = _core(tmp_path)
    results = QSignalSpy(core.signals.voice_result)
    core.start()

    try:
        core.transcribe_voice(PCM)
        assert wait_until(lambda: results.count() == 1)
        core.transcribe_voice(PCM + b"\x00\x00")
        assert wait_until(lambda: results.count() == 2)
        assert len(engine.calls) == 2
    finally:
        core.stop()


def test_second_transcription_while_busy_is_rejected(
    qt_app, tmp_path, engine
) -> None:
    engine.delay = 0.4
    core = _core(tmp_path)
    results = QSignalSpy(core.signals.voice_result)
    errors = QSignalSpy(core.signals.voice_error)
    core.start()

    try:
        core.transcribe_voice(PCM)
        assert wait_until(lambda: engine.entered.is_set())
        core.transcribe_voice(PCM)
        assert wait_until(lambda: errors.count() == 1)
        assert errors.at(0)[0] == "Busy"
        assert wait_until(lambda: results.count() == 1)
        assert len(engine.calls) == 1
    finally:
        core.stop()


def test_transcription_error_is_delivered_once(
    qt_app, tmp_path, engine
) -> None:
    engine.fail = ModelLoadError("model unavailable")
    core = _core(tmp_path)
    results = QSignalSpy(core.signals.voice_result)
    errors = QSignalSpy(core.signals.voice_error)
    core.start()

    try:
        core.transcribe_voice(PCM)
        assert wait_until(lambda: errors.count() == 1)
        settle(0.2)
        assert errors.count() == 1
        assert errors.at(0)[0] == "ModelLoadError"
        assert results.count() == 0
    finally:
        core.stop()


def test_cancel_in_flight_transcription_emits_cancelled(
    qt_app, tmp_path, engine
) -> None:
    engine.delay = 5.0
    core = _core(tmp_path)
    results = QSignalSpy(core.signals.voice_result)
    errors = QSignalSpy(core.signals.voice_error)
    cancelled = QSignalSpy(core.signals.voice_cancelled)
    core.start()

    try:
        core.transcribe_voice(PCM)
        assert wait_until(lambda: engine.entered.is_set())
        core.cancel_voice_input()
        assert wait_until(lambda: cancelled.count() == 1)
        settle(0.2)
        assert results.count() == 0
        assert errors.count() == 0
    finally:
        core.stop()


def test_empty_audio_is_rejected_without_creating_the_engine(
    qt_app, tmp_path, monkeypatch
) -> None:
    created: list[dict] = []
    monkeypatch.setattr(
        "friday.voice.stt.create_transcription_engine",
        lambda **kwargs: created.append(kwargs) or FakeTranscriptionEngine(),
    )
    core = _core(tmp_path)
    errors = QSignalSpy(core.signals.voice_error)
    core.start()

    try:
        core.transcribe_voice(b"")
        assert errors.count() == 1
        assert errors.at(0)[0] == "EmptyAudio"
        assert created == []
    finally:
        core.stop()


def test_voice_transcription_requires_a_running_core(qt_app) -> None:
    core = CoreService()
    errors = QSignalSpy(core.signals.voice_error)

    core.transcribe_voice(PCM)

    assert errors.count() == 1
    assert errors.at(0)[0] == "CoreNotRunning"


def test_engine_is_created_once_for_repeated_attempts(
    qt_app, tmp_path, monkeypatch
) -> None:
    engine = FakeTranscriptionEngine()
    created: list[dict] = []

    def factory(**kwargs):
        created.append(kwargs)
        return engine

    monkeypatch.setattr(
        "friday.voice.stt.create_transcription_engine", factory
    )
    core = _core(tmp_path)
    results = QSignalSpy(core.signals.voice_result)
    core.start()

    try:
        core.transcribe_voice(PCM)
        assert wait_until(lambda: results.count() == 1)
        core.transcribe_voice(PCM)
        assert wait_until(lambda: results.count() == 2)
        assert len(created) == 1
    finally:
        core.stop()
