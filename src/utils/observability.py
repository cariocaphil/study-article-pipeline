"""
Logging, timing, token usage, and user-facing error helpers for pipeline runs.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from types import TracebackType

from anthropic import APIConnectionError, APIStatusError, RateLimitError
from anthropic.types import Message

StageCallback = Callable[[str], None]

STAGE_LABELS = {
    "search": "Searching for articles…",
    "filter": "Filtering and fetching articles…",
    "extract": "Extracting vocabulary and reviewing phrases…",
    "compile": "Compiling document…",
}

APPLICATIONINSIGHTS_CONNECTION_STRING_ENV = "APPLICATIONINSIGHTS_CONNECTION_STRING"

logger = logging.getLogger(__name__)

_telemetry_configured = False


def configure_logging() -> None:
    """Configure root logging once for CLI and Streamlit server processes."""
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def _configure_azure_monitor(connection_string: str) -> None:
    import importlib

    module = importlib.import_module("azure.monitor.opentelemetry")
    configure = getattr(module, "configure_azure_monitor")
    configure(connection_string=connection_string)


def configure_observability() -> bool:
    """
    Enable Azure Monitor OpenTelemetry when a connection string is configured.

    Returns True when Azure Monitor was configured for this process, False when
    telemetry stays a no-op (missing/blank env var, or already configured).
    """
    global _telemetry_configured
    if _telemetry_configured:
        return False

    connection_string = os.getenv(APPLICATIONINSIGHTS_CONNECTION_STRING_ENV, "").strip()
    if not connection_string:
        logger.debug(
            "%s not set; Azure Monitor telemetry disabled",
            APPLICATIONINSIGHTS_CONNECTION_STRING_ENV,
        )
        return False

    _configure_azure_monitor(connection_string)
    _telemetry_configured = True
    logger.info("Azure Monitor OpenTelemetry configured")
    return True


def reset_observability_for_tests() -> None:
    """Reset process-level telemetry configuration state (tests only)."""
    global _telemetry_configured
    _telemetry_configured = False


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass
class UsageTracker:
    """Accumulates Anthropic token usage; safe for concurrent filter workers."""

    input_tokens: int = 0
    output_tokens: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add(self, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            self.input_tokens += input_tokens
            self.output_tokens += output_tokens


@dataclass
class StageTimer:
    seconds: dict[str, float] = field(default_factory=dict[str, float])

    def track(self, stage: str, callback: StageCallback | None = None):
        return _StageContext(self, stage, callback)


class _StageContext:
    def __init__(
        self,
        timer: StageTimer,
        stage: str,
        callback: StageCallback | None,
    ) -> None:
        self._timer = timer
        self._stage = stage
        self._callback = callback
        self._start = 0.0

    def __enter__(self) -> None:
        if self._callback:
            self._callback(self._stage)
        self._start = time.perf_counter()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        elapsed = time.perf_counter() - self._start
        self._timer.seconds[self._stage] = self._timer.seconds.get(self._stage, 0.0) + elapsed


def record_api_usage(
    response: Message,
    *,
    agent: str,
    usage: UsageTracker | None = None,
    logger: logging.Logger | None = None,
) -> None:
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    if usage is not None:
        usage.add(input_tokens, output_tokens)
    log = logger or logging.getLogger(__name__)
    log.info(
        "agent=%s input_tokens=%d output_tokens=%d",
        agent,
        input_tokens,
        output_tokens,
    )


def user_facing_pipeline_error(exc: Exception) -> str:
    """Map internal exceptions to short messages suitable for the Streamlit UI."""
    if isinstance(exc, ValueError):
        message = str(exc)
        if message.startswith("Pipeline stopped:"):
            return message
        if (
            message.startswith("Please enter a topic.")
            or "Topic contains" in message
            or "Topic is too long" in message
            or message == "Topic contains disallowed content."
        ):
            return message
        if "could not parse" in message.lower():
            return (
                "The pipeline could not process the model response for one of the steps. "
                "Please try again. If the problem persists, try a different topic or "
                "fewer articles."
            )
        if any(
            marker in message
            for marker in ("Search agent", "Extract agent", "Review agent", "no reachable URLs")
        ):
            return (
                "Something went wrong while finding or processing articles. "
                "Please try again or adjust your topic."
            )
        return message
    if isinstance(exc, (RateLimitError, APIConnectionError)):
        return "The language service is temporarily unavailable. Please try again in a moment."
    if isinstance(exc, APIStatusError) and exc.status_code in {500, 502, 503, 529}:
        return "The language service encountered a temporary error. Please try again."
    return "An unexpected error occurred. Please try again later."
