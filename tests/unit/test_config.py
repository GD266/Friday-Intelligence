"""Tests for config module."""

import tempfile
from pathlib import Path

import pytest

from friday.config.settings import (
    ensure_config_exists,
    load_settings,
)


class TestConfigDefaults:
    """Test default configuration creation and loading."""

    def test_default_config_created(self, monkeypatch):
        """Test that default config is created when missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            config_path = ensure_config_exists()
            assert config_path.exists()
            content = config_path.read_text()
            assert "FRIDAY 2.0" in content
            assert "base_url" in content

    def test_load_default_settings(self, monkeypatch):
        """Test loading default settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            settings = load_settings()
            assert settings.app.name == "FRIDAY 2.0"
            assert settings.gateway.base_url == "https://api.openai.com/v1"
            assert settings.gateway.model == "gpt-4o-mini"

    def test_invalid_config_rejected(self, monkeypatch):
        """Test that invalid config raises clear error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            config_path = Path(tmpdir) / "Friday" / "config.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text("invalid = toml content [", encoding="utf-8")

            with pytest.raises(ValueError) as exc_info:
                load_settings()
            assert (
            "Invalid TOML" in str(exc_info.value)
            or "Invalid configuration" in str(exc_info.value)
        )

    def test_invalid_field_rejected(self, monkeypatch):
        """Test that invalid field values are rejected with clear message."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            config_path = Path(tmpdir) / "Friday" / "config.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                '[gateway]\ntimeout = "not-a-number"\n',
                encoding="utf-8",
            )

            with pytest.raises(ValueError) as exc_info:
                load_settings()
            assert (
            "gateway.timeout" in str(exc_info.value) or "timeout" in str(exc_info.value)
        )

    def test_env_override(self, monkeypatch):
        """Test environment variable override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            monkeypatch.setenv("FRIDAY_APP__LOG_LEVEL", "DEBUG")
            monkeypatch.setenv("FRIDAY_GATEWAY__MODEL", "gpt-4")
            settings = load_settings()
            assert settings.app.log_level == "DEBUG"
            assert settings.gateway.model == "gpt-4"
