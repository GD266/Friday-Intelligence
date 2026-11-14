#!/usr/bin/env python3
"""Secret check script for FRIDAY 2.0.

Stores a dummy secret, reads it back, prints only OK/FAIL, then deletes it.
"""

import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from friday.security.secrets import SecretManager


def main() -> int:
    """Run secret check."""
    manager = SecretManager("friday-test")
    test_key = "test-secret-check"
    test_value = "dummy-secret-value-12345"

    try:
        # Store
        manager.set_secret(test_key, test_value)

        # Retrieve
        retrieved = manager.get_secret(test_key)

        if retrieved != test_value:
            print("FAIL")
            return 1

        # Delete
        manager.delete_secret(test_key)

        # Verify deletion
        if manager.get_secret(test_key) is not None:
            print("FAIL")
            return 1

        print("OK")
        return 0

    except Exception as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
