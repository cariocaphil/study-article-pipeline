"""
Tests for src/utils/run_summary.py.
"""

from src.schemas.pipeline_result import PipelineRunResult
from src.utils.run_summary import (
    escape_markdown_text,
    format_post_run_summary,
    format_run_summary,
)


def test_format_run_summary_includes_all_fields():
    summary = format_run_summary(
        topic="Amadeus",
        topic_type_label="Theatre production",
        source_language="english",
        translation_language="german",
        user_level="C1",
        n_articles=5,
    )

    assert "**Topic:** Amadeus (Theatre production)" in summary
    assert "**Source language:** english" in summary
    assert "**Translation language:** german" in summary
    assert "**Your CEFR level:** C1" in summary
    assert "**Articles requested:** 5" in summary


def test_escape_markdown_text_neutralizes_markdown_syntax():
    assert escape_markdown_text("**Amadeus**") == "\\*\\*Amadeus\\*\\*"
    assert escape_markdown_text("[click](http://evil.com)") == (
        "\\[click\\]\\(http://evil\\.com\\)"
    )


def test_format_run_summary_escapes_user_topic_markdown():
    summary = format_run_summary(
        topic="**Amadeus**",
        topic_type_label="Theatre production",
        source_language="english",
        translation_language="german",
        user_level="C1",
        n_articles=5,
    )

    assert "**Topic:** \\*\\*Amadeus\\*\\* (Theatre production)" in summary
    assert "**Topic:** **Amadeus**" not in summary


def test_format_post_run_summary_includes_key_metrics():
    summary = format_post_run_summary(
        PipelineRunResult(
            output_path="output/test.pdf",
            run_id="abc123",
            elapsed_seconds=95.0,
            articles_kept=5,
            phrase_count=42,
            token_input=12000,
            token_output=3500,
        )
    )

    assert "**Run ID:** `abc123`" in summary
    assert "**Articles in document:** 5" in summary
    assert "**Phrases extracted:** 42" in summary
    assert "**Elapsed time:** 1.6 min" in summary
    assert "**API tokens:** 12,000 in / 3,500 out" in summary
