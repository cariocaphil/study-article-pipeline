"""Tests for src/prompts prompt loading."""

from src.agents.extract_agent import CONTINUATION_PROMPT, TRUNCATED_JSON_PROMPT
from src.prompts import load_prompt
from src.schemas.article import CEFRLevel
from src.utils.untrusted_content import UNTRUSTED_CONTENT_PREAMBLE


def test_load_prompt_raises_for_missing_file():
    try:
        load_prompt("does_not_exist")
    except FileNotFoundError:
        return
    raise AssertionError("Expected FileNotFoundError for missing prompt")


def test_extract_static_retry_prompts_match_previous_inline_text():
    assert CONTINUATION_PROMPT == (
        "Continue by calling verify_quote and validate_translation for each item. "
        "When finished, return ONLY the final JSON array with no other text, "
        "markdown, or explanation."
    )
    assert TRUNCATED_JSON_PROMPT == (
        "Your previous JSON array was cut off before it finished. "
        "Return ONLY the complete JSON array with all phrase objects. "
        "Keep each sentence_context as a verbatim quote. "
        "If needed, return fewer high-quality items so the full array fits. "
        "No markdown or explanation."
    )


def test_search_articles_prompt_interpolates_variables():
    prompt = load_prompt(
        "search_articles",
        n_articles=3,
        topic="Madre (2017)",
        source_language="spanish",
        topic_label="film",
        topic_type_guidance="The topic is a film.",
        disambiguation_section="\nDisambiguation: keep Madre.\n",
    )

    assert 'review articles about "Madre (2017)" written in spanish' in prompt
    assert "Topic type: film." in prompt
    assert "The topic is a film." in prompt
    assert "Disambiguation: keep Madre." in prompt
    assert "validate_url_reachable" in prompt


def test_filter_article_prompt_renders_literal_json_braces():
    prompt = load_prompt(
        "filter_article",
        filter_criteria="Accept genuine reviews.",
        untrusted_content_preamble=UNTRUSTED_CONTENT_PREAMBLE,
        url="https://example.com/review",
        source_language="portuguese",
    )

    assert "Accept genuine reviews." in prompt
    assert "Fetch this URL and assess it: https://example.com/review" in prompt
    assert '"is_review": true or false' in prompt
    assert "{{" not in prompt


def test_extract_phrases_prompt_uses_cefr_level_enum_string():
    prompt = load_prompt(
        "extract_phrases",
        user_level=CEFRLevel.C1,
        source_language="portuguese",
        cefr_guide="CEFR guide body",
        untrusted_content_preamble=UNTRUSTED_CONTENT_PREAMBLE,
        wrapped_article="<article>texto</article>",
        translation_language="german",
    )

    assert "helping a C1 level portuguese learner" in prompt
    assert "translation into german" in prompt
    assert "<article>texto</article>" in prompt
    assert '"category": "vocab"' in prompt


def test_review_and_judge_prompts_render():
    review = load_prompt(
        "review_phrases",
        reviewer_guide="Reviewer guide",
        topic="Entroncamento",
        untrusted_content_preamble=UNTRUSTED_CONTENT_PREAMBLE,
        wrapped_phrase_list='[{"phrase": "x"}]',
    )
    judge = load_prompt(
        "judge_translation",
        rubric="Rubric body",
        source_language="portuguese",
        translation_language="german",
        phrase="saudade",
        sentence_context="Sinto saudade.",
        translation="Sehnsucht",
    )

    assert 'topic of the article this phrase list was extracted from is: "Entroncamento"' in review
    assert '"action": "keep"' in review
    assert "Proposed translation: Sehnsucht" in judge
    assert '{"adequate": true' in judge
