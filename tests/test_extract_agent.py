"""
Tests for src/agents/extract_agent.py.

These make real calls to the Anthropic API, so they're marked slow.
Run `uv run pytest -m "not slow"` to skip them.
"""

import pytest

from src.agents.extract_agent import extract_phrases
from src.schemas.article import CEFRLevel, ExtractedPhrase


@pytest.mark.slow
def test_extract_phrases_returns_list(anthropic_client, sample_portuguese_text):
    phrases = extract_phrases(
        full_text=sample_portuguese_text,
        source_language="portuguese",
        translation_language="german",
        user_level=CEFRLevel.C1,
        client=anthropic_client,
    )

    assert isinstance(phrases, list)
    assert len(phrases) > 0
    assert all(isinstance(p, ExtractedPhrase) for p in phrases)


@pytest.mark.slow
def test_extract_phrases_respects_level_floor(anthropic_client, sample_portuguese_text):
    phrases = extract_phrases(
        full_text=sample_portuguese_text,
        source_language="portuguese",
        translation_language="german",
        user_level=CEFRLevel.C1,
        client=anthropic_client,
    )

    assert len(phrases) > 0
    for phrase in phrases:
        assert phrase.estimated_level >= CEFRLevel.C1


@pytest.mark.slow
def test_extract_phrases_validates_schema(anthropic_client, sample_portuguese_text):
    phrases = extract_phrases(
        full_text=sample_portuguese_text,
        source_language="portuguese",
        translation_language="german",
        user_level=CEFRLevel.C1,
        client=anthropic_client,
    )

    assert len(phrases) > 0
    for phrase in phrases:
        # Round-tripping through the model re-validates every field/type.
        revalidated = ExtractedPhrase.model_validate(phrase.model_dump())
        assert revalidated == phrase
