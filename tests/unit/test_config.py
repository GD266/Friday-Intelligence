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
            assert (
                settings.provider.base_url
                == "https://integrate.api.nvidia.com/v1"
            )
            assert settings.provider.model == ""
            assert settings.provider.connect_timeout_seconds == 10.0
            assert settings.provider.read_timeout_seconds == 90.0
            assert settings.provider.system_prompt

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
                '[provider]\nconnect_timeout_seconds = "not-a-number"\n',
                encoding="utf-8",
            )

            with pytest.raises(ValueError) as exc_info:
                load_settings()
            assert (
            "provider.connect_timeout_seconds" in str(exc_info.value)
            or "connect_timeout_seconds" in str(exc_info.value)
        )

    def test_env_override(self, monkeypatch):
        """Test environment variable override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            monkeypatch.setenv("FRIDAY_APP__LOG_LEVEL", "DEBUG")
            monkeypatch.setenv("FRIDAY_PROVIDER__MODEL", "meta/llama-3.1-8b")
            monkeypatch.setenv("FRIDAY_PROVIDER__READ_TIMEOUT_SECONDS", "12.5")
            settings = load_settings()
            assert settings.app.log_level == "DEBUG"
            assert settings.provider.model == "meta/llama-3.1-8b"
            assert settings.provider.read_timeout_seconds == 12.5


class TestConfigFileCompatibility:
    """Test old and new config file formats."""

    def test_old_gateway_section_rejected_with_path_and_section(self, monkeypatch):
        """Test that a Phase 0 config with [gateway] is rejected clearly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            config_path = Path(tmpdir) / "Friday" / "config.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                '[gateway]\nhost = "127.0.0.1"\nport = 8765\n',
                encoding="utf-8",
            )

            with pytest.raises(ValueError) as exc_info:
                load_settings()

            message = str(exc_info.value)
            assert str(config_path) in message
            assert "gateway" in message
            assert (
                "Fix the field, or rename/delete this file to regenerate defaults."
                in message
            )

    def test_valid_new_format_config_loads(self, monkeypatch):
        """Test that a valid current-format config loads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            config_path = Path(tmpdir) / "Friday" / "config.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                '[app]\nname = "Custom FRIDAY"\n\n'
                '[provider]\nmodel = "meta/llama-3.1-8b"\n'
                "read_timeout_seconds = 12.5\n",
                encoding="utf-8",
            )

            settings = load_settings()

            assert settings.app.name == "Custom FRIDAY"
            assert settings.provider.model == "meta/llama-3.1-8b"
            assert settings.provider.read_timeout_seconds == 12.5
            assert (
                settings.provider.base_url
                == "https://integrate.api.nvidia.com/v1"
            )

    def test_missing_provider_section_uses_defaults(self, monkeypatch):
        """Test that a config without [provider] loads with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            config_path = Path(tmpdir) / "Friday" / "config.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                '[app]\nname = "FRIDAY without provider"\n',
                encoding="utf-8",
            )

            settings = load_settings()

            assert settings.app.name == "FRIDAY without provider"
            assert (
                settings.provider.base_url
                == "https://integrate.api.nvidia.com/v1"
            )
            assert settings.provider.model == ""
            assert settings.provider.connect_timeout_seconds == 10.0
            assert settings.provider.read_timeout_seconds == 90.0
