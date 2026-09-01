"""
Search agent.
Finds candidate article URLs written in the source language about the given topic.
Returns a list of raw URLs — no content fetching happens here.
"""

import json
import logging
from typing import cast

import anthropic
from anthropic.types import MessageParam, ToolResultBlockParam, ToolUnionParam

from src.schemas.article import TOPIC_TYPE_LABELS, TopicType
from src.tools.validate_url_reachable import validate_url_reachable
from src.utils.anthropic_retry import create_message_with_retry
from src.utils.anthropic_utils import as_tool_param, message_text, require_str_field
from src.utils.json_utils import extract_json
from src.utils.observability import UsageTracker, record_api_usage

logger = logging.getLogger(__name__)

VALIDATE_URL_TOOL = as_tool_param(
    {
        "name": "validate_url_reachable",
        "description": (
            "Check whether a URL is reachable via an HTTP HEAD request. "
            "Returns true for HTTP 2xx/3xx responses, false otherwise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to validate.",
                }
            },
            "required": ["url"],
        },
    }
)

WEB_SEARCH_TOOL: ToolUnionParam = cast(
    ToolUnionParam,
    {"type": "web_search_20250305", "name": "web_search"},
)


def _run_validate_url_tool(tool_input: object) -> bool:
    url = require_str_field(tool_input, "url")
    return validate_url_reachable(url)


def _topic_type_search_guidance(topic_type: TopicType) -> str:
    guidance = {
        TopicType.film: (
            "The topic is a film. Search for film reviews and cinema criticism — "
            "not TV series, book reviews, theatre reviews, or album reviews."
        ),
        TopicType.series: (
            "The topic is a TV series. Search for television reviews and series "
            "criticism — not the film adaptation, book, theatre production, or album."
        ),
        TopicType.book: (
            "The topic is a book. Search for literary reviews and book criticism — "
            "not film or TV adaptations, theatre productions, or album reviews unless "
            "they are clearly about the book itself."
        ),
        TopicType.theatre: (
            "The topic is a theatre production or stage play. Search for theatre "
            "reviews and performance criticism — not the film, TV series, novel, "
            "or album unless they are clearly about the stage production."
        ),
        TopicType.album: (
            "The topic is a music album. Search for album reviews and music criticism — "
            "not film, TV series, book, or theatre reviews."
        ),
    }
    return guidance[topic_type]


def search_articles(
    topic: str,
    source_language: str,
    n_articles: int,
    client: anthropic.Anthropic,
    *,
    topic_type: TopicType = TopicType.film,
    usage: UsageTracker | None = None,
) -> list[str]:
    topic_label = TOPIC_TYPE_LABELS[topic_type]

    prompt = f"""
You are a research assistant helping a language learner find articles to study.

Search for {n_articles} review articles about "{topic}" written in {source_language}.

Topic type: {topic_label}.
{_topic_type_search_guidance(topic_type)}

Requirements:
- Articles must be written IN {source_language} (not translated into it).
- Articles must be genuine reviews or critical analyses — not plot summaries,
  ticketing pages, trailers, or listicles.
- Prefer articles from established film/book/culture publications or blogs.
- Each article should come from a different source.

Before returning the list, validate each URL using the validate_url_reachable tool.
Only return URLs that are reachable.

Return ONLY a JSON array of URLs, with no other text, no markdown, no explanation.
Example format: ["https://...", "https://...", "https://..."]
"""

    messages: list[MessageParam] = [{"role": "user", "content": prompt}]
    validation_results: dict[str, bool] = {}
    response = None

    while True:
        response = create_message_with_retry(
            client,
            model="claude-sonnet-4-6",
            max_tokens=2000,
            tools=[WEB_SEARCH_TOOL, VALIDATE_URL_TOOL],
            messages=messages,
        )
        record_api_usage(response, agent="search_agent", usage=usage, logger=logger)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "tool_use":
            tool_results: list[ToolResultBlockParam] = []
            for block in response.content:
                if block.type != "tool_use" or block.name != "validate_url_reachable":
                    continue
                reachable = _run_validate_url_tool(block.input)
                url = require_str_field(block.input, "url")
                validation_results[url] = reachable
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(reachable),
                    }
                )
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
                continue

        if response.stop_reason == "pause_turn":
            continue

        break

    full_text = message_text(response)

    try:
        urls = extract_json(full_text, "[", "]")
    except ValueError as e:
        raise ValueError(f"Search agent could not parse URL list.\n{e}")

    if not isinstance(urls, list):
        raise ValueError(f"Search agent returned no URLs for topic '{topic}'.")

    reachable_urls = [
        url for url in urls if isinstance(url, str) and validation_results.get(url) is True
    ]

    if not reachable_urls:
        raise ValueError(f"Search agent returned no reachable URLs for topic '{topic}'.")

    logger.info("Found %d reachable URLs.", len(reachable_urls))
    return reachable_urls


# ── Manual test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    urls = search_articles(
        topic="Entroncamento",
        source_language="portuguese",
        n_articles=5,
        client=client,
    )
    for u in urls:
        print(u)
