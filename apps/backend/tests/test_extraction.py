import pytest

from ved_backend.extraction import (
    MARKDOWN,
    NO_TEXT_LAYER,
    PDF,
    PLAIN_TEXT,
    ExtractionError,
    UnsupportedDocumentError,
    decode_text,
    extract_pages,
    sniff_media_type,
)

PNG_HEAD = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01\x00"


def test_a_pdf_is_recognised_by_its_signature(make_pdf):
    assert sniff_media_type(make_pdf([["hi"]]), "lease.bin") == PDF


def test_a_pdf_extension_on_plain_text_is_treated_as_text():
    assert sniff_media_type(b"Just some notes", "lease.pdf") == PLAIN_TEXT


def test_markdown_comes_from_the_extension_once_the_bytes_are_text():
    assert sniff_media_type(b"# Notes\n\n- one", "notes.MD") == MARKDOWN


def test_binary_content_is_rejected_whatever_the_name():
    with pytest.raises(UnsupportedDocumentError):
        sniff_media_type(PNG_HEAD, "notes.txt")


def test_utf8_text_with_a_bom_is_decoded():
    assert decode_text("\ufeffcafé".encode()) == "café"


def test_non_utf8_text_falls_back_instead_of_failing():
    assert decode_text("café".encode("cp1252")) == "café"


def test_pdf_pages_keep_their_numbers(make_pdf, tmp_path):
    path = tmp_path / "lease"
    path.write_bytes(make_pdf([["cover page"], ["deposit is 50000"]]))

    pages = extract_pages(path, PDF)

    assert [page.number for page in pages] == [1, 2]
    assert "deposit is 50000" in pages[1].text


def test_a_pdf_without_a_text_layer_fails_with_a_clear_reason(make_pdf, tmp_path):
    path = tmp_path / "scan"
    path.write_bytes(make_pdf([[], []]))

    with pytest.raises(ExtractionError) as raised:
        extract_pages(path, PDF)

    assert str(raised.value) == NO_TEXT_LAYER
    assert "OCR" in NO_TEXT_LAYER


def test_a_corrupt_pdf_fails_instead_of_crashing(tmp_path):
    path = tmp_path / "broken"
    path.write_bytes(b"%PDF-1.7\nthis is not really a pdf")

    with pytest.raises(ExtractionError):
        extract_pages(path, PDF)


def test_text_is_one_page_without_a_number(tmp_path):
    path = tmp_path / "notes"
    path.write_bytes(b"line one\n\nline two")

    (page,) = extract_pages(path, PLAIN_TEXT)

    assert page.number is None
    assert page.text == "line one\n\nline two"


def test_an_empty_text_file_fails(tmp_path):
    path = tmp_path / "blank"
    path.write_bytes(b"  \n ")

    with pytest.raises(ExtractionError):
        extract_pages(path, PLAIN_TEXT)
