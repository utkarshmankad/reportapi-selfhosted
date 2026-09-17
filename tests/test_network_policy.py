"""Exercise the real HTTP transport down to the numeric dial and TLS boundary."""

import ipaddress
import socket
from unittest.mock import AsyncMock

import httpcore
import pytest

from app.config import settings
from app.core import ssrf_guard as guard


@pytest.fixture
def public_dns(monkeypatch):
    def resolver(host):
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(guard, "_resolve_ips", resolver)


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "https://user:secret@example.com", "http://example.com:bad", "https://"],
)
def test_rejects_invalid_and_credentialed_origins(url):
    with pytest.raises(guard.UnsafeURLError):
        guard.origin(url)


@pytest.mark.parametrize(
    "url", ["https://example.com.evil.test", "http://example.com", "https://example.com:8443"]
)
def test_allowlist_matches_whole_origin(url):
    with pytest.raises(guard.UnsafeURLError):
        guard.safe_client(url, "jira")


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "169.254.169.254",
        "0.0.0.0",
        "::",
        "::1",
        "::ffff:127.0.0.1",
        "fe80::1",
        "224.0.0.1",
    ],
)
@pytest.mark.asyncio
async def test_blocked_addresses_cannot_be_allowed_by_operator(monkeypatch, address):
    monkeypatch.setattr(guard, "_resolve_ips", lambda host: [ipaddress.ip_address(address)])
    with pytest.raises(guard.UnsafeURLError):
        await guard.validate_target("http://ollama:11434", "ollama")


@pytest.mark.asyncio
async def test_private_network_requires_exact_operator_permission(monkeypatch):
    monkeypatch.setattr(guard, "_resolve_ips", lambda host: [ipaddress.ip_address("10.0.0.8")])
    await guard.validate_target("http://ollama:11434", "ollama")
    with pytest.raises(guard.UnsafeURLError):
        await guard.validate_target("https://example.com", "jira")
    monkeypatch.setattr(settings, "outbound_private_origins", "https://example.com")
    await guard.validate_target("https://example.com", "jira")


@pytest.mark.asyncio
async def test_dns_rebinding_is_checked_again_at_connect(monkeypatch, public_dns):
    await guard.validate_target("https://example.com", "jira")
    dial = AsyncMock()
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", dial)
    monkeypatch.setattr(guard, "_resolve_ips", lambda host: [ipaddress.ip_address("127.0.0.1")])
    async with guard.safe_client("https://example.com", "jira") as client:
        with pytest.raises(guard.UnsafeURLError):
            await client.get("https://example.com/rest/api/3/myself")
    dial.assert_not_awaited()


@pytest.mark.asyncio
async def test_mixed_public_private_dns_fails_closed(monkeypatch):
    monkeypatch.setattr(
        guard,
        "_resolve_ips",
        lambda host: [ipaddress.ip_address("93.184.216.34"), ipaddress.ip_address("10.0.0.1")],
    )
    with pytest.raises(guard.UnsafeURLError):
        await guard.validate_target("https://example.com", "jira")


@pytest.mark.asyncio
async def test_numeric_dial_retains_host_and_tls_sni(monkeypatch, public_dns):
    stream = httpcore.AsyncMockStream([b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}"])
    stream.write = AsyncMock()
    stream.start_tls = AsyncMock(return_value=stream)
    dial = AsyncMock(return_value=stream)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", dial)
    # Environment proxies must not create a second, unvalidated resolution path.
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    async with guard.safe_client("https://example.com", "jira") as client:
        response = await client.get("https://example.com/test")
    assert response.json() == {}
    assert dial.call_args.args[:2] == ("93.184.216.34", 443)
    assert stream.start_tls.call_args.kwargs["server_hostname"] == "example.com"
    assert stream.start_tls.call_args.kwargs["ssl_context"].check_hostname
    wire = b"".join(call.args[0] for call in stream.write.call_args_list)
    assert b"Host: example.com" in wire


@pytest.mark.asyncio
async def test_redirects_never_forward_credentials(monkeypatch, public_dns):
    stream = httpcore.AsyncMockStream(
        [b"HTTP/1.1 302 Found\r\nLocation: http://169.254.169.254/\r\nContent-Length: 0\r\n\r\n"]
    )
    dial = AsyncMock(return_value=stream)
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", dial)
    async with guard.safe_client("https://example.com", "jira", auth=("user", "secret")) as client:
        with pytest.raises(guard.UnsafeURLError, match="redirects"):
            await client.get("https://example.com/test")
    dial.assert_awaited_once()


@pytest.mark.asyncio
async def test_other_origin_is_rejected_before_connect():
    async with guard.safe_client("https://example.com", "jira") as client:
        with pytest.raises(guard.UnsafeURLError, match="changed"):
            await client.get("https://test.atlassian.net/test")


@pytest.mark.asyncio
async def test_response_size_is_bounded(monkeypatch, public_dns):
    oversized = b"x" * (10 * 1024 * 1024 + 1)
    stream = httpcore.AsyncMockStream(
        [f"HTTP/1.1 200 OK\r\nContent-Length: {len(oversized)}\r\n\r\n".encode(), oversized]
    )
    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", AsyncMock(return_value=stream))
    async with guard.safe_client("https://example.com", "jira") as client:
        with pytest.raises(guard.UnsafeURLError, match="10 MiB"):
            await client.get("https://example.com/test")


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["?token=x", "#fragment"])
async def test_base_url_rejects_query_and_fragment(suffix):
    with pytest.raises(guard.UnsafeURLError):
        await guard.validate_target("https://example.com" + suffix, "jira")


def test_resolution_errors_are_safe(monkeypatch):
    def fail(*args, **kwargs):
        raise socket.gaierror("sensitive internal details")

    monkeypatch.setattr(socket, "getaddrinfo", fail)
    with pytest.raises(guard.UnsafeURLError, match="^Could not resolve target host$"):
        guard._resolve_ips("example.com")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
    with pytest.raises(guard.UnsafeURLError, match="Could not resolve target host"):
        guard._resolve_ips("example.com")
