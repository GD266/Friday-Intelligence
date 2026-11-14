"""Secret management using keyring."""

from typing import Optional

import keyring
from keyring.errors import KeyringError


class SecretManager:
    """Thin wrapper over keyring for secret management.

    Service name is "friday".
    """

    SERVICE_NAME = "friday"

    def __init__(self, service_name: str = SERVICE_NAME):
        self._service = service_name

    def set_secret(self, key: str, value: str) -> None:
        """Store a secret."""
        try:
            keyring.set_password(self._service, key, value)
        except KeyringError as e:
            raise RuntimeError(f"Failed to store secret '{key}': {e}")

    def get_secret(self, key: str) -> Optional[str]:
        """Retrieve a secret. Returns None if not found."""
        try:
            return keyring.get_password(self._service, key)
        except KeyringError as e:
            raise RuntimeError(f"Failed to retrieve secret '{key}': {e}")

    def delete_secret(self, key: str) -> bool:
        """Delete a secret. Returns True if deleted, False if not found."""
        try:
            keyring.delete_password(self._service, key)
            return True
        except KeyringError:
            return False

    def has_secret(self, key: str) -> bool:
        """Check if a secret exists."""
        return self.get_secret(key) is not None

    def __repr__(self) -> str:
        return f"SecretManager(service={self._service!r})"
