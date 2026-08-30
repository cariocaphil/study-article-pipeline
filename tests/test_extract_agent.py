"""
Tests for src/agents/extract_agent.py.

Fast unit tests mock the Anthropic client and validation tools. Slow tests make
real API calls. Run `uv run pytest -m "not slow"` to skip the integration tests.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agents.extract_agent import extract_phrases
from src.schemas.article import CEFRLevel, ExtractedPhrase


def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _verify_quote_tool_use(tool_id: str, sentence: str):
    return SimpleNamespace(
        type="tool_use",
        id=tool_id,
        name="verify_quote",
        input={"sentence": sentence},
    )


def _validate_translation_tool_use(tool_id: str, phrase: str, translation: str):
    return SimpleNamespace(
        type="tool_use",
        id=tool_id,
        name="validate_translation",
        input={"phrase": phrase, "translation": translation},
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


@patch("src.agents.extract_agent.validate_translation")
@patch("src.agents.extract_agent.verify_quote")
class TestExtractPhrasesToolLoop:
    def test_returns_only_verified_quotes_and_translations(
        self, mock_verify, mock_validate
    ):
        article = "Laura foge de um passado turbulento."
        verified_sentence = "Laura foge de um passado turbulento."
        unverified_sentence = "Laura foge de um passado calmo."
        mock_verify.side_effect = lambda sentence, _: sentence == verified_sentence
        mock_validate.side_effect = (
            lambda phrase, translation: translation != phrase
        )

        client = MagicMock()
        client.messages.create.side_effect = [
            _response(
                [
                    _verify_quote_tool_use("tool-1", verified_sentence),
                    _verify_quote_tool_use("tool-2", unverified_sentence),
                    _validate_translation_tool_use("tool-3", "turbulento", "turbulent"),
                ],
                "tool_use",
            ),
            _response(
                [
                    _text_block(
                        _phrases_json(
                            _phrase_item(
                                "turbulento",
                                verified_sentence,
                                translation="turbulent",
                            )
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
        assert phrases[0].phrase == "turbulento"
        assert phrases[0].sentence_context == verified_sentence
        assert phrases[0].translation == "turbulent"

    def test_drops_items_not_verified_by_quote_tool(self, mock_verify, mock_validate):
        article = "Laura foge de um passado turbulento."
        verified_sentence = "Laura foge de um passado turbulento."
        mock_verify.return_value = True
        mock_validate.return_value = True

        client = MagicMock()
        client.messages.create.side_effect = [
            _response(
                [
                    _verify_quote_tool_use("tool-1", verified_sentence),
                    _validate_translation_tool_use("tool-2", "turbulento", "turbulent"),
                ],
                "tool_use",
            ),
            _response(
                [
                    _text_block(
                        _phrases_json(
                            _phrase_item(
                                "turbulento",
                                verified_sentence,
                                translation="turbulent",
                            ),
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

    def test_drops_items_not_validated_by_translation_tool(
        self, mock_verify, mock_validate
    ):
        article = "Laura foge de um passado turbulento."
        verified_sentence = "Laura foge de um passado turbulento."
        mock_verify.return_value = True
        mock_validate.side_effect = (
            lambda phrase, translation: translation == "turbulent"
        )

        client = MagicMock()
        client.messages.create.side_effect = [
            _response(
                [
                    _verify_quote_tool_use("tool-1", verified_sentence),
                    _validate_translation_tool_use("tool-3", "turbulento", "turbulent"),
                ],
                "tool_use",
            ),
            _response(
                [
                    _text_block(
                        _phrases_json(
                            _phrase_item(
                                "turbulento",
                                verified_sentence,
                                translation="turbulent",
                            ),
                            _phrase_item(
                                "calmo",
                                verified_sentence,
                                translation="calmo",
                            ),
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
        assert phrases[0].phrase == "turbulento"

    def test_skips_items_below_user_level_after_validation(
        self, mock_verify, mock_validate
    ):
        article = "Laura foge de um passado turbulento."
        sentence = "Laura foge de um passado turbulento."
        mock_verify.return_value = True
        mock_validate.return_value = True

        client = MagicMock()
        client.messages.create.side_effect = [
            _response(
                [
                    _verify_quote_tool_use("tool-1", sentence),
                    _validate_translation_tool_use("tool-2", "Laura", "Laura"),
                ],
                "tool_use",
            ),
            _response(
                [
                    _text_block(
                        _phrases_json(
                            _phrase_item("Laura", sentence, translation="Laura", estimated_level="B1")
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

        assert phrases == []

    def test_raises_when_final_response_is_not_parseable_json(
        self, mock_verify, mock_validate
    ):
        article = "Laura foge de um passado turbulento."
        sentence = "Laura foge de um passado turbulento."
        mock_verify.return_value = True
        mock_validate.return_value = True

        client = MagicMock()
        client.messages.create.side_effect = [
            _response(
                [
                    _verify_quote_tool_use("tool-1", sentence),
                    _validate_translation_tool_use("tool-2", "turbulento", "turbulent"),
                ],
                "tool_use",
            ),
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
