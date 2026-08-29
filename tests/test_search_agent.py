"""
Tests for src/agents/search_agent.py.

These make real calls to the Anthropic API (with web search enabled), so
they're marked slow. Run `uv run pytest -m "not slow"` to skip them.
"""

import pytest

from src.agents.search_agent import search_articles


@pytest.mark.slow
def test_search_articles_returns_urls(anthropic_client):
    urls = search_articles("Entroncamento", "portuguese", 3, anthropic_client)

    assert isinstance(urls, list)
    assert len(urls) >= 1
    assert all(isinstance(url, str) and url.startswith("http") for url in urls)


@pytest.mark.slow
def test_search_articles_empty_result(anthropic_client):
    # A nonsense, non-existent topic should yield no genuine review articles
    # — search_agent raises ValueError either because the URL list comes
    # back empty, or because Claude's refusal/explanation text can't be
    # parsed as JSON. Either path is an acceptable failure mode here.
    with pytest.raises(ValueError):
        search_articles(
            "xqzvwplm7719 fictional nonexistent gibberish topic",
            "portuguese",
            3,
            anthropic_client,
        )
