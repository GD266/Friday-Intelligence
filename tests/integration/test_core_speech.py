"""CoreService speech integration tests (real SpeechQueue, fake engine)."""

from __future__ import annotations

import asyncio
import tempfile
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from friday.config.settings import (
    MemorySettings,
    Settings,
    ToolsSettings,
    VoiceSettings,
)
from friday.core.service import CoreService
from friday.core.ui_bridge import DenyingUIBridge
from friday.gateway.base import Provider
from friday.gateway.types import (
    EVENT_DONE,
    EVENT_TOKEN,
    EVENT_TOOL_CALLS,
    StreamEvent,
    ToolCall,
)
from friday.voice.tts.base import SynthesisResult, TTSEngine


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


class FakeEngine(TTSEngine):
    """Fake engine that records synthesis calls and optionally fails."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[int] = []

    @property
    def name(self) -> str:
        return "fake"

    async def list_voices(self) -> list:
        return []

    async def synthesize(
        self, text: str, voice: str, rate_percent: int
    ) -> SynthesisResult:
        self.calls.append(len(text))
        if self.fail:
            from friday.voice.errors import TTSNetworkError

            raise TTSNetworkError("synthesis boom")
        return SynthesisResult(
            audio_path=str(_audio_file()), format="mp3"
        )

    async def close(self) -> None:
        pass


_AUDIO_COUNTER = 0


def _audio_file():
    global _AUDIO_COUNTER
    _AUDIO_COUNTER += 1
    return Path(tempfile.gettempdir()) / f"friday_speech_{_AUDIO_COUNTER}.mp3"


class RecordingBridge:
    """UI bridge fake that records playback and serves clipboard reads."""

    def __init__(
        self, *, clipboard: str | None = None, approve: bool = True
    ) -> None:
        self.play_requests: list[str] = []
        self.stopped = False
        self.clipboard = clipboard
        self.approve = approve

    async def play_audio(self, path: str) -> None:
        self.play_requests.append(path)

    async def stop_audio(self) -> None:
        self.stopped = True

    async def confirm(self, tool: str, description: str, args: str) -> bool:
        return self.approve

    async def read_clipboard_text(self) -> str | None:
        return self.clipboard

    def deny_pending(self) -> None:
        pass


class FakeProvider(Provider):
    """Provider that streams one reply per call from a fixed script."""

    def __init__(self, replies: list[str], *, clipboard_turn: bool = False) -> None:
        self._replies = list(replies)
        self._clipboard_turn = clipboard_turn
        self.calls = 0

    async def stream_chat(self, messages, tools=(), tool_choice=None):
        self.calls += 1
        if self._clipboard_turn and self.calls == 1:
            yield StreamEvent(
                EVENT_TOOL_CALLS,
                tool_calls=(ToolCall("call_1", "read_clipboard", "{}"),),
            )
            yield StreamEvent(EVENT_DONE)
            return
        reply = self._replies.pop(0) if self._replies else "ok"
        yield StreamEvent(EVENT_TOKEN, reply)
        yield StreamEvent(EVENT_DONE)


def wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


def settle(seconds: float = 0.1) -> None:
    """Process Qt events while the core thread catches up."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.01)
    QCoreApplication.processEvents()


def voice_settings(tmp_path, *, engine: str = "edge") -> Settings:
    return Settings(
        memory=MemorySettings(db_path=str(tmp_path / "friday.db")),
        tools=ToolsSettings(),
        voice=VoiceSettings(
            speak_replies=True,
            engine=engine,
            voice_name="en-US-Test",
            rate_percent=0,
        ),
    )


@pytest.fixture
def fake_engine(monkeypatch):
    engine = FakeEngine()
    monkeypatch.setattr("friday.voice.create_engine", lambda name: engine)
    return engine


def run_on_core(core: CoreService, coroutine, timeout: float = 5.0):
    future = asyncio.run_coroutine_threadsafe(coroutine, core._loop)
    return future.result(timeout=timeout)


def make_core(settings, provider) -> CoreService:
    return CoreService(settings=settings, provider=provider)


def test_stop_during_startup_still_plays_next_reply(
    qapp, tmp_path, fake_engine
) -> None:
    """The real startup order: DenyingUIBridge, start, bridge swap, stop, chat."""
    bridge = RecordingBridge()
    provider = FakeProvider(["Hello from Friday."])
    core = make_core(voice_settings(tmp_path), provider)
    errors = QSignalSpy(core.signals.speech_error)
    core.start()

    try:
        assert wait_until(lambda: core._speech_queue is not None)
        core.set_ui_bridge(bridge)
        run_on_core(core, core.stop_speech())

        core.chat_send("hello")

        assert wait_until(lambda: len(bridge.play_requests) > 0)
        assert errors.count() == 0
    finally:
        core.stop()

    assert fake_engine.calls


def test_set_ui_bridge_after_startup_plays_through_new_bridge(
    qapp, tmp_path, fake_engine
) -> None:
    """A bridge attached after startup is the one that receives playback."""
    first = RecordingBridge()
    second = RecordingBridge()
    core = make_core(
        voice_settings(tmp_path), FakeProvider(["Bridge swap reply."])
    )
    core.start()

    try:
        assert wait_until(lambda: core._speech_queue is not None)
        core.set_ui_bridge(first)
        core.set_ui_bridge(second)
        core.chat_send("hello")

        assert wait_until(lambda: len(second.play_requests) > 0)
        assert first.play_requests == []
    finally:
        core.stop()


@pytest.mark.parametrize(
    "trigger",
    [
        "stop",
        "new_message",
        "new_chat",
        "clear_chat",
        "open_conversation",
        "disable_enable",
        "window_close",
    ],
)
def test_every_stop_trigger_is_followed_by_playback(
    qapp, tmp_path, fake_engine, trigger
) -> None:
    """No stop path may leave the speech queue permanently dead."""
    bridge = RecordingBridge()
    core = make_core(
        voice_settings(tmp_path),
        FakeProvider(["First reply.", "Second reply."]),
    )
    errors = QSignalSpy(core.signals.speech_error)
    core.start()

    try:
        assert wait_until(lambda: core._speech_queue is not None)
        core.set_ui_bridge(bridge)
        core.chat_send("first")
        assert wait_until(lambda: len(bridge.play_requests) >= 1)
        first_count = len(bridge.play_requests)
        conversation_id = core.current_conversation_id

        if trigger == "stop":
            core.cancel_chat()
        elif trigger == "new_message":
            pass  # the second chat_send itself is the trigger
        elif trigger == "new_chat":
            core.new_conversation()
        elif trigger == "clear_chat":
            core.clear_chat()
        elif trigger == "open_conversation":
            core.open_conversation(conversation_id)
        elif trigger == "disable_enable":
            core.set_speech_enabled_sync(False)
            assert wait_until(lambda: core._speech_queue is None)
            core.set_speech_enabled_sync(True)
            assert wait_until(lambda: core._speech_queue is not None)
        elif trigger == "window_close":
            core.request_speech_stop()
        else:  # pragma: no cover - parametrization guard
            raise AssertionError(trigger)

        # Let any scheduled stop reach the core loop first.
        settle()
        core.chat_send("second")

        assert wait_until(
            lambda: len(bridge.play_requests) > first_count
        ), f"no playback after {trigger}: {bridge.play_requests}"
        assert errors.count() == 0
    finally:
        core.stop()


def test_synthesis_error_emits_exactly_one_speech_error(
    qapp, tmp_path, monkeypatch
) -> None:
    """A failing engine reports one speech_error and does not retry."""
    failing = FakeEngine(fail=True)
    monkeypatch.setattr(
        "friday.voice.create_engine", lambda name: failing
    )
    core = make_core(
        voice_settings(tmp_path), FakeProvider(["Unspeakable reply."])
    )
    errors = QSignalSpy(core.signals.speech_error)
    core.start()

    try:
        core.chat_send("hello")
        assert wait_until(lambda: errors.count() == 1)
        settle(0.2)
        assert errors.count() == 1
        assert errors.at(0)[0] == "TTSNetworkError"
    finally:
        core.stop()


def test_denying_bridge_emits_speech_error(qapp, tmp_path, fake_engine) -> None:
    """Without an attached player, playback fails visibly."""
    core = CoreService(
        settings=voice_settings(tmp_path),
        provider=FakeProvider(["No player reply."]),
        ui_bridge=DenyingUIBridge(),
    )
    errors = QSignalSpy(core.signals.speech_error)
    core.start()

    try:
        core.chat_send("hello")
        assert wait_until(lambda: errors.count() == 1)
        assert errors.at(0)[0] == "PlaybackNotAvailable"
    finally:
        core.stop()


def test_speak_replies_false_never_constructs_engine(
    qapp, tmp_path, monkeypatch
) -> None:
    """Voice disabled: no queue, no engine, no playback."""
    created: list[str] = []
    monkeypatch.setattr(
        "friday.voice.create_engine",
        lambda name: created.append(name) or FakeEngine(),
    )
    settings = Settings(
        memory=MemorySettings(db_path=str(tmp_path / "friday.db")),
        voice=VoiceSettings(speak_replies=False),
    )
    core = make_core(settings, FakeProvider(["Silent reply."]))
    done = QSignalSpy(core.signals.message_done)
    core.start()

    try:
        core.chat_send("hello")
        assert wait_until(lambda: done.count() >= 1)
        assert core._speech_queue is None
        assert created == []
    finally:
        core.stop()


def test_read_clipboard_turn_with_online_engine_is_notice_only(
    qapp, tmp_path, fake_engine
) -> None:
    """Tainted turn + online engine: a notice, never a play request."""
    bridge = RecordingBridge(clipboard="clipboard secret")
    core = make_core(
        voice_settings(tmp_path, engine="edge"),
        FakeProvider(["Clipboard reply."], clipboard_turn=True),
    )
    notices = QSignalSpy(core.signals.speech_notice)
    core.start()

    try:
        core.set_ui_bridge(bridge)
        core.chat_send("read my clipboard")
        assert wait_until(lambda: notices.count() >= 1)
        settle(0.2)
        assert bridge.play_requests == []
        assert "clipboard" in notices.at(0)[0]
    finally:
        core.stop()
