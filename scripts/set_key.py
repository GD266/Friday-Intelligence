#!/usr/bin/env python3
"""Store the OpenAI-compatible provider API key in Windows Credential Manager."""

import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from friday.security.secrets import PROVIDER_API_KEY, SecretManager  # noqa: E402


def main() -> int:
    """Prompt for the key without echoing it, then store it."""
    try:
        api_key = getpass.getpass("Provider API key (input hidden): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 1

    if not api_key:
        print("No key entered; nothing saved.", file=sys.stderr)
        return 1

    try:
        SecretManager().set_secret(PROVIDER_API_KEY, api_key)
    except Exception as exc:
        print(f"Failed to save the key: {exc}", file=sys.stderr)
        return 1

    print("Saved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
