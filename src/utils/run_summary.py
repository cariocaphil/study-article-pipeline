"""
Helpers for displaying a pre-run summary of pipeline inputs.
"""


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
        f"**Topic:** {topic} ({topic_type_label})\n\n"
        f"**Source language:** {source_language}\n\n"
        f"**Translation language:** {translation_language}\n\n"
        f"**Your CEFR level:** {user_level}\n\n"
        f"**Articles requested:** {n_articles}"
    )
