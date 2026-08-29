"""
Extract agent.
Reads the full article text and extracts vocabulary, constructions, and idioms
that are at or above the user's CEFR level.
Returns a list of ExtractedPhrase objects.
"""

import anthropic
from src.schemas.article import ExtractedPhrase, CEFRLevel, PhraseCategory
from src.utils import load_skill
from src.utils.json_utils import extract_json


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

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    full_response = " ".join(
        block.text for block in response.content if hasattr(block, "text")
    )

    try:
        raw_phrases = extract_json(full_response, "[", "]")
    except ValueError as e:
        raise ValueError(f"Extract agent could not parse phrase list.\n{e}")

    phrases = []
    for item in raw_phrases:
        try:
            phrase = ExtractedPhrase(
                phrase=item["phrase"],
                sentence_context=item["sentence_context"],
                translation=item["translation"],
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