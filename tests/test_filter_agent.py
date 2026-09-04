"""
Tests for src/agents/filter_agent.py.

These make real calls to the Anthropic API (with web search enabled), so
they're marked slow. Run `uv run pytest -m "not slow"` to skip them.

Uses hand-picked URLs expected to remain stable over time. If a target site
goes offline or is redesigned, these tests may need a replacement URL.
"""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from src.agents.filter_agent import filter_articles
from tests.anthropic_mocks import mock_message

GOOD_REVIEW_URL = (
    "https://www.magazine-hd.com/apps/wp/entroncamento-critica-filme-pedro-cabeleira-ana-vilaca/"
)
SYNOPSIS_URL = "https://en.wikipedia.org/wiki/The_Shawshank_Redemption"


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _filter_json(**fields: object) -> str:
    payload: dict[str, Any] = {
        "is_review": True,
        "is_correct_language": True,
        "title": "Sample review",
        "author": "Ada",
        "source_name": "magazine",
        "full_text": "Enough body text for a review.",
    }
    payload.update(fields)
    return json.dumps(payload)


@patch("src.agents.filter_agent.create_message_with_retry")
class TestFilterArticlesParsing:
    def test_accepts_review_and_coerces_non_string_fields(self, mock_create: MagicMock):
        mock_create.return_value = mock_message(
            [
                _text_block(
                    _filter_json(
                        title=123,
                        author=99,
                        source_name=False,
                        full_text=["not", "text"],
                    )
                )
            ],
            "end_turn",
        )

        results = filter_articles(["https://example.com/review"], "portuguese", MagicMock())

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/review"
        assert results[0]["title"] == ""
        assert results[0]["author"] is None
        assert results[0]["source_name"] == ""
        assert results[0]["full_text"] == ""

    def test_rejects_when_not_a_review(self, mock_create: MagicMock):
        mock_create.return_value = mock_message(
            [_text_block(_filter_json(is_review=False))],
            "end_turn",
        )

        results = filter_articles(["https://example.com/synopsis"], "english", MagicMock())

        assert results == []

    def test_skips_non_object_json(self, mock_create: MagicMock):
        mock_create.return_value = mock_message(
            [_text_block("irrelevant")],
            "end_turn",
        )

        with patch(
            "src.agents.filter_agent.extract_json",
            return_value=["not", "an", "object"],
        ):
            results = filter_articles(["https://example.com/bad"], "english", MagicMock())

        assert results == []

    def test_rejects_wrong_language(self, mock_create: MagicMock):
        mock_create.return_value = mock_message(
            [_text_block(_filter_json(is_correct_language=False))],
            "end_turn",
        )

        results = filter_articles(["https://example.com/wrong-lang"], "portuguese", MagicMock())

        assert results == []

    def test_skips_unparseable_response(self, mock_create: MagicMock):
        mock_create.return_value = mock_message(
            [_text_block("no json here at all")],
            "end_turn",
        )

        results = filter_articles(["https://example.com/broken"], "english", MagicMock())

        assert results == []


@pytest.mark.slow
def test_filter_articles_accepts_good_review(anthropic_client: anthropic.Anthropic):
    results = filter_articles([GOOD_REVIEW_URL], "portuguese", anthropic_client)

    assert len(results) == 1
    article = results[0]
    assert article["title"]
    assert "author" in article
    assert article["source_name"]
    assert len(article["full_text"]) > 200


@pytest.mark.slow
def test_filter_articles_rejects_synopsis(anthropic_client: anthropic.Anthropic):
    results = filter_articles([SYNOPSIS_URL], "english", anthropic_client)

    urls_in_results = [r["url"] for r in results]
    assert SYNOPSIS_URL not in urls_in_results
