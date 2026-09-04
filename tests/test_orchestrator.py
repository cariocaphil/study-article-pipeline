"""
Tests for src/orchestrator.py input guardrails.
"""

from unittest.mock import patch

import pytest

from src.orchestrator import run_pipeline
from src.schemas.article import TopicType


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
        patch("src.orchestrator.review_phrases", side_effect=lambda phrases, *_a, **_k: phrases),
        patch("src.orchestrator.compile_document") as mock_compile,
        patch("src.orchestrator.anthropic.Anthropic"),
    ):
        result = run_pipeline("Entroncamento", "portuguese", "german", "C1")

    assert result.articles_kept == 3
    assert result.phrase_count == 0
    mock_compile.assert_called_once()
    compiled_output = mock_compile.call_args.args[0]
    assert len(compiled_output.articles) == 3
