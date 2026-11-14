"""Tests for logging redaction."""

import logging

from friday.core.logging import RedactionFilter, setup_logging


class TestLogRedaction:
    """Test log redaction filter."""

    def test_redacts_openai_key(self):
        """Test OpenAI API key redaction."""
        filter_ = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Using key sk-abcdefghijklmnopqrstuvwxyz123456789012345678901234",
            args=(), exc_info=None,
        )
        filter_.filter(record)
        assert "sk-***REDACTED***" in record.getMessage()
        assert (
            "sk-abcdefghijklmnopqrstuvwxyz123456789012345678901234"
            not in record.getMessage()
        )

    def test_redacts_anthropic_key(self):
        """Test Anthropic API key redaction."""
        filter_ = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=(
                "Key: sk-ant-"
                "abcdefghijklmnopqrstuvwxyz123456789012345678901234567890123456789012345"
                "abcdefghijklmnopqrstuvwxy"
            ),  # 95+ chars after sk-ant-
            args=(), exc_info=None,
        )
        filter_.filter(record)
        assert "sk-ant-***REDACTED***" in record.getMessage()

    def test_redacts_google_key(self):
        """Test Google API key redaction."""
        filter_ = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="AIzaSyAbcdefghijklmnopqrstuvwxyz12345678901234",  # 35 chars after AIza
            args=(), exc_info=None,
        )
        filter_.filter(record)
        assert "AIza***REDACTED***" in record.getMessage()

    def test_redacts_bearer_token(self):
        """Test Bearer token redaction."""
        filter_ = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            args=(), exc_info=None,
        )
        filter_.filter(record)
        assert "Bearer ***REDACTED***" in record.getMessage()

    def test_redacts_gsk_key(self):
        """Test Groq API key redaction."""
        filter_ = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="gsk_abcdefghijklmnopqrstuvwxyz123456789012345678901234",
            args=(), exc_info=None,
        )
        filter_.filter(record)
        assert "gsk_***REDACTED***" in record.getMessage()

    def test_redacts_generic_sk_key(self):
        """Test generic sk- key redaction."""
        filter_ = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="sk-abcdef1234567890abcdef1234567890",
            args=(), exc_info=None,
        )
        filter_.filter(record)
        assert "sk-***REDACTED***" in record.getMessage()

    def test_redacts_args(self):
        """Test redaction in log args."""
        filter_ = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="API key: %s",
            args=(
            "sk-abcdefghijklmnopqrstuvwxyz123456789012345678901234",
        ),
        exc_info=None,
        )
        filter_.filter(record)
        assert "sk-***REDACTED***" in record.getMessage()

    def test_setup_logging_creates_file(self, monkeypatch, tmp_path):
        """Test that setup_logging creates log file."""
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        logger = setup_logging("DEBUG")
        logger.info("Test message")
        log_file = tmp_path / "Friday" / "logs" / "friday.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content
