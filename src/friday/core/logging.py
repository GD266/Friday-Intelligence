"""Logging configuration for FRIDAY 2.0."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from friday.security import redaction
from friday.security.redaction import contains_secret, redact_text

__all__ = [
    "RedactionFilter",
    "contains_secret",
    "get_log_dir",
    "get_logger",
    "redact_text",
    "setup_logging",
]


class RedactionFilter(logging.Filter):
    """Filter that redacts API keys and sensitive tokens from log messages."""

    # Populated from the central security module so every redaction path
    # shares exactly the same patterns.
    PATTERNS = redaction.PATTERNS

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact(record.msg)
        if record.args:
            record.args = tuple(
                self._redact(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True

    def _redact(self, text: str) -> str:
        return redact_text(text)



def get_log_dir() -> Path:
    """Get the log directory (%LOCALAPPDATA%\\Friday\\logs)."""
    localappdata = os.environ.get("LOCALAPPDATA")
    if not localappdata:
        raise RuntimeError("LOCALAPPDATA environment variable not set")
    log_dir = Path(localappdata) / "Friday" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure logging with rotating file handler and redaction filter."""
    log_dir = get_log_dir()
    log_file = log_dir / "friday.log"

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    logger.handlers.clear()

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_formatter)
    file_handler.addFilter(RedactionFilter())
    logger.addHandler(file_handler)

    # Console handler (optional, for debugging)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_formatter = logging.Formatter(
        "%(levelname)-8s | %(name)s | %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(RedactionFilter())
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
