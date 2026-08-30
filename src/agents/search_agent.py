"""
Search agent.
Finds candidate article URLs written in the source language about the given topic.
Returns a list of raw URLs — no content fetching happens here.
"""

import json

import anthropic

from src.tools.validate_url_reachable import validate_url_reachable
from src.utils.json_utils import extract_json

VALIDATE_URL_TOOL = {
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


def _run_validate_url_tool(tool_input: dict) -> bool:
    url = tool_input["url"]
    return validate_url_reachable(url)


def search_articles(
    topic: str,
    source_language: str,
    n_articles: int,
    client: anthropic.Anthropic,
) -> list[str]:

    prompt = f"""
You are a research assistant helping a language learner find articles to study.

Search for {n_articles} review articles about "{topic}" written in {source_language}.

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

    messages = [{"role": "user", "content": prompt}]
    validation_results: dict[str, bool] = {}
    response = None

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            tools=[
                {"type": "web_search_20250305", "name": "web_search"},
                VALIDATE_URL_TOOL,
            ],
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use" or block.name != "validate_url_reachable":
                    continue
                reachable = _run_validate_url_tool(block.input)
                validation_results[block.input["url"]] = reachable
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

    full_text = " ".join(
        block.text for block in response.content if hasattr(block, "text")
    )

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

    print(f"[search_agent] Found {len(reachable_urls)} reachable URLs.")
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