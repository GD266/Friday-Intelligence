"""Built-in ``read_clipboard`` tool."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from friday.tools.base import (
    Permission,
    Tool,
    ToolContext,
    ToolResult,
)


class ReadClipboardArgs(BaseModel):
    """Arguments for ``read_clipboard`` (none)."""

    model_config = ConfigDict(extra="forbid")


class ReadClipboardTool(Tool):
    """Read clipboard text through the UI-thread bridge."""

    name = "read_clipboard"
    description = "Read the current clipboard text."
    args_model = ReadClipboardArgs
    permission = Permission.SENSITIVE
    requires_confirmation = True
    returns_untrusted = True

    async def execute(
        self, args: BaseModel, ctx: ToolContext
    ) -> ToolResult:
        bridge = ctx.ui_bridge
        if bridge is None:
            return ToolResult.failure(
                "Clipboard access is unavailable.",
                "ClipboardUnavailable",
            )
        try:
            text = await bridge.read_clipboard_text()
        except Exception as exc:  # pragma: no cover - bridge defensive path
            return ToolResult.failure(
                f"Could not read the clipboard ({exc.__class__.__name__}).",
                "ClipboardError",
            )

        if text is None:
            return ToolResult.failure(
                "The clipboard does not contain text.",
                "ClipboardNotText",
            )
        if not text.strip():
            return ToolResult.failure(
                "The clipboard is empty.",
                "ClipboardEmpty",
            )
        return ToolResult.success(text)

    def confirmation_description(self, args: BaseModel) -> str:
        return (
            "FRIDAY wants to read your clipboard. "
            "Its contents will be sent to the AI provider."
        )

    def result_summary(self, result: ToolResult) -> str:
        if result.ok:
            return f"clipboard text read ({len(result.text)} characters)"
        return super().result_summary(result)


__all__ = ["ReadClipboardArgs", "ReadClipboardTool"]
