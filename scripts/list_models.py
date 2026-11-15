#!/usr/bin/env python3
"""List model ids exposed by the configured OpenAI-compatible provider.

MANUAL ONLY: this script performs a real network request and must never be
run by pytest.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import httpx  # noqa: E402

from friday.config.settings import load_settings  # noqa: E402
from friday.gateway.errors import (  # noqa: E402
    GatewayError,
    MalformedResponse,
    NetworkError,
    NotConfigured,
    TimeoutError,
    build_http_error,
)
from friday.security.secrets import PROVIDER_API_KEY, SecretManager  # noqa: E402


async def fetch_model_ids() -> list[str]:
    """Fetch model ids from ``{base_url}/models``."""
    settings = load_settings()
    api_key = SecretManager().get_secret(PROVIDER_API_KEY)
    if not api_key:
        raise NotConfigured(
            "No API key is stored.\nRun: python scripts/set_key.py"
        )

    base_url = settings.provider.base_url.rstrip("/")
    url = f"{base_url}/models"
    timeout = httpx.Timeout(
        connect=settings.provider.connect_timeout_seconds,
        read=settings.provider.read_timeout_seconds,
        write=settings.provider.read_timeout_seconds,
        pool=settings.provider.connect_timeout_seconds,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
            )
    except httpx.TimeoutException as exc:
        raise TimeoutError(
            "The provider timed out while listing models."
        ) from exc
    except httpx.TransportError as exc:
        raise NetworkError(
            "Network error while contacting the provider "
            f"({exc.__class__.__name__})."
        ) from exc

    if response.status_code != 200:
        raise build_http_error(
            response.status_code,
            response.text,
            secret=api_key,
            retry_after_header=response.headers.get("Retry-After"),
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise MalformedResponse(
            "The provider returned a non-JSON model list."
        ) from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise MalformedResponse(
            "The provider returned an unexpected model list shape."
        )

    model_ids = {
        entry["id"]
        for entry in data
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    return sorted(model_ids)


def main() -> int:
    """Print sorted model ids, one per line."""
    try:
        model_ids = asyncio.run(fetch_model_ids())
    except GatewayError as exc:
        print(f"{exc.kind}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"{exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1

    for model_id in model_ids:
        print(model_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
