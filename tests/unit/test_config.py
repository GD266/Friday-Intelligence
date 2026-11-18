"""Tests for config module."""

import tempfile
from pathlib import Path

import pytest

from friday.config.settings import (
    STTSettings,
    ToolsSettings,
    VoiceSettings,
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
            assert "[tools]" in content
            assert "max_iterations = 5" in content
            assert "max_calls_per_turn = 8" in content
            assert "[tools.allowed_apps]" in content
            assert 'notepad = "notepad.exe"' in content

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
            assert settings.chat.context_char_budget == 24000
            assert settings.memory.enabled is True
            assert settings.memory.fact_char_budget == 2000
            assert settings.memory.max_facts_in_prompt == 20
            assert settings.tools.enabled is True
            assert settings.tools.max_iterations == 5
            assert settings.tools.max_calls_per_turn == 8
            assert settings.tools.tool_timeout_seconds == 10.0
            assert settings.tools.confirm_timeout_seconds == 60.0
            assert settings.tools.max_result_chars == 2000
            assert settings.tools.allowed_apps == {
                "notepad": "notepad.exe",
                "calculator": "calc.exe",
                "paint": "mspaint.exe",
            }

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

    def test_invalid_tools_values_rejected(self, monkeypatch):
        """Test that unsafe or nonsensical tool settings are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            config_path = Path(tmpdir) / "Friday" / "config.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                "[tools]\nmax_iterations = 0\n",
                encoding="utf-8",
            )

            with pytest.raises(ValueError) as exc_info:
                load_settings()
            assert "tools.max_iterations" in str(exc_info.value)

    def test_empty_allowed_apps_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one app"):
            ToolsSettings(allowed_apps={})

    def test_allowed_apps_reject_empty_executable(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            ToolsSettings(allowed_apps={"notepad": "   "})

    def test_allowed_apps_reject_null_character(self) -> None:
        with pytest.raises(ValueError, match="null character"):
            ToolsSettings(allowed_apps={"notepad": "note\x00pad.exe"})

    def test_allowed_apps_names_are_trimmed(self) -> None:
        settings = ToolsSettings(
            allowed_apps={" notepad ": " notepad.exe "}
        )
        assert settings.allowed_apps == {"notepad": "notepad.exe"}

    def test_voice_prefetch_bounds(self) -> None:
        """prefetch_sentences defaults to 2 and is limited to 1..4."""
        assert VoiceSettings().prefetch_sentences == 2
        assert VoiceSettings(prefetch_sentences=1).prefetch_sentences == 1
        assert VoiceSettings(prefetch_sentences=4).prefetch_sentences == 4
        with pytest.raises(ValueError):
            VoiceSettings(prefetch_sentences=0)
        with pytest.raises(ValueError):
            VoiceSettings(prefetch_sentences=5)

    def test_voice_record_settings_bounds(self) -> None:
        """Recording settings have safe defaults and reject bad values."""
        voice = VoiceSettings()
        assert voice.input_device == ""
        assert voice.max_record_seconds == 30
        assert voice.min_record_seconds == 0.3
        assert voice.silence_peak_threshold == 0.01

        assert VoiceSettings(max_record_seconds=1).max_record_seconds == 1
        assert VoiceSettings(max_record_seconds=60).max_record_seconds == 60
        with pytest.raises(ValueError):
            VoiceSettings(max_record_seconds=0)
        with pytest.raises(ValueError):
            VoiceSettings(max_record_seconds=61)

        assert VoiceSettings(min_record_seconds=0.1).min_record_seconds == 0.1
        with pytest.raises(ValueError):
            VoiceSettings(min_record_seconds=0)
        with pytest.raises(ValueError):
            VoiceSettings(min_record_seconds=61)

        with pytest.raises(ValueError):
            VoiceSettings(silence_peak_threshold=-0.01)
        with pytest.raises(ValueError):
            VoiceSettings(silence_peak_threshold=1.01)

    def test_stt_defaults(self) -> None:
        """STT defaults to the multilingual tiny model with auto language."""
        stt = STTSettings()
        assert stt.model == "tiny"
        assert stt.cpu_threads == 0
        assert stt.language == "auto"
        assert stt.beam_size == 5
        assert stt.vad_filter is True
        assert stt.vad_threshold == 0.4
        assert stt.vad_min_silence_ms == 500
        assert stt.vad_speech_pad_ms == 400
        assert stt.vad_min_speech_ms == 0

    def test_stt_accepts_multilingual_tiny_and_base(self) -> None:
        assert STTSettings(model="tiny").model == "tiny"
        assert STTSettings(model="base").model == "base"

    def test_stt_beam_size_bounds(self) -> None:
        assert STTSettings(beam_size=1).beam_size == 1
        assert STTSettings(beam_size=5).beam_size == 5
        with pytest.raises(ValueError):
            STTSettings(beam_size=0)
        with pytest.raises(ValueError):
            STTSettings(beam_size=11)

    def test_stt_vad_bounds(self) -> None:
        with pytest.raises(ValueError):
            STTSettings(vad_threshold=0)
        with pytest.raises(ValueError):
            STTSettings(vad_threshold=1)
        with pytest.raises(ValueError):
            STTSettings(vad_min_silence_ms=-1)
        with pytest.raises(ValueError):
            STTSettings(vad_speech_pad_ms=-1)
        with pytest.raises(ValueError):
            STTSettings(vad_min_speech_ms=-1)

    def test_stt_rejects_english_only_models(self) -> None:
        """tiny.en is English-only and must never be used."""
        with pytest.raises(ValueError, match="English-only"):
            STTSettings(model="tiny.en")

    def test_stt_rejects_unknown_model(self) -> None:
        with pytest.raises(ValueError, match="model must be one of"):
            STTSettings(model="gigantic")

    def test_stt_model_is_normalized(self) -> None:
        assert STTSettings(model=" Tiny ").model == "tiny"

    def test_stt_rejects_unsupported_language(self) -> None:
        with pytest.raises(ValueError, match="language must be one of"):
            STTSettings(language="fr")

    def test_stt_cpu_threads_bounds(self) -> None:
        assert STTSettings(cpu_threads=0).cpu_threads == 0
        assert STTSettings(cpu_threads=4).cpu_threads == 4
        with pytest.raises(ValueError):
            STTSettings(cpu_threads=-1)
        with pytest.raises(ValueError):
            STTSettings(cpu_threads=65)

    def test_stt_section_in_default_config(self, monkeypatch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            content = ensure_config_exists().read_text(encoding="utf-8")
            assert "[stt]" in content
            assert 'model = "tiny"' in content
            assert 'language = "auto"' in content
            assert "beam_size = 5" in content
            assert "vad_filter = true" in content
            assert load_settings().stt.model == "tiny"

    def test_env_override(self, monkeypatch):
        """Test environment variable override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("APPDATA", tmpdir)
            monkeypatch.setenv("FRIDAY_APP__LOG_LEVEL", "DEBUG")
            monkeypatch.setenv("FRIDAY_PROVIDER__MODEL", "meta/llama-3.1-8b")
            monkeypatch.setenv("FRIDAY_PROVIDER__READ_TIMEOUT_SECONDS", "12.5")
            monkeypatch.setenv("FRIDAY_CHAT__CONTEXT_CHAR_BUDGET", "1234")
            monkeypatch.setenv("FRIDAY_MEMORY__ENABLED", "false")
            monkeypatch.setenv("FRIDAY_MEMORY__FACT_CHAR_BUDGET", "1500")
            monkeypatch.setenv("FRIDAY_MEMORY__MAX_FACTS_IN_PROMPT", "7")
            monkeypatch.setenv("FRIDAY_TOOLS__ENABLED", "false")
            monkeypatch.setenv("FRIDAY_TOOLS__MAX_ITERATIONS", "3")
            monkeypatch.setenv("FRIDAY_TOOLS__MAX_CALLS_PER_TURN", "4")
            monkeypatch.setenv(
                "FRIDAY_TOOLS__TOOL_TIMEOUT_SECONDS", "2.5"
            )
            monkeypatch.setenv(
                "FRIDAY_TOOLS__CONFIRM_TIMEOUT_SECONDS", "7.5"
            )
            monkeypatch.setenv("FRIDAY_TOOLS__MAX_RESULT_CHARS", "500")
            monkeypatch.setenv("FRIDAY_STT__MODEL", "small")
            monkeypatch.setenv("FRIDAY_STT__CPU_THREADS", "6")
            monkeypatch.setenv("FRIDAY_STT__LANGUAGE", "hi")
            monkeypatch.setenv("FRIDAY_STT__BEAM_SIZE", "1")
            monkeypatch.setenv("FRIDAY_STT__VAD_FILTER", "true")
            monkeypatch.setenv("FRIDAY_STT__VAD_THRESHOLD", "0.35")
            monkeypatch.setenv("FRIDAY_STT__VAD_MIN_SILENCE_MS", "300")
            monkeypatch.setenv("FRIDAY_STT__VAD_SPEECH_PAD_MS", "500")
            monkeypatch.setenv("FRIDAY_STT__VAD_MIN_SPEECH_MS", "80")
            settings = load_settings()
            assert settings.app.log_level == "DEBUG"
            assert settings.provider.model == "meta/llama-3.1-8b"
            assert settings.provider.read_timeout_seconds == 12.5
            assert settings.chat.context_char_budget == 1234
            assert settings.memory.enabled is False
            assert settings.memory.fact_char_budget == 1500
            assert settings.memory.max_facts_in_prompt == 7
            assert settings.tools.enabled is False
            assert settings.tools.max_iterations == 3
            assert settings.tools.max_calls_per_turn == 4
            assert settings.tools.tool_timeout_seconds == 2.5
            assert settings.tools.confirm_timeout_seconds == 7.5
            assert settings.tools.max_result_chars == 500
            assert settings.stt.model == "small"
            assert settings.stt.cpu_threads == 6
            assert settings.stt.language == "hi"
            assert settings.stt.beam_size == 1
            assert settings.stt.vad_filter is True
            assert settings.stt.vad_threshold == pytest.approx(0.35)
            assert settings.stt.vad_min_silence_ms == 300
            assert settings.stt.vad_speech_pad_ms == 500
            assert settings.stt.vad_min_speech_ms == 80


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
