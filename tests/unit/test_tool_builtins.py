"""Tests for the three built-in tools (no real subprocess/clipboard)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from friday.config.settings import ToolsSettings
from friday.tools.base import Permission, ToolContext, ToolResult
from friday.tools.builtin import build_builtin_registry
from friday.tools.builtin.get_time import GetTimeTool
from friday.tools.builtin.open_app import OpenAppTool
from friday.tools.builtin.read_clipboard import ReadClipboardTool


def make_context(bridge=None, settings: ToolsSettings | None = None):
    return ToolContext(
        settings=settings or ToolsSettings(),
        ui_bridge=bridge,
        conversation_id=1,
    )


async def test_get_time_valid_zone() -> None:
    tool = GetTimeTool()
    args = tool.args_model.model_validate({"timezone": "Asia/Tokyo"})

    result = await tool.execute(args, make_context())

    assert result.ok is True
    assert "Asia/Tokyo" in result.text
    assert "+09:00" in result.text
    assert tool.pure is True
    assert tool.permission is Permission.SAFE


async def test_get_time_invalid_zone_is_helpful_error() -> None:
    tool = GetTimeTool()
    args = tool.args_model.model_validate(
        {"timezone": "Mars/Olympus_Mons"}
    )

    result = await tool.execute(args, make_context())

    assert result.ok is False
    assert result.error_kind == "InvalidTimezone"
    assert "IANA" in result.text
    assert "Asia/Tokyo" in result.text


async def test_get_time_defaults_to_local_timezone() -> None:
    tool = GetTimeTool()
    args = tool.args_model.model_validate({})

    result = await tool.execute(args, make_context())

    assert result.ok is True
    assert "(" in result.text
    assert ")" in result.text


async def test_get_time_missing_key_uses_local() -> None:
    """Missing timezone key entirely should use local timezone."""
    tool = GetTimeTool()
    args = tool.args_model.model_validate({})

    result = await tool.execute(args, make_context())

    assert result.ok is True
    assert "(" in result.text
    assert ")" in result.text


async def test_open_app_launches_only_allowlisted_executable(
    monkeypatch,
) -> None:
    calls: list[tuple[tuple, dict]] = []

    def fake_popen(*args, **kwargs):
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(
        "friday.tools.builtin.open_app.subprocess.Popen", fake_popen
    )
    settings = ToolsSettings(
        allowed_apps={"notepad": "notepad.exe", "paint": "mspaint.exe"}
    )
    tool = OpenAppTool(settings.allowed_apps)
    args = tool.args_model.model_validate({"name": "notepad"})

    result = await tool.execute(args, make_context(settings=settings))

    assert result.ok is True
    assert "notepad" in result.text
    assert len(calls) == 1
    positional, keyword = calls[0]
    assert positional == (["notepad.exe"],)
    assert keyword == {"shell": False}


async def test_open_app_unknown_name_lists_allowed_names() -> None:
    tool = OpenAppTool(
        {"notepad": "notepad.exe", "calculator": "calc.exe"}
    )

    @dataclass
    class FakeArgs:
        name: str

    result = await tool.execute(
        FakeArgs(name="cmd"), make_context()  # type: ignore[arg-type]
    )

    assert result.ok is False
    assert result.error_kind == "UnknownApp"
    assert "notepad" in result.text
    assert "calculator" in result.text


async def test_open_app_launch_failure_is_error(monkeypatch) -> None:
    def failing_popen(*args, **kwargs):
        raise OSError("not found")

    monkeypatch.setattr(
        "friday.tools.builtin.open_app.subprocess.Popen", failing_popen
    )
    tool = OpenAppTool({"notepad": "notepad.exe"})
    args = tool.args_model.model_validate({"name": "notepad"})

    result = await tool.execute(args, make_context())

    assert result.ok is False
    assert result.error_kind == "LaunchFailed"


class FakeClipboardBridge:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.reads = 0

    async def confirm(self, tool: str, description: str, args: str) -> bool:
        return True

    async def read_clipboard_text(self) -> str | None:
        self.reads += 1
        return self.text


async def test_read_clipboard_returns_text() -> None:
    bridge = FakeClipboardBridge("hello clipboard")
    tool = ReadClipboardTool()
    args = tool.args_model.model_validate({})

    result = await tool.execute(args, make_context(bridge=bridge))

    assert result.ok is True
    assert result.text == "hello clipboard"
    assert bridge.reads == 1
    assert tool.requires_confirmation is True
    assert tool.returns_untrusted is True


@pytest.mark.parametrize(
    ("text", "kind"),
    [(None, "ClipboardNotText"), ("   ", "ClipboardEmpty")],
)
async def test_read_clipboard_empty_or_non_text_is_error(
    text: str | None, kind: str
) -> None:
    tool = ReadClipboardTool()
    args = tool.args_model.model_validate({})

    result = await tool.execute(
        args, make_context(bridge=FakeClipboardBridge(text))
    )

    assert result.ok is False
    assert result.error_kind == kind


async def test_read_clipboard_without_bridge_is_error() -> None:
    tool = ReadClipboardTool()
    args = tool.args_model.model_validate({})

    result = await tool.execute(args, make_context())

    assert result.ok is False
    assert result.error_kind == "ClipboardUnavailable"


def test_builtin_registry_uses_configured_allowed_apps() -> None:
    settings = ToolsSettings(
        allowed_apps={"myeditor": r"C:\Tools\editor.exe"}
    )
    registry = build_builtin_registry(settings)
    open_app = registry.get("open_app")
    assert isinstance(open_app, OpenAppTool)

    schema = open_app.args_model.model_json_schema()
    assert schema["properties"]["name"]["enum"] == ["myeditor"]


def test_confirmation_description_for_clipboard() -> None:
    tool = ReadClipboardTool()
    args = tool.args_model.model_validate({})

    description = tool.confirmation_description(args)

    assert "read your clipboard" in description
    assert "sent to the AI provider" in description


def test_result_success_and_failure_helpers() -> None:
    assert ToolResult.success("ok").status == "ok"
    assert ToolResult.failure("bad").status == "error"
