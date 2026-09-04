"""
URL safety checks for outbound HTTP requests.

Blocks schemes, hosts, and addresses that must not be fetched by the pipeline
(e.g. private networks, loopback, link-local/metadata endpoints).

Hostname checks include DNS resolution: every address returned by the resolver
must be public. Callers should re-run these checks for each redirect hop.

Residual risk: DNS rebinding / TOCTOU between resolution and the TCP connect
is not eliminated without pinning the peer address for the whole exchange.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
    }
)

HostnameResolver = Callable[[str], list[ipaddress.IPv4Address | ipaddress.IPv6Address]]


def resolve_hostname_ips(
    hostname: str,
) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """Resolve a hostname to unique IP addresses (IPv4 and IPv6)."""
    try:
        results = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise OSError(f"DNS resolution failed for {hostname!r}") from exc

    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
    for result in results:
        sockaddr = result[4]
        ip = ipaddress.ip_address(sockaddr[0])
        if ip not in seen:
            seen.add(ip)
            ips.append(ip)
    return ips


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def url_safety_error(
    url: str,
    *,
    resolve: HostnameResolver | None = None,
) -> str | None:
    """
    Return an error message when a URL must not be fetched, otherwise None.

    When ``resolve`` is omitted, ``resolve_hostname_ips`` is used for non-IP
    hostnames. Every resolved address must be public.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return "URL is malformed."

    if parsed.scheme not in ("http", "https"):
        return "URL must use http or https."

    hostname = parsed.hostname
    if not hostname:
        return "URL must include a hostname."

    if parsed.username or parsed.password:
        return "URL must not include embedded credentials."

    normalized_host = hostname.lower().rstrip(".")
    if normalized_host in _BLOCKED_HOSTNAMES or normalized_host.endswith(".localhost"):
        return "URL hostname is not allowed."

    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None

    if literal_ip is not None:
        if _is_blocked_ip(literal_ip):
            return "URL resolves to a non-public address."
        return None

    resolver = resolve or resolve_hostname_ips
    try:
        resolved = resolver(normalized_host)
    except OSError:
        return "URL hostname could not be resolved."

    if not resolved:
        return "URL hostname could not be resolved."

    if any(_is_blocked_ip(ip) for ip in resolved):
        return "URL resolves to a non-public address."

    return None


def is_safe_fetch_url(
    url: str,
    *,
    resolve: HostnameResolver | None = None,
) -> bool:
    """Return True when the URL is allowed for outbound HTTP requests."""
    return url_safety_error(url, resolve=resolve) is None
