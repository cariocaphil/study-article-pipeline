"""
Search agent.
Finds candidate article URLs written in the source language about the given topic.
Returns a list of raw URLs — no content fetching happens here.
"""

import json
import anthropic


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

Return ONLY a JSON array of URLs, with no other text, no markdown, no explanation.
Example format: ["https://...", "https://...", "https://..."]
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": prompt}],
    )

    full_text = " ".join(
        block.text for block in response.content if hasattr(block, "text")
    )

    try:
        clean = full_text.strip().strip("```json").strip("```").strip()
        start = clean.index("[")
        end = clean.rindex("]") + 1
        urls = json.loads(clean[start:end])
    except (ValueError, json.JSONDecodeError) as e:
        raise ValueError(
            f"Search agent could not parse URL list.\n"
            f"Raw response: {full_text}\nError: {e}"
        )

    if not isinstance(urls, list) or len(urls) == 0:
        raise ValueError(f"Search agent returned no URLs for topic '{topic}'.")

    print(f"[search_agent] Found {len(urls)} candidate URLs.")
    return urls


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