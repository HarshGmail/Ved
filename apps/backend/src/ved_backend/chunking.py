import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

MAX_CHUNK_CHARS = 1200
TARGET_CHUNK_CHARS = 800
CHUNK_OVERLAP_CHARS = 150
PARAGRAPH_SEPARATOR = "\n\n"

PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
WHITESPACE_RUN = re.compile(r"\s+")


@dataclass(frozen=True)
class Page:
    text: str
    number: int | None = None


@dataclass(frozen=True)
class Chunk:
    ordinal: int
    text: str
    page_number: int | None


def paragraphs(text: str) -> list[str]:
    cleaned = (
        WHITESPACE_RUN.sub(" ", part).strip() for part in PARAGRAPH_BREAK.split(text)
    )
    return [paragraph for paragraph in cleaned if paragraph]


def overlap_tail(text: str, overlap: int = CHUNK_OVERLAP_CHARS) -> str:
    if len(text) <= overlap:
        return text
    tail = text[-overlap:]
    if text[-overlap - 1].isspace():
        return tail.strip()
    first_break = tail.find(" ")
    return "" if first_break == -1 else tail[first_break:].strip()


def last_word_boundary(text: str, limit: int) -> int:
    if len(text) <= limit:
        return len(text)
    if text[limit].isspace():
        return limit
    boundary = text.rfind(" ", 0, limit)
    return limit if boundary <= 0 else boundary


def split_long_paragraph(paragraph: str) -> Iterator[str]:
    remaining = paragraph
    while len(remaining) > MAX_CHUNK_CHARS:
        cut = last_word_boundary(remaining, MAX_CHUNK_CHARS)
        piece = remaining[:cut].strip()
        yield piece
        overlap = overlap_tail(piece)
        rest = remaining[cut:].strip()
        remaining = f"{overlap} {rest}" if overlap else rest
    if remaining:
        yield remaining


def joined(first: str, second: str) -> str:
    return f"{first}{PARAGRAPH_SEPARATOR}{second}" if first else second


def chunk_page(text: str) -> Iterator[str]:
    current = ""
    for paragraph in paragraphs(text):
        candidate = joined(current, paragraph)
        chunk_is_full = len(current) >= TARGET_CHUNK_CHARS
        if not chunk_is_full and len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            yield current
            current = joined(overlap_tail(current), paragraph)
        else:
            current = paragraph
        if len(current) > MAX_CHUNK_CHARS:
            *complete, current = split_long_paragraph(current)
            yield from complete
    if current:
        yield current


def chunk_pages(pages: Iterable[Page]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page in pages:
        for text in chunk_page(page.text):
            chunks.append(
                Chunk(ordinal=len(chunks), text=text, page_number=page.number)
            )
    return chunks
