"""Core module for FRIDAY 2.0.

Exports are resolved lazily so importing :mod:`friday.core.logging` (for
example from the gateway) never pulls in the Qt-dependent core service.
"""

from typing import Any

__all__ = ["CoreService", "setup_logging", "get_logger"]


def __getattr__(name: str) -> Any:
    if name == "CoreService":
        from friday.core.service import CoreService

        return CoreService
    if name in ("setup_logging", "get_logger"):
        from friday.core.logging import get_logger, setup_logging

        return {"setup_logging": setup_logging, "get_logger": get_logger}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
