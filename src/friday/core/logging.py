"""Logging configuration for FRIDAY 2.0."""

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


class RedactionFilter(logging.Filter):
    """Filter that redacts API keys and sensitive tokens from log messages."""

    # Patterns for common API key formats (order matters - more specific first)
    PATTERNS = [
        # Anthropic API keys (sk-ant-...)
        (re.compile(r"sk-ant-[a-zA-Z0-9-_]{95,}"), "sk-ant-***REDACTED***"),
        # Google API keys (AIza...)
        (re.compile(r"AIza[a-zA-Z0-9-_]{35}"), "AIza***REDACTED***"),
        # Generic Bearer tokens
        (re.compile(r"Bearer\s+[a-zA-Z0-9-_=]+"), "Bearer ***REDACTED***"),
        # gsk_... keys (Groq)
        (re.compile(r"gsk_[a-zA-Z0-9]{50,}"), "gsk_***REDACTED***"),
        # NVIDIA API keys (nvapi-...)
        (re.compile(r"nvapi-[a-zA-Z0-9-_]{20,}"), "nvapi-***REDACTED***"),
        # OpenAI API keys (sk-... 48 chars)
        (re.compile(r"sk-[a-zA-Z0-9]{48}"), "sk-***REDACTED***"),
        # Generic sk-... keys (fallback)
        (re.compile(r"sk-[a-zA-Z0-9-_]{20,}"), "sk-***REDACTED***"),
    ]

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


def redact_text(text: str) -> str:
    """Return *text* with known API key formats masked."""
    for pattern, replacement in RedactionFilter.PATTERNS:
        text = pattern.sub(replacement, text)
    return text



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
