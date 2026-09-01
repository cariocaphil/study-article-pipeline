"""
Translation quality evaluator.

Scores LLM judge adequacy verdicts against human-labeled translation pairs.
Supports offline scoring from cached judge predictions or live judge runs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import anthropic

from evals.evaluators.base import EvalFailure, EvalResult
from evals.evaluators.utils import safe_divide
from src.utils import load_skill
from src.utils.anthropic_utils import message_text
from src.utils.json_utils import extract_json

DEFAULT_PASS_THRESHOLD = 1.0


@dataclass
class TranslationCase:
    id: str
    phrase: str
    sentence_context: str
    translation: str
    source_language: str
    translation_language: str
    expected_adequate: bool


@dataclass
class TranslationJudgment:
    adequate: bool
    reason: str = ""


class TranslationQualityEvaluator:
    name = "translation_quality"

    def __init__(self, pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> None:
        self.pass_threshold = pass_threshold

    def run(
        self,
        cases: list[TranslationCase],
        predictions: dict[str, TranslationJudgment],
    ) -> EvalResult:
        failures: list[EvalFailure] = []
        true_positive = 0
        true_negative = 0
        false_positive = 0
        false_negative = 0

        for case in cases:
            prediction = predictions.get(case.id)
            if prediction is None:
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="missing_prediction",
                        message="No judge prediction recorded for labeled translation case",
                        details={
                            "phrase": case.phrase,
                            "translation": case.translation,
                        },
                    )
                )
                continue

            predicted_adequate = prediction.adequate
            expected_adequate = case.expected_adequate

            if expected_adequate and predicted_adequate:
                true_positive += 1
            elif not expected_adequate and not predicted_adequate:
                true_negative += 1
            elif not expected_adequate and predicted_adequate:
                false_positive += 1
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="false_adequate",
                        message="Translation was judged adequate but should be inadequate",
                        details={
                            "phrase": case.phrase,
                            "translation": case.translation,
                            "reason": prediction.reason,
                        },
                    )
                )
            else:
                false_negative += 1
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="false_inadequate",
                        message="Translation was judged inadequate but should be adequate",
                        details={
                            "phrase": case.phrase,
                            "translation": case.translation,
                            "reason": prediction.reason,
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


def judge_translation(
    case: TranslationCase,
    client: anthropic.Anthropic,
) -> TranslationJudgment:
    rubric = load_skill("translation-adequacy-rubric")

    prompt = f"""
You are judging translation quality for language-study material.

## Rubric
{rubric}

## Item to judge
Source language: {case.source_language}
Target language: {case.translation_language}
Phrase: {case.phrase}
Sentence context: {case.sentence_context}
Proposed translation: {case.translation}

Return ONLY a JSON object with:
- adequate: boolean — true if the translation is adequate for study, false otherwise
- reason: short string explaining the verdict

Example:
{{"adequate": true, "reason": "Captures the idiomatic meaning in natural German."}}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = message_text(response)
    parsed = extract_json(raw_text, "{", "}")

    if not isinstance(parsed, dict) or "adequate" not in parsed:
        raise ValueError(f"Translation judge could not parse verdict for {case.id}: {raw_text}")

    return TranslationJudgment(
        adequate=bool(parsed["adequate"]),
        reason=str(parsed.get("reason", "")),
    )


def collect_live_predictions(
    cases: list[TranslationCase],
    client: anthropic.Anthropic,
    *,
    judge_fn: Callable[[TranslationCase, anthropic.Anthropic], TranslationJudgment] | None = None,
) -> dict[str, TranslationJudgment]:
    run_judge = judge_fn or judge_translation
    return {case.id: run_judge(case, client) for case in cases}
