BOUNDARY = "ved-test-boundary"
CONTENT_TYPE = f"multipart/form-data; boundary={BOUNDARY}"
PIECE_BYTES = 1024


def multipart_body(
    content: bytes, filename: str = "notes.txt", field: str = "file"
) -> bytes:
    return (
        (
            f"--{BOUNDARY}\r\n"
            f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        + content
        + f"\r\n--{BOUNDARY}--\r\n".encode()
    )


class CountingBody:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.pieces_sent = 0

    async def __aiter__(self):
        for start in range(0, len(self._body), PIECE_BYTES):
            self.pieces_sent += 1
            yield self._body[start : start + PIECE_BYTES]

    @property
    def total_pieces(self) -> int:
        return -(-len(self._body) // PIECE_BYTES)
