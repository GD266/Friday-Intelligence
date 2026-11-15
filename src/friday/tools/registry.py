"""Tool registry and OpenAI tool-schema generation."""

from __future__ import annotations

from dataclasses import dataclass

from friday.tools.base import Permission, Tool


@dataclass(frozen=True, slots=True)
class ToolInfo:
    """A read-only description of a registered tool for the UI."""

    name: str
    description: str
    permission: str
    requires_confirmation: bool
    returns_untrusted: bool


class ToolRegistry:
    """The only source of tools exposed to the model."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register *tool*, rejecting duplicate names."""
        if not tool.name or not tool.name.strip():
            raise ValueError("Tool name must not be empty.")
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} is already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """Return a registered tool by exact name."""
        return self._tools.get(name)

    def list(self) -> tuple[Tool, ...]:
        """Return all registered tools sorted by name."""
        return tuple(self._tools[name] for name in sorted(self._tools))

    def info(self) -> tuple[ToolInfo, ...]:
        """Return immutable descriptions for the Tools dialog."""
        return tuple(
            ToolInfo(
                name=tool.name,
                description=tool.description,
                permission=tool.permission.value,
                requires_confirmation=tool.requires_confirmation,
                returns_untrusted=tool.returns_untrusted,
            )
            for tool in self.list()
        )

    def provider_specs(self) -> tuple[dict[str, object], ...]:
        """Generate OpenAI ``tools`` entries from registered Pydantic models."""
        return tuple(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.args_model.model_json_schema(),
                },
            }
            for tool in self.list()
        )

    def __len__(self) -> int:
        return len(self._tools)


__all__ = ["Permission", "ToolInfo", "ToolRegistry"]
