"""Tests for voice text preparation and sentence splitting."""

from __future__ import annotations

import pytest

from friday.voice.text import (
    cap_sentences,
    prepare_and_split,
    prepare_for_speech,
    split_sentences,
)


class TestPrepareForSpeech:
    """Tests for prepare_for_speech function."""

    def test_empty_input(self) -> None:
        assert prepare_for_speech("") == ""
        assert prepare_for_speech("   ") == ""

    def test_code_blocks_removed(self) -> None:
        text = "Here is code:\n```python\nprint('hello')\n```\nDone."
        result = prepare_for_speech(text)
        assert "print('hello')" not in result
        assert "```" not in result
        assert "Here is code:" in result
        assert "Done." in result

    def test_inline_code_stripped(self) -> None:
        text = "Use `print()` function."
        result = prepare_for_speech(text)
        assert "`" not in result
        assert "print()" in result

    def test_bold_italic_stripped(self) -> None:
        text = "**bold** and *italic* text."
        result = prepare_for_speech(text)
        assert "**" not in result
        assert "*" not in result
        assert "bold and italic text" in result

    def test_headings_stripped(self) -> None:
        text = "# Heading\n## Subheading\nText."
        result = prepare_for_speech(text)
        assert "#" not in result
        assert "Heading" in result
        assert "Subheading" in result

    def test_list_markers_removed(self) -> None:
        text = "- Item 1\n- Item 2\n1. First\n2. Second"
        result = prepare_for_speech(text)
        assert "- " not in result
        assert "1. " not in result
        assert "Item 1" in result

    def test_links_kept_text_dropped_url(self) -> None:
        text = "See [Google](https://google.com) for search."
        result = prepare_for_speech(text)
        assert "Google" in result
        assert "https://google.com" not in result
        assert "(" not in result and ")" not in result

    def test_urls_dropped(self) -> None:
        text = "Visit https://example.com now."
        result = prepare_for_speech(text)
        assert "https://example.com" not in result
        assert "Visit now" in result

    def test_emoji_dropped(self) -> None:
        text = "Hello 😀 world 🎉"
        result = prepare_for_speech(text)
        assert "😀" not in result
        assert "🎉" not in result
        assert "Hello world" in result

    def test_whitespace_collapsed(self) -> None:
        text = "Hello    world\n\n\nnew line"
        result = prepare_for_speech(text)
        assert result == "Hello world new line"


class TestSplitSentences:
    """Tests for split_sentences function."""

    def test_simple_split(self) -> None:
        text = "Hello world. How are you? I am fine."
        sentences = split_sentences(text)
        assert sentences == ["Hello world.", "How are you?", "I am fine."]

    def test_decimal_not_split(self) -> None:
        text = "The value is 3.5 and 1.23 is another."
        sentences = split_sentences(text)
        assert len(sentences) == 1
        assert "3.5" in sentences[0]
        assert "1.23" in sentences[0]

    def test_abbreviations_not_split(self) -> None:
        text = "Dr. Smith went to the U.S. last week. He saw Prof. Jones."
        sentences = split_sentences(text)
        # Should not split on Dr., U.S., Prof.
        assert len(sentences) == 2
        assert "Dr. Smith went to the U.S. last week." in sentences[0]
        assert "He saw Prof. Jones." in sentences[1]

    def test_ellipsis_not_split(self) -> None:
        text = "Wait... what? That's it."
        sentences = split_sentences(text)
        # Ellipsis should NOT cause a split; split should happen at the question mark
        assert len(sentences) == 2
        assert "Wait... what?" in sentences[0]
        assert "That's it." in sentences[1]

    def test_unicode_text(self) -> None:
        text = "こんにちは。元気ですか？"
        sentences = split_sentences(text)
        assert len(sentences) == 2

    def test_no_punctuation(self) -> None:
        text = "Hello world"
        sentences = split_sentences(text)
        assert sentences == ["Hello world"]

    def test_url_not_split(self) -> None:
        text = "Visit https://example.com. It is great."
        sentences = split_sentences(text)
        assert len(sentences) == 2

    def test_cap_on_sentence_boundary(self) -> None:
        text = (
            "Short. Medium length sentence. Very long sentence that exceeds "
            "the limit significantly."
        )
        sentences = split_sentences(text, max_chars=30)
        total_chars = sum(len(s) for s in sentences) + len(sentences) - 1
        assert total_chars <= 30
        # Should not cut mid-sentence
        for s in sentences:
            assert s.endswith(".") or s.endswith("?") or s.endswith("!")


class TestCapSentences:
    """Tests for cap_sentences function."""

    def test_basic_cap(self) -> None:
        sentences = [
            "Short.",
            "Medium length.",
            "Very long sentence that exceeds limit.",
        ]
        capped = cap_sentences(sentences, 30)
        total = sum(len(s) for s in capped) + len(capped) - 1
        assert total <= 30

    def test_empty_list(self) -> None:
        assert cap_sentences([], 100) == []

    def test_single_sentence_under_limit(self) -> None:
        assert cap_sentences(["Hello."], 100) == ["Hello."]

    def test_single_sentence_over_limit(self) -> None:
        # Single sentence over limit should still be included
        # (first sentence always included)
        long_sentence = "This is a very long sentence that exceeds the limit."
        result = cap_sentences([long_sentence], 10)
        assert result == [long_sentence]


class TestPrepareAndSplit:
    """Tests for the convenience function."""

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty after preparation"):
            prepare_and_split("")

    def test_code_block_removed_then_split(self) -> None:
        text = "Here is code:\n```python\nprint('hi')\n```\nDone."
        result = prepare_and_split(text, max_chars=100)
        # Code block is removed, but preceding text remains
        assert result == ["Here is code: Done."]

    def test_emoji_removed_then_split(self) -> None:
        text = "Hello 😀 world."
        result = prepare_and_split(text, max_chars=100)
        assert "😀" not in " ".join(result)
        assert "Hello world" in " ".join(result)
