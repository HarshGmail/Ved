from dataclasses import dataclass

import lxml.html
from lxml.etree import ParserError
from readability import Document
from readability.readability import Unparseable

BLOCK_TAGS = (
    "blockquote",
    "dd",
    "dt",
    "figcaption",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "p",
    "pre",
    "td",
    "th",
)
MINIMUM_ARTICLE_CHARACTERS = 200


@dataclass(frozen=True)
class ReadableText:
    title: str
    text: str


def block_text(html: str) -> str:
    try:
        tree = lxml.html.fromstring(html)
    except (ParserError, ValueError):
        return ""
    for unwanted in tree.iter("script", "style", "noscript", "template"):
        unwanted.drop_tree()

    blocks: list[str] = []
    for element in tree.iter(*BLOCK_TAGS):
        nested_in_block = any(
            ancestor.tag in BLOCK_TAGS for ancestor in element.iterancestors()
        )
        if nested_in_block:
            continue
        text = " ".join(element.text_content().split())
        if text:
            blocks.append(text)
    if blocks:
        return "\n".join(blocks)
    return " ".join(tree.text_content().split())


def readable_text(html: str) -> ReadableText:
    try:
        document = Document(html)
        title = document.short_title().strip()
        article = block_text(document.summary(html_partial=True))
    except (Unparseable, ParserError, ValueError):
        title, article = "", ""

    if len(article) >= MINIMUM_ARTICLE_CHARACTERS:
        return ReadableText(title=title, text=article)
    whole_page = block_text(html)
    return ReadableText(title=title, text=max(article, whole_page, key=len))


def plain_text(text: str) -> ReadableText:
    lines = (" ".join(line.split()) for line in text.splitlines())
    return ReadableText(title="", text="\n".join(line for line in lines if line))


def truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip(), True
