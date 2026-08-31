"""
Compare scores between two eval runs.

Examples:
    uv run python -m evals.runners.compare_runs \\
        --baseline evals/results/20260830T120000Z \\
        --candidate evals/results/20260830T130000Z
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class EvaluatorComparison:
    evaluator: str
    baseline_score: float
    candidate_score: float
    delta: float
    baseline_passed: bool
    candidate_passed: bool
    status: str


def resolve_scores_path(path: Path) -> Path:
    if path.is_dir():
        scores_path = path / "scores.json"
        if not scores_path.exists():
            raise FileNotFoundError(f"scores.json not found in run directory: {path}")
        return scores_path
    if not path.exists():
        raise FileNotFoundError(f"Scores file not found: {path}")
    return path


def load_scores(path: Path) -> dict[str, Any]:
    scores_path = resolve_scores_path(path)
    return json.loads(scores_path.read_text(encoding="utf-8"))


def compare_runs(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    regression_threshold: float = 0.0,
) -> list[EvaluatorComparison]:
    baseline_scores = baseline.get("scores", {})
    candidate_scores = candidate.get("scores", {})
    evaluators = sorted(set(baseline_scores) | set(candidate_scores))

    comparisons: list[EvaluatorComparison] = []
    for evaluator in evaluators:
        baseline_entry = baseline_scores.get(evaluator)
        candidate_entry = candidate_scores.get(evaluator)

        if baseline_entry is None or candidate_entry is None:
            comparisons.append(
                EvaluatorComparison(
                    evaluator=evaluator,
                    baseline_score=baseline_entry["score"] if baseline_entry else 0.0,
                    candidate_score=candidate_entry["score"] if candidate_entry else 0.0,
                    delta=0.0,
                    baseline_passed=bool(baseline_entry and baseline_entry["passed"]),
                    candidate_passed=bool(candidate_entry and candidate_entry["passed"]),
                    status="missing_in_one_run",
                )
            )
            continue

        baseline_score = float(baseline_entry["score"])
        candidate_score = float(candidate_entry["score"])
        delta = candidate_score - baseline_score

        if delta < -regression_threshold:
            status = "regressed"
        elif delta > regression_threshold:
            status = "improved"
        else:
            status = "unchanged"

        comparisons.append(
            EvaluatorComparison(
                evaluator=evaluator,
                baseline_score=baseline_score,
                candidate_score=candidate_score,
                delta=delta,
                baseline_passed=bool(baseline_entry["passed"]),
                candidate_passed=bool(candidate_entry["passed"]),
                status=status,
            )
        )

    return comparisons


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare eval scores between two saved runs")
    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
        help="Baseline run directory or scores.json path",
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        required=True,
        help="Candidate run directory or scores.json path",
    )
    parser.add_argument(
        "--regression-threshold",
        type=float,
        default=0.0,
        help="Score drop larger than this counts as a regression",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write comparison JSON",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        baseline = load_scores(args.baseline.resolve())
        candidate = load_scores(args.candidate.resolve())
    except FileNotFoundError as exc:
        parser.error(str(exc))

    comparisons = compare_runs(
        baseline,
        candidate,
        regression_threshold=args.regression_threshold,
    )

    summary = {
        "baseline_run_id": baseline.get("run_id"),
        "candidate_run_id": candidate.get("run_id"),
        "regression_threshold": args.regression_threshold,
        "comparisons": [
            {
                "evaluator": item.evaluator,
                "baseline_score": item.baseline_score,
                "candidate_score": item.candidate_score,
                "delta": item.delta,
                "baseline_passed": item.baseline_passed,
                "candidate_passed": item.candidate_passed,
                "status": item.status,
            }
            for item in comparisons
        ],
    }

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"Comparing {summary['baseline_run_id']} -> {summary['candidate_run_id']}")
    for item in comparisons:
        print(
            f"[{item.evaluator}] "
            f"baseline={item.baseline_score:.3f} "
            f"candidate={item.candidate_score:.3f} "
            f"delta={item.delta:+.3f} "
            f"status={item.status}"
        )

    has_regression = any(item.status == "regressed" for item in comparisons)
    return 1 if has_regression else 0


if __name__ == "__main__":
    sys.exit(main())
