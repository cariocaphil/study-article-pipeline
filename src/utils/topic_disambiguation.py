"""Helpers for preserving topic identity metadata in search prompts."""

from __future__ import annotations

import re

from src.schemas.article import TOPIC_TYPE_LABELS, TopicType

_TRAILING_RELEASE_YEAR = re.compile(r"^(?P<base>.+?)\s*\(\s*(?P<year>(?:19|20)\d{2})\s*\)\s*$")


def parse_optional_release_year(topic: str) -> tuple[str, int | None]:
    """Return the base title and trailing release/publication year when present."""
    match = _TRAILING_RELEASE_YEAR.match(topic.strip())
    if match is None:
        return topic.strip(), None

    return match.group("base").strip(), int(match.group("year"))


def topic_disambiguation_guidance(
    topic: str,
    topic_type: TopicType,
) -> str:
    """Return prompt text that keeps title, content type, and year aligned."""
    _, release_year = parse_optional_release_year(topic)
    if release_year is None:
        return ""

    topic_label = TOPIC_TYPE_LABELS[topic_type]
    return (
        f'Disambiguation: the user requested the {topic_label} "{topic}" exactly as written. '
        f"The year {release_year} is identifying metadata — use it to find the correct work. "
        "Do not substitute a different work because the title translates, sounds similar, "
        "or shares the same release year. "
        "Prefer reviews whose title or metadata refer to the entered title, "
        f"{topic_label} type, and year {release_year}."
    )
