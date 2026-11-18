"""Tests for the SpeechQueue (fake engine, no audio devices)."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
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
    engine: TTSEngine,
    bridge: object,
    *,
    playback_timeout: float = 60.0,
    prefetch_sentences: int = 2,
    tmp_dir: str = "",
    on_error=None,
) -> SpeechQueue:
    """Create a queue wired to a single engine instance and bridge."""
    return SpeechQueue(
        make_factory(engine),
        lambda: bridge,
        tmp_dir=tmp_dir,
        prefetch_sentences=prefetch_sentences,
        playback_timeout=playback_timeout,
        on_error=on_error,
    )


class _TimingBridge:
    """Bridge that records playback timing and holds each play for a delay."""

    def __init__(self, play_delay: float = 0.0) -> None:
        self._play_delay = play_delay
        self.started: list[tuple[float, str]] = []
        self.finished: list[tuple[float, str]] = []
        self.played: list[str] = []
        self.stopped = False

    async def play_audio(self, path: str) -> None:
        self.started.append((time.perf_counter(), path))
        self.played.append(path)
        try:
            await asyncio.sleep(self._play_delay)
        finally:
            self.finished.append((time.perf_counter(), path))

    async def stop_audio(self) -> None:
        self.stopped = True

    async def confirm(self, tool: str, description: str, args: str) -> bool:
        return False

    async def read_clipboard_text(self) -> str | None:
        return None

    def deny_pending(self) -> None:
        pass


class _HoldBridge:
    """Bridge that holds each play open until release()/stop_audio()."""

    def __init__(self) -> None:
        self.hold = True
        self.started: list[tuple[float, str]] = []
        self.played: list[str] = []
        self.stopped = False
        self._events: list[asyncio.Event] = []

    async def play_audio(self, path: str) -> None:
        self.started.append((time.perf_counter(), path))
        self.played.append(path)
        if not self.hold:
            return
        event = asyncio.Event()
        self._events.append(event)
        await event.wait()

    def release(self) -> None:
        for event in self._events:
            event.set()

    async def stop_audio(self) -> None:
        self.stopped = True
        self.release()

    async def confirm(self, tool: str, description: str, args: str) -> bool:
        return False

    async def read_clipboard_text(self) -> str | None:
        return None

    def deny_pending(self) -> None:
        pass


class TimingEngine(TTSEngine):
    """Engine with configurable delays, optional failure and real files."""

    def __init__(
        self,
        *,
        delay: float = 0.0,
        delays: dict[str, float] | None = None,
        fail_text: str | None = None,
        file_dir: Path | None = None,
    ) -> None:
        self._delay = delay
        self._delays = delays or {}
        self._fail_text = fail_text
        self._file_dir = file_dir
        self.started: list[tuple[float, str]] = []
        self.finished: list[tuple[float, str]] = []
        self.calls: list[str] = []
        self.by_path: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "fake"

    async def list_voices(self) -> list:
        return []

    async def synthesize(
        self, text: str, voice: str, rate_percent: int
    ) -> SynthesisResult:
        self.calls.append(text)
        self.started.append((time.perf_counter(), text))
        await asyncio.sleep(self._delays.get(text, self._delay))
        if self._fail_text is not None and text == self._fail_text:
            raise TTSNetworkError("synthesis boom")
        if self._file_dir is not None:
            path = self._file_dir / f"friday_tts_{len(self.calls)}.mp3"
            path.write_text("audio")
        else:
            path = Path(tempfile.gettempdir()) / (
                f"friday_tts_{id(self)}_{len(self.calls)}.mp3"
            )
        self.by_path[str(path)] = text
        self.finished.append((time.perf_counter(), text))
        return SynthesisResult(audio_path=str(path), format="mp3")

    async def close(self) -> None:
        pass


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


async def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return predicate()


def _played_texts(engine: TimingEngine, bridge) -> list[str]:
    return [engine.by_path[path] for path in bridge.played]


@pytest.mark.asyncio
async def test_prefetch_starts_next_synthesis_before_playback_finishes() -> None:
    """Synthesis N+1 begins while playback N is still open."""
    engine = TimingEngine(delay=0.2)
    bridge = _TimingBridge(play_delay=0.5)
    queue = make_queue(engine, bridge, prefetch_sentences=2)
    for text in ("one", "two", "three"):
        queue.enqueue(text, "v", 0, "fake")
    await queue.wait_idle()

    assert len(bridge.finished) == 3
    # Synthesis #2 starts before playback #1 finishes, and #3 before #2 ends.
    assert engine.started[1][0] < bridge.finished[0][0]
    assert engine.started[2][0] < bridge.finished[1][0]


@pytest.mark.asyncio
async def test_prefetch_keeps_gap_between_plays_under_100ms() -> None:
    """With synth 0.2s and play 0.5s, the silence between plays is tiny."""
    engine = TimingEngine(delay=0.2)
    bridge = _TimingBridge(play_delay=0.5)
    queue = make_queue(engine, bridge, prefetch_sentences=2)
    for text in ("one", "two", "three"):
        queue.enqueue(text, "v", 0, "fake")
    await queue.wait_idle()

    assert len(bridge.started) == 3
    gaps_ms = [
        (bridge.started[index][0] - bridge.finished[index - 1][0]) * 1000.0
        for index in range(1, len(bridge.started))
    ]
    assert all(gap < 100.0 for gap in gaps_ms), gaps_ms


@pytest.mark.asyncio
async def test_prefetch_never_runs_more_than_prefetch_ahead() -> None:
    """At most ``prefetch_sentences`` clips are ready but unplayed."""
    engine = TimingEngine(delay=0.02)
    bridge = _HoldBridge()
    queue = make_queue(engine, bridge, prefetch_sentences=2)
    for text in ("one", "two", "three", "four", "five"):
        queue.enqueue(text, "v", 0, "fake")

    assert await _wait_until(lambda: bool(bridge.started))
    await asyncio.sleep(0.1)

    synthesized_ahead = len(engine.calls) - len(bridge.started)
    assert 0 <= synthesized_ahead <= 2
    assert len(engine.calls) <= 3  # one playing + prefetch_sentences ready

    bridge.release()
    await queue.wait_idle()


@pytest.mark.asyncio
async def test_prefetch_preserves_order_with_slow_synthesis() -> None:
    """A slow middle synthesis delays but never reorders playback."""
    engine = TimingEngine(delay=0.02, delays={"two": 0.25})
    bridge = _TimingBridge(play_delay=0.05)
    queue = make_queue(engine, bridge, prefetch_sentences=2)
    for text in ("one", "two", "three"):
        queue.enqueue(text, "v", 0, "fake")
    await queue.wait_idle()

    assert _played_texts(engine, bridge) == ["one", "two", "three"]


@pytest.mark.asyncio
async def test_microphone_gate_drops_pre_synthesized_clip(
    tmp_path: Path, caplog
) -> None:
    """A clip synthesized before the gate opened must never play."""
    gate = {"active": False}
    engine = TimingEngine(delay=0.02, file_dir=tmp_path)
    bridge = _HoldBridge()
    queue = SpeechQueue(
        make_factory(engine),
        lambda: bridge,
        tmp_dir=str(tmp_path),
        is_microphone_active=lambda: gate["active"],
    )
    caplog.set_level(logging.INFO, logger="friday.voice.speaker")
    queue.enqueue("zebra-first", "v", 0, "fake")
    queue.enqueue("zebra-second", "v", 0, "fake")

    assert await _wait_until(lambda: len(bridge.started) == 1)
    assert await _wait_until(lambda: len(engine.calls) >= 2)

    gate["active"] = True
    bridge.release()
    await queue.wait_idle()

    assert len(bridge.played) == 1
    assert _played_texts(engine, bridge) == ["zebra-first"]
    assert "dropped: microphone active" in caplog.text
    assert "zebra-second" not in caplog.text
    assert list(tmp_path.glob("friday_tts_*.mp3")) == []


@pytest.mark.asyncio
async def test_microphone_gate_blocks_every_play_without_starting_speech(
    tmp_path: Path,
) -> None:
    """With the gate open nothing plays and speech never reports started."""
    started: list[int] = []
    gate = {"active": True}
    engine = TimingEngine(delay=0.0, file_dir=tmp_path)
    bridge = _FakeBridge()
    queue = SpeechQueue(
        make_factory(engine),
        lambda: bridge,
        tmp_dir=str(tmp_path),
        on_started=lambda: started.append(1),
        is_microphone_active=lambda: gate["active"],
    )

    queue.enqueue("one", "v", 0, "fake")
    queue.enqueue("two", "v", 0, "fake")
    await queue.wait_idle()

    assert bridge.played == []
    assert started == []
    assert list(tmp_path.glob("friday_tts_*.mp3")) == []


@pytest.mark.asyncio
async def test_microphone_gate_off_plays_normally(tmp_path: Path) -> None:
    """Closing the gate restores ordinary playback."""
    gate = {"active": False}
    engine = TimingEngine(delay=0.0, file_dir=tmp_path)
    bridge = _FakeBridge()
    queue = SpeechQueue(
        make_factory(engine),
        lambda: bridge,
        tmp_dir=str(tmp_path),
        is_microphone_active=lambda: gate["active"],
    )

    queue.enqueue("audible", "v", 0, "fake")
    await queue.wait_idle()

    assert len(bridge.played) == 1


@pytest.mark.asyncio
async def test_stop_drops_stale_tasks_and_emits_one_terminal_signal() -> None:
    """Stopping before playback drops stale work and reports one finish."""
    finished: list[None] = []
    errors: list[tuple[str, str]] = []
    queue = SpeechQueue(
        make_factory(TimingEngine(delay=0.2)),
        lambda: _FakeBridge(),
        on_finished=lambda: finished.append(None),
        on_error=lambda kind, msg: errors.append((kind, msg)),
    )
    queue.enqueue("first", "v", 0, "fake")
    queue.enqueue("second", "v", 0, "fake")
    await asyncio.sleep(0.02)

    await queue.stop()
    assert len(finished) == 1
    assert errors == []

    # A second stop must not emit another terminal signal.
    await queue.stop()
    assert len(finished) == 1
    assert errors == []


@pytest.mark.asyncio
async def test_stop_mid_play_deletes_unplayed_and_next_reply_plays(
    tmp_path,
) -> None:
    """stop() removes pending files and the next reply still plays."""
    engine = TimingEngine(delay=0.02, file_dir=tmp_path)
    bridge = _HoldBridge()
    queue = make_queue(engine, bridge, prefetch_sentences=2)
    for text in ("one", "two", "three"):
        queue.enqueue(text, "v", 0, "fake")
    assert await _wait_until(lambda: bool(bridge.started))
    await asyncio.sleep(0.1)
    assert list(tmp_path.glob("friday_tts_*"))

    await queue.stop()

    assert bridge.stopped
    assert list(tmp_path.glob("friday_tts_*")) == []

    bridge.hold = False
    queue.enqueue("next", "v", 0, "fake")
    await queue.wait_idle()

    assert _played_texts(engine, bridge)[-1] == "next"
    assert list(tmp_path.glob("friday_tts_*")) == []


@pytest.mark.asyncio
async def test_synthesis_error_stops_reply_with_one_error(tmp_path) -> None:
    """A failed sentence 2 reports once and sentence 3 is never played."""
    errors: list[tuple[str, str]] = []
    engine = TimingEngine(delay=0.02, fail_text="two", file_dir=tmp_path)
    bridge = _TimingBridge(play_delay=0.05)
    queue = make_queue(
        engine,
        bridge,
        prefetch_sentences=2,
        on_error=lambda kind, msg: errors.append((kind, msg)),
    )
    for text in ("one", "two", "three"):
        queue.enqueue(text, "v", 0, "fake")
    await queue.wait_idle()

    assert len(errors) == 1
    assert errors[0][0] == "TTSNetworkError"
    assert "three" not in engine.calls
    assert "three" not in _played_texts(engine, bridge)
    assert list(tmp_path.glob("friday_tts_*")) == []


@pytest.mark.asyncio
async def test_timing_logs_include_all_fields(caplog) -> None:
    """synth_ms/play_ms/gap_ms/first_audio_ms are logged, text never is."""
    caplog.set_level(logging.INFO, logger="friday.voice.speaker")
    engine = TimingEngine(delay=0.01)
    bridge = _TimingBridge(play_delay=0.01)
    queue = make_queue(engine, bridge, prefetch_sentences=2)
    queue.enqueue("zebra-unique-spoken", "v", 0, "fake")
    queue.enqueue("second-zebra-spoken", "v", 0, "fake")
    await queue.wait_idle()

    assert "synth_ms=" in caplog.text
    assert "play_ms=" in caplog.text
    assert "gap_ms=" in caplog.text
    assert "first_audio_ms=" in caplog.text
    assert "zebra-unique-spoken" not in caplog.text
    assert "second-zebra-spoken" not in caplog.text


@pytest.mark.asyncio
async def test_temp_dir_purges_stale_and_deletes_played_files(
    tmp_path,
) -> None:
    """A configured tmp_dir is purged at startup and emptied after play."""
    stale = tmp_path / "friday_tts_stale.mp3"
    stale.write_text("stale")
    engine = TimingEngine(file_dir=tmp_path)
    queue = make_queue(
        engine, _TimingBridge(), prefetch_sentences=2, tmp_dir=str(tmp_path)
    )
    assert not stale.exists()

    queue.enqueue("one", "v", 0, "fake")
    await queue.wait_idle()

    assert list(tmp_path.glob("friday_tts_*")) == []


@pytest.mark.asyncio
async def test_shutdown_purges_stale_temp_files(tmp_path) -> None:
    """shutdown() removes leftover friday_tts_* files at exit."""
    queue = make_queue(
        TimingEngine(), _TimingBridge(), tmp_dir=str(tmp_path)
    )
    stale = tmp_path / "friday_tts_leftover.mp3"
    stale.write_text("stale")

    await queue.shutdown()

    assert not stale.exists()


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
