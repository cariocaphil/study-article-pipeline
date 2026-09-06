"""
Tests for src/agents/filter_agent.py.

These make real calls to the Anthropic API (with web search enabled), so
they're marked slow. Run `uv run pytest -m "not slow"` to skip them.

Uses hand-picked URLs expected to remain stable over time. If a target site
goes offline or is redesigned, these tests may need a replacement URL.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import cast
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from src.agents.filter_agent import filter_articles
from src.schemas.filter import FilterArticleVerdict
from src.utils.observability import UsageTracker
from tests.anthropic_mocks import mock_parsed_message

GOOD_REVIEW_URL = (
    "https://www.magazine-hd.com/apps/wp/entroncamento-critica-filme-pedro-cabeleira-ana-vilaca/"
)
SYNOPSIS_URL = "https://en.wikipedia.org/wiki/The_Shawshank_Redemption"


def _verdict(**fields: object) -> FilterArticleVerdict:
    payload: dict[str, object] = {
        "is_review": True,
        "is_correct_language": True,
        "title": "Sample review",
        "author": "Ada",
        "source_name": "magazine",
        "full_text": "Enough body text for a review.",
    }
    payload.update(fields)
    return FilterArticleVerdict.model_validate(payload)


@patch("src.agents.filter_agent.parse_message_with_retry")
class TestFilterArticlesParsing:
    def test_accepts_review_and_maps_fields(self, mock_parse: MagicMock):
        mock_parse.return_value = mock_parsed_message(
            _verdict(
                title="Mapped title",
                author=None,
                source_name="example.com",
                full_text="Body text.",
            )
        )

        results = filter_articles(["https://example.com/review"], "portuguese", MagicMock())

        assert len(results) == 1
        assert results[0]["url"] == "https://example.com/review"
        assert results[0]["title"] == "Mapped title"
        assert results[0]["author"] is None
        assert results[0]["source_name"] == "example.com"
        assert results[0]["full_text"] == "Body text."
        assert mock_parse.call_args.kwargs["output_format"] is FilterArticleVerdict

    def test_rejects_when_not_a_review(self, mock_parse: MagicMock):
        mock_parse.return_value = mock_parsed_message(_verdict(is_review=False))

        results = filter_articles(["https://example.com/synopsis"], "english", MagicMock())

        assert results == []

    def test_skips_when_parsed_output_missing(self, mock_parse: MagicMock):
        mock_parse.return_value = mock_parsed_message(None)

        results = filter_articles(["https://example.com/bad"], "english", MagicMock())

        assert results == []

    def test_rejects_wrong_language(self, mock_parse: MagicMock):
        mock_parse.return_value = mock_parsed_message(_verdict(is_correct_language=False))

        results = filter_articles(["https://example.com/wrong-lang"], "portuguese", MagicMock())

        assert results == []


@patch("src.agents.filter_agent.parse_message_with_retry")
class TestFilterArticlesConcurrency:
    def test_preserves_input_order_among_accepted_urls(self, mock_parse: MagicMock):
        responses = {
            "https://example.com/a": mock_parsed_message(_verdict(title="First")),
            "https://example.com/b": mock_parsed_message(_verdict(is_review=False)),
            "https://example.com/c": mock_parsed_message(_verdict(title="Third")),
        }

        def parse_for_url(*_args: object, **kwargs: object):
            messages = kwargs["messages"]
            assert isinstance(messages, list) and messages
            first_message = cast(dict[str, object], messages[0])
            prompt = first_message["content"]
            assert isinstance(prompt, str)
            for url, response in responses.items():
                if url in prompt:
                    return response
            raise AssertionError(f"Unexpected prompt: {prompt!r}")

        mock_parse.side_effect = parse_for_url

        results = filter_articles(
            [
                "https://example.com/a",
                "https://example.com/b",
                "https://example.com/c",
            ],
            "english",
            MagicMock(),
            max_workers=3,
        )

        assert [article["url"] for article in results] == [
            "https://example.com/a",
            "https://example.com/c",
        ]
        assert [article["title"] for article in results] == ["First", "Third"]

    def test_returns_empty_for_no_urls(self, mock_parse: MagicMock):
        assert filter_articles([], "english", MagicMock()) == []
        mock_parse.assert_not_called()

    def test_caps_thread_pool_to_max_workers(self, mock_parse: MagicMock):
        mock_parse.return_value = mock_parsed_message(_verdict(title="Ok"))
        urls = [f"https://example.com/{i}" for i in range(5)]

        with patch(
            "src.agents.filter_agent.ThreadPoolExecutor",
            wraps=ThreadPoolExecutor,
        ) as mock_pool:
            results = filter_articles(urls, "english", MagicMock(), max_workers=2)

        assert len(results) == 5
        mock_pool.assert_called_once_with(max_workers=2)

    def test_records_usage_across_concurrent_calls(self, mock_parse: MagicMock):
        mock_parse.return_value = mock_parsed_message(
            _verdict(title="Ok"),
            input_tokens=10,
            output_tokens=4,
        )
        usage = UsageTracker()

        results = filter_articles(
            ["https://example.com/1", "https://example.com/2", "https://example.com/3"],
            "english",
            MagicMock(),
            usage=usage,
            max_workers=3,
        )

        assert len(results) == 3
        assert usage.input_tokens == 30
        assert usage.output_tokens == 12


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
