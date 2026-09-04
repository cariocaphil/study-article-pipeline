"""
Orchestrator.
Wires the four agents together in sequence.
Handles inputs, fallback logic, and file naming.
"""

import logging
import os
import time

import anthropic
from dotenv import load_dotenv

from src.agents.compile_agent import compile_document
from src.agents.extract_agent import extract_phrases
from src.agents.filter_agent import filter_articles
from src.agents.review_agent import review_phrases
from src.agents.search_agent import search_articles
from src.schemas.article import Article, CEFRLevel, PipelineOutput, TopicType
from src.schemas.pipeline_result import PipelineRunResult
from src.tools.validate_topic import filename_safe_topic, topic_validation_error
from src.utils.observability import (
    StageCallback,
    StageTimer,
    UsageTracker,
    configure_logging,
    new_run_id,
)

load_dotenv()

logger = logging.getLogger(__name__)

MIN_ARTICLES = 3


def run_pipeline(
    topic: str,
    source_language: str,
    translation_language: str,
    user_level: str,
    n_articles: int = 5,
    *,
    topic_type: TopicType = TopicType.film,
    on_stage: StageCallback | None = None,
) -> PipelineRunResult:
    """
    Runs the full pipeline and returns metrics plus the path to the generated PDF.
    """

    configure_logging()

    validation_error = topic_validation_error(topic)
    if validation_error:
        raise ValueError(validation_error)
    topic = topic.strip()

    run_id = new_run_id()
    started_at = time.perf_counter()
    stage_timer = StageTimer()
    usage = UsageTracker()

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    level = CEFRLevel(user_level.upper())

    logger.info(
        "run_id=%s stage=start topic=%r topic_type=%s source=%s translation=%s level=%s n_articles=%d",
        run_id,
        topic,
        topic_type.value,
        source_language,
        translation_language,
        level.value,
        n_articles,
    )

    # ── Step 1: Search ────────────────────────────────────────────────────────
    with stage_timer.track("search", on_stage):
        urls = search_articles(
            topic,
            source_language,
            n_articles,
            client,
            topic_type=topic_type,
            usage=usage,
        )

    # ── Step 2: Filter ────────────────────────────────────────────────────────
    with stage_timer.track("filter", on_stage):
        raw_articles = filter_articles(urls, source_language, client, usage=usage)

    if len(raw_articles) < MIN_ARTICLES:
        raise ValueError(
            f"Pipeline stopped: only {len(raw_articles)} article(s) passed the filter "
            f"(minimum is {MIN_ARTICLES}). Try a different topic or broaden the search."
        )

    # ── Step 3: Extract + review ──────────────────────────────────────────────
    articles: list[Article] = []
    with stage_timer.track("extract", on_stage):
        for raw in raw_articles:
            phrases = extract_phrases(
                full_text=raw["full_text"],
                source_language=source_language,
                translation_language=translation_language,
                user_level=level,
                client=client,
                usage=usage,
            )
            phrases = review_phrases(phrases, topic, client, usage=usage)
            articles.append(
                Article(
                    title=raw["title"],
                    author=raw["author"],
                    url=raw["url"],
                    source_name=raw["source_name"],
                    full_text=raw["full_text"],
                    phrases=phrases,
                )
            )

    # ── Step 4: Compile ───────────────────────────────────────────────────────
    pipeline_output = PipelineOutput(
        topic=topic,
        topic_type=topic_type,
        source_language=source_language,
        translation_language=translation_language,
        user_level=level,
        articles=articles,
    )

    filename = (
        f"{filename_safe_topic(topic)}_{source_language}_{translation_language}_{level.value}.pdf"
    )
    output_path = os.path.join("output", filename)
    os.makedirs("output", exist_ok=True)

    with stage_timer.track("compile", on_stage):
        compile_document(pipeline_output, output_path)

    phrase_count = sum(len(article.phrases) for article in articles)
    elapsed_seconds = time.perf_counter() - started_at

    logger.info(
        "run_id=%s stage=complete output=%s urls=%d articles=%d phrases=%d elapsed=%.1fs "
        "tokens_in=%d tokens_out=%d stages=%s",
        run_id,
        output_path,
        len(urls),
        len(articles),
        phrase_count,
        elapsed_seconds,
        usage.input_tokens,
        usage.output_tokens,
        stage_timer.seconds,
    )

    return PipelineRunResult(
        output_path=output_path,
        run_id=run_id,
        elapsed_seconds=elapsed_seconds,
        stage_seconds=dict(stage_timer.seconds),
        urls_found=len(urls),
        articles_kept=len(articles),
        phrase_count=phrase_count,
        token_input=usage.input_tokens,
        token_output=usage.output_tokens,
    )


# ── Manual test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 5:
        print(
            "Usage: python -m src.orchestrator <topic> <source_language> "
            "<translation_language> <cefr_level> [topic_type] [n_articles]"
        )
        print("topic_type: film (default), series, book, theatre, album")
        sys.exit(1)

    topic_type = TopicType.film
    n_articles = 5
    if len(sys.argv) > 5:
        if sys.argv[5].isdigit():
            n_articles = int(sys.argv[5])
        else:
            topic_type = TopicType(sys.argv[5])
            if len(sys.argv) > 6:
                n_articles = int(sys.argv[6])

    try:
        result = run_pipeline(
            topic=sys.argv[1],
            source_language=sys.argv[2],
            translation_language=sys.argv[3],
            user_level=sys.argv[4],
            n_articles=n_articles,
            topic_type=topic_type,
        )
        print(f"Document saved to {result.output_path}")
        print(
            f"Run {result.run_id}: {result.articles_kept} articles, "
            f"{result.phrase_count} phrases, {result.elapsed_seconds:.1f}s"
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
