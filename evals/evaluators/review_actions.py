"""
Review actions evaluator.

Scores review agent keep/review/remove decisions against labeled phrase lists.
Removal precision and recall are the primary metrics.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

import anthropic

from evals.evaluators.base import EvalFailure, EvalResult
from evals.evaluators.utils import safe_divide
from src.schemas.article import ExtractedPhrase

DEFAULT_PASS_THRESHOLD = 1.0

ReviewAction = Literal["keep", "review", "remove"]


@dataclass
class ReviewCase:
    id: str
    topic: str
    phrases: list[ExtractedPhrase]
    expected_actions: dict[str, ReviewAction] = field(default_factory=dict)


def _is_removed(action: ReviewAction) -> bool:
    return action == "remove"


class ReviewActionsEvaluator:
    name = "review_actions"

    def __init__(self, pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> None:
        self.pass_threshold = pass_threshold

    def run(
        self,
        cases: list[ReviewCase],
        predictions: dict[str, dict[str, ReviewAction]],
    ) -> EvalResult:
        failures: list[EvalFailure] = []
        removal_tp = 0
        removal_fp = 0
        removal_fn = 0
        action_correct = 0
        action_total = 0

        for case in cases:
            case_predictions = predictions.get(case.id)
            if case_predictions is None:
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="missing_prediction",
                        message="No prediction recorded for labeled review case",
                        details={"topic": case.topic},
                    )
                )
                continue

            for phrase_item in case.phrases:
                phrase = phrase_item.phrase
                expected_action = case.expected_actions.get(phrase)
                predicted_action = case_predictions.get(phrase)

                if expected_action is None:
                    failures.append(
                        EvalFailure(
                            case_id=case.id,
                            category="missing_label",
                            message="Phrase missing from expected_actions",
                            details={"phrase": phrase, "topic": case.topic},
                        )
                    )
                    continue

                if predicted_action is None:
                    failures.append(
                        EvalFailure(
                            case_id=case.id,
                            category="missing_prediction",
                            message="Phrase missing from predicted actions",
                            details={"phrase": phrase, "topic": case.topic},
                        )
                    )
                    continue

                action_total += 1
                if predicted_action == expected_action:
                    action_correct += 1

                expected_removed = _is_removed(expected_action)
                predicted_removed = _is_removed(predicted_action)

                if expected_removed and predicted_removed:
                    removal_tp += 1
                elif not expected_removed and predicted_removed:
                    removal_fp += 1
                    failures.append(
                        EvalFailure(
                            case_id=case.id,
                            category="false_remove",
                            message="Phrase was removed but should have been kept or flagged",
                            details={
                                "phrase": phrase,
                                "topic": case.topic,
                                "expected_action": expected_action,
                                "predicted_action": predicted_action,
                            },
                        )
                    )
                elif expected_removed and not predicted_removed:
                    removal_fn += 1
                    failures.append(
                        EvalFailure(
                            case_id=case.id,
                            category="missed_remove",
                            message="Phrase should have been removed",
                            details={
                                "phrase": phrase,
                                "topic": case.topic,
                                "expected_action": expected_action,
                                "predicted_action": predicted_action,
                            },
                        )
                    )

        removal_precision = safe_divide(removal_tp, removal_tp + removal_fp)
        removal_recall = safe_divide(removal_tp, removal_tp + removal_fn)
        removal_f1 = safe_divide(
            2 * removal_precision * removal_recall,
            removal_precision + removal_recall,
        )
        action_accuracy = safe_divide(action_correct, action_total)

        metrics = {
            "total_phrases": action_total,
            "action_correct": action_correct,
            "action_accuracy": action_accuracy,
            "removal_true_positive": removal_tp,
            "removal_false_positive": removal_fp,
            "removal_false_negative": removal_fn,
            "removal_precision": removal_precision,
            "removal_recall": removal_recall,
            "removal_f1": removal_f1,
            "pass_threshold": self.pass_threshold,
        }

        return EvalResult(
            evaluator=self.name,
            passed=removal_f1 >= self.pass_threshold,
            score=removal_f1,
            metrics=metrics,
            failures=failures,
        )


def collect_live_predictions(
    cases: list[ReviewCase],
    client: anthropic.Anthropic,
    *,
    review_fn: Callable[[list[ExtractedPhrase], str, anthropic.Anthropic], list[ExtractedPhrase]]
    | None = None,
) -> dict[str, dict[str, ReviewAction]]:
    from src.agents.review_agent import review_phrases

    run_review = review_fn or review_phrases
    predictions: dict[str, dict[str, ReviewAction]] = {}

    for case in cases:
        kept = run_review(case.phrases, case.topic, client)
        kept_phrases = {phrase.phrase for phrase in kept}
        predictions[case.id] = {
            phrase.phrase: "keep" if phrase.phrase in kept_phrases else "remove"
            for phrase in case.phrases
        }

    return predictions
