import hashlib
import re
from collections.abc import AsyncIterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO

from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header

FILE_FIELD = b"file"
MULTIPART_FORM_DATA = b"multipart/form-data"
SNIFF_BYTES = 8192
KIBIBYTE = 1024
MEBIBYTE = 1024 * KIBIBYTE
MULTIPART_OVERHEAD_BYTES = 64 * KIBIBYTE
MAX_FILENAME_CHARS = 255
UNNAMED_FILE = "untitled"
PATH_ONLY_NAMES = frozenset({".", ".."})
UNSAFE_FILENAME_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


class UploadRejectedError(ValueError):
    pass


class UploadTooLargeError(UploadRejectedError):
    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            f"The file is larger than the {max_bytes / MEBIBYTE:g} MB limit."
        )
        self.max_bytes = max_bytes


class MalformedUploadError(UploadRejectedError):
    pass


@dataclass(frozen=True)
class ReceivedFile:
    filename: str
    sha256: str
    size_bytes: int
    head: bytes


def display_filename(raw: bytes) -> str:
    decoded = raw.decode("utf-8", errors="replace").replace("\\", "/")
    name = UNSAFE_FILENAME_CHARACTERS.sub("", PurePosixPath(decoded).name).strip()
    if name in PATH_ONLY_NAMES:
        return UNNAMED_FILE
    return name[:MAX_FILENAME_CHARS] or UNNAMED_FILE


def multipart_boundary(content_type: str | None) -> bytes:
    media_type, options = parse_options_header(content_type)
    boundary = options.get(b"boundary")
    if media_type != MULTIPART_FORM_DATA or not boundary:
        raise MalformedUploadError("Send the file as multipart/form-data.")
    return boundary


class FilePartWriter:
    def __init__(self, destination: BinaryIO, max_bytes: int) -> None:
        self._destination = destination
        self._max_bytes = max_bytes
        self._digest = hashlib.sha256()
        self._head = bytearray()
        self._header_field = bytearray()
        self._header_value = bytearray()
        self._part_headers: dict[bytes, bytes] = {}
        self._writing = False
        self.filename: str | None = None
        self.size_bytes = 0

    def callbacks(self) -> dict:
        return {
            "on_part_begin": self._on_part_begin,
            "on_header_field": self._on_header_field,
            "on_header_value": self._on_header_value,
            "on_header_end": self._on_header_end,
            "on_headers_finished": self._on_headers_finished,
            "on_part_data": self._on_part_data,
            "on_part_end": self._on_part_end,
        }

    def received(self) -> ReceivedFile:
        if self.filename is None:
            raise MalformedUploadError(
                "Attach the document in a form field named 'file'."
            )
        if self.size_bytes == 0:
            raise MalformedUploadError("The file is empty.")
        return ReceivedFile(
            filename=self.filename,
            sha256=self._digest.hexdigest(),
            size_bytes=self.size_bytes,
            head=bytes(self._head),
        )

    def _on_part_begin(self) -> None:
        self._part_headers = {}

    def _on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_field += data[start:end]

    def _on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def _on_header_end(self) -> None:
        self._part_headers[bytes(self._header_field).lower()] = bytes(
            self._header_value
        )
        self._header_field.clear()
        self._header_value.clear()

    def _on_headers_finished(self) -> None:
        _, options = parse_options_header(
            self._part_headers.get(b"content-disposition")
        )
        is_first_file = (
            self.filename is None
            and options.get(b"name") == FILE_FIELD
            and b"filename" in options
        )
        if is_first_file:
            self.filename = display_filename(options[b"filename"])
            self._writing = True

    def _on_part_data(self, data: bytes, start: int, end: int) -> None:
        if not self._writing:
            return
        piece = data[start:end]
        self.size_bytes += len(piece)
        if self.size_bytes > self._max_bytes:
            raise UploadTooLargeError(self._max_bytes)
        self._digest.update(piece)
        if len(self._head) < SNIFF_BYTES:
            self._head += piece[: SNIFF_BYTES - len(self._head)]
        self._destination.write(piece)

    def _on_part_end(self) -> None:
        self._writing = False


async def receive_file(
    body: AsyncIterable[bytes],
    content_type: str | None,
    destination: BinaryIO,
    *,
    max_bytes: int,
) -> ReceivedFile:
    writer = FilePartWriter(destination, max_bytes)
    parser = MultipartParser(multipart_boundary(content_type), writer.callbacks())
    body_limit = max_bytes + MULTIPART_OVERHEAD_BYTES
    streamed = 0
    try:
        async for piece in body:
            streamed += len(piece)
            if streamed > body_limit:
                raise UploadTooLargeError(max_bytes)
            parser.write(piece)
        parser.finalize()
    except MultipartParseError as error:
        raise MalformedUploadError(
            f"The upload could not be parsed: {error}"
        ) from error
    return writer.received()
