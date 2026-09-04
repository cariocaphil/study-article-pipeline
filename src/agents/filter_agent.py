"""
Filter agent.
For each candidate URL:
  1. Fetches the page content via Claude's web search.
  2. Confirms it is a genuine review or critical article.
  3. Extracts: title, author, source_name, full_text.
Discards URLs that fail the review check.

URL checks run concurrently with a bounded thread pool so Anthropic +
web_search latency overlaps across candidates.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import cast

import anthropic
from anthropic.types import ToolUnionParam

from src.prompts import load_prompt
from src.schemas.article import FilteredArticle
from src.utils import load_skill
from src.utils.anthropic_retry import create_message_with_retry
from src.utils.anthropic_utils import message_text
from src.utils.json_utils import extract_json
from src.utils.observability import UsageTracker, record_api_usage
from src.utils.untrusted_content import UNTRUSTED_CONTENT_PREAMBLE

logger = logging.getLogger(__name__)

DEFAULT_FILTER_WORKERS = 3

WEB_SEARCH_TOOL: ToolUnionParam = cast(
    ToolUnionParam,
    {"type": "web_search_20250305", "name": "web_search"},
)


def _filter_one_url(
    url: str,
    *,
    source_language: str,
    filter_criteria: str,
    client: anthropic.Anthropic,
    usage: UsageTracker | None,
) -> FilteredArticle | None:
    logger.info("Checking URL: %s", url)

    prompt = load_prompt(
        "filter_article",
        filter_criteria=filter_criteria,
        untrusted_content_preamble=UNTRUSTED_CONTENT_PREAMBLE,
        url=url,
        source_language=source_language,
    )

    response = create_message_with_retry(
        client,
        model="claude-sonnet-4-6",
        max_tokens=4000,
        tools=[WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": prompt}],
    )
    record_api_usage(response, agent="filter_agent", usage=usage, logger=logger)

    full_text = message_text(response)

    try:
        data = extract_json(full_text, "{", "}")
    except ValueError as e:
        logger.warning("Could not parse response for %s: %s", url, e)
        return None

    if not isinstance(data, dict):
        logger.warning("Could not parse response for %s: expected JSON object", url)
        return None

    parsed = cast(dict[str, object], data)

    if not parsed.get("is_review") or not parsed.get("is_correct_language"):
        logger.info("Rejected URL: %s", url)
        return None

    title = parsed.get("title", "")
    author = parsed.get("author")
    source_name = parsed.get("source_name", "")
    article_text = parsed.get("full_text", "")

    article: FilteredArticle = {
        "title": title if isinstance(title, str) else "",
        "author": author if isinstance(author, str) else None,
        "url": url,
        "source_name": source_name if isinstance(source_name, str) else "",
        "full_text": article_text if isinstance(article_text, str) else "",
    }
    accepted_title = title if isinstance(title, str) else url
    logger.info("Accepted article: %s", accepted_title)
    return article


def filter_articles(
    urls: list[str],
    source_language: str,
    client: anthropic.Anthropic,
    *,
    usage: UsageTracker | None = None,
    max_workers: int = DEFAULT_FILTER_WORKERS,
) -> list[FilteredArticle]:
    if not urls:
        return []

    filter_criteria = load_skill("article-filter-criteria")
    workers = max(1, min(max_workers, len(urls)))

    def _task(url: str) -> FilteredArticle | None:
        return _filter_one_url(
            url,
            source_language=source_language,
            filter_criteria=filter_criteria,
            client=client,
            usage=usage,
        )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # map preserves input URL order among completed futures
        evaluated = list(executor.map(_task, urls))

    return [article for article in evaluated if article is not None]


# ── Manual test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Paste one URL from the search agent output to test
    test_urls = [
        "https://www.magazine-hd.com/apps/wp/entroncamento-critica-filme-pedro-cabeleira-ana-vilaca/",
    ]

    articles = filter_articles(test_urls, "portuguese", client)
    for a in articles:
        print(f"\nTitle: {a['title']}")
        print(f"Author: {a['author']}")
        print(f"Source: {a['source_name']}")
        print(f"Text preview: {a['full_text'][:300]}...")
