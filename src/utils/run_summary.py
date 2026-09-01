"""
Helpers for displaying pre-run and post-run pipeline summaries.
"""

from src.schemas.pipeline_result import PipelineRunResult

_MARKDOWN_ESCAPE_CHARS = "\\`*_{}[]()#+-.!|"


def escape_markdown_text(text: str) -> str:
    """Escape user-controlled text before embedding it in Streamlit markdown."""
    normalized = " ".join(text.split())
    return "".join(f"\\{char}" if char in _MARKDOWN_ESCAPE_CHARS else char for char in normalized)


def format_run_summary(
    *,
    topic: str,
    topic_type_label: str,
    source_language: str,
    translation_language: str,
    user_level: str,
    n_articles: int,
) -> str:
    """
    Return markdown summarizing the pipeline run the user is about to start.
    """
    return (
        f"**Topic:** {escape_markdown_text(topic)} ({topic_type_label})\n\n"
        f"**Source language:** {source_language}\n\n"
        f"**Translation language:** {translation_language}\n\n"
        f"**Your CEFR level:** {user_level}\n\n"
        f"**Articles requested:** {n_articles}"
    )


def format_post_run_summary(result: PipelineRunResult) -> str:
    """
    Return markdown summarizing a completed pipeline run for the Streamlit UI.
    """
    if result.elapsed_seconds < 60:
        elapsed = f"{result.elapsed_seconds:.0f}s"
    else:
        elapsed = f"{result.elapsed_seconds / 60:.1f} min"

    return (
        f"**Run ID:** `{result.run_id}`\n\n"
        f"**Articles in document:** {result.articles_kept}\n\n"
        f"**Phrases extracted:** {result.phrase_count}\n\n"
        f"**Elapsed time:** {elapsed}\n\n"
        f"**API tokens:** {result.token_input:,} in / {result.token_output:,} out"
    )
