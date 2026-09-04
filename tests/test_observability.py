"""
Tests for src/utils/observability.py.
"""

import logging

import pytest

from src.utils.observability import (
    StageTimer,
    UsageTracker,
    user_facing_pipeline_error,
)


def test_usage_tracker_accumulates_tokens():
    usage = UsageTracker()
    usage.add(100, 50)
    usage.add(25, 10)

    assert usage.input_tokens == 125
    assert usage.output_tokens == 60


def test_stage_timer_records_elapsed_seconds():
    timer = StageTimer()
    stages: list[str] = []

    with timer.track("search", lambda stage: stages.append(stage)):
        pass

    assert stages == ["search"]
    assert timer.seconds["search"] >= 0


def test_user_facing_pipeline_error_keeps_filter_stop_message():
    message = user_facing_pipeline_error(
        ValueError("Pipeline stopped: only 1 article(s) passed the filter.")
    )
    assert message == "Pipeline stopped: only 1 article(s) passed the filter."


def test_user_facing_pipeline_error_sanitizes_parse_failures():
    message = user_facing_pipeline_error(
        ValueError("Extract agent could not parse phrase list.\nsubstring not found")
    )
    assert "could not process the model response" in message
    assert "substring not found" not in message


def test_user_facing_pipeline_error_generic_for_unexpected():
    message = user_facing_pipeline_error(RuntimeError("boom"))
    assert message == "An unexpected error occurred. Please try again later."


def test_user_facing_pipeline_error_for_transient_api_status():
    import httpx2 as httpx
    from anthropic import InternalServerError

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(500, request=request)
    error = InternalServerError("boom", response=response, body={})

    message = user_facing_pipeline_error(error)

    assert message == ("The language service encountered a temporary error. Please try again.")


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
