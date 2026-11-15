"""Configuration settings for FRIDAY 2.0."""

import os
import tomllib
from pathlib import Path

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_allowed_apps() -> dict[str, str]:
    return {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "paint": "mspaint.exe",
    }


class AppSettings(BaseModel):
    """Application settings."""

    name: str = "FRIDAY 2.0"
    version: str = "0.1.0"
    log_level: str = "INFO"
    debug: bool = False


class CoreSettings(BaseModel):
    """Core service settings."""

    ping_timeout: float = 5.0
    max_queue_size: int = 100


class ChatSettings(BaseModel):
    """Chat context settings."""

    context_char_budget: int = 24000


class ProviderSettings(BaseModel):
    """OpenAI-compatible AI provider settings."""

    base_url: str = "https://integrate.api.nvidia.com/v1"
    model: str = ""
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 90.0
    system_prompt: str = (
        "You are FRIDAY, a concise, helpful personal assistant."
    )


class MemorySettings(BaseModel):
    """Memory system settings."""

    db_path: str = ""
    max_conversations: int = 1000
    max_messages_per_conversation: int = 500
    enabled: bool = True
    fact_char_budget: int = 2000
    max_facts_in_prompt: int = 20


class UISettings(BaseModel):
    """UI settings."""

    window_width: int = 800
    window_height: int = 600
    theme: str = "system"


class ToolsSettings(BaseModel):
    """Tool runtime settings."""

    enabled: bool = True
    max_iterations: int = Field(default=5, ge=1)
    max_calls_per_turn: int = Field(default=8, ge=1)
    tool_timeout_seconds: float = Field(default=10.0, gt=0)
    confirm_timeout_seconds: float = Field(default=60.0, gt=0)
    max_result_chars: int = Field(default=2000, ge=1)
    allowed_apps: dict[str, str] = Field(
        default_factory=_default_allowed_apps
    )

    @field_validator("allowed_apps")
    @classmethod
    def _validate_allowed_apps(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("allowed_apps must contain at least one app")
        cleaned: dict[str, str] = {}
        for name, executable in value.items():
            clean_name = name.strip()
            clean_executable = executable.strip()
            if not clean_name:
                raise ValueError("allowed_apps names must not be empty")
            if not clean_executable:
                raise ValueError(
                    f"allowed_apps.{clean_name} must not be empty"
                )
            if "\x00" in clean_executable:
                raise ValueError(
                    f"allowed_apps.{clean_name} contains a null character"
                )
            cleaned[clean_name] = clean_executable
        return cleaned


class Settings(BaseSettings):
    """Main settings container."""

    app: AppSettings = Field(default_factory=AppSettings)
    core: CoreSettings = Field(default_factory=CoreSettings)
    chat: ChatSettings = Field(default_factory=ChatSettings)
    provider: ProviderSettings = Field(default_factory=ProviderSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    tools: ToolsSettings = Field(default_factory=ToolsSettings)
    ui: UISettings = Field(default_factory=UISettings)

    model_config = SettingsConfigDict(
        env_prefix="FRIDAY_",
        env_nested_delimiter="__",
    )

    @classmethod
    def from_toml(cls, path: Path) -> "Settings":
        """Load settings from a TOML file."""
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with path.open("rb") as f:
            data = tomllib.load(f)
        return cls(**data)


DEFAULT_CONFIG_TOML = """
[app]
name = "FRIDAY 2.0"
version = "0.1.0"
log_level = "INFO"
debug = false

[core]
ping_timeout = 5.0
max_queue_size = 100

[chat]
context_char_budget = 24000

[provider]
base_url = "https://integrate.api.nvidia.com/v1"
model = ""
connect_timeout_seconds = 10.0
read_timeout_seconds = 90.0
system_prompt = "You are FRIDAY, a concise, helpful personal assistant."

[memory]
db_path = ""
max_conversations = 1000
max_messages_per_conversation = 500
enabled = true
fact_char_budget = 2000
max_facts_in_prompt = 20

[tools]
enabled = true
max_iterations = 5
max_calls_per_turn = 8
tool_timeout_seconds = 10.0
confirm_timeout_seconds = 60.0
max_result_chars = 2000

[tools.allowed_apps]
notepad = "notepad.exe"
calculator = "calc.exe"
paint = "mspaint.exe"

[ui]
window_width = 800
window_height = 600
theme = "system"
""".strip()


def get_config_dir() -> Path:
    """Get the configuration directory (%APPDATA%\\Friday)."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable not set")
    config_dir = Path(appdata) / "Friday"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Get the configuration file path."""
    return get_config_dir() / "config.toml"


def ensure_config_exists() -> Path:
    """Ensure config file exists, create with defaults if missing."""
    config_path = get_config_path()
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")
    return config_path


def load_settings() -> Settings:
    """Load settings from config file, creating defaults if needed.

    Environment variables (FRIDAY_*) override config file values.
    """
    config_path = ensure_config_exists()
    try:
        # First validate TOML syntax
        content = config_path.read_text(encoding="utf-8")
        if not _get_valid_toml(content):
            raise ValueError(
                f"Invalid TOML syntax in {config_path}. "
                "Please check the configuration file format. "
                "Fix the field, or rename/delete this file to regenerate defaults."
            )
        # Parse TOML
        data = tomllib.loads(content)
        # Apply environment variable overrides
        data = _apply_env_overrides(data)
        return Settings.model_validate(data)
    except ValidationError as e:
        errors = []
        for error in e.errors():
            field = ".".join(str(x) for x in error["loc"])
            msg = error["msg"]
            errors.append(f"{field}: {msg}")
        raise ValueError(
            f"Invalid configuration in {config_path}:\n"
            + "\n".join(errors)
            + "\nFix the field, or rename/delete this file to regenerate defaults."
        ) from e
    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to load configuration from {config_path}: {e}")


def _apply_env_overrides(data: dict) -> dict:
    """Apply environment variable overrides to config data."""
    import os

    # Mapping of env vars to config paths
    env_mapping = {
        "FRIDAY_APP__LOG_LEVEL": ("app", "log_level"),
        "FRIDAY_APP__DEBUG": ("app", "debug"),
        "FRIDAY_CORE__PING_TIMEOUT": ("core", "ping_timeout"),
        "FRIDAY_CORE__MAX_QUEUE_SIZE": ("core", "max_queue_size"),
        "FRIDAY_CHAT__CONTEXT_CHAR_BUDGET": ("chat", "context_char_budget"),
        "FRIDAY_PROVIDER__BASE_URL": ("provider", "base_url"),
        "FRIDAY_PROVIDER__MODEL": ("provider", "model"),
        "FRIDAY_PROVIDER__CONNECT_TIMEOUT_SECONDS": (
            "provider",
            "connect_timeout_seconds",
        ),
        "FRIDAY_PROVIDER__READ_TIMEOUT_SECONDS": (
            "provider",
            "read_timeout_seconds",
        ),
        "FRIDAY_PROVIDER__SYSTEM_PROMPT": ("provider", "system_prompt"),
        "FRIDAY_MEMORY__DB_PATH": ("memory", "db_path"),
        "FRIDAY_MEMORY__MAX_CONVERSATIONS": ("memory", "max_conversations"),
        "FRIDAY_MEMORY__MAX_MESSAGES_PER_CONVERSATION": (
            "memory",
            "max_messages_per_conversation",
        ),
        "FRIDAY_MEMORY__ENABLED": ("memory", "enabled"),
        "FRIDAY_MEMORY__FACT_CHAR_BUDGET": ("memory", "fact_char_budget"),
        "FRIDAY_MEMORY__MAX_FACTS_IN_PROMPT": (
            "memory",
            "max_facts_in_prompt",
        ),
        "FRIDAY_TOOLS__ENABLED": ("tools", "enabled"),
        "FRIDAY_TOOLS__MAX_ITERATIONS": ("tools", "max_iterations"),
        "FRIDAY_TOOLS__MAX_CALLS_PER_TURN": ("tools", "max_calls_per_turn"),
        "FRIDAY_TOOLS__TOOL_TIMEOUT_SECONDS": (
            "tools",
            "tool_timeout_seconds",
        ),
        "FRIDAY_TOOLS__CONFIRM_TIMEOUT_SECONDS": (
            "tools",
            "confirm_timeout_seconds",
        ),
        "FRIDAY_TOOLS__MAX_RESULT_CHARS": ("tools", "max_result_chars"),
        "FRIDAY_UI__WINDOW_WIDTH": ("ui", "window_width"),
        "FRIDAY_UI__WINDOW_HEIGHT": ("ui", "window_height"),
        "FRIDAY_UI__THEME": ("ui", "theme"),
    }

    result = data.copy()
    for env_var, (section, key) in env_mapping.items():
        value = os.environ.get(env_var)
        if value is not None:
            # Convert value to appropriate type
            if key in ("debug", "enabled"):
                value = value.lower() in ("true", "1", "yes")
            elif key in (
                "ping_timeout",
                "connect_timeout_seconds",
                "read_timeout_seconds",
                "max_queue_size",
                "max_conversations",
                "max_messages_per_conversation",
                "fact_char_budget",
                "max_facts_in_prompt",
                "window_width",
                "window_height",
                "context_char_budget",
                "max_iterations",
                "max_calls_per_turn",
                "max_result_chars",
                "tool_timeout_seconds",
                "confirm_timeout_seconds",
            ):
                is_float = key in (
                    "ping_timeout",
                    "connect_timeout_seconds",
                    "read_timeout_seconds",
                    "tool_timeout_seconds",
                    "confirm_timeout_seconds",
                )
                value = float(value) if is_float else int(value)

            if section not in result:
                result[section] = {}
            result[section][key] = value

    return result


def _get_valid_toml(content: str) -> bool:
    """Check if content is valid TOML."""
    try:
        tomllib.loads(content)
        return True
    except tomllib.TOMLDecodeError:
        return False


def save_settings(settings: Settings) -> None:
    """Save settings to config file."""
    config_path = get_config_path()
    # Convert to dict and write as TOML
    import tomli_w
    data = settings.model_dump()
    config_path.write_text(tomli_w.dumps(data), encoding="utf-8")
