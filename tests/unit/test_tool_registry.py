"""Tool registry and Pydantic argument validation tests."""

import pytest
from pydantic import ValidationError

from friday.config.settings import ToolsSettings
from friday.tools.base import Permission
from friday.tools.builtin import build_builtin_registry
from friday.tools.builtin.get_time import GetTimeArgs
from friday.tools.builtin.open_app import build_open_app_args_model
from friday.tools.registry import ToolRegistry


def test_registry_contains_exactly_three_tools() -> None:
    registry = build_builtin_registry(ToolsSettings())

    assert [tool.name for tool in registry.list()] == [
        "get_time",
        "open_app",
        "read_clipboard",
    ]
    assert len(registry) == 3


def test_registry_generates_openai_function_specs() -> None:
    registry = build_builtin_registry(ToolsSettings())

    specs = registry.provider_specs()

    assert [spec["type"] for spec in specs] == ["function"] * 3
    functions = {
        spec["function"]["name"]: spec["function"]  # type: ignore[index]
        for spec in specs
    }
    # timezone is now optional string (nullable) with default null
    tz_prop = functions["get_time"]["parameters"]["properties"]["timezone"]
    # Check that it accepts string (via anyOf)
    has_string = False
    if tz_prop.get("type") == "string":
        has_string = True
    elif "anyOf" in tz_prop:
        for opt in tz_prop["anyOf"]:
            if opt.get("type") == "string":
                has_string = True
                break
    assert has_string, f"timezone property should accept string, got: {tz_prop}"
    assert "required" not in functions["get_time"]["parameters"]
    assert functions["open_app"]["parameters"]["properties"]["name"][
        "enum"
    ] == ["calculator", "notepad", "paint"]
    assert (
        functions["open_app"]["parameters"]["additionalProperties"] is False
    )


def test_tool_info_reports_permissions_and_confirmation() -> None:
    registry = build_builtin_registry(ToolsSettings())

    info = {item.name: item for item in registry.info()}

    assert info["get_time"].permission == Permission.SAFE.value
    assert info["get_time"].requires_confirmation is False
    assert info["open_app"].permission == Permission.SENSITIVE.value
    assert info["open_app"].requires_confirmation is False
    assert info["read_clipboard"].permission == Permission.SENSITIVE.value
    assert info["read_clipboard"].requires_confirmation is True
    assert info["read_clipboard"].returns_untrusted is True


def test_registry_rejects_duplicate_and_empty_names() -> None:
    registry = ToolRegistry()
    tool = build_builtin_registry(ToolsSettings()).get("get_time")
    assert tool is not None
    registry.register(tool)

    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)


def test_pydantic_models_reject_bad_missing_and_extra_arguments() -> None:
    get_time = GetTimeArgs
    assert get_time.model_validate({}).timezone is None
    assert get_time.model_validate(
        {"timezone": "Asia/Tokyo"}
    ).timezone == "Asia/Tokyo"

    for bad in (
        {"timezone": 5},
        {"timezone": "x" * 101},
        {"timezone": "UTC", "extra": True},
    ):
        with pytest.raises(ValidationError):
            get_time.model_validate(bad)

    open_app = build_open_app_args_model(("notepad", "paint"))
    assert open_app.model_validate({"name": "paint"}).name == "paint"
    for bad in (
        {},
        {"name": "cmd"},
        {"name": "notepad", "path": r"C:\Windows\System32\cmd.exe"},
    ):
        with pytest.raises(ValidationError):
            open_app.model_validate(bad)


def test_registry_get_unknown_returns_none() -> None:
    registry = build_builtin_registry(ToolsSettings())
    assert registry.get("nope") is None
