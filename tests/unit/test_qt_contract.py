"""Contract checks against the real PySide6 classes used by the UI.

These tests exist because fake multimedia objects can silently drift from
the installed PySide6 API: the fakes previously defined ``QAudioSource.Error``
which Qt 6 does not have.
"""

# PySide6 must load after pydantic is fully initialised: shiboken's import
# hook breaks pydantic's lazy imports on this interpreter.
# ruff: noqa: I001

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest
from PySide6.QtCore import QIODevice
from PySide6.QtMultimedia import (
    QAudio,
    QAudioDevice,
    QAudioFormat,
    QAudioSource,
    QMediaDevices,
    QMediaPlayer,
)
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[2]
UI_DIR = ROOT / "src" / "friday" / "ui"
SOURCES = (UI_DIR / "audio_recorder.py", UI_DIR / "audio_player.py")


def _qt_names(tree: ast.Module) -> dict[str, object]:
    """Map each name imported from PySide6 to the real object."""
    names: dict[str, object] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if not node.module.startswith("PySide6"):
                continue
            module = importlib.import_module(node.module)
            for alias in node.names:
                names[alias.asname or alias.name] = getattr(
                    module, alias.name
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("PySide6"):
                    names[alias.asname or alias.name.rsplit(".", 1)[-1]] = (
                        importlib.import_module(alias.name)
                    )
    return names


def _attribute_chains(tree: ast.Module) -> set[tuple[str, ...]]:
    """Collect every dotted chain rooted at a plain name."""
    chains: set[tuple[str, ...]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        parts: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            continue
        parts.append(current.id)
        parts.reverse()
        chains.add(tuple(parts))
    return chains


@pytest.mark.parametrize("path", SOURCES, ids=lambda item: item.name)
def test_qt_attribute_chains_exist_on_real_classes(path: Path) -> None:
    """Every ``QtName.attr.attr`` used in the UI resolves in PySide6."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    qt_names = _qt_names(tree)
    missing: list[str] = []
    for chain in sorted(_attribute_chains(tree)):
        if chain[0] not in qt_names:
            continue
        dotted = ".".join(chain)
        target = qt_names[chain[0]]
        for attribute in chain[1:]:
            if not hasattr(target, attribute):
                missing.append(dotted)
                break
            target = getattr(target, attribute)
    assert not missing, f"missing Qt attributes: {missing}"


@pytest.mark.parametrize(
    ("qt_class", "signal_name"),
    [
        (QAudioSource, "stateChanged"),
        (QMediaPlayer, "mediaStatusChanged"),
        (QMediaPlayer, "errorOccurred"),
        (QIODevice, "readyRead"),
    ],
)
def test_qt_signals_exist(qt_class: type, signal_name: str) -> None:
    """Signals used by the player/recorder remain real Qt signals."""
    assert hasattr(qt_class, signal_name)


def test_audio_error_enum_lives_on_qaudio() -> None:
    """Qt 6 exposes the capture error enum as ``QAudio.Error``."""
    assert QAudio.Error.NoError.name == "NoError"
    assert hasattr(QAudioSource, "error")
    assert not hasattr(QAudioSource, "Error")


def test_real_qaudioformat_round_trip() -> None:
    """A 16 kHz mono Int16 format is accepted by the real QAudioFormat."""
    audio_format = QAudioFormat()
    audio_format.setSampleRate(16_000)
    audio_format.setChannelCount(1)
    audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)

    assert audio_format.sampleRate() == 16_000
    assert audio_format.channelCount() == 1
    assert audio_format.sampleFormat() == QAudioFormat.SampleFormat.Int16
    assert audio_format.bytesPerSample() == 2
    assert audio_format.isValid() is True


def test_real_media_devices_lists_audio_inputs(
    qt_app: QApplication,
) -> None:
    """The real QMediaDevices instance API returns a device list."""
    devices = QMediaDevices().audioInputs()
    assert isinstance(devices, list)
    assert all(isinstance(item, QAudioDevice) for item in devices)


def test_real_qaudio_source_constructs_with_default_device(
    qt_app: QApplication,
) -> None:
    """A real QAudioSource accepts the real default input device."""
    device = QMediaDevices().defaultAudioInput()
    if device.isNull():
        pytest.skip("Qt reports no default audio input device")

    audio_format = QAudioFormat()
    audio_format.setSampleRate(16_000)
    audio_format.setChannelCount(1)
    audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)

    source = QAudioSource(device, audio_format)
    try:
        assert source.error().value == QAudio.Error.NoError.value
        assert source.state().value == QAudio.State.StoppedState.value
        assert source.format().sampleRate() > 0
    finally:
        source.deleteLater()
