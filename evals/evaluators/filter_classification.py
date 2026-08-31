"""
Filter classification evaluator.

Scores filter accept/reject decisions against a labeled URL dataset.
Supports offline scoring from cached predictions or live runs via filter_agent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import anthropic

from evals.evaluators.base import EvalFailure, EvalResult
from evals.evaluators.utils import safe_divide

DEFAULT_PASS_THRESHOLD = 1.0


@dataclass
class FilterCase:
    id: str
    url: str
    source_language: str
    expected: str
    reason: str

    @property
    def expected_accept(self) -> bool:
        return self.expected == "accept"


class FilterClassificationEvaluator:
    name = "filter_classification"

    def __init__(self, pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> None:
        self.pass_threshold = pass_threshold

    def run(
        self,
        cases: list[FilterCase],
        predictions: dict[str, bool],
    ) -> EvalResult:
        failures: list[EvalFailure] = []
        true_positive = 0
        true_negative = 0
        false_positive = 0
        false_negative = 0

        for case in cases:
            if case.id not in predictions:
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="missing_prediction",
                        message="No prediction recorded for labeled case",
                        details={"url": case.url, "expected": case.expected},
                    )
                )
                continue

            predicted_accept = predictions[case.id]
            expected_accept = case.expected_accept

            if expected_accept and predicted_accept:
                true_positive += 1
            elif not expected_accept and not predicted_accept:
                true_negative += 1
            elif not expected_accept and predicted_accept:
                false_positive += 1
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="false_accept",
                        message="URL was accepted but should have been rejected",
                        details={
                            "url": case.url,
                            "expected": case.expected,
                            "reason": case.reason,
                        },
                    )
                )
            else:
                false_negative += 1
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="false_reject",
                        message="URL was rejected but should have been accepted",
                        details={
                            "url": case.url,
                            "expected": case.expected,
                            "reason": case.reason,
                        },
                    )
                )

        total = len(cases)
        correct = true_positive + true_negative
        accuracy = safe_divide(correct, total)
        precision = safe_divide(true_positive, true_positive + false_positive)
        recall = safe_divide(true_positive, true_positive + false_negative)
        f1 = safe_divide(2 * precision * recall, precision + recall)

        metrics = {
            "total_cases": total,
            "correct": correct,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "true_positive": true_positive,
            "true_negative": true_negative,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "pass_threshold": self.pass_threshold,
        }

        return EvalResult(
            evaluator=self.name,
            passed=accuracy >= self.pass_threshold,
            score=accuracy,
            metrics=metrics,
            failures=failures,
        )


def collect_live_predictions(
    cases: list[FilterCase],
    client: anthropic.Anthropic,
    *,
    filter_fn: Callable[[list[str], str, anthropic.Anthropic], list[dict]] | None = None,
) -> dict[str, bool]:
    from src.agents.filter_agent import filter_articles

    run_filter = filter_fn or filter_articles
    predictions: dict[str, bool] = {}

    for case in cases:
        results = run_filter([case.url], case.source_language, client)
        predictions[case.id] = any(result.get("url") == case.url for result in results)

    return predictions
