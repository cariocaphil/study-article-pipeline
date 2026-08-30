"""
Extract agent.
Reads the full article text and extracts vocabulary, constructions, and idioms
that are at or above the user's CEFR level.
Returns a list of ExtractedPhrase objects.
"""

import json

import anthropic
from src.schemas.article import ExtractedPhrase, CEFRLevel, PhraseCategory
from src.tools.validate_translation import validate_translation
from src.tools.verify_quote import verify_quote
from src.utils import load_skill
from src.utils.json_utils import extract_json

VERIFY_QUOTE_TOOL = {
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


VALIDATE_TRANSLATION_TOOL = {
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


def _run_verify_quote_tool(tool_input: dict, article_text: str) -> bool:
    return verify_quote(tool_input["sentence"], article_text)


def _run_validate_translation_tool(tool_input: dict) -> bool:
    return validate_translation(tool_input["phrase"], tool_input["translation"])


def extract_phrases(
    full_text: str,
    source_language: str,
    translation_language: str,
    user_level: CEFRLevel,
    client: anthropic.Anthropic,
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

    messages = [{"role": "user", "content": prompt}]
    verification_results: dict[str, bool] = {}
    translation_results: dict[tuple[str, str], bool] = {}
    response = None

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            tools=[VERIFY_QUOTE_TOOL, VALIDATE_TRANSLATION_TOOL],
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue

                if block.name == "verify_quote":
                    verified = _run_verify_quote_tool(block.input, full_text)
                    verification_results[block.input["sentence"]] = verified
                    result = verified
                elif block.name == "validate_translation":
                    valid = _run_validate_translation_tool(block.input)
                    translation_key = (block.input["phrase"], block.input["translation"])
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

        break

    full_response = " ".join(
        block.text for block in response.content if hasattr(block, "text")
    )

    try:
        raw_phrases = extract_json(full_response, "[", "]")
    except ValueError as e:
        raise ValueError(f"Extract agent could not parse phrase list.\n{e}")

    phrases = []
    for item in raw_phrases:
        sentence_context = item.get("sentence_context", "")
        phrase_text = item.get("phrase", "")
        translation_text = item.get("translation", "")

        if verification_results.get(sentence_context) is not True:
            print(
                f"[extract_agent] Skipping unverified quote: {sentence_context[:80]}"
            )
            continue

        if translation_results.get((phrase_text, translation_text)) is not True:
            print(
                f"[extract_agent] Skipping invalid translation: {phrase_text[:80]}"
            )
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
            print(f"[extract_agent] Skipping malformed item: {item} — {e}")
            continue

    print(f"[extract_agent] Extracted {len(phrases)} phrases at or above {user_level}.")
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