import ipaddress

import httpcore2
import pytest

from ved_web.fetch import FetchRefusedError, PageFetcher
from ved_web.guard import (
    BlockedAddressError,
    PublicOnlyTransport,
    is_public_address,
    public_addresses,
)

PUBLIC_IP = "93.184.215.14"
PRIVATE_IP = "10.0.0.5"


class FakeResolver:
    def __init__(self, table: dict[str, list[str]]) -> None:
        self.table = table
        self.asked: list[str] = []

    async def __call__(self, host: str, port: int) -> list[str]:
        self.asked.append(host)
        return self.table.get(host, [])


class RecordingBackend(httpcore2.AsyncNetworkBackend):
    def __init__(self, replies: dict[str, bytes]) -> None:
        self.replies = replies
        self.connected: list[str] = []

    async def connect_tcp(
        self, host, port, timeout=None, local_address=None, socket_options=None
    ):
        self.connected.append(host)
        return httpcore2.AsyncMockStream([self.replies[host]])


def http_reply(status: str, headers: dict[str, str], body: bytes = b"") -> bytes:
    lines = [f"HTTP/1.1 {status}", f"Content-Length: {len(body)}"]
    lines += [f"{name}: {value}" for name, value in headers.items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode() + body


def guarded_fetcher(resolver: FakeResolver, backend: RecordingBackend) -> PageFetcher:
    return PageFetcher(
        timeout_seconds=5,
        max_bytes=100_000,
        max_characters=5_000,
        max_redirects=3,
        user_agent="test",
        transport=PublicOnlyTransport(resolver, backend),
    )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.10",
        "169.254.169.254",
        "100.100.100.100",
        "0.0.0.0",
        "224.0.0.251",
        "::1",
        "::",
        "fe80::1",
        "fd00::1",
        "::ffff:127.0.0.1",
        "64:ff9b::a00:5",
    ],
)
def test_internal_addresses_are_not_public(address):
    assert not is_public_address(ipaddress.ip_address(address))


@pytest.mark.parametrize("address", ["93.184.215.14", "2606:4700::1111"])
def test_internet_addresses_are_public(address):
    assert is_public_address(ipaddress.ip_address(address))


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "[::1]", "169.254.169.254", "192.168.0.1"]
)
async def test_ip_literals_are_checked_without_dns(host):
    resolver = FakeResolver({})

    with pytest.raises(BlockedAddressError, match="private, loopback or link-local"):
        await public_addresses(host, 80, resolver)
    assert resolver.asked == []


async def test_a_public_looking_name_that_resolves_private_is_blocked():
    resolver = FakeResolver({"intranet.example.com": [PRIVATE_IP]})

    with pytest.raises(BlockedAddressError, match="resolves to 10.0.0.5"):
        await public_addresses("intranet.example.com", 443, resolver)


async def test_one_private_address_among_public_ones_blocks_the_host():
    resolver = FakeResolver({"mixed.example.com": [PUBLIC_IP, "127.0.0.1"]})

    with pytest.raises(BlockedAddressError):
        await public_addresses("mixed.example.com", 80, resolver)


async def test_a_name_that_resolves_nowhere_is_a_connect_error():
    with pytest.raises(httpcore2.ConnectError, match="did not resolve"):
        await public_addresses("nothing.example.com", 80, FakeResolver({}))


async def test_the_connection_goes_to_the_checked_address_not_a_fresh_lookup():
    resolver = FakeResolver({"news.example.com": [PUBLIC_IP]})
    page = http_reply("200 OK", {"Content-Type": "text/plain"}, b"hello")
    backend = RecordingBackend({PUBLIC_IP: page})

    fetched = await guarded_fetcher(resolver, backend).fetch("http://news.example.com/")

    assert fetched.text == "hello"
    assert backend.connected == [PUBLIC_IP]


async def test_loopback_is_refused_before_any_connection():
    backend = RecordingBackend({})

    with pytest.raises(FetchRefusedError, match="private, loopback"):
        await guarded_fetcher(FakeResolver({}), backend).fetch("http://127.0.0.1:5432/")
    assert backend.connected == []


async def test_ipv6_loopback_is_refused():
    with pytest.raises(FetchRefusedError, match="private, loopback"):
        await guarded_fetcher(FakeResolver({}), RecordingBackend({})).fetch(
            "http://[::1]:8000/health"
        )


async def test_a_redirect_to_a_private_address_is_refused_on_that_hop():
    resolver = FakeResolver(
        {"news.example.com": [PUBLIC_IP], "metadata.example.com": ["169.254.169.254"]}
    )
    redirect = http_reply(
        "302 Found", {"Location": "http://metadata.example.com/latest/meta-data/"}
    )
    backend = RecordingBackend({PUBLIC_IP: redirect})

    with pytest.raises(FetchRefusedError, match="169.254.169.254"):
        await guarded_fetcher(resolver, backend).fetch("http://news.example.com/")
    assert backend.connected == [PUBLIC_IP]
    assert resolver.asked == ["news.example.com", "metadata.example.com"]


async def test_unix_sockets_are_never_opened():
    transport = PublicOnlyTransport(FakeResolver({}), RecordingBackend({}))
    backend = transport._pool._network_backend

    with pytest.raises(BlockedAddressError):
        await backend.connect_unix_socket("/var/run/docker.sock")
