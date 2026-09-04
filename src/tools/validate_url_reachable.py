"""
URL reachability validator.
Performs a lightweight HTTP HEAD request to check whether a candidate
article URL actually resolves, without fetching the full page body.

Each request hop is SSRF-checked (including DNS) before it is sent. Redirects
are followed manually so every Location target is validated the same way.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from http.client import HTTPMessage
from urllib.parse import urljoin

from src.tools.url_safety import is_safe_fetch_url

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5
MAX_REDIRECTS = 5
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_USER_AGENT = "Mozilla/5.0 (compatible; study-article-pipeline/1.0)"


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Surface redirect responses as HTTPError so callers can validate hops."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)  # type: ignore[arg-type]


def _head_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirectHandler)


def validate_url_reachable(url: str) -> bool:
    """
    Check whether a URL is reachable via an HTTP HEAD request.

    Returns True for HTTP 2xx responses (and for final non-redirect success).
    Returns False on unsafe URLs, unsafe redirect targets, 4xx/5xx responses,
    too many redirects, timeouts, or connection failures.
    """
    current = url

    for _ in range(MAX_REDIRECTS + 1):
        if not is_safe_fetch_url(current):
            logger.info("%s → blocked", current)
            return False

        request = urllib.request.Request(
            current,
            method="HEAD",
            headers={"User-Agent": _USER_AGENT},
        )
        try:
            with _head_opener().open(request, timeout=TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                reachable = isinstance(status, int) and 200 <= status < 300
        except urllib.error.HTTPError as e:
            if e.code in _REDIRECT_STATUS_CODES:
                location = e.headers.get("Location")
                if not location:
                    logger.info("%s → unreachable", current)
                    return False
                current = urljoin(current, location)
                continue
            reachable = 200 <= e.code < 400 and e.code not in _REDIRECT_STATUS_CODES
        except (urllib.error.URLError, TimeoutError, ValueError):
            reachable = False

        status_label = "reachable" if reachable else "unreachable"
        logger.info("%s → %s", current, status_label)
        return reachable

    logger.info("%s → blocked (too many redirects)", url)
    return False
