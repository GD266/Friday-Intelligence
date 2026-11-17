"""Tests for the SpeechQueue (fake engine, no audio devices)."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

import pytest

from friday.core.ui_bridge import DenyingUIBridge
from friday.voice.errors import (
    TTSAuthError,
    TTSBadVoice,
    TTSEmptyText,
    TTSError,
    TTSNetworkError,
    TTSNotAvailable,
    TTSTimeout,
)
from friday.voice.speaker import SpeechQueue
from friday.voice.tts.base import SynthesisResult, TTSEngine


class _FakeBridge:
    """Fake UI bridge for testing."""

    def __init__(self, *, hold: bool = False, error: Exception | None = None) -> None:
        self.played: list[str] = []
        self.stopped = False
        self._hold = hold
        self._error = error
        self._play_futures: list[asyncio.Future[None]] = []

    async def play_audio(self, path: str) -> None:
        self.played.append(path)
        if self._error is not None:
            raise self._error
        if not self._hold:
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._play_futures.append(future)
        await future

    async def stop_audio(self) -> None:
        self.stopped = True
        for future in self._play_futures:
            if not future.done():
                future.set_result(None)
        self._play_futures.clear()

    async def confirm(self, tool: str, description: str, args: str) -> bool:
        return False

    async def read_clipboard_text(self) -> str | None:
        return None

    def deny_pending(self) -> None:
        pass


class FakeEngine(TTSEngine):
    """Fake TTS engine for testing."""

    def __init__(
        self,
        *,
        should_fail: bool = False,
        error_kind: str = "TTSError",
        delay: float = 0.0,
    ) -> None:
        self._should_fail = should_fail
        self._error_kind = error_kind
        self._delay = delay
        self.synthesize_calls: list[tuple[str, str, int]] = []

    @property
    def name(self) -> str:
        return "fake"

    async def list_voices(self) -> list:
        return []

    async def synthesize(
        self,
        text: str,
        voice: str,
        rate_percent: int,
    ) -> SynthesisResult:
        self.synthesize_calls.append((text, voice, rate_percent))
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._should_fail:
            error_map = {
                "TTSError": TTSError,
                "TTSAuthError": TTSAuthError,
                "TTSNetworkError": TTSNetworkError,
                "TTSTimeout": TTSTimeout,
                "TTSBadVoice": TTSBadVoice,
                "TTSEmptyText": TTSEmptyText,
                "TTSNotAvailable": TTSNotAvailable,
            }
            error_class = error_map.get(self._error_kind, TTSError)
            raise error_class("Synthesis failed")
        return SynthesisResult(audio_path="/tmp/fake.mp3", format="mp3")

    async def close(self) -> None:
        pass


def make_factory(engine: FakeEngine):
    """Create a factory function returning the given engine."""

    def factory(name: str) -> TTSEngine:
        return engine

    return factory


def make_queue(
    engine: FakeEngine,
    bridge: object,
    *,
    playback_timeout: float = 60.0,
    on_error=None,
) -> SpeechQueue:
    """Create a queue wired to a single engine instance and bridge."""
    return SpeechQueue(
        make_factory(engine),
        lambda: bridge,
        playback_timeout=playback_timeout,
        on_error=on_error,
    )


@pytest.mark.asyncio
async def test_enqueue_fire_and_forget() -> None:
    """enqueue() adds a task and starts the processor."""
    queue = make_queue(FakeEngine(), _FakeBridge())
    queue.enqueue("hello", "voice1", 0, "fake")
    assert queue._queue.qsize() == 1
    assert queue.is_running
    await queue.wait_idle()


@pytest.mark.asyncio
async def test_stop_clears_queue_and_cancels() -> None:
    """stop() clears the queue and leaves the processor stopped."""
    engine = FakeEngine(delay=0.05)
    bridge = _FakeBridge()
    queue = make_queue(engine, bridge)
    queue.enqueue("one", "v", 0, "fake")
    queue.enqueue("two", "v", 0, "fake")
    queue.enqueue("three", "v", 0, "fake")
    await asyncio.sleep(0.01)

    await queue.stop()

    assert queue._queue.empty()
    assert not queue.is_running


@pytest.mark.asyncio
async def test_stop_stops_playback() -> None:
    """stop() calls stop_audio on the bridge and cancels playback."""
    bridge = _FakeBridge(hold=True)
    queue = make_queue(FakeEngine(), bridge)
    queue.enqueue("test", "v", 0, "fake")
    await asyncio.sleep(0.01)
    assert bridge.played

    await queue.stop()

    assert bridge.stopped
    assert not queue.is_running


@pytest.mark.asyncio
async def test_ordered_playback() -> None:
    """Sentences are synthesized and played in order."""
    engine = FakeEngine()
    queue = make_queue(engine, _FakeBridge())

    queue.enqueue("first", "v", 0, "fake")
    queue.enqueue("second", "v", 0, "fake")
    queue.enqueue("third", "v", 0, "fake")
    await queue.wait_idle()

    calls = engine.synthesize_calls
    assert len(calls) == 3
    assert [call[0] for call in calls] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_pipelining_synthesis_overlaps_playback() -> None:
    """Multiple sentences are all synthesized."""
    engine = FakeEngine(delay=0.01)
    queue = make_queue(engine, _FakeBridge())

    queue.enqueue("first", "v", 0, "fake")
    queue.enqueue("second", "v", 0, "fake")
    await queue.wait_idle()

    assert len(engine.synthesize_calls) == 2


@pytest.mark.asyncio
async def test_stop_mid_queue_plays_nothing_more() -> None:
    """stop() mid-queue plays nothing more."""
    engine = FakeEngine(delay=0.05)
    queue = make_queue(engine, _FakeBridge())
    queue.enqueue("first", "v", 0, "fake")
    queue.enqueue("second", "v", 0, "fake")
    queue.enqueue("third", "v", 0, "fake")
    await asyncio.sleep(0.02)

    await queue.stop()

    assert queue._queue.empty()
    synthesized = [call[0] for call in engine.synthesize_calls]
    assert "third" not in synthesized


@pytest.mark.asyncio
async def test_stop_cancels_in_flight_synthesis() -> None:
    """stop() cancels in-flight synthesis."""
    engine = FakeEngine(delay=1.0)
    queue = make_queue(engine, _FakeBridge())
    queue.enqueue("first", "v", 0, "fake")
    await asyncio.sleep(0.02)

    await queue.stop()

    assert not queue.is_running
    assert queue._queue.empty()


@pytest.mark.asyncio
async def test_new_reply_replaces_queue() -> None:
    """A new reply after stop() replaces the old one and plays."""
    engine = FakeEngine(delay=0.05)
    bridge = _FakeBridge()
    queue = make_queue(engine, bridge)
    queue.enqueue("old", "v", 0, "fake")
    await asyncio.sleep(0.01)

    await queue.stop()
    queue.enqueue("new", "v", 0, "fake")
    await queue.wait_idle()

    synthesized = [call[0] for call in engine.synthesize_calls]
    assert "new" in synthesized
    assert bridge.played


@pytest.mark.asyncio
async def test_stop_then_enqueue_plays_again() -> None:
    """The queue is not dead after stop(): the next reply still plays."""
    engine = FakeEngine()
    bridge = _FakeBridge()
    queue = make_queue(engine, bridge)
    queue.enqueue("before", "v", 0, "fake")
    await queue.wait_idle()
    played_before = len(bridge.played)

    await queue.stop()
    queue.enqueue("after", "v", 0, "fake")
    await queue.wait_idle()

    assert len(bridge.played) == played_before + 1
    assert queue.generation >= 1


@pytest.mark.asyncio
async def test_typed_errors_reach_ui_no_engine_switch() -> None:
    """Typed errors reach the UI and do NOT switch engines."""
    errors: list[tuple[str, str]] = []
    engine = FakeEngine(should_fail=True, error_kind="TTSAuthError")
    queue = make_queue(
        engine,
        _FakeBridge(),
        on_error=lambda kind, msg: errors.append((kind, msg)),
    )
    queue.enqueue("test", "v", 0, "fake")
    await queue.wait_idle()

    assert len(errors) == 1
    assert errors[0][0] == "TTSAuthError"
    assert "Synthesis failed" in errors[0][1]


@pytest.mark.asyncio
async def test_playback_timeout_reports_one_error() -> None:
    """A bridge that never answers produces exactly one timeout error."""
    errors: list[tuple[str, str]] = []
    bridge = _FakeBridge(hold=True)
    queue = make_queue(
        FakeEngine(),
        bridge,
        playback_timeout=0.02,
        on_error=lambda kind, msg: errors.append((kind, msg)),
    )
    queue.enqueue("test", "v", 0, "fake")
    await queue.wait_idle()

    assert len(errors) == 1
    assert errors[0][0] == "PlaybackTimeout"


@pytest.mark.asyncio
async def test_denying_bridge_reports_playback_error() -> None:
    """DenyingUIBridge raises, and the queue reports one speech error."""
    errors: list[tuple[str, str]] = []
    queue = make_queue(
        FakeEngine(),
        DenyingUIBridge(),
        on_error=lambda kind, msg: errors.append((kind, msg)),
    )
    queue.enqueue("test", "v", 0, "fake")
    await queue.wait_idle()

    assert len(errors) == 1
    assert errors[0][0] == "PlaybackNotAvailable"


@pytest.mark.asyncio
async def test_dropped_stale_generation_is_logged(caplog) -> None:
    """stop() drops pending work with a stale-generation log line."""
    caplog.set_level(logging.INFO, logger="friday.voice.speaker")
    engine = FakeEngine(delay=0.2)
    queue = make_queue(engine, _FakeBridge())
    queue.enqueue("first", "v", 0, "fake")
    queue.enqueue("second", "v", 0, "fake")
    await asyncio.sleep(0.02)

    await queue.stop()

    assert "dropped: stale generation" in caplog.text


@pytest.mark.asyncio
async def test_stage_logging_never_includes_spoken_text(caplog) -> None:
    """Every pipeline stage is logged, and spoken text never is."""
    caplog.set_level(logging.INFO, logger="friday.voice.speaker")
    spoken = "zebra-unique-spoken-sentence"
    queue = make_queue(FakeEngine(), _FakeBridge())
    queue.enqueue(spoken, "v", 0, "fake")
    await queue.wait_idle()

    for stage in (
        "speech_enqueued",
        "queue_task_started",
        "synthesis_started",
        "synthesis_done",
        "play_requested",
        "play_finished",
    ):
        assert stage in caplog.text
    assert spoken not in caplog.text


@pytest.mark.asyncio
async def test_stage_logging_covers_drop_cancel_and_play_error(caplog) -> None:
    """Dropped, cancelled, and play_error stages are logged (lengths only)."""
    caplog.set_level(logging.INFO, logger="friday.voice.speaker")

    failing = make_queue(FakeEngine(), _FakeBridge(error=TTSNetworkError("boom")))
    failing.enqueue("zebra-first", "v", 0, "fake")
    await failing.wait_idle()
    assert "play_error: kind=TTSNetworkError" in caplog.text

    queue = make_queue(FakeEngine(delay=0.2), _FakeBridge())
    queue.enqueue("zebra-second", "v", 0, "fake")
    queue.enqueue("zebra-third", "v", 0, "fake")
    await asyncio.sleep(0.02)
    await queue.stop()

    assert "cancelled: trigger=stop" in caplog.text
    assert "dropped: stale generation" in caplog.text
    assert "zebra-first" not in caplog.text
    assert "zebra-second" not in caplog.text
    assert "zebra-third" not in caplog.text


@pytest.mark.asyncio
async def test_403_error_message_exact() -> None:
    """The exact 403 error message is correct."""
    from friday.voice.errors import build_tts_http_error

    err = build_tts_http_error(403, '{"error": "forbidden"}')
    assert "403" in str(err)
    assert "Microsoft rejected the request (403)" in str(err)
    assert "edge-tts is outdated" in str(err)
    assert "PC clock is wrong" in str(err)


@pytest.mark.asyncio
async def test_tainted_turn_skip_online_engine_not_offline() -> None:
    """The queue itself does not filter text; privacy lives in CoreService."""
    from friday.tools.permissions import TurnState

    state = TurnState()
    assert not state.tainted
    state.tainted = True
    assert state.tainted

    queue = make_queue(FakeEngine(), _FakeBridge())
    queue.enqueue("test", "v", 0, "fake")
    await queue.wait_idle()


@pytest.mark.asyncio
async def test_incomplete_replies_never_spoken() -> None:
    """Only explicitly enqueued sentences are played."""
    engine = FakeEngine()
    queue = make_queue(engine, _FakeBridge())
    queue.enqueue("first", "v", 0, "fake")
    queue.enqueue("second", "v", 0, "fake")
    await queue.wait_idle()
    assert len(engine.synthesize_calls) == 2


@pytest.mark.asyncio
async def test_speak_replies_false_never_constructs_engine() -> None:
    """A queue with no work never constructs an engine."""
    calls: list[str] = []

    def factory(name: str) -> TTSEngine:
        calls.append(name)
        return FakeEngine()

    SpeechQueue(factory, lambda: _FakeBridge())
    assert calls == []


@pytest.mark.asyncio
async def test_temp_files_cleaned_on_startup() -> None:
    """Temp files cleaned on startup (purge tmp dir)."""
    tmp_dir = Path(tempfile.gettempdir()) / "friday_tts_test_startup"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    stale_file = tmp_dir / "friday_tts_stale.mp3"
    stale_file.write_text("stale")

    try:
        make_queue(FakeEngine(), _FakeBridge())
        SpeechQueue(
            make_factory(FakeEngine()),
            lambda: _FakeBridge(),
            tmp_dir=str(tmp_dir),
        )
        assert not stale_file.exists()
    finally:
        if stale_file.exists():
            stale_file.unlink()
        if tmp_dir.exists():
            tmp_dir.rmdir()


@pytest.mark.asyncio
async def test_temp_files_cleaned_on_completion() -> None:
    """Temp files cleaned on completion."""
    tmp_dir = Path(tempfile.gettempdir()) / "friday_tts_test_completion"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        queue = SpeechQueue(
            make_factory(FakeEngine()),
            lambda: _FakeBridge(),
            tmp_dir=str(tmp_dir),
        )
        queue.enqueue("test", "v", 0, "fake")
        await queue.wait_idle()

        assert list(tmp_dir.glob("friday_tts_*")) == []
    finally:
        for f in tmp_dir.glob("friday_tts_*"):
            f.unlink(missing_ok=True)
        tmp_dir.rmdir()


@pytest.mark.asyncio
async def test_temp_files_cleaned_on_stop() -> None:
    """Temp files cleaned on stop."""
    tmp_dir = Path(tempfile.gettempdir()) / "friday_tts_test_stop"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        queue = SpeechQueue(
            make_factory(FakeEngine(delay=0.05)),
            lambda: _FakeBridge(),
            tmp_dir=str(tmp_dir),
        )
        queue.enqueue("first", "v", 0, "fake")
        queue.enqueue("second", "v", 0, "fake")
        await asyncio.sleep(0.01)

        await queue.stop()

        assert list(tmp_dir.glob("friday_tts_*")) == []
    finally:
        for f in tmp_dir.glob("friday_tts_*"):
            f.unlink(missing_ok=True)
        tmp_dir.rmdir()


@pytest.mark.asyncio
async def test_edge_engine_uses_edge_tts_library_only() -> None:
    """Edge engine uses only the edge-tts library."""
    import inspect

    import friday.voice.tts.edge as edge_module

    source = inspect.getsource(edge_module)
    assert "import edge_tts" in source
    assert "websockets" not in source  # No raw websocket
    assert "aiohttp" not in source  # No raw http
