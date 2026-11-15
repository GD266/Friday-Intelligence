"""Permission and taint-rule tests."""

from __future__ import annotations

from pydantic import BaseModel

from friday.config.settings import ToolsSettings
from friday.tools.base import Permission, Tool, ToolContext, ToolResult
from friday.tools.builtin import build_builtin_registry
from friday.tools.permissions import Decision, TurnState, decide


class EmptyArgs(BaseModel):
    pass


class DestructiveTool(Tool):
    name = "destructive"
    description = "test only"
    args_model = EmptyArgs
    permission = Permission.DESTRUCTIVE

    async def execute(
        self, args: BaseModel, ctx: ToolContext
    ) -> ToolResult:
        return ToolResult.success("done")


class ConfirmingSafeTool(Tool):
    name = "confirming"
    description = "test only"
    args_model = EmptyArgs
    permission = Permission.SAFE
    requires_confirmation = True

    async def execute(
        self, args: BaseModel, ctx: ToolContext
    ) -> ToolResult:
        return ToolResult.success("done")


def test_get_time_is_pure_and_never_needs_confirmation() -> None:
    registry = build_builtin_registry(ToolsSettings())
    get_time = registry.get("get_time")
    assert get_time is not None

    assert decide(get_time, TurnState(tainted=True)) is Decision.ALLOW


def test_taint_forces_confirmation_for_non_pure_tools() -> None:
    registry = build_builtin_registry(ToolsSettings())
    open_app = registry.get("open_app")
    clipboard = registry.get("read_clipboard")
    assert open_app is not None and clipboard is not None

    assert decide(open_app, TurnState()) is Decision.ALLOW
    assert decide(open_app, TurnState(tainted=True)) is Decision.CONFIRM
    assert (
        decide(clipboard, TurnState(tainted=True)) is Decision.CONFIRM
    )


def test_destructive_and_explicit_confirmation_always_confirm() -> None:
    assert decide(DestructiveTool(), TurnState()) is Decision.CONFIRM
    assert decide(ConfirmingSafeTool(), TurnState()) is Decision.CONFIRM
