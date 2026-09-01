"""
URL safety checks for outbound HTTP requests.

Blocks schemes, hosts, and addresses that must not be fetched by the pipeline
(e.g. private networks, loopback, link-local/metadata endpoints).
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "metadata.google.internal",
    }
)


def url_safety_error(url: str) -> str | None:
    """
    Return an error message when a URL must not be fetched, otherwise None.
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
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return None

    if _is_blocked_ip(ip):
        return "URL resolves to a non-public address."

    return None


def is_safe_fetch_url(url: str) -> bool:
    """Return True when the URL is allowed for outbound HTTP requests."""
    return url_safety_error(url) is None


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )
