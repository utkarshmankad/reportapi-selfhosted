"""Operator allowlists and DNS-pinned connections for configurable upstreams."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

import httpcore
import httpx

from app.config import settings


class UnsafeURLError(ValueError):
    pass


def origin(url: str) -> str:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        host = parsed.hostname.lower()
        if ":" in host:
            host = f"[{host}]"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return f"{parsed.scheme}://{host}:{port}"
    except ValueError:
        raise UnsafeURLError(
            "A valid HTTP(S) URL without embedded credentials is required"
        ) from None


def _origins(value: str) -> set[str]:
    return {origin(url.strip()) for url in value.split(",") if url.strip()}


def target_policy(url: str, service: str) -> bool:
    """Return private-network permission after matching an operator-defined origin."""
    allowed = getattr(settings, f"{service}_allowed_origins")
    target = origin(url)
    if target not in _origins(allowed):
        raise UnsafeURLError(f"Target is not in the operator's {service.upper()}_ALLOWED_ORIGINS")
    return target in _origins(settings.outbound_private_origins)


def _resolve_ips(hostname: str) -> list:
    try:
        addresses = list(
            dict.fromkeys(
                info[4][0] for info in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
            )
        )
        if not addresses:
            raise ValueError("Host has no usable addresses")
        return [ipaddress.ip_address(address) for address in addresses]
    except (socket.gaierror, ValueError):
        raise UnsafeURLError("Could not resolve target host") from None


def _check_ips(addresses, allow_private: bool):
    for address in addresses:
        # IPv4-mapped IPv6 must receive exactly the same checks as IPv4.
        ip = getattr(address, "ipv4_mapped", None) or address
        if (
            ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeURLError("Host resolves to a disallowed address")
        if not allow_private and not ip.is_global:
            raise UnsafeURLError("Host resolves to a private address")


def assert_safe_url(url: str, *, allow_private: bool = False) -> None:
    origin(url)
    _check_ips(_resolve_ips(urlsplit(url).hostname), allow_private)


async def validate_target(url: str, service: str):
    allow_private = target_policy(url, service)
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment:
        raise UnsafeURLError("Base URLs cannot contain a query or fragment")
    addresses = await asyncio.wait_for(asyncio.to_thread(_resolve_ips, parsed.hostname), 5)
    _check_ips(addresses, allow_private)


class PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, url: str, service: str):
        self.url = url
        self.service = service
        self.backend = httpcore.AnyIOBackend()

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        parsed = urlsplit(self.url)
        if host != parsed.hostname or port != (
            parsed.port or (443 if parsed.scheme == "https" else 80)
        ):
            raise UnsafeURLError("Connection target changed")
        allow_private = target_policy(self.url, self.service)
        addresses = await asyncio.wait_for(
            asyncio.to_thread(_resolve_ips, host), min(timeout or 5, 5)
        )
        _check_ips(addresses, allow_private)
        # Dial the checked numeric address. httpcore retains the original Host and TLS SNI.
        return await self.backend.connect_tcp(
            str(addresses[0]),
            port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )

    async def connect_unix_socket(self, *args, **kwargs):
        raise UnsafeURLError("Unix sockets are disabled")

    async def sleep(self, seconds):
        await asyncio.sleep(seconds)


class GuardedTransport(httpx.AsyncBaseTransport):
    def __init__(self, url: str, service: str):
        target_policy(url, service)
        self.origin = origin(url)
        self.pool = httpcore.AsyncConnectionPool(network_backend=PinnedBackend(url, service))

    async def handle_async_request(self, request):
        if origin(str(request.url)) != self.origin:
            raise UnsafeURLError("Request target changed")
        response = await self.pool.handle_async_request(
            httpcore.Request(
                method=request.method,
                url=httpcore.URL(
                    scheme=request.url.raw_scheme,
                    host=request.url.raw_host,
                    port=request.url.port,
                    target=request.url.raw_path,
                ),
                headers=request.headers.raw,
                content=request.stream,
                extensions=request.extensions,
            )
        )
        body = bytearray()
        try:
            if 300 <= response.status < 400:
                raise UnsafeURLError("Upstream redirects are disabled")
            async for chunk in response.aiter_stream():
                if len(body) + len(chunk) > 10 * 1024 * 1024:
                    raise UnsafeURLError("Upstream response exceeds 10 MiB")
                body.extend(chunk)
            return httpx.Response(
                response.status,
                headers=response.headers,
                content=bytes(body),
                extensions=response.extensions,
            )
        finally:
            await response.aclose()

    async def aclose(self):
        await self.pool.aclose()


def safe_client(url: str, service: str, **kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=GuardedTransport(url, service), trust_env=False, follow_redirects=False, **kwargs
    )
