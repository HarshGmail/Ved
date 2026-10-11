import io

import pytest

from upload_bodies import CONTENT_TYPE, CountingBody, multipart_body
from ved_backend.uploads import (
    SNIFF_BYTES,
    MalformedUploadError,
    UploadTooLargeError,
    display_filename,
    receive_file,
)


async def test_the_file_is_written_hashed_and_measured():
    destination = io.BytesIO()
    content = b"the deposit is fifty thousand"

    received = await receive_file(
        CountingBody(multipart_body(content)),
        CONTENT_TYPE,
        destination,
        max_bytes=1000,
    )

    assert destination.getvalue() == content
    assert received.size_bytes == len(content)
    assert received.filename == "notes.txt"
    assert len(received.sha256) == 64
    assert received.head == content


async def test_the_size_cap_stops_reading_part_way():
    body = CountingBody(multipart_body(b"x" * 50_000))

    with pytest.raises(UploadTooLargeError):
        await receive_file(body, CONTENT_TYPE, io.BytesIO(), max_bytes=5_000)

    assert body.pieces_sent < body.total_pieces / 2


async def test_only_the_first_bytes_are_kept_for_sniffing():
    received = await receive_file(
        CountingBody(multipart_body(b"a" * (SNIFF_BYTES * 3))),
        CONTENT_TYPE,
        io.BytesIO(),
        max_bytes=SNIFF_BYTES * 4,
    )

    assert len(received.head) == SNIFF_BYTES


async def test_an_upload_without_a_file_field_is_rejected():
    with pytest.raises(MalformedUploadError):
        await receive_file(
            CountingBody(multipart_body(b"hi", field="other")),
            CONTENT_TYPE,
            io.BytesIO(),
            max_bytes=1000,
        )


async def test_an_empty_file_is_rejected():
    with pytest.raises(MalformedUploadError, match="empty"):
        await receive_file(
            CountingBody(multipart_body(b"")), CONTENT_TYPE, io.BytesIO(), max_bytes=10
        )


async def test_a_non_multipart_body_is_rejected():
    with pytest.raises(MalformedUploadError):
        await receive_file(
            CountingBody(b"raw"), "application/pdf", io.BytesIO(), max_bytes=10
        )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"../../etc/passwd", "passwd"),
        (b"C:\\Users\\me\\lease.pdf", "lease.pdf"),
        (b"lease\x00.pdf", "lease.pdf"),
        (b"..", "untitled"),
        (b"", "untitled"),
    ],
)
def test_display_names_lose_any_path(raw, expected):
    assert display_filename(raw) == expected
