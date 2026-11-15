"""Built-in ``open_app`` tool."""

from __future__ import annotations

import subprocess

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    create_model,
    field_validator,
)

from friday.tools.base import (
    Permission,
    Tool,
    ToolContext,
    ToolResult,
)


def build_open_app_args_model(names: tuple[str, ...]) -> type[BaseModel]:
    """Build a Pydantic model whose ``name`` field is a config enum."""
    allowed = tuple(sorted(names))

    def validate_name(value: str) -> str:
        if value not in allowed:
            raise ValueError(
                "app must be one of: " + ", ".join(allowed)
            )
        return value

    return create_model(
        "OpenAppArgs",
        __config__=ConfigDict(extra="forbid"),
        name=(
            str,
            Field(
                ...,
                description="Friendly app name from the configured allowlist.",
                json_schema_extra={"enum": list(allowed)},
            ),
        ),
        __validators__={
            "validate_name": field_validator("name")(validate_name)
        },
    )


class OpenAppTool(Tool):
    """Launch only an executable from the configured allowlist."""

    name = "open_app"
    description = (
        "Open an allowlisted desktop app by friendly name. "
        "The model cannot supply executable paths or arguments."
    )
    permission = Permission.SENSITIVE
    requires_confirmation = False
    returns_untrusted = False

    def __init__(self, allowed_apps: dict[str, str]) -> None:
        self._allowed_apps = dict(allowed_apps)
        self.args_model = build_open_app_args_model(
            tuple(sorted(self._allowed_apps))
        )

    async def execute(
        self, args: BaseModel, ctx: ToolContext
    ) -> ToolResult:
        name = str(getattr(args, "name", ""))
        executable = self._allowed_apps.get(name)
        if executable is None:
            allowed = ", ".join(sorted(self._allowed_apps))
            return ToolResult.failure(
                f"Unknown app {name!r}. Allowed apps: {allowed}.",
                "UnknownApp",
            )

        try:
            # The argv list is built from trusted configuration only. The
            # model never supplies a path, executable name, or arguments.
            subprocess.Popen([executable], shell=False)
        except OSError as exc:
            return ToolResult.failure(
                f"Could not launch {name}: {exc}",
                "LaunchFailed",
            )
        return ToolResult.success(f"Launched {name}.")

    def confirmation_description(self, args: BaseModel) -> str:
        name = str(getattr(args, "name", "an app"))
        return f"FRIDAY wants to open {name}."


__all__ = ["OpenAppTool", "build_open_app_args_model"]
