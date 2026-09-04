"""
Tests for src/utils/anthropic_retry.py.
"""

from collections.abc import Iterator
from unittest.mock import MagicMock

import httpx2 as httpx
import pytest
from anthropic import APIStatusError, InternalServerError, RateLimitError
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.utils.anthropic_retry import (
    create_message_with_retry,
    is_retryable_api_error,
)
from src.utils.observability import ANTHROPIC_CALL_SPAN
from tests.anthropic_mocks import mock_message


@pytest.fixture
def memory_spans(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr("src.utils.anthropic_retry.get_tracer", lambda: tracer)
    yield exporter
    exporter.clear()


def _api_status_error(status_code: int) -> APIStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code, request=request)
    return APIStatusError("api error", response=response, body={"type": "error"})


def test_is_retryable_api_error_for_transient_status_codes():
    assert is_retryable_api_error(_api_status_error(500)) is True
    assert is_retryable_api_error(_api_status_error(529)) is True
    assert is_retryable_api_error(_api_status_error(429)) is True


def test_is_retryable_api_error_rejects_client_errors():
    assert is_retryable_api_error(_api_status_error(400)) is False
    assert is_retryable_api_error(_api_status_error(404)) is False


def test_create_message_with_retry_returns_first_successful_response():
    client = MagicMock()
    expected = mock_message([], "end_turn")
    client.messages.create.return_value = expected

    response = create_message_with_retry(
        client,
        model="claude-sonnet-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}],
    )

    assert response is expected
    client.messages.create.assert_called_once()


def test_create_message_with_retry_retries_internal_server_error():
    client = MagicMock()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(500, request=request)
    error = InternalServerError("boom", response=response, body={})
    expected = mock_message([], "end_turn")
    client.messages.create.side_effect = [error, expected]
    sleeps: list[float] = []

    result = create_message_with_retry(
        client,
        max_attempts=3,
        base_delay_seconds=1.0,
        sleep_fn=sleeps.append,
        random_fn=lambda: 0.5,
        model="claude-sonnet-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}],
    )

    assert result is expected
    assert client.messages.create.call_count == 2
    assert sleeps == [1.0]


def test_create_message_with_retry_retries_rate_limit_error():
    client = MagicMock()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request)
    error = RateLimitError("rate limited", response=response, body={})
    expected = mock_message([], "end_turn")
    client.messages.create.side_effect = [error, expected]

    result = create_message_with_retry(
        client,
        max_attempts=3,
        sleep_fn=lambda _: None,
        random_fn=lambda: 0.0,
        model="claude-sonnet-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}],
    )

    assert result is expected
    assert client.messages.create.call_count == 2


def test_create_message_with_retry_raises_after_exhausting_attempts():
    client = MagicMock()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(500, request=request)
    error = InternalServerError("boom", response=response, body={})
    client.messages.create.side_effect = [error, error, error]

    with pytest.raises(InternalServerError):
        create_message_with_retry(
            client,
            max_attempts=3,
            sleep_fn=lambda _: None,
            random_fn=lambda: 0.0,
            model="claude-sonnet-4-6",
            max_tokens=10,
            messages=[{"role": "user", "content": "hi"}],
        )

    assert client.messages.create.call_count == 3


def test_create_message_with_retry_does_not_retry_client_errors():
    client = MagicMock()
    client.messages.create.side_effect = _api_status_error(400)

    with pytest.raises(APIStatusError):
        create_message_with_retry(
            client,
            max_attempts=3,
            sleep_fn=lambda _: None,
            model="claude-sonnet-4-6",
            max_tokens=10,
            messages=[{"role": "user", "content": "hi"}],
        )

    client.messages.create.assert_called_once()


def test_create_message_with_retry_emits_token_and_cost_span_attrs(
    memory_spans: InMemorySpanExporter,
) -> None:
    client = MagicMock()
    client.messages.create.return_value = mock_message(
        [],
        "end_turn",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )

    create_message_with_retry(
        client,
        model="claude-sonnet-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}],
    )

    spans = list(memory_spans.get_finished_spans())
    assert len(spans) == 1
    span = spans[0]
    assert span.name == ANTHROPIC_CALL_SPAN
    attrs = dict(span.attributes or {})
    assert attrs["gen_ai.system"] == "anthropic"
    assert attrs["gen_ai.request.model"] == "claude-sonnet-4-6"
    assert attrs["gen_ai.usage.input_tokens"] == 1_000_000
    assert attrs["gen_ai.usage.output_tokens"] == 1_000_000
    assert attrs["anthropic.attempt"] == 1
    assert attrs["anthropic.retry_count"] == 0
    # 3.0 + 15.0 USD per MTok at 1M each
    assert attrs["anthropic.estimated_cost_usd"] == pytest.approx(18.0)


def test_create_message_with_retry_records_retry_event_and_success(
    memory_spans: InMemorySpanExporter,
) -> None:
    client = MagicMock()
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(500, request=request)
    error = InternalServerError("boom", response=response, body={})
    expected = mock_message([], "end_turn", input_tokens=10, output_tokens=5)
    client.messages.create.side_effect = [error, expected]

    create_message_with_retry(
        client,
        max_attempts=3,
        sleep_fn=lambda _: None,
        random_fn=lambda: 0.0,
        model="claude-sonnet-4-6",
        max_tokens=10,
        messages=[{"role": "user", "content": "hi"}],
    )

    span = memory_spans.get_finished_spans()[0]
    attrs = dict(span.attributes or {})
    assert attrs["anthropic.attempt"] == 2
    assert attrs["anthropic.retry_count"] == 1
    assert attrs["gen_ai.usage.input_tokens"] == 10
    events = list(span.events)
    assert any(event.name == "anthropic.retry" for event in events)


def test_create_message_with_retry_marks_span_error_on_failure(
    memory_spans: InMemorySpanExporter,
) -> None:
    client = MagicMock()
    client.messages.create.side_effect = _api_status_error(400)

    with pytest.raises(APIStatusError):
        create_message_with_retry(
            client,
            max_attempts=3,
            sleep_fn=lambda _: None,
            model="claude-sonnet-4-6",
            max_tokens=10,
            messages=[{"role": "user", "content": "hi"}],
        )

    span = memory_spans.get_finished_spans()[0]
    assert span.status.status_code.name == "ERROR"
    attrs = dict(span.attributes or {})
    assert attrs["http.response.status_code"] == 400
    assert attrs["anthropic.retry_count"] == 0
