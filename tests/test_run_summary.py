"""
Tests for src/utils/run_summary.py.
"""

from src.utils.run_summary import format_run_summary


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
