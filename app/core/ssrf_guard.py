"""Guards against SSRF when the config UI's "test connection" endpoints
make outbound requests to a user-supplied URL (Jira URL, Ollama base URL).
"""

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(Exception):
    pass


def _resolve_ips(hostname: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise UnsafeURLError(f"Could not resolve host '{hostname}': {e}")
    return [ipaddress.ip_address(info[4][0]) for info in infos]


def assert_safe_url(url: str, *, allow_private: bool = False) -> None:
    """
    Raise UnsafeURLError unless the URL is http(s), resolves to a
    routable address, and (unless allow_private) isn't loopback/link-local/
    private/reserved. Cloud metadata endpoints are always blocked.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("URL must use http or https")

    if not parsed.hostname:
        raise UnsafeURLError("URL must include a hostname")

    for ip in _resolve_ips(parsed.hostname):
        if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            raise UnsafeURLError(f"Host resolves to a disallowed address ({ip})")
        # Cloud metadata endpoints (AWS/GCP/Azure) — never allowed, even
        # when allow_private is set for internal-network targets like Ollama.
        if str(ip) == "169.254.169.254":
            raise UnsafeURLError("Host resolves to a cloud metadata address")
        if not allow_private and (ip.is_private or ip.is_unspecified):
            raise UnsafeURLError(f"Host resolves to a private address ({ip})")
