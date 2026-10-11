import logging
from pathlib import Path
from typing import Literal

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from ved_backend.chunking import Page

logger = logging.getLogger(__name__)

MediaType = Literal["application/pdf", "text/plain", "text/markdown"]
PDF = "application/pdf"
PLAIN_TEXT = "text/plain"
MARKDOWN = "text/markdown"

PDF_SIGNATURE = b"%PDF-"
PDF_SIGNATURE_WINDOW = 1024
MARKDOWN_EXTENSIONS = (".md", ".markdown")
TEXT_FALLBACK_ENCODING = "cp1252"
UTF8_BOM = b"\xef\xbb\xbf"
BINARY_CONTROL_BYTES = frozenset(range(0x00, 0x09)) | frozenset(range(0x0E, 0x20))
MAX_BINARY_CONTROL_RATIO = 0.01

NO_TEXT_LAYER = (
    "This PDF has no text layer, so it is probably a scan. Ved cannot read "
    "scanned documents yet (OCR is not supported)."
)
EMPTY_DOCUMENT = "This document contains no readable text."
UNREADABLE_PDF = "This PDF could not be read: {detail}"
UNSUPPORTED_TYPE = "Only PDF, plain text and markdown files are supported."


class ExtractionError(ValueError):
    pass


class UnsupportedDocumentError(ValueError):
    def __init__(self) -> None:
        super().__init__(UNSUPPORTED_TYPE)


def looks_like_pdf(head: bytes) -> bool:
    return PDF_SIGNATURE in head[:PDF_SIGNATURE_WINDOW]


def looks_like_text(head: bytes) -> bool:
    if not head:
        return True
    control_bytes = sum(byte in BINARY_CONTROL_BYTES for byte in head)
    return control_bytes / len(head) <= MAX_BINARY_CONTROL_RATIO


def sniff_media_type(head: bytes, filename: str) -> MediaType:
    if looks_like_pdf(head):
        return PDF
    if looks_like_text(head):
        return (
            MARKDOWN if filename.lower().endswith(MARKDOWN_EXTENSIONS) else PLAIN_TEXT
        )
    raise UnsupportedDocumentError()


def decode_text(data: bytes) -> str:
    try:
        return data.removeprefix(UTF8_BOM).decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(TEXT_FALLBACK_ENCODING, errors="replace")


def read_pdf_pages(path: Path) -> list[Page]:
    try:
        reader = PdfReader(path)
        return [
            Page(text=page.extract_text() or "", number=number)
            for number, page in enumerate(reader.pages, start=1)
        ]
    except (PdfReadError, ValueError, KeyError, TypeError) as error:
        raise ExtractionError(UNREADABLE_PDF.format(detail=error)) from error


def extract_pages(path: Path, media_type: str) -> list[Page]:
    if media_type == PDF:
        pages = read_pdf_pages(path)
        if not any(page.text.strip() for page in pages):
            raise ExtractionError(NO_TEXT_LAYER)
        return pages
    text = decode_text(path.read_bytes())
    if not text.strip():
        raise ExtractionError(EMPTY_DOCUMENT)
    return [Page(text=text)]
