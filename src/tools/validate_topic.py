"""
Topic validator.
Checks that a pipeline topic is non-empty, within length limits, and safe
to use in filenames and agent prompts.
"""

from __future__ import annotations

import re

MAX_TOPIC_LENGTH = 200

UNSAFE_TOPIC_CHARS = re.compile(r'[/\\:*?"<>|\x00]')
INJECTION_PATTERN = re.compile(
    r"(?i)(ignore\s+(all\s+)?previous|system\s*:|<\s*/?\s*script\b|```)"
)


def topic_validation_error(topic: str) -> str | None:
    """
    Return an error message when topic is invalid, otherwise None.
    """
    stripped = topic.strip()
    if not stripped:
        return "Please enter a topic."
    if len(stripped) > MAX_TOPIC_LENGTH:
        return f"Topic is too long (maximum is {MAX_TOPIC_LENGTH} characters)."
    if UNSAFE_TOPIC_CHARS.search(stripped):
        return "Topic contains characters that are not allowed."
    if INJECTION_PATTERN.search(stripped):
        return "Topic contains disallowed content."
    return None


def validate_topic(topic: str, *, quiet: bool = False) -> bool:
    """
    Return True when topic passes basic input guardrails.
    """
    valid = topic_validation_error(topic) is None

    if not quiet:
        status_label = "valid" if valid else "invalid"
        print(f"[topic_validator] {topic!r} → {status_label}")
    return valid
