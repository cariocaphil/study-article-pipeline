"""
Tests for src/orchestrator.py input guardrails.
"""

from unittest.mock import patch

import pytest

from src.orchestrator import run_pipeline


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
