"""
Tests for src/utils/observability.py.
"""

import logging
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from src.utils.observability import (
    APPLICATIONINSIGHTS_CONNECTION_STRING_ENV,
    PIPELINE_RUN_SPAN,
    StageTimer,
    UsageTracker,
    configure_logging,
    configure_observability,
    estimate_anthropic_cost_usd,
    get_tracer,
    new_run_id,
    pipeline_run_span,
    reset_observability_for_tests,
    user_facing_pipeline_error,
)


@pytest.fixture(autouse=True)
def reset_telemetry_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    reset_observability_for_tests()
    monkeypatch.delenv(APPLICATIONINSIGHTS_CONNECTION_STRING_ENV, raising=False)
    yield
    reset_observability_for_tests()


@pytest.fixture
def memory_spans(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    """Attach spans to an in-memory exporter without fighting the global TracerProvider."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr("src.utils.observability.get_tracer", lambda: tracer)
    yield exporter
    exporter.clear()


def _finished_by_name(exporter: InMemorySpanExporter) -> dict[str, ReadableSpan]:
    return {span.name: span for span in exporter.get_finished_spans()}


def test_usage_tracker_accumulates_tokens():
    usage = UsageTracker()
    usage.add(100, 50)
    usage.add(25, 10)

    assert usage.input_tokens == 125
    assert usage.output_tokens == 60


def test_configure_observability_is_noop_without_connection_string() -> None:
    with patch("src.utils.observability._configure_azure_monitor") as mock_configure:
        assert configure_observability() is False
        mock_configure.assert_not_called()


def test_configure_observability_is_noop_for_blank_connection_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(APPLICATIONINSIGHTS_CONNECTION_STRING_ENV, "   ")
    with patch("src.utils.observability._configure_azure_monitor") as mock_configure:
        assert configure_observability() is False
        mock_configure.assert_not_called()


def test_configure_observability_enables_azure_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_string = "InstrumentationKey=00000000-0000-0000-0000-000000000000"
    monkeypatch.setenv(APPLICATIONINSIGHTS_CONNECTION_STRING_ENV, connection_string)

    with patch("src.utils.observability._configure_azure_monitor") as mock_configure:
        assert configure_observability() is True
        mock_configure.assert_called_once_with(connection_string)
        assert configure_observability() is False
        mock_configure.assert_called_once()


def test_usage_tracker_add_is_safe_under_concurrent_updates():
    usage = UsageTracker()

    def bump(_: int) -> None:
        for _ in range(200):
            usage.add(1, 2)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(bump, range(8)))

    assert usage.input_tokens == 1600
    assert usage.output_tokens == 3200


def test_stage_timer_records_elapsed_seconds():
    timer = StageTimer()
    stages: list[str] = []

    with timer.track("search", lambda stage: stages.append(stage)):
        pass

    assert stages == ["search"]
    assert timer.seconds["search"] >= 0


def test_estimate_anthropic_cost_usd_for_known_model() -> None:
    cost = estimate_anthropic_cost_usd("claude-sonnet-4-6", 1_000_000, 500_000)
    assert cost == pytest.approx(3.0 + 7.5)


def test_estimate_anthropic_cost_usd_unknown_model_returns_none() -> None:
    assert estimate_anthropic_cost_usd("unknown-model", 100, 50) is None


def test_pipeline_run_span_sets_safe_attributes(memory_spans: InMemorySpanExporter) -> None:
    with pipeline_run_span(
        "abc123def456",
        source_language="portuguese",
        translation_language="german",
        user_level="C1",
        n_articles=5,
        topic_type="film",
    ) as span:
        span.set_attribute("pipeline.articles_kept", 3)

    finished = _finished_by_name(memory_spans)
    run = finished[PIPELINE_RUN_SPAN]
    attrs = dict(run.attributes or {})
    assert run.kind == SpanKind.CLIENT
    assert attrs["pipeline.run_id"] == "abc123def456"
    assert attrs["pipeline.source_language"] == "portuguese"
    assert attrs["pipeline.translation_language"] == "german"
    assert attrs["pipeline.user_level"] == "C1"
    assert attrs["pipeline.n_articles"] == 5
    assert attrs["pipeline.topic_type"] == "film"
    assert attrs["pipeline.articles_kept"] == 3
    assert "topic" not in attrs
    assert not any("Entroncamento" in str(v) for v in attrs.values())


def test_stage_spans_nest_under_pipeline_run(memory_spans: InMemorySpanExporter) -> None:
    timer = StageTimer()
    with pipeline_run_span(
        "runnest001",
        source_language="portuguese",
        translation_language="german",
        user_level="B2",
        n_articles=3,
        topic_type="book",
    ):
        with timer.track("search"):
            pass
        with timer.track("filter"):
            pass

    finished = _finished_by_name(memory_spans)
    run = finished[PIPELINE_RUN_SPAN]
    search = finished["pipeline.stage.search"]
    filter_span = finished["pipeline.stage.filter"]

    assert search.parent is not None
    assert filter_span.parent is not None
    assert run.context is not None
    assert run.kind == SpanKind.CLIENT
    assert search.kind == SpanKind.CLIENT
    assert filter_span.kind == SpanKind.CLIENT
    assert search.parent.span_id == run.context.span_id
    assert filter_span.parent.span_id == run.context.span_id
    assert dict(search.attributes or {})["pipeline.stage"] == "search"
    assert dict(filter_span.attributes or {})["pipeline.stage"] == "filter"


def test_pipeline_run_span_records_errors(memory_spans: InMemorySpanExporter) -> None:
    with pytest.raises(ValueError, match="stopped"):
        with pipeline_run_span(
            "errrun000001",
            source_language="portuguese",
            translation_language="german",
            user_level="C1",
            n_articles=5,
            topic_type="film",
        ):
            raise ValueError("Pipeline stopped: only 1 article(s) passed the filter.")

    run = _finished_by_name(memory_spans)[PIPELINE_RUN_SPAN]
    assert run.status.status_code.name == "ERROR"


def test_user_facing_pipeline_error_keeps_filter_stop_message():
    message = user_facing_pipeline_error(
        ValueError("Pipeline stopped: only 1 article(s) passed the filter.")
    )
    assert message == "Pipeline stopped: only 1 article(s) passed the filter."


def test_user_facing_pipeline_error_keeps_topic_validation_message():
    message = user_facing_pipeline_error(ValueError("Please enter a topic."))
    assert message == "Please enter a topic."


def test_user_facing_pipeline_error_sanitizes_parse_failures():
    message = user_facing_pipeline_error(
        ValueError("Extract agent could not parse phrase list.\nsubstring not found")
    )
    assert "could not process the model response" in message
    assert "substring not found" not in message


def test_user_facing_pipeline_error_sanitizes_agent_failures():
    message = user_facing_pipeline_error(ValueError("Search agent failed: boom"))
    assert "finding or processing articles" in message
    assert "boom" not in message


def test_user_facing_pipeline_error_keeps_other_value_errors():
    message = user_facing_pipeline_error(ValueError("Custom validation failed"))
    assert message == "Custom validation failed"


def test_user_facing_pipeline_error_generic_for_unexpected():
    message = user_facing_pipeline_error(RuntimeError("boom"))
    assert message == "An unexpected error occurred. Please try again later."


def test_user_facing_pipeline_error_for_rate_limit():
    import httpx2 as httpx
    from anthropic import RateLimitError

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request)
    error = RateLimitError("rate limited", response=response, body={})

    message = user_facing_pipeline_error(error)
    assert "temporarily unavailable" in message


def test_user_facing_pipeline_error_for_connection_error():
    import httpx2 as httpx
    from anthropic import APIConnectionError

    error = APIConnectionError(
        message="offline",
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )
    message = user_facing_pipeline_error(error)
    assert "temporarily unavailable" in message


def test_user_facing_pipeline_error_for_transient_api_status():
    import httpx2 as httpx
    from anthropic import InternalServerError

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(500, request=request)
    error = InternalServerError("boom", response=response, body={})

    message = user_facing_pipeline_error(error)

    assert message == ("The language service encountered a temporary error. Please try again.")


def test_configure_logging_configures_when_root_has_no_handlers() -> None:
    root = logging.getLogger()
    saved = list(root.handlers)
    try:
        for handler in saved:
            root.removeHandler(handler)
        assert not root.handlers
        configure_logging()
        assert root.handlers
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in saved:
            root.addHandler(handler)


def test_configure_logging_is_noop_when_handlers_exist() -> None:
    root = logging.getLogger()
    assert root.handlers
    before = list(root.handlers)
    configure_logging()
    assert list(root.handlers) == before


def test_configure_azure_monitor_calls_sdk() -> None:
    from src.utils import observability as obs

    fake_configure = MagicMock()
    fake_module = MagicMock()
    fake_module.configure_azure_monitor = fake_configure

    with patch("importlib.import_module", return_value=fake_module) as mock_import:
        obs._configure_azure_monitor("InstrumentationKey=test")

    mock_import.assert_called_once_with("azure.monitor.opentelemetry")
    fake_configure.assert_called_once_with(connection_string="InstrumentationKey=test")


def test_new_run_id_is_twelve_hex_chars() -> None:
    run_id = new_run_id()
    assert len(run_id) == 12
    assert int(run_id, 16) >= 0


def test_get_tracer_returns_tracer() -> None:
    tracer = get_tracer()
    assert tracer is not None


def test_record_api_usage_logs_and_accumulates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from anthropic.types import Message, Usage

    from src.utils.observability import record_api_usage

    usage = UsageTracker()
    response = Message(
        id="msg_test",
        content=[],
        model="claude-sonnet-4-6",
        role="assistant",
        stop_reason="end_turn",
        type="message",
        usage=Usage(input_tokens=10, output_tokens=5),
    )

    with caplog.at_level(logging.INFO):
        record_api_usage(response, agent="search_agent", usage=usage)

    assert usage.input_tokens == 10
    assert usage.output_tokens == 5
    assert any("search_agent" in record.message for record in caplog.records)
