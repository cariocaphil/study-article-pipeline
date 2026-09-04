"""
Tests for src/orchestrator.py input guardrails.
"""

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.orchestrator import run_pipeline
from src.schemas.article import TopicType
from src.utils.observability import PIPELINE_RUN_SPAN


def _passthrough_phrases(phrases: object, *_a: object, **_k: object) -> object:
    return phrases


@pytest.fixture
def memory_spans(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    monkeypatch.setattr("src.utils.observability.get_tracer", lambda: tracer)
    yield exporter
    exporter.clear()


def test_run_pipeline_rejects_empty_topic_before_search():
    with patch("src.orchestrator.search_articles") as mock_search:
        with pytest.raises(ValueError, match="Please enter a topic."):
            run_pipeline("", "portuguese", "german", "C1")

    mock_search.assert_not_called()


def test_run_pipeline_rejects_unsafe_topic_before_search():
    with patch("src.orchestrator.search_articles") as mock_search:
        with pytest.raises(ValueError, match="characters that are not allowed"):
            run_pipeline("Entroncamento/Film", "portuguese", "german", "C1")

    mock_search.assert_not_called()


def test_run_pipeline_strips_topic_before_search():
    with (
        patch("src.orchestrator.search_articles", return_value=[]) as mock_search,
        patch("src.orchestrator.filter_articles", return_value=[]),
    ):
        with pytest.raises(ValueError, match="Pipeline stopped"):
            run_pipeline("  Entroncamento  ", "portuguese", "german", "C1")

    mock_search.assert_called_once()
    assert mock_search.call_args.args[0] == "Entroncamento"


def test_run_pipeline_passes_topic_type_to_search():
    with (
        patch("src.orchestrator.search_articles", return_value=[]) as mock_search,
        patch("src.orchestrator.filter_articles", return_value=[]),
    ):
        with pytest.raises(ValueError, match="Pipeline stopped"):
            run_pipeline(
                "Amadeus",
                "english",
                "german",
                "C1",
                topic_type=TopicType.theatre,
            )

    assert mock_search.call_args.kwargs["topic_type"] == TopicType.theatre


def test_run_pipeline_builds_articles_after_filter_passes():
    filtered = [
        {
            "title": f"Review {i}",
            "author": "Ada",
            "url": f"https://example.com/{i}",
            "source_name": "magazine",
            "full_text": f"body {i}",
        }
        for i in range(3)
    ]
    with (
        patch("src.orchestrator.search_articles", return_value=["https://example.com/1"]),
        patch("src.orchestrator.filter_articles", return_value=filtered),
        patch("src.orchestrator.extract_phrases", return_value=[]),
        patch("src.orchestrator.review_phrases", side_effect=_passthrough_phrases),
        patch("src.orchestrator.compile_document") as mock_compile,
        patch("src.orchestrator.anthropic.Anthropic"),
    ):
        result = run_pipeline("Entroncamento", "portuguese", "german", "C1")

    assert result.articles_kept == 3
    assert result.phrase_count == 0
    mock_compile.assert_called_once()
    compiled_output = mock_compile.call_args.args[0]
    assert len(compiled_output.articles) == 3


def test_run_pipeline_emits_run_and_stage_spans(memory_spans: InMemorySpanExporter) -> None:
    filtered = [
        {
            "title": f"Review {i}",
            "author": "Ada",
            "url": f"https://example.com/{i}",
            "source_name": "magazine",
            "full_text": f"body {i}",
        }
        for i in range(3)
    ]
    with (
        patch("src.orchestrator.search_articles", return_value=["https://example.com/1"]),
        patch("src.orchestrator.filter_articles", return_value=filtered),
        patch("src.orchestrator.extract_phrases", return_value=[]),
        patch("src.orchestrator.review_phrases", side_effect=_passthrough_phrases),
        patch("src.orchestrator.compile_document"),
        patch("src.orchestrator.anthropic.Anthropic"),
    ):
        result = run_pipeline("Entroncamento", "portuguese", "german", "C1")

    by_name = {span.name: span for span in memory_spans.get_finished_spans()}
    assert PIPELINE_RUN_SPAN in by_name
    for stage in ("search", "filter", "extract", "compile"):
        assert f"pipeline.stage.{stage}" in by_name

    run = by_name[PIPELINE_RUN_SPAN]
    attrs = dict(run.attributes or {})
    assert attrs["pipeline.run_id"] == result.run_id
    assert attrs["pipeline.articles_kept"] == 3
    assert attrs["pipeline.urls_found"] == 1
    assert "topic" not in attrs
    assert not any(v == "Entroncamento" for v in attrs.values())
