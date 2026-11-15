"""Text preparation and sentence splitting for TTS."""

from __future__ import annotations

import re

# Regex patterns for text cleaning
CODE_BLOCK_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)
INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
BOLD_PATTERN = re.compile(r"\*\*([^*]+)\*\*")
ITALIC_PATTERN = re.compile(r"\*([^*]+)\*")
HEADING_PATTERN = re.compile(r"^#{1,6}\s+", re.MULTILINE)
LIST_MARKER_PATTERN = re.compile(r"^[\s]*[-*+]\s+", re.MULTILINE)
ORDERED_LIST_PATTERN = re.compile(r"^[\s]*\d+\.\s+", re.MULTILINE)
LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]+\)")
URL_PATTERN = re.compile(r"https?://\S+")
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)

# Abbreviations that should NOT trigger sentence splitting
# Only include forms WITH trailing period to avoid partial matches
ABBREVIATIONS = {
    "dr.", "mr.", "mrs.", "ms.", "prof.", "sr.", "jr.", "vs.", "etc.", "e.g.",
    "i.e.", "fig.", "figs.", "eq.", "eqs.", "cf.", "ca.", "approx.", "resp.",
    "viz.", "al.", "vol.", "ed.", "eds.", "trans.", "tr.", "ch.", "sec.",
    "secs.", "pp.", "p.", "jan.", "feb.", "mar.", "apr.", "jun.", "jul.",
    "aug.", "sep.", "oct.", "nov.", "dec.", "mon.", "tue.", "wed.", "thu.",
    "fri.", "sat.", "sun.", "a.m.", "p.m.", "am.", "pm.", "u.s.", "u.k.",
    "e.u.", "u.n.", "n.a.s.a.", "f.b.i.", "c.i.a.",
}

# Build abbreviation pattern for protection - match abbreviation
# followed by whitespace or end
ABBREV_PATTERN = re.compile(
    r"(?i)(" + "|".join(re.escape(ab) for ab in ABBREVIATIONS) + r")(?=\s|$|[,;:])"
)

# Ellipsis pattern
ELLIPSIS_PATTERN = re.compile(r"\.{3,}")

# Decimal number pattern (to avoid splitting on decimals)
DECIMAL_PATTERN = re.compile(r"\d+\.\d+")

# URL pattern (to avoid splitting on URLs)
URL_PATTERN = re.compile(r"https?://\S+")

# Sentence boundary pattern - matches punctuation followed by optional
# whitespace and capital letter. Includes ASCII (.!?) and Japanese (。！？)
# punctuation. Also handles cases without space after punctuation (common
# in Japanese). For Japanese, we also split on punctuation followed by
# any non-whitespace character.
SENTENCE_BOUNDARY = re.compile(
    r"(?<=[.!?。！？])(?:\s+(?=[A-Z\"'\(])|(?=\S))"
)


def prepare_for_speech(text: str) -> str:
    """
    Prepare markdown text for speech synthesis.

    - Removes code blocks entirely
    - Strips inline code markers, bold, italics, headings, list markers
    - Keeps link text, drops URLs
    - Drops emoji
    - Collapses whitespace
    """
    if not text or not text.strip():
        return ""

    # Remove code blocks entirely
    text = CODE_BLOCK_PATTERN.sub("", text)

    # Replace inline code with just the content
    text = INLINE_CODE_PATTERN.sub(r"\1", text)

    # Remove bold markers
    text = BOLD_PATTERN.sub(r"\1", text)

    # Remove italic markers
    text = ITALIC_PATTERN.sub(r"\1", text)

    # Remove heading markers
    text = HEADING_PATTERN.sub("", text)

    # Remove list markers
    text = LIST_MARKER_PATTERN.sub("", text)
    text = ORDERED_LIST_PATTERN.sub("", text)

    # Keep link text, drop URL
    text = LINK_PATTERN.sub(r"\1", text)

    # Drop URLs
    text = URL_PATTERN.sub("", text)

    # Drop emoji
    text = EMOJI_PATTERN.sub("", text)

    # Collapse whitespace
    text = " ".join(text.split())

    return text.strip()


def split_sentences(text: str, max_chars: int = 1200) -> list[str]:
    """
    Split text into sentences, respecting:
    - Decimals (3.5, 1.23)
    - Abbreviations (Dr., e.g., etc.)
    - Ellipses (...)
    - URLs
    - Unicode text
    - Caps total at max_chars on sentence boundary
    """
    if not text or not text.strip():
        return []

    # Protect special patterns with placeholders
    placeholders: dict[str, str] = {}
    placeholder_counter = 0

    def make_placeholder(prefix: str) -> str:
        nonlocal placeholder_counter
        placeholder = f"__PH_{prefix}_{placeholder_counter}__"
        placeholder_counter += 1
        return placeholder

    # Protect abbreviations (case-insensitive)
    def protect_abbrev(match: re.Match) -> str:
        ph = make_placeholder("ABBR")
        placeholders[ph] = match.group(0)
        return ph

    text = ABBREV_PATTERN.sub(protect_abbrev, text)

    # Protect decimals
    decimal_placeholders: dict[str, str] = {}

    def protect_decimal(match: re.Match) -> str:
        ph = make_placeholder("DEC")
        decimal_placeholders[ph] = match.group(0)
        return ph

    text = DECIMAL_PATTERN.sub(protect_decimal, text)

    # Protect ellipses
    ellipsis_placeholders: dict[str, str] = {}

    def protect_ellipsis(match: re.Match) -> str:
        ph = make_placeholder("ELLIPSIS")
        ellipsis_placeholders[ph] = match.group(0)
        return ph

    text = ELLIPSIS_PATTERN.sub(protect_ellipsis, text)

    # Protect URLs - preserve trailing punctuation
    url_placeholders: dict[str, str] = {}

    def protect_url(match: re.Match) -> str:
        url = match.group(0)
        # Check if URL ends with sentence-ending punctuation
        trailing_punct = ""
        if url.endswith((".", "!", "?", "。", "？", "！")):
            trailing_punct = url[-1]
            url = url[:-1]
        ph = make_placeholder("URL")
        url_placeholders[ph] = url
        return ph + trailing_punct

    text = URL_PATTERN.sub(protect_url, text)

    # Split on sentence boundaries
    parts = SENTENCE_BOUNDARY.split(text)
    sentences: list[str] = []
    current = ""

    for part in parts:
        # Restore placeholders in this part
        for ph, original in placeholders.items():
            part = part.replace(ph, original)
        for ph, original in decimal_placeholders.items():
            part = part.replace(ph, original)
        for ph, original in ellipsis_placeholders.items():
            part = part.replace(ph, original)
        for ph, original in url_placeholders.items():
            part = part.replace(ph, original)

        part = part.strip()
        if not part:
            continue

        # Check if this part ends with sentence-ending punctuation (ASCII + Unicode)
        ascii_end = part.endswith((".", "!", "?"))
        unicode_end = part.endswith(("。", "？", "！"))
        ends_with_punct = ascii_end or unicode_end

        if current:
            current += " " + part
        else:
            current = part

        if ends_with_punct:
            sentences.append(current)
            current = ""

    if current:
        sentences.append(current)

    # Remove URLs from each sentence (URLs were protected during
# splitting, now drop them)
    sentences = [URL_PATTERN.sub("", s) for s in sentences]

    # Apply max_chars cap on sentence boundary
    return cap_sentences(sentences, max_chars)


def cap_sentences(sentences: list[str], max_chars: int) -> list[str]:
    """
    Cap total characters at max_chars on sentence boundary.
    Always includes at least the first sentence.
    """
    if not sentences:
        return []

    total = 0
    result = []
    for i, s in enumerate(sentences):
        if i > 0 and total + len(s) + 1 > max_chars:
            break
        result.append(s)
        total += len(s) + (1 if total > 0 else 0)
    return result


def prepare_and_split(text: str, max_chars: int = 1200) -> list[str]:
    """Convenience function: prepare_for_speech then split_sentences with cap."""
    prepared = prepare_for_speech(text)
    if not prepared:
        raise ValueError("Text is empty after preparation")
    sentences = split_sentences(prepared, max_chars)
    return cap_sentences(sentences, max_chars)


__all__ = [
    "prepare_for_speech",
    "split_sentences",
    "cap_sentences",
    "prepare_and_split",
]
