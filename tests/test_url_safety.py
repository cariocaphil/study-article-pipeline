"""
Tests for src/tools/url_safety.py.
"""

import pytest

from src.tools.url_safety import is_safe_fetch_url, url_safety_error


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
    assert is_safe_fetch_url(url) is True
    assert url_safety_error(url) is None


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
    assert is_safe_fetch_url(url) is False
    error = url_safety_error(url)
    assert error is not None
    assert reason in error.lower()
