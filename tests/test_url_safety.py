"""
Tests for src/tools/url_safety.py.
"""

from __future__ import annotations

import ipaddress
from unittest.mock import patch

import pytest

from src.tools.url_safety import is_safe_fetch_url, resolve_hostname_ips, url_safety_error


def _public_v4(_: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("93.184.216.34")]


def _private_v4(_: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("10.0.0.5")]


def _mixed_public_private(_: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [
        ipaddress.ip_address("93.184.216.34"),
        ipaddress.ip_address("10.0.0.5"),
    ]


def _link_local_metadata(_: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("169.254.169.254")]


def _ipv6_ula(_: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("fd12:3456:789a:1::1")]


def _ipv6_loopback(_: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("::1")]


def _public_ipv6(_: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    return [ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946")]


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "https://example.com/article",
        "http://fiocondutor.com.pt/review",
        "https://www.magazine-hd.com/apps/wp/entroncamento-critica-filme-pedro-cabeleira-ana-vilaca/",
    ],
)
def test_allows_public_http_and_https_urls(url: str):
    assert is_safe_fetch_url(url, resolve=_public_v4) is True
    assert url_safety_error(url, resolve=_public_v4) is None


def test_allows_hostname_that_resolves_only_to_public_ipv6():
    url = "https://ipv6.example.com/path"
    assert is_safe_fetch_url(url, resolve=_public_ipv6) is True


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("file:///etc/passwd", "http or https"),
        ("javascript:alert(1)", "http or https"),
        ("ftp://example.com", "http or https"),
        ("not-a-valid-url", "http or https"),
        ("http:///missing-host", "hostname"),
        ("https://user:pass@example.com", "credentials"),
        ("http://localhost", "not allowed"),
        ("http://LOCALHOST", "not allowed"),
        ("http://app.localhost", "not allowed"),
        ("http://127.0.0.1", "non-public"),
        ("http://[::1]", "non-public"),
        ("http://10.0.0.1", "non-public"),
        ("http://192.168.0.10", "non-public"),
        ("http://172.16.5.4", "non-public"),
        ("http://169.254.169.254", "non-public"),
        ("https://0.0.0.0", "non-public"),
    ],
)
def test_blocks_unsafe_urls(url: str, reason: str):
    assert is_safe_fetch_url(url, resolve=_public_v4) is False
    error = url_safety_error(url, resolve=_public_v4)
    assert error is not None
    assert reason in error.lower()


def test_blocks_hostname_that_resolves_to_private_ipv4():
    error = url_safety_error("https://internal.example", resolve=_private_v4)
    assert error is not None
    assert "non-public" in error.lower()


def test_blocks_hostname_with_mixed_public_and_private_results():
    error = url_safety_error("https://dual.example", resolve=_mixed_public_private)
    assert error is not None
    assert "non-public" in error.lower()


def test_blocks_hostname_that_resolves_to_metadata_address():
    error = url_safety_error("https://metadata.example", resolve=_link_local_metadata)
    assert error is not None
    assert "non-public" in error.lower()


def test_blocks_hostname_that_resolves_to_private_ipv6():
    error = url_safety_error("https://ula.example", resolve=_ipv6_ula)
    assert error is not None
    assert "non-public" in error.lower()


def test_blocks_hostname_that_resolves_to_ipv6_loopback():
    error = url_safety_error("https://loop6.example", resolve=_ipv6_loopback)
    assert error is not None
    assert "non-public" in error.lower()


def test_blocks_when_dns_resolution_fails():
    def boom(_: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        raise OSError("name or service not known")

    error = url_safety_error("https://does-not-resolve.example", resolve=boom)
    assert error is not None
    assert "could not be resolved" in error.lower()


def test_blocks_when_dns_returns_no_addresses():
    def empty(_: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        return []

    error = url_safety_error("https://empty.example", resolve=empty)
    assert error is not None
    assert "could not be resolved" in error.lower()


def test_resolve_hostname_ips_uses_getaddrinfo():
    fake = [
        (2, 1, 6, "", ("93.184.216.34", 0)),
        (2, 1, 6, "", ("93.184.216.34", 0)),
        (10, 1, 6, "", ("2606:2800:220:1:248:1893:25c8:1946", 0, 0, 0)),
    ]
    with patch("src.tools.url_safety.socket.getaddrinfo", return_value=fake):
        ips = resolve_hostname_ips("example.com")

    assert ips == [
        ipaddress.ip_address("93.184.216.34"),
        ipaddress.ip_address("2606:2800:220:1:248:1893:25c8:1946"),
    ]


def test_resolve_hostname_ips_raises_on_dns_failure():
    import socket

    with patch(
        "src.tools.url_safety.socket.getaddrinfo",
        side_effect=socket.gaierror(8, "nodename nor servname provided"),
    ):
        with pytest.raises(OSError, match="DNS resolution failed"):
            resolve_hostname_ips("missing.example")
