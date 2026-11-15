"""Test that no hardcoded model IDs exist in source or scripts."""

from __future__ import annotations

import re
from pathlib import Path

MODEL_ID_PATTERN = re.compile(
    r"\b(meta|nvidia|mistralai|google|openai|deepseek-ai)/[\w.\-]+"
)


def test_no_hardcoded_model_ids_in_src() -> None:
    """Scan src/ and scripts/ for provider-style model ID literals."""
    root = Path(__file__).parent.parent
    search_dirs = [root / "src", root / "scripts"]
    violations: list[tuple[str, int, str]] = []

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for file_path in search_dir.rglob("*.py"):
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for i, line in enumerate(content.splitlines(), 1):
                match = MODEL_ID_PATTERN.search(line)
                if match:
                    violations.append(
                        (str(file_path.relative_to(root)), i, match.group(0))
                    )

    assert not violations, (
        "Hardcoded model IDs found in source/scripts. "
        "Use settings.provider.model from config.toml instead.\n"
        + "\n".join(f"{f}:{ln}: {mid}" for f, ln, mid in violations)
    )
