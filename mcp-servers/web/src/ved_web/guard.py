import ipaddress
import socket
import typing
from collections.abc import Awaitable, Callable

import anyio
import httpcore2
import httpx2

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Awaitable[list[str]]]

NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")


class BlockedAddressError(ValueError):
    pass


async def resolve_host(host: str, port: int) -> list[str]:
    try:
        entries = await anyio.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as error:
        raise httpcore2.ConnectError(f"Could not resolve {host}: {error}") from error
    return list(dict.fromkeys(str(entry[4][0]) for entry in entries))


def embedded_ipv4(address: IPAddress) -> ipaddress.IPv4Address | None:
    if not isinstance(address, ipaddress.IPv6Address):
        return None
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address in NAT64_PREFIX:
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return None


def is_public_address(address: IPAddress) -> bool:
    inner = embedded_ipv4(address)
    if inner is not None and not is_public_address(inner):
        return False
    return address.is_global and not address.is_multicast


def parse_ip_literal(host: str) -> IPAddress | None:
    try:
        return ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
    except ValueError:
        return None


async def public_addresses(host: str, port: int, resolver: Resolver) -> list[str]:
    literal = parse_ip_literal(host)
    candidates = [str(literal)] if literal is not None else await resolver(host, port)
    if not candidates:
        raise httpcore2.ConnectError(f"{host} did not resolve to any address")

    for candidate in candidates:
        address = parse_ip_literal(candidate)
        if address is None or not is_public_address(address):
            subject = host if literal is not None else f"{host} resolves to {candidate}"
            raise BlockedAddressError(
                f"{subject}: a private, loopback or link-local address. Only "
                f"public internet addresses can be read."
            )
    return candidates


class PublicOnlyNetworkBackend(httpcore2.AsyncNetworkBackend):
    def __init__(
        self,
        resolver: Resolver = resolve_host,
        inner: httpcore2.AsyncNetworkBackend | None = None,
    ) -> None:
        self._resolver = resolver
        self._inner = inner or httpcore2.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        addresses = await public_addresses(host, port, self._resolver)
        last_error: Exception | None = None
        for address in addresses:
            try:
                return await self._inner.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except httpcore2.ConnectError as error:
                last_error = error
        raise httpcore2.ConnectError(f"Could not connect to {host}") from last_error

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: typing.Iterable[httpcore2.SOCKET_OPTION] | None = None,
    ) -> httpcore2.AsyncNetworkStream:
        raise BlockedAddressError("Unix sockets are never reachable from web.fetch")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PublicOnlyTransport(httpx2.AsyncHTTPTransport):
    def __init__(
        self,
        resolver: Resolver = resolve_host,
        inner: httpcore2.AsyncNetworkBackend | None = None,
    ) -> None:
        super().__init__()
        self._pool = httpcore2.AsyncConnectionPool(
            ssl_context=httpx2.create_ssl_context(),
            network_backend=PublicOnlyNetworkBackend(resolver, inner),
        )
