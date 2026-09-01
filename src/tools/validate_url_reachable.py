"""
URL reachability validator.
Performs a lightweight HTTP HEAD request to check whether a candidate
article URL actually resolves, without fetching the full page body.
"""

import logging
import urllib.error
import urllib.request

from src.tools.url_safety import is_safe_fetch_url

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5


def validate_url_reachable(url: str) -> bool:
    """
    Check whether a URL is reachable via an HTTP HEAD request.

    Returns True for HTTP 2xx/3xx responses. Returns False on unsafe URLs,
    4xx/5xx responses, timeouts, or connection failures.
    """
    if not is_safe_fetch_url(url):
        logger.info("%s → blocked", url)
        return False

    try:
        request = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 (compatible; study-article-pipeline/1.0)"},
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            reachable = 200 <= response.status < 400
    except urllib.error.HTTPError as e:
        reachable = 200 <= e.code < 400
    except (urllib.error.URLError, TimeoutError, ValueError):
        reachable = False

    status_label = "reachable" if reachable else "unreachable"
    logger.info("%s → %s", url, status_label)
    return reachable
