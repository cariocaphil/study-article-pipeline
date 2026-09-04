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
from opentelemetry.trace import Span, Status, StatusCode

from src.utils.observability import (
    ANTHROPIC_CALL_SPAN,
    estimate_anthropic_cost_usd,
    get_tracer,
)

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


def _set_usage_attributes(span: Span, *, model: str | None, response: Message) -> None:
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
    if model is None:
        return
    cost = estimate_anthropic_cost_usd(model, input_tokens, output_tokens)
    if cost is not None:
        span.set_attribute("anthropic.estimated_cost_usd", cost)


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

    Emits an OpenTelemetry span (no-op without a TracerProvider) covering the
    full retry loop, with token usage and optional estimated cost on success.
    """
    model_raw = create_kwargs.get("model")
    model = model_raw if isinstance(model_raw, str) else None

    with get_tracer().start_as_current_span(ANTHROPIC_CALL_SPAN) as span:
        span.set_attribute("gen_ai.system", "anthropic")
        span.set_attribute("gen_ai.operation.name", "chat")
        if model is not None:
            span.set_attribute("gen_ai.request.model", model)

        last_error: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = cast(Message, client.messages.create(**create_kwargs))
                span.set_attribute("anthropic.attempt", attempt)
                span.set_attribute("anthropic.retry_count", attempt - 1)
                _set_usage_attributes(span, model=model, response=response)
                return response
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts or not is_retryable_api_error(exc):
                    span.set_attribute("anthropic.attempt", attempt)
                    span.set_attribute("anthropic.retry_count", attempt - 1)
                    if isinstance(exc, APIStatusError):
                        span.set_attribute("http.response.status_code", exc.status_code)
                    span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                    span.record_exception(exc)
                    raise

                delay = _retry_delay_seconds(
                    attempt,
                    base_delay_seconds=base_delay_seconds,
                    random_fn=random_fn,
                )
                span.add_event(
                    "anthropic.retry",
                    {
                        "anthropic.attempt": attempt,
                        "error.type": type(exc).__name__,
                        "anthropic.retry_delay_seconds": delay,
                    },
                )
                logger.warning(
                    "Anthropic API call failed (attempt %d/%d): %s. Retrying in %.1fs.",
                    attempt,
                    max_attempts,
                    exc,
                    delay,
                )
                sleep_fn(delay)

        assert last_error is not None  # pragma: no cover
        raise last_error  # pragma: no cover
