"""
Tests for src/utils/anthropic_retry.py.
"""

from unittest.mock import MagicMock

import httpx2 as httpx
import pytest
from anthropic import APIStatusError, InternalServerError, RateLimitError

from src.utils.anthropic_retry import (
    create_message_with_retry,
    is_retryable_api_error,
)
from tests.anthropic_mocks import mock_message


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
