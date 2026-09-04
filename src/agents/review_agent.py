"""
Review agent.
Independently reviews the extracted phrase list and removes low-quality items.
Applies the phrase-quality-reviewer skill as its evaluation criteria.
Does not see the original article text directly, but phrase entries include
sentence_context quotes from the article — those are wrapped as untrusted data.
"""

import json
import logging
from typing import cast

import anthropic

from src.prompts import load_prompt
from src.schemas.article import CEFRLevel, ExtractedPhrase, PhraseCategory
from src.utils import load_skill
from src.utils.anthropic_retry import create_message_with_retry
from src.utils.anthropic_utils import message_text
from src.utils.json_utils import extract_json
from src.utils.observability import UsageTracker, record_api_usage
from src.utils.untrusted_content import UNTRUSTED_CONTENT_PREAMBLE, wrap_untrusted_content

logger = logging.getLogger(__name__)


def review_phrases(
    phrases: list[ExtractedPhrase],
    topic: str,
    client: anthropic.Anthropic,
    *,
    usage: UsageTracker | None = None,
) -> list[ExtractedPhrase]:

    if not phrases:
        return phrases

    reviewer_guide = load_skill("phrase-quality-reviewer")

    phrase_list_json = json.dumps(
        [p.model_dump(mode="json") for p in phrases], ensure_ascii=False, indent=2
    )
    wrapped_phrase_list = wrap_untrusted_content(phrase_list_json, label="extracted_phrases")

    prompt = load_prompt(
        "review_phrases",
        reviewer_guide=reviewer_guide,
        topic=topic,
        untrusted_content_preamble=UNTRUSTED_CONTENT_PREAMBLE,
        wrapped_phrase_list=wrapped_phrase_list,
    )

    response = create_message_with_retry(
        client,
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    record_api_usage(response, agent="review_agent", usage=usage, logger=logger)

    full_response = message_text(response)

    try:
        raw_verdicts = extract_json(full_response, "[", "]")
    except ValueError as e:
        raise ValueError(f"Review agent could not parse review verdicts.\n{e}")

    if not isinstance(raw_verdicts, list):
        raise ValueError("Review agent could not parse review verdicts: expected JSON array.")

    verdicts_by_phrase: dict[str, tuple[str, str]] = {}
    for raw_item in cast(list[object], raw_verdicts):
        if not isinstance(raw_item, dict):
            logger.warning("Skipping malformed verdict: %r", raw_item)
            continue
        item = cast(dict[str, object], raw_item)
        try:
            phrase_raw = item["phrase"]
            action_raw = item["action"]
            if not isinstance(phrase_raw, str) or not isinstance(action_raw, str):
                raise TypeError("phrase and action must be strings")
            reason_raw = item.get("reason", "")
            reason = reason_raw if isinstance(reason_raw, str) else ""
            verdicts_by_phrase[phrase_raw] = (action_raw, reason)
        except (KeyError, TypeError) as e:
            logger.warning("Skipping malformed verdict: %r — %s", item, e)
            continue

    kept: list[ExtractedPhrase] = []
    n_flagged = 0
    n_removed = 0
    for phrase in phrases:
        action, reason = verdicts_by_phrase.get(phrase.phrase, ("keep", ""))

        if action == "remove":
            n_removed += 1
            logger.info("Removed phrase %r: %s", phrase.phrase, reason)
            continue

        if action == "review":
            n_flagged += 1
            logger.info("Flagged for review %r: %s", phrase.phrase, reason)

        kept.append(phrase)

    logger.info(
        "Kept %d, flagged %d for review, removed %d (of %d phrases).",
        len(kept),
        n_flagged,
        n_removed,
        len(phrases),
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
                'Em "Entroncamento" acompanhamos Laura, que foge de um passado turbulento'
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
