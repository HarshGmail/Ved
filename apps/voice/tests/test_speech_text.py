import pytest

from ved_voice.speech_text import clean_for_speech, split_sentences


@pytest.mark.parametrize(
    ("markup", "spoken"),
    [
        ("**Bold** and *italic* text.", "Bold and italic text."),
        ("Use `pip install` now.", "Use pip install now."),
        ("See [the docs](https://example.com/docs) today.", "See the docs today."),
        ("Visit https://example.com for more.", "Visit for more."),
        ("![chart](https://example.com/c.png)", "chart."),
        ("# Title\nBody text", "Title. Body text."),
        ("- first\n- second", "first. second."),
        ("1. step one\n2. step two", "step one. step two."),
        ("> quoted words", "quoted words."),
        ("Before\n```python\nprint('x')\n```\nAfter", "Before. After."),
        ("| a | b |\n|---|---|\n| 1 | 2 |", "a b. 1 2."),
        ("Ready 🎉 now ✅", "Ready now."),
        ("Call bm_george now", "Call bm_george now."),
        ("__strong__ words", "strong words."),
        ("<b>tags</b> go", "tags go."),
    ],
)
def test_markup_is_removed_for_speech(markup: str, spoken: str) -> None:
    assert clean_for_speech(markup) == spoken


def test_only_markup_leaves_nothing_to_say() -> None:
    assert clean_for_speech("```\nprint()\n```\n---") == ""


def test_sentences_split_after_terminal_punctuation() -> None:
    assert split_sentences("First one. Second one! Third? Fourth.") == [
        "First one.",
        "Second one!",
        "Third?",
        "Fourth.",
    ]


def test_devanagari_danda_ends_a_sentence() -> None:
    assert split_sentences("नमस्ते। आप कैसे हैं।") == ["नमस्ते।", "आप कैसे हैं।"]


def test_punctuation_only_fragments_are_dropped() -> None:
    assert split_sentences("Hello there. ... Bye.") == ["Hello there.", "Bye."]


def test_empty_text_has_no_sentences() -> None:
    assert split_sentences("   ") == []
