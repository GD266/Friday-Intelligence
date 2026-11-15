"""Safe conversion of user text into SQLite FTS5 MATCH queries.

Raw user input is never passed to ``MATCH``.  Text is split into word tokens,
FTS operators and punctuation are discarded, every token is quoted, and the
tokens are joined with ``AND`` for search (or ``OR`` for relevance ranking).
The final token uses a prefix search.
"""

from __future__ import annotations

import re

MAX_QUERY_TOKENS = 24
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

_FTS_OPERATORS = frozenset({"and", "or", "not", "near"})
_TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def _query_tokens(text: str) -> list[str]:
    if not isinstance(text, str) or not text:
        return []
    tokens = [
        token
        for token in _TOKEN_PATTERN.findall(text)
        if token.casefold() not in _FTS_OPERATORS
    ]
    return tokens[:MAX_QUERY_TOKENS]


def _quoted_query(tokens: list[str], operator: str) -> str:
    if not tokens:
        return ""
    quoted = [f'"{token}"' for token in tokens]
    quoted[-1] = quoted[-1] + "*"
    return f" {operator} ".join(quoted)


def fts_match_query(text: str) -> str:
    """Return a quoted AND query, or ``""`` when nothing is usable."""
    return _quoted_query(_query_tokens(text), "AND")


def fts_relevance_query(text: str) -> str:
    """Return a quoted OR query for ranking, or ``""`` when unusable."""
    return _quoted_query(_query_tokens(text), "OR")


def normalize_limit(limit: int, *, default: int = DEFAULT_LIMIT) -> int:
    """Clamp a result limit to the supported range."""
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = default
    return max(0, min(value, MAX_LIMIT))
