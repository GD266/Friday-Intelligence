"""Core module for FRIDAY 2.0."""

from friday.core.logging import get_logger, setup_logging
from friday.core.service import CoreService

__all__ = ["CoreService", "setup_logging", "get_logger"]
