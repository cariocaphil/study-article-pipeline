"""
Tests for src/agents/extract_agent.py.

Fast unit tests mock the Anthropic client and quote verifier. Slow tests make
real API calls. Run `uv run pytest -m "not slow"` to skip the integration tests.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agents.extract_agent import extract_phrases
from src.schemas.article import CEFRLevel, ExtractedPhrase, PhraseCategory


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_use(tool_id: str, sentence: str):
    return SimpleNamespace(
        type="tool_use",
        id=tool_id,
        name="verify_quote",
        input={"sentence": sentence},
    )


def _response(content, stop_reason: str):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


def _phrases_json(*items: dict) -> str:
    return json.dumps(list(items))


def _phrase_item(
    phrase: str,
    sentence_context: str,
    translation: str = "translation",
    category: str = "vocab",
    estimated_level: str = "C1",
) -> dict:
    return {
        "phrase": phrase,
        "sentence_context": sentence_context,
        "translation": translation,
        "category": category,
        "estimated_level": estimated_level,
    }


class TestExtractPhrasesToolLoop:
    @patch("src.agents.extract_agent.verify_quote")
    def test_returns_only_verified_quotes(self, mock_verify):
        article = "Laura foge de um passado turbulento."
        verified_sentence = "Laura foge de um passado turbulento."
        unverified_sentence = "Laura foge de um passado calmo."
        mock_verify.side_effect = lambda sentence, _: sentence == verified_sentence

        client = MagicMock()
        client.messages.create.side_effect = [
            _response(
                [
                    _tool_use("tool-1", verified_sentence),
                    _tool_use("tool-2", unverified_sentence),
                ],
                "tool_use",
            ),
            _response(
                [_text_block(_phrases_json(_phrase_item("turbulento", verified_sentence)))],
                "end_turn",
            ),
        ]

        phrases = extract_phrases(
            full_text=article,
            source_language="portuguese",
            translation_language="german",
            user_level=CEFRLevel.C1,
            client=client,
        )

        assert len(phrases) == 1
        assert phrases[0].phrase == "turbulento"
        assert phrases[0].sentence_context == verified_sentence

    @patch("src.agents.extract_agent.verify_quote")
    def test_drops_items_not_verified_by_tool(self, mock_verify):
        article = "Laura foge de um passado turbulento."
        verified_sentence = "Laura foge de um passado turbulento."
        mock_verify.return_value = True

        client = MagicMock()
        client.messages.create.side_effect = [
            _response([_tool_use("tool-1", verified_sentence)], "tool_use"),
            _response(
                [
                    _text_block(
                        _phrases_json(
                            _phrase_item("turbulento", verified_sentence),
                            _phrase_item("calmo", "Laura foge de um passado calmo."),
                        )
                    )
                ],
                "end_turn",
            ),
        ]

        phrases = extract_phrases(
            full_text=article,
            source_language="portuguese",
            translation_language="german",
            user_level=CEFRLevel.C1,
            client=client,
        )

        assert len(phrases) == 1
        assert phrases[0].sentence_context == verified_sentence
        mock_verify.assert_called_once_with(verified_sentence, article)

    @patch("src.agents.extract_agent.verify_quote")
    def test_skips_items_below_user_level_after_verification(self, mock_verify):
        article = "Laura foge de um passado turbulento."
        sentence = "Laura foge de um passado turbulento."
        mock_verify.return_value = True

        client = MagicMock()
        client.messages.create.side_effect = [
            _response([_tool_use("tool-1", sentence)], "tool_use"),
            _response(
                [_text_block(_phrases_json(_phrase_item("Laura", sentence, estimated_level="B1")))],
                "end_turn",
            ),
        ]

        phrases = extract_phrases(
            full_text=article,
            source_language="portuguese",
            translation_language="german",
            user_level=CEFRLevel.C1,
            client=client,
        )

        assert phrases == []

    @patch("src.agents.extract_agent.verify_quote")
    def test_raises_when_final_response_is_not_parseable_json(self, mock_verify):
        article = "Laura foge de um passado turbulento."
        sentence = "Laura foge de um passado turbulento."
        mock_verify.return_value = True

        client = MagicMock()
        client.messages.create.side_effect = [
            _response([_tool_use("tool-1", sentence)], "tool_use"),
            _response([_text_block("Sorry, I could not extract phrases.")], "end_turn"),
        ]

        with pytest.raises(ValueError, match="could not parse phrase list"):
            extract_phrases(
                full_text=article,
                source_language="portuguese",
                translation_language="german",
                user_level=CEFRLevel.C1,
                client=client,
            )


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
