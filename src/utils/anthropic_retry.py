"""
Retry helpers for transient Anthropic API failures.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import Any, cast

import anthropic
from anthropic import APIConnectionError, APIStatusError, RateLimitError
from anthropic.types import Message

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_SECONDS = 1.0
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 529})


def is_retryable_api_error(exc: Exception) -> bool:
    """Return True for Anthropic errors that are worth retrying."""
    if isinstance(exc, (RateLimitError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in RETRYABLE_STATUS_CODES
    return False


def _retry_delay_seconds(
    attempt: int,
    *,
    base_delay_seconds: float,
    random_fn: Callable[[], float],
) -> float:
    delay = base_delay_seconds * (2 ** (attempt - 1))
    return delay * (0.5 + random_fn())


def create_message_with_retry(
    client: anthropic.Anthropic,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay_seconds: float = DEFAULT_BASE_DELAY_SECONDS,
    sleep_fn: Callable[[float], None] = time.sleep,
    random_fn: Callable[[], float] = random.random,
    **create_kwargs: Any,
) -> Message:
    """
    Call client.messages.create with retries on transient API failures.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return cast(Message, client.messages.create(**create_kwargs))
        except Exception as exc:
            last_error = exc
            if attempt >= max_attempts or not is_retryable_api_error(exc):
                raise

            delay = _retry_delay_seconds(
                attempt,
                base_delay_seconds=base_delay_seconds,
                random_fn=random_fn,
            )
            logger.warning(
                "Anthropic API call failed (attempt %d/%d): %s. Retrying in %.1fs.",
                attempt,
                max_attempts,
                exc,
                delay,
            )
            sleep_fn(delay)

    assert last_error is not None
    raise last_error
