"""
Extract agent.
Reads the full article text and extracts vocabulary, constructions, and idioms
that are at or above the user's CEFR level.
Returns a list of ExtractedPhrase objects.
"""

import json
import logging

import anthropic
from anthropic.types import MessageParam, ToolResultBlockParam

from src.schemas.article import CEFRLevel, ExtractedPhrase, PhraseCategory
from src.tools.validate_translation import validate_translation
from src.tools.verify_quote import verify_quote
from src.utils import load_skill
from src.utils.anthropic_utils import as_tool_param, message_text, require_str_field
from src.utils.json_utils import extract_json
from src.utils.observability import UsageTracker, record_api_usage

logger = logging.getLogger(__name__)

VERIFY_QUOTE_TOOL = as_tool_param(
    {
        "name": "verify_quote",
        "description": (
            "Check whether a sentence appears verbatim in the article text. "
            "Returns true if the sentence is an exact quote from the article, "
            "false otherwise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sentence": {
                    "type": "string",
                    "description": "The sentence to verify against the article.",
                }
            },
            "required": ["sentence"],
        },
    }
)


VALIDATE_TRANSLATION_TOOL = as_tool_param(
    {
        "name": "validate_translation",
        "description": (
            "Check whether a translation is valid for the source phrase. "
            "Returns true if the translation is non-empty and not identical "
            "to the source phrase, false otherwise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phrase": {
                    "type": "string",
                    "description": "The source-language phrase.",
                },
                "translation": {
                    "type": "string",
                    "description": "The proposed translation.",
                },
            },
            "required": ["phrase", "translation"],
        },
    }
)


def _run_verify_quote_tool(tool_input: object, article_text: str) -> bool:
    sentence = require_str_field(tool_input, "sentence")
    return verify_quote(sentence, article_text)


def _run_validate_translation_tool(tool_input: object) -> bool:
    phrase = require_str_field(tool_input, "phrase")
    translation = require_str_field(tool_input, "translation")
    return validate_translation(phrase, translation)


MAX_PARSE_ATTEMPTS = 3
CONTINUATION_PROMPT = (
    "Continue by calling verify_quote and validate_translation for each item. "
    "When finished, return ONLY the final JSON array with no other text, "
    "markdown, or explanation."
)
TRUNCATED_JSON_PROMPT = (
    "Your previous JSON array was cut off before it finished. "
    "Return ONLY the complete JSON array with all phrase objects. "
    "Keep each sentence_context as a verbatim quote. "
    "If needed, return fewer high-quality items so the full array fits. "
    "No markdown or explanation."
)


def _looks_truncated_json(text: str, open_char: str = "[", close_char: str = "]") -> bool:
    clean = text.strip()
    if open_char not in clean:
        return False
    start = clean.index(open_char)
    return close_char not in clean[start:]


def _parse_retry_prompt(response_text: str, stop_reason: str | None) -> str:
    if stop_reason == "max_tokens" or _looks_truncated_json(response_text):
        return TRUNCATED_JSON_PROMPT
    return CONTINUATION_PROMPT


def extract_phrases(
    full_text: str,
    source_language: str,
    translation_language: str,
    user_level: CEFRLevel,
    client: anthropic.Anthropic,
    *,
    usage: UsageTracker | None = None,
) -> list[ExtractedPhrase]:

    cefr_guide = load_skill("cefr-extraction-guide")

    prompt = f"""
You are a language teaching assistant helping a {user_level} level {source_language} learner
identify vocabulary and expressions worth studying.

## CEFR Level Reference
{cefr_guide}

Here is an article in {source_language}:

---
{full_text}
---

Extract vocabulary, constructions, and idioms from this article that would be
useful for a {user_level} level learner to acquire.

Rules:
- Only include items at or above {user_level} level. Skip anything a {user_level}
  learner almost certainly already knows.
- For each item provide:
    - phrase: the word, expression, or construction as it appears
    - sentence_context: the exact sentence from the article where it appears
    - translation: translation into {translation_language}
    - category: one of "vocab", "construction", or "idiom"
    - estimated_level: your estimate of its CEFR level (A1/A2/B1/B2/C1/C2)
- Aim for 8-15 items per article. Prioritise quality over quantity.
- Do not include proper nouns or character names.

Before returning the list, verify each sentence_context using the verify_quote tool.
Only return items whose sentence_context is verified as a verbatim quote from the article.
Validate each translation using the validate_translation tool.
Only return items whose translation is validated.

Do not list candidates or explain your process in prose. Use the tools directly,
then return the final JSON array.

Return ONLY a JSON array of objects with no other text, no markdown, no explanation.
Example format:
[
  {{
    "phrase": "...",
    "sentence_context": "...",
    "translation": "...",
    "category": "vocab",
    "estimated_level": "B2"
  }}
]
"""

    messages: list[MessageParam] = [{"role": "user", "content": prompt}]
    verification_results: dict[str, bool] = {}
    translation_results: dict[tuple[str, str], bool] = {}
    response = None
    raw_phrases = None
    parse_attempts = 0

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            tools=[VERIFY_QUOTE_TOOL, VALIDATE_TRANSLATION_TOOL],
            messages=messages,
        )
        record_api_usage(response, agent="extract_agent", usage=usage, logger=logger)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "tool_use":
            tool_results: list[ToolResultBlockParam] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                if block.name == "verify_quote":
                    verified = _run_verify_quote_tool(block.input, full_text)
                    sentence = require_str_field(block.input, "sentence")
                    verification_results[sentence] = verified
                    result = verified
                elif block.name == "validate_translation":
                    valid = _run_validate_translation_tool(block.input)
                    phrase = require_str_field(block.input, "phrase")
                    translation = require_str_field(block.input, "translation")
                    translation_key = (phrase, translation)
                    translation_results[translation_key] = valid
                    result = valid
                else:
                    continue

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
                continue

        full_response = message_text(response)
        try:
            raw_phrases = extract_json(full_response, "[", "]")
            break
        except ValueError as e:
            parse_attempts += 1
            if parse_attempts >= MAX_PARSE_ATTEMPTS:
                raise ValueError(f"Extract agent could not parse phrase list.\n{e}")
            messages.append(
                {
                    "role": "user",
                    "content": _parse_retry_prompt(full_response, response.stop_reason),
                }
            )
            continue

    if not isinstance(raw_phrases, list):
        raise ValueError(
            "Extract agent could not parse phrase list.\nExtract agent response was not a JSON array."
        )

    phrases = []
    for item in raw_phrases:
        sentence_context = item.get("sentence_context", "")
        phrase_text = item.get("phrase", "")
        translation_text = item.get("translation", "")

        if verification_results.get(sentence_context) is not True:
            logger.debug("Skipping unverified quote: %s", sentence_context[:80])
            continue

        if translation_results.get((phrase_text, translation_text)) is not True:
            logger.debug("Skipping invalid translation: %s", phrase_text[:80])
            continue

        try:
            phrase = ExtractedPhrase(
                phrase=phrase_text,
                sentence_context=sentence_context,
                translation=translation_text,
                category=PhraseCategory(item["category"]),
                estimated_level=CEFRLevel(item["estimated_level"]),
            )
            # Apply the floor filter — skip anything below user's level
            if phrase.estimated_level >= user_level:
                phrases.append(phrase)
        except (KeyError, ValueError) as e:
            logger.warning("Skipping malformed item: %s — %s", item, e)
            continue

    logger.info("Extracted %d phrases at or above %s.", len(phrases), user_level)
    return phrases


# ── Manual test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os

    from dotenv import load_dotenv

    load_dotenv()
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Paste a text sample from your filter agent output to test
    sample_text = """
    Em "Entroncamento" acompanhamos Laura, que foge de um passado turbulento,
    refugiando-se nesta cidade do distrito de Santarém para recomeçar a sua vida.
    Contudo, apesar de tentar encontrar um emprego honesto e uma vida melhor,
    começa a entrar em pequenos esquemas e crimes, motivados por familiares e
    conhecidos que a envolvem numa teia de cumplicidades difícil de escapar.
    """

    phrases = extract_phrases(
        full_text=sample_text,
        source_language="portuguese",
        translation_language="german",
        user_level=CEFRLevel.C1,
        client=client,
    )

    for p in phrases:
        print(f"\n[{p.category.value}] [{p.estimated_level.value}] {p.phrase}")
        print(f"  Context: {p.sentence_context}")
        print(f"  Translation: {p.translation}")
