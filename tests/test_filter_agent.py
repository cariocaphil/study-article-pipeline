"""
Tests for src/agents/filter_agent.py.

These make real calls to the Anthropic API (with web search enabled), so
they're marked slow. Run `uv run pytest -m "not slow"` to skip them.

Uses hand-picked URLs expected to remain stable over time. If a target site
goes offline or is redesigned, these tests may need a replacement URL.
"""

import pytest

from src.agents.filter_agent import filter_articles

GOOD_REVIEW_URL = (
    "https://www.magazine-hd.com/apps/wp/entroncamento-critica-filme-pedro-cabeleira-ana-vilaca/"
)
SYNOPSIS_URL = "https://en.wikipedia.org/wiki/The_Shawshank_Redemption"


@pytest.mark.slow
def test_filter_articles_accepts_good_review(anthropic_client):
    results = filter_articles([GOOD_REVIEW_URL], "portuguese", anthropic_client)

    assert len(results) == 1
    article = results[0]
    assert article["title"]
    assert "author" in article
    assert article["source_name"]
    assert len(article["full_text"]) > 200


@pytest.mark.slow
def test_filter_articles_rejects_synopsis(anthropic_client):
    results = filter_articles([SYNOPSIS_URL], "english", anthropic_client)

    urls_in_results = [r["url"] for r in results]
    assert SYNOPSIS_URL not in urls_in_results
