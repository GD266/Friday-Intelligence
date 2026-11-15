"""Tests for secrets module."""

import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.compat import properties

from friday.security.redaction import redact_text
from friday.security.secrets import SecretManager


class InMemoryKeyring(KeyringBackend):
    """In-memory keyring backend for testing."""

    def __init__(self):
        self._store = {}

    @properties.classproperty
    def priority(self):
        return 100

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self._store:
            from keyring.errors import PasswordDeleteError
            raise PasswordDeleteError("Password not found")
        del self._store[(service, username)]


class TestSecrets:
    """Test secret management with in-memory keyring backend."""

    @pytest.fixture(autouse=True)
    def _setup_keyring(self):
        """Set up in-memory keyring backend."""
        # Register our in-memory backend
        self._backend = InMemoryKeyring()
        keyring.set_keyring(self._backend)
        yield
        # Restore default by getting a new default backend
        keyring.set_keyring(keyring.get_keyring())

    def test_set_get_delete(self):
        """Test set, get, and delete operations."""
        manager = SecretManager("test-service")
        test_key = "test-key"
        test_value = "test-secret-value"

        # Set
        manager.set_secret(test_key, test_value)

        # Get
        retrieved = manager.get_secret(test_key)
        assert retrieved == test_value

        # Delete
        result = manager.delete_secret(test_key)
        assert result is True

        # Verify deletion
        assert manager.get_secret(test_key) is None

    def test_delete_nonexistent(self):
        """Test deleting a non-existent key."""
        manager = SecretManager("test-service")
        result = manager.delete_secret("nonexistent")
        assert result is False

    def test_has_secret(self):
        """Test has_secret method."""
        manager = SecretManager("test-service")
        assert not manager.has_secret("new-key")

        manager.set_secret("new-key", "value")
        assert manager.has_secret("new-key")

        manager.delete_secret("new-key")
        assert not manager.has_secret("new-key")

    def test_repr_masks_value(self):
        """Test that repr doesn't expose secret values."""
        manager = SecretManager("test-service")
        manager.set_secret("secret-key", "super-secret-value")
        repr_str = repr(manager)
        assert "super-secret-value" not in repr_str
        assert "test-service" in repr_str

    def test_get_secret_registers_value_for_redaction(self):
        """Retrieved arbitrary-format secrets are masked by exact value."""
        manager = SecretManager("test-service")
        value = "registry-arbitrary-Q7"
        manager.set_secret("registry-key", value)

        assert manager.get_secret("registry-key") == value

        text = redact_text(f"provider echoed {value}")
        assert value not in text
        assert "***REDACTED***" in text

    def test_logs_dont_contain_secrets(self, caplog):
        """Test that secrets don't appear in logs."""
        import logging

        caplog.set_level(logging.DEBUG)
        manager = SecretManager("test-service")
        manager.set_secret("log-test", "secret-in-log")
        manager.get_secret("log-test")

        # Check logs don't contain the secret
        for record in caplog.records:
            assert "secret-in-log" not in record.getMessage()
