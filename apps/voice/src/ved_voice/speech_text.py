import re

FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
BARE_URL = re.compile(r"https?://\S+")
INLINE_CODE = re.compile(r"`([^`]*)`")
HTML_TAG = re.compile(r"<[^>]+>")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.MULTILINE)
BLOCKQUOTE = re.compile(r"^\s*>\s?", re.MULTILINE)
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.MULTILINE)
TABLE_OR_RULE_LINE = re.compile(r"^[\s:|-]*-[\s:|-]*$", re.MULTILINE)
EMPHASIS_UNDERSCORE = re.compile(r"(?<!\w)_+|_+(?!\w)")
MARKUP_SYMBOLS = re.compile(r"[*#`~^<>\[\]{}|\\]")
EMOJI = re.compile(
    "[\u2190-\u21ff\u2300-\u23ff\u2600-\u27bf\u2b00-\u2bff\U0001f000-\U0001faff\ufe0f\u200d\u20e3]"
)
SENTENCE_END = re.compile(r"(?<=[.!?\u0964])\s+")
SENTENCE_PUNCTUATION = (".", "!", "?", ":", ";")


def clean_for_speech(text: str) -> str:
    cleaned = FENCED_CODE.sub(" ", text)
    cleaned = IMAGE.sub(r"\1", cleaned)
    cleaned = LINK.sub(r"\1", cleaned)
    cleaned = BARE_URL.sub(" ", cleaned)
    cleaned = INLINE_CODE.sub(r"\1", cleaned)
    cleaned = HTML_TAG.sub(" ", cleaned)
    cleaned = HEADING.sub("", cleaned)
    cleaned = BLOCKQUOTE.sub("", cleaned)
    cleaned = LIST_MARKER.sub("", cleaned)
    cleaned = TABLE_OR_RULE_LINE.sub("", cleaned)
    cleaned = EMOJI.sub(" ", cleaned)
    cleaned = MARKUP_SYMBOLS.sub(" ", cleaned)
    cleaned = EMPHASIS_UNDERSCORE.sub("", cleaned)
    spoken_lines = [" ".join(line.split()) for line in cleaned.splitlines()]
    return " ".join(with_final_punctuation(line) for line in spoken_lines if line)


def with_final_punctuation(line: str) -> str:
    return line if line.endswith(SENTENCE_PUNCTUATION) else f"{line}."


def split_sentences(text: str) -> list[str]:
    return [
        sentence
        for sentence in SENTENCE_END.split(text.strip())
        if any(character.isalnum() for character in sentence)
    ]
