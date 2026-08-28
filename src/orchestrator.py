"""
Orchestrator.
Wires the four agents together in sequence.
Handles inputs, fallback logic, and file naming.
"""

import os
import anthropic
from dotenv import load_dotenv

from src.schemas.article import (
    Article, CEFRLevel, PipelineOutput
)
from src.agents.search_agent import search_articles
from src.agents.filter_agent import filter_articles
from src.agents.extract_agent import extract_phrases
from src.agents.compile_agent import compile_document

load_dotenv()

MIN_ARTICLES = 3


def run_pipeline(
    topic: str,
    source_language: str,
    translation_language: str,
    user_level: str,
    n_articles: int = 5,
) -> str:
    """
    Runs the full pipeline and returns the path to the generated .docx.
    """

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    level = CEFRLevel(user_level.upper())

    print(f"\n── Starting pipeline ──────────────────────────────────────")
    print(f"Topic: {topic}")
    print(f"Source language: {source_language}")
    print(f"Translation language: {translation_language}")
    print(f"User level: {level.value}")
    print(f"Articles requested: {n_articles}")
    print(f"───────────────────────────────────────────────────────────\n")

    # ── Step 1: Search ────────────────────────────────────────────────────────
    urls = search_articles(topic, source_language, n_articles, client)

    # ── Step 2: Filter ────────────────────────────────────────────────────────
    raw_articles = filter_articles(urls, source_language, client)

    if len(raw_articles) < MIN_ARTICLES:
        raise ValueError(
            f"Pipeline stopped: only {len(raw_articles)} article(s) passed the filter "
            f"(minimum is {MIN_ARTICLES}). Try a different topic or broaden the search."
        )

    # ── Step 3: Extract ───────────────────────────────────────────────────────
    articles = []
    for raw in raw_articles:
        phrases = extract_phrases(
            full_text=raw["full_text"],
            source_language=source_language,
            translation_language=translation_language,
            user_level=level,
            client=client,
        )
        articles.append(Article(
            title=raw["title"],
            author=raw["author"],
            url=raw["url"],
            source_name=raw["source_name"],
            full_text=raw["full_text"],
            phrases=phrases,
        ))

    # ── Step 4: Compile ───────────────────────────────────────────────────────
    pipeline_output = PipelineOutput(
        topic=topic,
        source_language=source_language,
        translation_language=translation_language,
        user_level=level,
        articles=articles,
    )

    filename = (
        f"{topic.replace(' ', '_')}_{source_language}_{translation_language}_{level.value}.docx"
    )
    output_path = os.path.join("output", filename)
    os.makedirs("output", exist_ok=True)

    return compile_document(pipeline_output, output_path)


# ── Manual test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_pipeline(
        topic="Entroncamento",
        source_language="portuguese",
        translation_language="german",
        user_level="C1",
        n_articles=5,
    )