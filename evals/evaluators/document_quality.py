"""
Document-level quality evaluator.

Scores complete Study Article Collection documents with an LLM-as-judge
rubric. Offline runs use cached judgments; live runs call the judge.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import anthropic

from evals.evaluators.base import EvalFailure, EvalResult
from evals.evaluators.utils import safe_divide
from src.prompts import load_prompt
from src.schemas.article import TOPIC_TYPE_LABELS, PipelineOutput
from src.utils import load_skill
from src.utils.anthropic_retry import create_message_with_retry
from src.utils.anthropic_utils import message_text
from src.utils.json_utils import extract_json

DEFAULT_PASS_THRESHOLD = 0.6
SCORE_MIN = 1.0
SCORE_MAX = 5.0
MAX_ARTICLE_TEXT_CHARS = 1500

DOCUMENT_QUALITY_DIMENSIONS = (
    "structure_completeness",
    "topic_relevance",
    "article_usefulness",
    "phrase_quality",
    "translation_quality",
    "quote_faithfulness",
    "duplication",
    "overall_usefulness",
)


@dataclass
class DocumentQualityCase:
    id: str
    document: PipelineOutput
    expected_overall_min: float | None = None


@dataclass
class DocumentQualityJudgment:
    overall: float
    dimensions: dict[str, float]
    summary: str = ""
    defects: list[str] = field(default_factory=list[str])


def _validate_score(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number from {SCORE_MIN} to {SCORE_MAX}")
    score = float(value)
    if score < SCORE_MIN or score > SCORE_MAX:
        raise ValueError(f"{field_name} must be a number from {SCORE_MIN} to {SCORE_MAX}")
    return score


def parse_document_quality_judgment(data: Mapping[str, Any]) -> DocumentQualityJudgment:
    if "overall" not in data or "dimensions" not in data:
        raise ValueError("Judgment must include overall and dimensions")

    raw_dimensions = data["dimensions"]
    if not isinstance(raw_dimensions, dict):
        raise ValueError("dimensions must be an object")

    dimensions_data = cast(dict[str, object], raw_dimensions)
    dimensions: dict[str, float] = {}
    for name in DOCUMENT_QUALITY_DIMENSIONS:
        if name not in dimensions_data:
            raise ValueError(f"Missing dimension score: {name}")
        dimensions[name] = _validate_score(dimensions_data[name], field_name=name)

    overall = _validate_score(data["overall"], field_name="overall")

    summary = str(data.get("summary", "")).strip()
    if not summary:
        raise ValueError("summary must be a non-empty string")

    raw_defects = data.get("defects", [])
    if not isinstance(raw_defects, list):
        raise ValueError("defects must be an array of strings")
    defects = [
        stripped for item in cast(list[object], raw_defects) if (stripped := str(item).strip())
    ]

    return DocumentQualityJudgment(
        overall=overall,
        dimensions=dimensions,
        summary=summary,
        defects=defects,
    )


def document_for_judge(document: PipelineOutput) -> dict[str, Any]:
    payload = document.model_dump(mode="json")
    for article in payload.get("articles", []):
        full_text = article.get("full_text", "")
        if isinstance(full_text, str) and len(full_text) > MAX_ARTICLE_TEXT_CHARS:
            article["full_text"] = full_text[:MAX_ARTICLE_TEXT_CHARS] + "…"
    return payload


class DocumentQualityEvaluator:
    name = "document_quality"

    def __init__(self, pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> None:
        self.pass_threshold = pass_threshold

    def run(
        self,
        cases: list[DocumentQualityCase],
        predictions: dict[str, DocumentQualityJudgment],
    ) -> EvalResult:
        failures: list[EvalFailure] = []
        overall_scores: list[float] = []
        dimension_totals = {name: 0.0 for name in DOCUMENT_QUALITY_DIMENSIONS}
        dimension_counts = {name: 0 for name in DOCUMENT_QUALITY_DIMENSIONS}
        cases_below_threshold = 0
        expected_floor_failures = 0

        for case in cases:
            prediction = predictions.get(case.id)
            if prediction is None:
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="missing_prediction",
                        message="No judge prediction recorded for document quality case",
                        details={"topic": case.document.topic},
                    )
                )
                continue

            overall_scores.append(prediction.overall)
            normalized = prediction.overall / SCORE_MAX
            if normalized < self.pass_threshold:
                cases_below_threshold += 1
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="low_overall_score",
                        message="Document overall score fell below the pass threshold",
                        details={
                            "overall": prediction.overall,
                            "normalized_overall": normalized,
                            "pass_threshold": self.pass_threshold,
                            "summary": prediction.summary,
                            "defects": prediction.defects,
                        },
                    )
                )

            if (
                case.expected_overall_min is not None
                and prediction.overall < case.expected_overall_min
            ):
                expected_floor_failures += 1
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="below_expected_floor",
                        message="Judge overall score fell below the labeled minimum",
                        details={
                            "overall": prediction.overall,
                            "expected_overall_min": case.expected_overall_min,
                            "summary": prediction.summary,
                        },
                    )
                )

            for name, score in prediction.dimensions.items():
                dimension_totals[name] += score
                dimension_counts[name] += 1

        judged_cases = len(overall_scores)
        mean_overall = safe_divide(sum(overall_scores), judged_cases)
        score = mean_overall / SCORE_MAX
        mean_dimensions = {
            name: safe_divide(dimension_totals[name], dimension_counts[name])
            for name in DOCUMENT_QUALITY_DIMENSIONS
        }

        metrics: dict[str, Any] = {
            "total_cases": len(cases),
            "judged_cases": judged_cases,
            "mean_overall": mean_overall,
            "mean_dimensions": mean_dimensions,
            "cases_below_threshold": cases_below_threshold,
            "expected_floor_failures": expected_floor_failures,
            "pass_threshold": self.pass_threshold,
        }

        return EvalResult(
            evaluator=self.name,
            passed=(
                judged_cases == len(cases)
                and score >= self.pass_threshold
                and expected_floor_failures == 0
            ),
            score=score,
            metrics=metrics,
            failures=failures,
        )


def judge_document_quality(
    case: DocumentQualityCase,
    client: anthropic.Anthropic,
) -> DocumentQualityJudgment:
    rubric = load_skill("document-quality-rubric")
    document = case.document

    prompt = load_prompt(
        "judge_document_quality",
        rubric=rubric,
        topic=document.topic,
        topic_type=TOPIC_TYPE_LABELS[document.topic_type],
        source_language=document.source_language,
        translation_language=document.translation_language,
        user_level=document.user_level.value,
        document_json=json.dumps(document_for_judge(document), ensure_ascii=False, indent=2),
    )

    response = create_message_with_retry(
        client,
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = message_text(response)
    parsed = extract_json(raw_text, "{", "}")

    if not isinstance(parsed, dict):
        raise ValueError(
            f"Document quality judge could not parse verdict for {case.id}: {raw_text}"
        )

    try:
        return parse_document_quality_judgment(cast(dict[str, Any], parsed))
    except ValueError as exc:
        raise ValueError(
            f"Document quality judge returned invalid verdict for {case.id}: {exc}"
        ) from exc


def collect_live_predictions(
    cases: list[DocumentQualityCase],
    client: anthropic.Anthropic,
    *,
    judge_fn: (
        Callable[[DocumentQualityCase, anthropic.Anthropic], DocumentQualityJudgment] | None
    ) = None,
) -> dict[str, DocumentQualityJudgment]:
    run_judge = judge_fn or judge_document_quality
    return {case.id: run_judge(case, client) for case in cases}
