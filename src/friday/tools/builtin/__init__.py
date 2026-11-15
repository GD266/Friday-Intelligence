"""Built-in tools allowed in Phase 4."""

from __future__ import annotations

from friday.config.settings import ToolsSettings
from friday.tools.builtin.get_time import GetTimeTool
from friday.tools.builtin.open_app import OpenAppTool
from friday.tools.builtin.read_clipboard import ReadClipboardTool
from friday.tools.registry import ToolRegistry


def build_builtin_registry(settings: ToolsSettings) -> ToolRegistry:
    """Create the fixed registry of exactly the three Phase 4 tools."""
    registry = ToolRegistry()
    registry.register(GetTimeTool())
    registry.register(OpenAppTool(settings.allowed_apps))
    registry.register(ReadClipboardTool())
    return registry


__all__ = [
    "GetTimeTool",
    "OpenAppTool",
    "ReadClipboardTool",
    "build_builtin_registry",
]
