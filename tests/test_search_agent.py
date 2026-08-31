"""
Tests for src/agents/search_agent.py.

Fast unit tests mock the Anthropic client and URL validator. Slow tests make
real API calls (with web search and URL validation enabled).
Run `uv run pytest -m "not slow"` to skip the integration tests.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agents.search_agent import search_articles


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_use(tool_id: str, url: str):
    return SimpleNamespace(
        type="tool_use",
        id=tool_id,
        name="validate_url_reachable",
        input={"url": url},
    )


def _response(content, stop_reason: str):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


class TestSearchArticlesToolLoop:
    @patch("src.agents.search_agent.validate_url_reachable")
    def test_returns_only_reachable_urls_validated_via_tool(self, mock_validate):
        good_url = "https://example.com/good"
        bad_url = "https://example.com/bad"
        mock_validate.side_effect = lambda url: url == good_url

        client = MagicMock()
        client.messages.create.side_effect = [
            _response(
                [
                    _tool_use("tool-1", good_url),
                    _tool_use("tool-2", bad_url),
                ],
                "tool_use",
            ),
            _response(
                [_text_block(f'["{good_url}", "{bad_url}"]')],
                "end_turn",
            ),
        ]

        urls = search_articles("Entroncamento", "portuguese", 2, client)

        assert urls == [good_url]
        assert mock_validate.call_count == 2

    @patch("src.agents.search_agent.validate_url_reachable")
    def test_drops_urls_not_validated_by_tool(self, mock_validate):
        validated_url = "https://example.com/validated"
        mock_validate.return_value = True

        client = MagicMock()
        client.messages.create.side_effect = [
            _response([_tool_use("tool-1", validated_url)], "tool_use"),
            _response(
                [_text_block('["https://example.com/validated", "https://example.com/skipped"]')],
                "end_turn",
            ),
        ]

        urls = search_articles("Entroncamento", "portuguese", 2, client)

        assert urls == [validated_url]
        mock_validate.assert_called_once_with(validated_url)

    @patch("src.agents.search_agent.validate_url_reachable")
    def test_raises_when_all_validated_urls_are_unreachable(self, mock_validate):
        bad_url = "https://example.com/bad"
        mock_validate.return_value = False

        client = MagicMock()
        client.messages.create.side_effect = [
            _response([_tool_use("tool-1", bad_url)], "tool_use"),
            _response([_text_block(f'["{bad_url}"]')], "end_turn"),
        ]

        with pytest.raises(ValueError, match="no reachable URLs"):
            search_articles("Entroncamento", "portuguese", 1, client)

    @patch("src.agents.search_agent.validate_url_reachable")
    def test_handles_pause_turn_before_tool_validation(self, mock_validate):
        good_url = "https://example.com/good"
        mock_validate.return_value = True

        client = MagicMock()
        client.messages.create.side_effect = [
            _response([], "pause_turn"),
            _response([_tool_use("tool-1", good_url)], "tool_use"),
            _response([_text_block(f'["{good_url}"]')], "end_turn"),
        ]

        urls = search_articles("Entroncamento", "portuguese", 1, client)

        assert urls == [good_url]
        assert client.messages.create.call_count == 3

    @patch("src.agents.search_agent.validate_url_reachable")
    def test_raises_when_final_response_is_not_parseable_json(self, mock_validate):
        good_url = "https://example.com/good"
        mock_validate.return_value = True

        client = MagicMock()
        client.messages.create.side_effect = [
            _response([_tool_use("tool-1", good_url)], "tool_use"),
            _response([_text_block("Sorry, I could not find any articles.")], "end_turn"),
        ]

        with pytest.raises(ValueError, match="could not parse URL list"):
            search_articles("Entroncamento", "portuguese", 1, client)


@pytest.mark.slow
def test_search_articles_returns_urls(anthropic_client):
    urls = search_articles("Entroncamento", "portuguese", 3, anthropic_client)

    assert isinstance(urls, list)
    assert len(urls) >= 1
    assert all(isinstance(url, str) and url.startswith("http") for url in urls)


@pytest.mark.slow
def test_search_articles_empty_result(anthropic_client):
    # A nonsense topic should yield no reachable URLs — either because Claude
    # finds nothing, validation filters everything out, or the response can't
    # be parsed as JSON.
    with pytest.raises(ValueError):
        search_articles(
            "xqzvwplm7719 fictional nonexistent gibberish topic",
            "portuguese",
            3,
            anthropic_client,
        )
