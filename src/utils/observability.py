"""
Logging, timing, token usage, and user-facing error helpers for pipeline runs.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from types import TracebackType

from anthropic import APIConnectionError, APIStatusError, RateLimitError
from anthropic.types import Message
from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

StageCallback = Callable[[str], None]

STAGE_LABELS = {
    "search": "Searching for articles…",
    "filter": "Filtering and fetching articles…",
    "extract": "Extracting vocabulary and reviewing phrases…",
    "compile": "Compiling document…",
}

APPLICATIONINSIGHTS_CONNECTION_STRING_ENV = "APPLICATIONINSIGHTS_CONNECTION_STRING"
TRACER_NAME = "study_article_pipeline"
PIPELINE_RUN_SPAN = "pipeline.run"
PIPELINE_STAGE_SPAN_PREFIX = "pipeline.stage"
ANTHROPIC_CALL_SPAN = "anthropic.messages.create"

# Approximate USD per 1M tokens (input, output). Rates go stale — estimates only.
_ANTHROPIC_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
}

logger = logging.getLogger(__name__)

_telemetry_configured = False


def get_tracer() -> Tracer:
    """Return the process tracer (no-op until a real TracerProvider is configured)."""
    return trace.get_tracer(TRACER_NAME)


def force_flush_traces(timeout_millis: int = 5000) -> None:
    """
    Flush pending spans to the exporter when the provider supports it.

    No-op for the default ProxyTracerProvider (local/CI without Azure Monitor).
    """
    provider = trace.get_tracer_provider()
    force_flush = getattr(provider, "force_flush", None)
    if callable(force_flush):
        force_flush(timeout_millis)


def estimate_anthropic_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """
    Rough USD cost from a static price table, or None when the model is unknown.

    Prices are intentionally approximate and must be updated when Anthropic rates change.
    """
    rates = _ANTHROPIC_USD_PER_MTOK.get(model)
    if rates is None:
        return None
    input_rate, output_rate = rates
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000.0


@contextmanager
def pipeline_run_span(
    run_id: str,
    *,
    source_language: str,
    translation_language: str,
    user_level: str,
    n_articles: int,
    topic_type: str,
) -> Generator[Span, None, None]:
    """
    Parent span for one pipeline execution.

    Omits the raw topic string from attributes (privacy); callers may set
    aggregate outcome attributes on the yielded span before exit.

    Uses CLIENT kind so Azure Monitor exports the run as a dependency alongside
    stages (SERVER mapped to requests but was not reliably ingested for this
    long-lived, non-HTTP root). Forces a trace flush after the span closes so
    the batch exporter sends the root promptly under Streamlit.
    """
    try:
        with get_tracer().start_as_current_span(
            PIPELINE_RUN_SPAN,
            kind=SpanKind.CLIENT,
        ) as span:
            span.set_attribute("pipeline.run_id", run_id)
            span.set_attribute("pipeline.source_language", source_language)
            span.set_attribute("pipeline.translation_language", translation_language)
            span.set_attribute("pipeline.user_level", user_level)
            span.set_attribute("pipeline.n_articles", n_articles)
            span.set_attribute("pipeline.topic_type", topic_type)
            try:
                yield span
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
                span.record_exception(exc)
                raise
    finally:
        force_flush_traces()


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
        """Time a stage and emit a child OpenTelemetry span when a provider is set."""
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
        self._span_cm: AbstractContextManager[Span] | None = None

    def __enter__(self) -> None:
        if self._callback:
            self._callback(self._stage)
        self._start = time.perf_counter()
        span_cm = get_tracer().start_as_current_span(
            f"{PIPELINE_STAGE_SPAN_PREFIX}.{self._stage}",
            kind=SpanKind.CLIENT,
            attributes={"pipeline.stage": self._stage},
        )
        self._span_cm = span_cm
        span_cm.__enter__()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        elapsed = time.perf_counter() - self._start
        self._timer.seconds[self._stage] = self._timer.seconds.get(self._stage, 0.0) + elapsed
        span_cm = self._span_cm
        self._span_cm = None
        if span_cm is not None:
            span_cm.__exit__(exc_type, exc, tb)


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
