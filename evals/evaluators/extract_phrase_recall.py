"""
Extract phrase recall evaluator.

Scores extract agent output against human-labeled gold phrases for fixed
article excerpts. Primary metric is phrase recall; recall@k is reported for a
configurable k (default 10).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import anthropic

from evals.evaluators.base import EvalFailure, EvalResult
from src.schemas.article import CEFRLevel, ExtractedPhrase

DEFAULT_PASS_THRESHOLD = 1.0
DEFAULT_RECALL_K = 10


@dataclass
class ExtractRecallCase:
    id: str
    topic: str
    full_text: str
    source_language: str
    translation_language: str
    user_level: CEFRLevel
    gold_phrases: list[str]


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _normalize_phrase(phrase: str) -> str:
    return " ".join(phrase.lower().split())


def _match_phrase(gold_phrase: str, predicted_phrases: set[str]) -> bool:
    normalized_gold = _normalize_phrase(gold_phrase)
    return normalized_gold in predicted_phrases


def _predicted_phrase_set(phrases: list[str], *, limit: int | None = None) -> set[str]:
    selected = phrases if limit is None else phrases[:limit]
    return {_normalize_phrase(phrase) for phrase in selected}


class ExtractPhraseRecallEvaluator:
    name = "extract_phrase_recall"

    def __init__(
        self,
        pass_threshold: float = DEFAULT_PASS_THRESHOLD,
        recall_k: int = DEFAULT_RECALL_K,
    ) -> None:
        self.pass_threshold = pass_threshold
        self.recall_k = recall_k

    def run(
        self,
        cases: list[ExtractRecallCase],
        predictions: dict[str, list[str]],
    ) -> EvalResult:
        failures: list[EvalFailure] = []
        matched_gold = 0
        total_gold = 0
        matched_gold_at_k = 0

        for case in cases:
            case_predictions = predictions.get(case.id)
            if case_predictions is None:
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="missing_prediction",
                        message="No prediction recorded for labeled extract case",
                        details={"topic": case.topic},
                    )
                )
                continue

            predicted_all = _predicted_phrase_set(case_predictions)
            predicted_at_k = _predicted_phrase_set(case_predictions, limit=self.recall_k)

            for gold_phrase in case.gold_phrases:
                total_gold += 1
                matched = _match_phrase(gold_phrase, predicted_all)
                matched_at_k = _match_phrase(gold_phrase, predicted_at_k)

                if matched:
                    matched_gold += 1
                if matched_at_k:
                    matched_gold_at_k += 1

                if not matched:
                    failures.append(
                        EvalFailure(
                            case_id=case.id,
                            category="missed_gold_phrase",
                            message="Gold phrase was not extracted",
                            details={
                                "phrase": gold_phrase,
                                "topic": case.topic,
                                "predicted_phrases": case_predictions,
                            },
                        )
                    )

        recall = _safe_divide(matched_gold, total_gold)
        recall_at_k = _safe_divide(matched_gold_at_k, total_gold)

        metrics = {
            "total_gold_phrases": total_gold,
            "matched_gold_phrases": matched_gold,
            "recall": recall,
            "recall_k": self.recall_k,
            "recall_at_k": recall_at_k,
            "pass_threshold": self.pass_threshold,
        }

        return EvalResult(
            evaluator=self.name,
            passed=recall >= self.pass_threshold,
            score=recall,
            metrics=metrics,
            failures=failures,
        )


def collect_live_predictions(
    cases: list[ExtractRecallCase],
    client: anthropic.Anthropic,
    *,
    extract_fn: Callable[
        [str, str, str, CEFRLevel, anthropic.Anthropic], list[ExtractedPhrase]
    ]
    | None = None,
) -> dict[str, list[str]]:
    from src.agents.extract_agent import extract_phrases

    run_extract = extract_fn or extract_phrases
    predictions: dict[str, list[str]] = {}

    for case in cases:
        extracted = run_extract(
            case.full_text,
            case.source_language,
            case.translation_language,
            case.user_level,
            client,
        )
        predictions[case.id] = [phrase.phrase for phrase in extracted]

    return predictions
