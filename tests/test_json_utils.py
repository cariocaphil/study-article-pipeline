"""
Tests for src/utils/json_utils.py.

These cover the malformed-JSON patterns Claude has actually produced in
this pipeline (see git history), so regressions here would reproduce real
orchestrator crashes.
"""

import pytest

from src.utils.json_utils import extract_json


class TestExtractJsonHappyPath:
    def test_parses_clean_json_array(self):
        raw = '[{"phrase": "foo", "translation": "bar"}]'
        assert extract_json(raw, "[", "]") == [{"phrase": "foo", "translation": "bar"}]

    def test_parses_clean_json_object(self):
        raw = '{"is_review": true, "title": "Some Title"}'
        assert extract_json(raw, "{", "}") == {"is_review": True, "title": "Some Title"}

    def test_strips_markdown_fences(self):
        raw = '```json\n[{"a": 1}]\n```'
        assert extract_json(raw, "[", "]") == [{"a": 1}]

    def test_ignores_preamble_and_trailing_text(self):
        raw = (
            "Sure, here is the JSON you asked for:\n\n"
            '```json\n{"a": 1}\n```\n\n'
            "Let me know if you need anything else."
        )
        assert extract_json(raw, "{", "}") == {"a": 1}

    def test_normalizes_curly_quotes_embedded_in_a_string_value(self):
        # Curly quotes embedded inside a properly double-quoted value should
        # be normalized to single quotes rather than left as-is (which has
        # previously produced invalid escape sequences in LLM output).
        raw = '[{"phrase": "he said \u201chello\u201d to her"}]'
        assert extract_json(raw, "[", "]") == [{"phrase": "he said 'hello' to her"}]


class TestExtractJsonEmbeddedQuotes:
    """Regression tests for: Expecting ',' delimiter (unescaped inner quotes)."""

    def test_single_embedded_quoted_word(self):
        # Simulates raw (unescaped) LLM output: a straight quote embedded
        # inside a string value, as opposed to a properly escaped \".
        raw = (
            '{"sentence_context": '
            '"Este e o primeiro filme que filmou o "Entroncamento" no pais."}'
        )
        data = extract_json(raw, "{", "}")
        assert data["sentence_context"] == (
            'Este e o primeiro filme que filmou o "Entroncamento" no pais.'
        )

    def test_multiple_objects_with_embedded_quotes(self):
        raw = """```json
[
  {
    "phrase": "turbulento",
    "sentence_context": "Em "Entroncamento" acompanhamos Laura.",
    "translation": "turbulent",
    "category": "vocab",
    "estimated_level": "B2"
  },
  {
    "phrase": "opacidade",
    "sentence_context": "um "pacto de escuta" que permita conservar a opacidade.",
    "translation": "Undurchsichtigkeit",
    "category": "vocab",
    "estimated_level": "C1"
  }
]
```"""
        data = extract_json(raw, "[", "]")
        assert len(data) == 2
        assert data[0]["sentence_context"] == 'Em "Entroncamento" acompanhamos Laura.'
        assert data[1]["sentence_context"] == (
            'um "pacto de escuta" que permita conservar a opacidade.'
        )
        assert data[1]["translation"] == "Undurchsichtigkeit"


class TestExtractJsonQuoteFollowedByComma:
    """
    Regression tests for: Expecting property name enclosed in double quotes.

    A quoted phrase followed by a comma and more lowercase prose (very
    common in Portuguese dialogue/quotation style) must NOT be mistaken for
    the end of the JSON string value.
    """

    def test_quoted_dialogue_followed_by_comma_and_prose(self):
        # Simulates raw (unescaped) LLM output containing quoted dialogue.
        raw = (
            '{"full_text": "na noite lisboeta, de bebedeira e ganza, '
            '"depois de acabado o curso o que e que voces estao a pensarfazer?", '
            'com o ruido ambiente abafando a sua voz - '
            '"nao consigo ouvir, tens de falar mais alto" - ou como Maria."}'
        )
        data = extract_json(raw, "{", "}")
        assert data["full_text"] == (
            "na noite lisboeta, de bebedeira e ganza, "
            '"depois de acabado o curso o que e que voces estao a pensarfazer?", '
            "com o ruido ambiente abafando a sua voz - "
            '"nao consigo ouvir, tens de falar mais alto" - ou como Maria.'
        )

    def test_embedded_quoted_word_mid_sentence_before_next_key(self):
        raw = (
            '{"sentence_context": "ele disse "ola" no filme", '
            '"translation": "he said hello in the movie"}'
        )
        data = extract_json(raw, "{", "}")
        assert data["sentence_context"] == 'ele disse "ola" no filme'
        assert data["translation"] == "he said hello in the movie"

    def test_quote_before_new_array_element_still_closes_string(self):
        raw = (
            '[{"sentence_context": "ele disse "ola""}, {"sentence_context": "tchau"}]'
        )
        data = extract_json(raw, "[", "]")
        assert data[0]["sentence_context"] == 'ele disse "ola"'
        assert data[1]["sentence_context"] == "tchau"

    def test_full_original_bug_report_response(self):
        raw = """I found a search result. Let me compile everything into the JSON response.

```json
{
  "is_review": true,
  "is_correct_language": true,
  "title": "ENTRONCAMENTO - PEDRO CABELEIRA (2025)",
  "author": "Antonio Roma Torres",
  "source_name": "todaamemoriadomundo.com",
  "full_text": "Talvez Verao Danado (2017) tenha sido para Pedro Cabeleira uma falsa partida. na noite lisboeta, de bebedeira e ganza, "depois de acabado o curso o que e que voces estao a pensarfazer?", com o ruido ambiente abafando ou confundindo a sua voz - "nao consigo ouvir, tens de falar mais alto" - ou como Maria (Lia Carvalho) se nao e melhor abalar para Londres."
}
```"""
        data = extract_json(raw, "{", "}")
        assert data["is_review"] is True
        assert data["title"] == "ENTRONCAMENTO - PEDRO CABELEIRA (2025)"
        assert data["source_name"] == "todaamemoriadomundo.com"
        assert '"depois de acabado o curso' in data["full_text"]
        assert data["full_text"].endswith("para Londres.")


class TestExtractJsonFailureModes:
    def test_raises_value_error_when_no_brackets_present(self):
        with pytest.raises(ValueError, match="no brackets here"):
            extract_json("no brackets here", "[", "]")

    def test_raises_value_error_on_unrecoverable_malformed_json(self):
        raw = '[{"phrase": "foo", "translation": }]'
        with pytest.raises(ValueError, match="Raw response"):
            extract_json(raw, "[", "]")
