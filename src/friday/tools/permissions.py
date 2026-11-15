"""Permission decisions for tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from friday.tools.base import Permission, Tool


class Decision(str, Enum):
    """The permission outcome for one tool call."""

    ALLOW = "allow"
    CONFIRM = "confirm"


@dataclass(slots=True)
class TurnState:
    """Security state that lives only for the current user turn."""

    tainted: bool = False


def decide(tool: Tool, turn_state: TurnState) -> Decision:
    """Decide whether *tool* may run automatically or needs confirmation."""
    if tool.requires_confirmation:
        return Decision.CONFIRM
    if tool.permission is Permission.DESTRUCTIVE:
        return Decision.CONFIRM
    if turn_state.tainted and not tool.pure:
        return Decision.CONFIRM
    return Decision.ALLOW


__all__ = ["Decision", "TurnState", "decide"]
