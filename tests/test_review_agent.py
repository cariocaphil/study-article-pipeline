"""
Tests for src/agents/review_agent.py.

Fast unit tests mock the Anthropic client. Slow tests make real API calls.
Run `uv run pytest -m "not slow"` to skip the integration tests.
"""

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agents.review_agent import review_phrases
from src.schemas.article import CEFRLevel, ExtractedPhrase, PhraseCategory
from src.utils.untrusted_content import UNTRUSTED_CONTENT_PREAMBLE
from tests.anthropic_mocks import mock_message


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


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
    client.messages.create.return_value = mock_message(
        [
            _text_block(
                json.dumps(
                    [{"phrase": "teia de cumplicidades", "action": "keep", "reason": "ok"}]
                )
            )
        ],
        "end_turn",
    )

    review_phrases(phrases, topic="Entroncamento", client=client)

    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert UNTRUSTED_CONTENT_PREAMBLE in prompt
    assert "<untrusted_extracted_phrases>" in prompt
    assert "teia de cumplicidades" in prompt


@pytest.mark.slow
def test_review_removes_proper_nouns(anthropic_client, sample_phrases):
    reviewed = review_phrases(sample_phrases, topic="Entroncamento", client=anthropic_client)

    reviewed_text = [p.phrase for p in reviewed]
    assert "Entroncamento" not in reviewed_text
    assert len(reviewed) < len(sample_phrases)


@pytest.mark.slow
def test_review_flags_duplicates(anthropic_client, sample_phrases, caplog):
    with caplog.at_level(logging.INFO, logger="src.agents.review_agent"):
        review_phrases(sample_phrases, topic="Entroncamento", client=anthropic_client)

    flagged_lines = [line for line in caplog.text.splitlines() if "Flagged for review" in line]

    assert len(flagged_lines) >= 1
    assert any(
        phrase in line
        for line in flagged_lines
        for phrase in ("comunidades marginalizadas", "marginalização")
    )
