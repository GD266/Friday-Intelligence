"""Built-in ``get_time`` tool."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field

from friday.tools.base import (
    Permission,
    Tool,
    ToolContext,
    ToolResult,
)


class GetTimeArgs(BaseModel):
    """Arguments for ``get_time``."""

    model_config = ConfigDict(extra="forbid")

    timezone: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "IANA timezone name, for example Asia/Tokyo. "
            "Omit or use empty string to use the local timezone."
        ),
    )


class GetTimeTool(Tool):
    """Return the current time in a validated IANA timezone."""

    name = "get_time"
    description = (
        "Return the current date and time in an IANA timezone, "
        "or the local timezone when no timezone is given."
    )
    args_model = GetTimeArgs
    permission = Permission.SAFE
    requires_confirmation = False
    returns_untrusted = False
    pure = True

    async def execute(
        self, args: BaseModel, ctx: ToolContext
    ) -> ToolResult:
        assert isinstance(args, GetTimeArgs)
        requested = (args.timezone or "").strip()

        if not requested:
            now = datetime.now().astimezone()
            zone_name = now.tzname() or "local"
            return ToolResult.success(
                f"{now.isoformat()} ({zone_name})"
            )

        try:
            zone = ZoneInfo(requested)
        except (ZoneInfoNotFoundError, ValueError):
            return ToolResult.failure(
                f"Unknown timezone {requested!r}. "
                "Use an IANA timezone name such as Asia/Tokyo.",
                "InvalidTimezone",
            )

        now = datetime.now(zone)
        return ToolResult.success(f"{now.isoformat()} ({requested})")


__all__ = ["GetTimeArgs", "GetTimeTool"]
