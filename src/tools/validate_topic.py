"""
Topic validator.
Checks that a pipeline topic is non-empty, within length limits, and safe
to use in filenames and agent prompts.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

MAX_TOPIC_LENGTH = 200

UNSAFE_TOPIC_CHARS = re.compile(r'[/\\:*"<>|\x00]')
FILENAME_UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|]')
INJECTION_PATTERN = re.compile(r"(?i)(ignore\s+(all\s+)?previous|system\s*:|<\s*/?\s*script\b|```)")


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


def filename_safe_topic(topic: str) -> str:
    """
    Strip filesystem-unsafe characters and spaces for output filenames.
    """
    sanitized = FILENAME_UNSAFE_CHARS.sub("", topic.strip())
    return sanitized.replace(" ", "_")


def validate_topic(topic: str, *, quiet: bool = False) -> bool:
    """
    Return True when topic passes basic input guardrails.
    """
    valid = topic_validation_error(topic) is None

    if not quiet:
        status_label = "valid" if valid else "invalid"
        logger.info("%r → %s", topic, status_label)
    return valid
