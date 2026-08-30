"""
Run evaluation suites against saved pipeline outputs.

Example:
    uv run python -m evals.runners.run_evals \\
        --suite quote_faithfulness \\
        --input evals/datasets/fixtures/sample_pipeline_output.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evals.evaluators.base import (
    EvalReport,
    current_git_sha,
    load_pipeline_output,
    new_run_id,
)
from evals.evaluators.quote_faithfulness import QuoteFaithfulnessEvaluator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "evals" / "results"
DEFAULT_FIXTURE = (
    PROJECT_ROOT / "evals" / "datasets" / "fixtures" / "sample_pipeline_output.json"
)

SUITE_REGISTRY = {
    "quote_faithfulness": QuoteFaithfulnessEvaluator,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run study-article-pipeline evals")
    parser.add_argument(
        "--suite",
        required=True,
        choices=sorted(SUITE_REGISTRY),
        help="Evaluation suite to run",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Path to a PipelineOutput JSON file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Directory where run results will be stored",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run identifier (defaults to UTC timestamp)",
    )
    parser.add_argument(
        "--pass-threshold",
        type=float,
        default=1.0,
        help="Minimum faithfulness rate required to pass quote_faithfulness",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Optional label for this run (stored in report config)",
    )
    return parser


def run_suite(
    suite: str,
    input_path: Path,
    *,
    pass_threshold: float = 1.0,
):
    pipeline_output = load_pipeline_output(input_path)
    evaluator_cls = SUITE_REGISTRY[suite]

    if suite == "quote_faithfulness":
        evaluator = evaluator_cls(pass_threshold=pass_threshold)
    else:
        evaluator = evaluator_cls()

    return evaluator.run(
        pipeline_output,
        case_id=input_path.stem,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = args.input.resolve()
    if not input_path.exists():
        parser.error(f"Input file not found: {input_path}")

    result = run_suite(
        args.suite,
        input_path,
        pass_threshold=args.pass_threshold,
    )

    run_id = args.run_id or new_run_id()
    report = EvalReport(
        run_id=run_id,
        timestamp=new_run_id(),
        git_sha=current_git_sha(),
        config={
            "suite": args.suite,
            "input": str(input_path),
            "pass_threshold": args.pass_threshold,
        },
        results=[result],
    )
    if args.tag:
        report.config["tag"] = args.tag

    run_dir = args.output_dir.resolve() / report.run_id
    run_dir = report.save(run_dir)

    print(f"Eval run saved to {run_dir}")
    for result in report.results:
        print(
            f"[{result.evaluator}] score={result.score:.3f} "
            f"passed={result.passed} metrics={result.metrics}"
        )
        if result.failures:
            print(f"  failures={len(result.failures)}")

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
