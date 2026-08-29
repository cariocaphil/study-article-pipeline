"""
Review agent.
Independently reviews the extracted phrase list and removes low-quality items.
Applies the phrase-quality-reviewer skill as its evaluation criteria.
Does not see the original article text or the extract agent's reasoning —
only the phrase list itself.
"""

import json

import anthropic
from src.schemas.article import ExtractedPhrase, CEFRLevel, PhraseCategory
from src.utils import load_skill
from src.utils.json_utils import extract_json


def review_phrases(
    phrases: list[ExtractedPhrase],
    topic: str,
    client: anthropic.Anthropic,
) -> list[ExtractedPhrase]:

    if not phrases:
        return phrases

    reviewer_guide = load_skill("phrase-quality-reviewer")

    phrase_list_json = json.dumps(
        [p.model_dump(mode="json") for p in phrases], ensure_ascii=False, indent=2
    )

    prompt = f"""
You are independently auditing a list of language-learning phrases for
quality. You do not have access to the original article or the reasoning
used to extract these phrases — only the phrase list itself.

## Phrase Quality Reviewer
{reviewer_guide}

The topic of the article this phrase list was extracted from is: "{topic}"
Flag any phrase that is just the topic itself, or a derivative of it, for
removal.

Here is the phrase list to review:
---
{phrase_list_json}
---

For each phrase, decide whether to keep it, flag it for review, or remove it.

Return ONLY a JSON array of objects with no other text, no markdown, no explanation.
Example format:
[
  {{
    "phrase": "...",
    "action": "keep",
    "reason": "..."
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
        raw_verdicts = extract_json(full_response, "[", "]")
    except ValueError as e:
        raise ValueError(f"Review agent could not parse review verdicts.\n{e}")

    verdicts_by_phrase = {}
    for item in raw_verdicts:
        try:
            verdicts_by_phrase[item["phrase"]] = (item["action"], item.get("reason", ""))
        except (KeyError, TypeError) as e:
            print(f"[review_agent] Skipping malformed verdict: {item} — {e}")
            continue

    kept = []
    n_flagged = 0
    n_removed = 0
    for phrase in phrases:
        action, reason = verdicts_by_phrase.get(phrase.phrase, ("keep", ""))

        if action == "remove":
            n_removed += 1
            print(f"[review_agent] Removed '{phrase.phrase}': {reason}")
            continue

        if action == "review":
            n_flagged += 1
            print(f"[review_agent] Flagged for review '{phrase.phrase}': {reason}")

        kept.append(phrase)

    print(
        f"[review_agent] Kept {len(kept)}, flagged {n_flagged} for review, "
        f"removed {n_removed} (of {len(phrases)} phrases)."
    )
    return kept


# ── Manual test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    # Hardcoded sample list — includes a topic-derivative phrase that should
    # be flagged for removal, to sanity-check the reviewer's behavior.
    sample_phrases = [
        ExtractedPhrase(
            phrase="entrar em pequenos esquemas",
            sentence_context=(
                "começa a entrar em pequenos esquemas e crimes, motivados "
                "por familiares e conhecidos"
            ),
            translation="in kleine Machenschaften verwickelt werden",
            category=PhraseCategory.idiom,
            estimated_level=CEFRLevel.C1,
        ),
        ExtractedPhrase(
            phrase="Entroncamento",
            sentence_context=(
                'Em "Entroncamento" acompanhamos Laura, que foge de um '
                "passado turbulento"
            ),
            translation="Entroncamento (Ortsname)",
            category=PhraseCategory.vocab,
            estimated_level=CEFRLevel.C1,
        ),
        ExtractedPhrase(
            phrase="teia de cumplicidades",
            sentence_context="que a envolvem numa teia de cumplicidades difícil de escapar",
            translation="Netz aus Komplizenschaften",
            category=PhraseCategory.idiom,
            estimated_level=CEFRLevel.C1,
        ),
    ]

    reviewed = review_phrases(sample_phrases, topic="Entroncamento", client=client)

    for p in reviewed:
        print(f"\n[{p.category.value}] [{p.estimated_level.value}] {p.phrase}")
        print(f"  Translation: {p.translation}")
