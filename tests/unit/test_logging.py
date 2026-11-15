"""Tests for logging redaction."""

import logging

import pytest

from friday.core.logging import RedactionFilter, setup_logging
from friday.security.redaction import redact_text, register_secret

NEW_SECRET_SAMPLES = [
    pytest.param(
        "nvapi-abc123456789",
        "nvapi-***REDACTED***",
        id="reported-nvidia",
    ),
    pytest.param(
        "nvapi-" + "A1" * 10,
        "nvapi-***REDACTED***",
        id="nvidia",
    ),
    pytest.param(
        "ghp_" + "a1" * 12,
        "ghp_***REDACTED***",
        id="github-classic",
    ),
    pytest.param(
        "github_pat_" + "a1_" * 8,
        "github_pat_***REDACTED***",
        id="github-fine-grained",
    ),
    pytest.param(
        "AKIA" + "1234567890ABCDEF",
        "AKIA***REDACTED***",
        id="aws-access-key",
    ),
    pytest.param(
        "xoxb-1234567890-abcdef",
        "xox-***REDACTED***",
        id="slack",
    ),
    pytest.param(
        "eyJhbGciOiJIUzI1NiJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "***REDACTED-JWT***",
        id="jwt",
    ),
    pytest.param(
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA1234567890abcdef\n"
        "-----END RSA PRIVATE KEY-----",
        "***REDACTED PRIVATE KEY***",
        id="pem-private-key",
    ),
]


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

    @pytest.mark.parametrize(("secret", "marker"), NEW_SECRET_SAMPLES)
    def test_redacts_new_secret_formats(self, secret, marker):
        """Every newly supported format is masked in log records."""
        filter_ = RedactionFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=f"provider rejected {secret} during request",
            args=(),
            exc_info=None,
        )

        filter_.filter(record)

        message = record.getMessage()
        assert secret not in message
        assert marker in message

    def test_registered_secret_is_redacted_in_logs(self):
        """An arbitrary-format runtime secret is masked by exact value."""
        secret = "custom-format-secret-Q7"
        assert secret in redact_text(secret)

        register_secret(secret)

        message = redact_text(f"provider echoed {secret} back")
        assert secret not in message
        assert "***REDACTED***" in message

    def test_setup_logging_creates_file(self, monkeypatch, tmp_path):
        """Test that setup_logging creates log file."""
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
        logger = setup_logging("DEBUG")
        logger.info("Test message")
        log_file = tmp_path / "Friday" / "logs" / "friday.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content
