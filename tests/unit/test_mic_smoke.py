"""Tests for the manual microphone smoke script's stop timing."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "mic_smoke.py"


@pytest.fixture(scope="module")
def smoke():
    spec = importlib.util.spec_from_file_location(
        "friday_mic_smoke", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeScheduler:
    """Records single-shot timers against a simulated clock."""

    def __init__(self) -> None:
        self.now = 0.0
        self.pending: list[tuple[float, object]] = []

    def single_shot(self, delay_ms: int, callback) -> None:
        self.pending.append((self.now + delay_ms / 1000, callback))

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def fire_due(self) -> None:
        due = [
            item for item in self.pending if item[0] <= self.now
        ]
        for item in due:
            self.pending.remove(item)
            item[1]()


def test_stop_timer_starts_after_delayed_recording_start(smoke) -> None:
    """A slow start does not consume the requested recording duration."""
    scheduler = _FakeScheduler()
    stops: list[bool] = []
    stop_after = smoke._StopAfterStart(
        seconds=3.0,
        stop=lambda: stops.append(True),
        schedule=scheduler.single_shot,
    )

    scheduler.advance(1.2)  # simulated blocking QAudioSource.start()
    assert scheduler.pending == []

    stop_after.on_recording_started()
    assert len(scheduler.pending) == 1
    assert scheduler.pending[0][0] == pytest.approx(4.2)

    scheduler.advance(2.99)
    scheduler.fire_due()
    assert stops == []

    scheduler.advance(0.01)
    scheduler.fire_due()
    assert stops == [True]


def test_stop_timer_is_armed_and_stops_once(smoke) -> None:
    """Repeated start signals or timer callbacks stop the recorder once."""
    scheduler = _FakeScheduler()
    stops: list[bool] = []
    stop_after = smoke._StopAfterStart(
        seconds=2.0,
        stop=lambda: stops.append(True),
        schedule=scheduler.single_shot,
    )

    stop_after.on_recording_started()
    stop_after.on_recording_started()
    assert len(scheduler.pending) == 1

    _, callback = scheduler.pending[0]
    callback()
    callback()
    assert stops == [True]
