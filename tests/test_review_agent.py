"""
Tests for src/agents/review_agent.py.

Fast unit tests mock the Anthropic client. Slow tests make real API calls.
Run `uv run pytest -m "not slow"` to skip the integration tests.
"""

import logging
from unittest.mock import MagicMock

import anthropic
import pytest

from src.agents.review_agent import review_phrases
from src.schemas.article import CEFRLevel, ExtractedPhrase, PhraseCategory
from src.schemas.review import ReviewAction, ReviewVerdict, ReviewVerdicts
from src.utils.untrusted_content import UNTRUSTED_CONTENT_PREAMBLE
from tests.anthropic_mocks import mock_parsed_message


def test_prompt_wraps_phrase_list_as_untrusted_content():
    phrases = [
        ExtractedPhrase(
            phrase="teia de cumplicidades",
            sentence_context="numa teia de cumplicidades difícil de escapar",
            translation="Netz der Komplizenschaft",
            category=PhraseCategory.idiom,
            estimated_level=CEFRLevel.C1,
        )
    ]
    client = MagicMock()
    client.messages.parse.return_value = mock_parsed_message(
        ReviewVerdicts(
            verdicts=[
                ReviewVerdict(
                    phrase="teia de cumplicidades",
                    action=ReviewAction.keep,
                    reason="ok",
                )
            ]
        )
    )

    review_phrases(phrases, topic="Entroncamento", client=client)

    prompt = client.messages.parse.call_args.kwargs["messages"][0]["content"]
    assert client.messages.parse.call_args.kwargs["output_format"] is ReviewVerdicts
    assert UNTRUSTED_CONTENT_PREAMBLE in prompt
    assert "<untrusted_extracted_phrases>" in prompt
    assert "teia de cumplicidades" in prompt


def test_review_applies_keep_review_and_remove_actions():
    keep = ExtractedPhrase(
        phrase="keep-me",
        sentence_context="keep me in context",
        translation="behalten",
        category=PhraseCategory.vocab,
        estimated_level=CEFRLevel.C1,
    )
    remove = ExtractedPhrase(
        phrase="remove-me",
        sentence_context="remove me in context",
        translation="entfernen",
        category=PhraseCategory.vocab,
        estimated_level=CEFRLevel.C1,
    )
    flag = ExtractedPhrase(
        phrase="flag-me",
        sentence_context="flag me in context",
        translation="markieren",
        category=PhraseCategory.vocab,
        estimated_level=CEFRLevel.C1,
    )
    client = MagicMock()
    client.messages.parse.return_value = mock_parsed_message(
        ReviewVerdicts(
            verdicts=[
                ReviewVerdict(
                    phrase="remove-me",
                    action=ReviewAction.remove,
                    reason="topic derivative",
                ),
                ReviewVerdict(
                    phrase="flag-me",
                    action=ReviewAction.review,
                    reason="near duplicate",
                ),
                ReviewVerdict(
                    phrase="keep-me",
                    action=ReviewAction.keep,
                    reason="ok",
                ),
            ]
        )
    )

    reviewed = review_phrases([keep, remove, flag], topic="Entroncamento", client=client)

    assert [phrase.phrase for phrase in reviewed] == ["keep-me", "flag-me"]


def test_review_keeps_phrases_missing_from_verdicts():
    phrase = ExtractedPhrase(
        phrase="orphan",
        sentence_context="orphan in context",
        translation="Waise",
        category=PhraseCategory.vocab,
        estimated_level=CEFRLevel.C1,
    )
    client = MagicMock()
    client.messages.parse.return_value = mock_parsed_message(ReviewVerdicts(verdicts=[]))

    reviewed = review_phrases([phrase], topic="Entroncamento", client=client)

    assert [p.phrase for p in reviewed] == ["orphan"]


def test_review_raises_when_parsed_output_missing():
    phrases = [
        ExtractedPhrase(
            phrase="keep-me",
            sentence_context="keep me in context",
            translation="behalten",
            category=PhraseCategory.vocab,
            estimated_level=CEFRLevel.C1,
        )
    ]
    client = MagicMock()
    client.messages.parse.return_value = mock_parsed_message(None)

    with pytest.raises(ValueError, match="could not parse review verdicts"):
        review_phrases(phrases, topic="Entroncamento", client=client)


@pytest.mark.slow
def test_review_removes_proper_nouns(
    anthropic_client: anthropic.Anthropic, sample_phrases: list[ExtractedPhrase]
):
    reviewed = review_phrases(sample_phrases, topic="Entroncamento", client=anthropic_client)

    reviewed_text = [p.phrase for p in reviewed]
    assert "Entroncamento" not in reviewed_text
    assert len(reviewed) < len(sample_phrases)


@pytest.mark.slow
def test_review_flags_duplicates(
    anthropic_client: anthropic.Anthropic,
    sample_phrases: list[ExtractedPhrase],
    caplog: pytest.LogCaptureFixture,
):
    with caplog.at_level(logging.INFO, logger="src.agents.review_agent"):
        review_phrases(sample_phrases, topic="Entroncamento", client=anthropic_client)

    flagged_lines: list[str] = [
        line for line in caplog.text.splitlines() if "Flagged for review" in line
    ]

    assert len(flagged_lines) >= 1
    assert any(
        phrase in line
        for line in flagged_lines
        for phrase in ("comunidades marginalizadas", "marginalização")
    )
