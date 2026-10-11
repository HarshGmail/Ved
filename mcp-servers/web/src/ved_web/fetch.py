import codecs
from dataclasses import dataclass

import anyio
import httpx2
from pydantic import Field

from ved_web.extract import ReadableText, plain_text, readable_text, truncate
from ved_web.guard import BlockedAddressError, PublicOnlyTransport
from ved_web.trust import UntrustedWebContent

ALLOWED_SCHEMES = ("http", "https")
HTML_CONTENT_TYPES = ("text/html", "application/xhtml+xml")
PLAIN_CONTENT_TYPES = ("text/plain",)
ACCEPT_HEADER = "text/html,application/xhtml+xml,text/plain;q=0.8"
FALLBACK_ENCODING = "utf-8"


class FetchRefusedError(ValueError):
    pass


class FetchedPage(UntrustedWebContent):
    url: str = Field(description="Where the text came from, after redirects")
    title: str
    text: str = Field(description="Main readable text of the page")
    truncated: bool = Field(
        description="True when the page was longer than Ved reads and was cut"
    )


@dataclass(frozen=True)
class Body:
    content: bytes
    cut_short: bool


def checked_url(raw: str | httpx2.URL) -> httpx2.URL:
    try:
        url = httpx2.URL(raw)
    except httpx2.InvalidURL as error:
        raise FetchRefusedError(f"{str(raw)!r} is not a valid URL") from error
    if url.scheme not in ALLOWED_SCHEMES:
        raise FetchRefusedError(
            f"Only http and https pages can be read, got {str(raw)!r}"
        )
    if not url.host:
        raise FetchRefusedError(f"{str(raw)!r} has no host")
    return url


def media_type(response: httpx2.Response) -> str:
    return response.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def known_encoding(charset: str | None) -> str:
    if charset is None:
        return FALLBACK_ENCODING
    try:
        return codecs.lookup(charset).name
    except LookupError:
        return FALLBACK_ENCODING


def readable(media: str, body: str) -> ReadableText:
    if media in HTML_CONTENT_TYPES:
        return readable_text(body)
    return plain_text(body)


class PageFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float,
        max_bytes: int,
        max_characters: int,
        max_redirects: int,
        user_agent: str,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._max_characters = max_characters
        self._max_redirects = max_redirects
        self._client = httpx2.AsyncClient(
            transport=transport or PublicOnlyTransport(),
            timeout=timeout_seconds,
            follow_redirects=False,
            headers={"User-Agent": user_agent, "Accept": ACCEPT_HEADER},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, raw_url: str) -> FetchedPage:
        try:
            with anyio.fail_after(self._timeout_seconds):
                return await self._follow(checked_url(raw_url))
        except TimeoutError as error:
            raise FetchRefusedError(
                f"{raw_url} took longer than {self._timeout_seconds:g}s to load"
            ) from error
        except BlockedAddressError as error:
            raise FetchRefusedError(str(error)) from error
        except httpx2.HTTPError as error:
            raise FetchRefusedError(
                f"Could not load {raw_url}: {str(error) or type(error).__name__}"
            ) from error

    async def _follow(self, url: httpx2.URL) -> FetchedPage:
        for _ in range(self._max_redirects + 1):
            request = self._client.build_request("GET", url)
            response = await self._client.send(request, stream=True)
            try:
                if response.is_redirect and response.has_redirect_location:
                    url = checked_url(url.join(response.headers["location"]))
                    continue
                return await self._read(response)
            finally:
                await response.aclose()
        raise FetchRefusedError(
            f"Gave up after {self._max_redirects} redirects, last at {url}"
        )

    async def _read(self, response: httpx2.Response) -> FetchedPage:
        if response.status_code != httpx2.codes.OK:
            raise FetchRefusedError(
                f"{response.url} answered {response.status_code}, not a page"
            )
        media = media_type(response)
        if media not in HTML_CONTENT_TYPES + PLAIN_CONTENT_TYPES:
            raise FetchRefusedError(
                f"{response.url} is {media or 'an unknown type'}; only HTML and "
                f"plain text pages can be read"
            )

        body = await self._read_capped(response)
        encoding = known_encoding(response.charset_encoding)
        extracted = readable(media, body.content.decode(encoding, errors="replace"))
        text, text_cut = truncate(extracted.text, self._max_characters)
        return FetchedPage(
            url=str(response.url),
            title=extracted.title,
            text=text,
            truncated=text_cut or body.cut_short,
        )

    async def _read_capped(self, response: httpx2.Response) -> Body:
        received = bytearray()
        async for chunk in response.aiter_bytes():
            received.extend(chunk)
            if len(received) >= self._max_bytes:
                return Body(content=bytes(received[: self._max_bytes]), cut_short=True)
        return Body(content=bytes(received), cut_short=False)
