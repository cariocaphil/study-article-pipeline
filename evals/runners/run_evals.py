"""
Run evaluation suites against saved pipeline outputs or labeled datasets.

Examples:
    uv run python -m evals.runners.run_evals \\
        --suite quote_faithfulness \\
        --input evals/datasets/fixtures/sample_pipeline_output.json

    uv run python -m evals.runners.run_evals \\
        --suite filter_classification \\
        --input evals/datasets/filter/urls.jsonl \\
        --predictions evals/datasets/fixtures/filter_predictions.jsonl

    uv run python -m evals.runners.run_evals \\
        --suite review_actions \\
        --input evals/datasets/review/phrase_lists.jsonl \\
        --predictions evals/datasets/fixtures/review_predictions.jsonl

    uv run python -m evals.runners.run_evals \\
        --suite extract_phrase_recall \\
        --input evals/datasets/extract/gold_phrases.jsonl \\
        --predictions evals/datasets/fixtures/extract_predictions.jsonl

    uv run python -m evals.runners.run_evals \\
        --suite translation_quality \\
        --input evals/datasets/translation/phrases.jsonl \\
        --predictions evals/datasets/fixtures/translation_judge_predictions.jsonl

    uv run python -m evals.runners.run_evals \\
        --suite search_url_recall \\
        --input evals/datasets/search/gold_urls.jsonl \\
        --predictions evals/datasets/fixtures/search_predictions.jsonl

    uv run python -m evals.runners.run_evals \\
        --suite pipeline_quality \\
        --input evals/datasets/fixtures/sample_pipeline_output.json
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from evals.evaluators.base import (
    EvalReport,
    current_git_sha,
    load_extract_predictions,
    load_extract_recall_dataset,
    load_filter_dataset,
    load_filter_predictions,
    load_pipeline_output,
    load_review_dataset,
    load_review_predictions,
    load_search_predictions,
    load_search_recall_dataset,
    load_translation_dataset,
    load_translation_predictions,
    new_run_id,
)
from evals.evaluators.extract_phrase_recall import (
    ExtractPhraseRecallEvaluator,
)
from evals.evaluators.extract_phrase_recall import (
    collect_live_predictions as collect_extract_live_predictions,
)
from evals.evaluators.filter_classification import (
    FilterClassificationEvaluator,
)
from evals.evaluators.filter_classification import (
    collect_live_predictions as collect_filter_live_predictions,
)
from evals.evaluators.pipeline_quality import PipelineQualityEvaluator
from evals.evaluators.quote_faithfulness import QuoteFaithfulnessEvaluator
from evals.evaluators.review_actions import (
    ReviewActionsEvaluator,
)
from evals.evaluators.review_actions import (
    collect_live_predictions as collect_review_live_predictions,
)
from evals.evaluators.search_url_recall import (
    SearchUrlRecallEvaluator,
)
from evals.evaluators.search_url_recall import (
    collect_live_predictions as collect_search_live_predictions,
)
from evals.evaluators.translation_quality import (
    TranslationQualityEvaluator,
)
from evals.evaluators.translation_quality import (
    collect_live_predictions as collect_translation_live_predictions,
)

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "evals" / "results"
DEFAULT_PIPELINE_FIXTURE = (
    PROJECT_ROOT / "evals" / "datasets" / "fixtures" / "sample_pipeline_output.json"
)
DEFAULT_FILTER_DATASET = PROJECT_ROOT / "evals" / "datasets" / "filter" / "urls.jsonl"
DEFAULT_FILTER_PREDICTIONS = (
    PROJECT_ROOT / "evals" / "datasets" / "fixtures" / "filter_predictions.jsonl"
)
DEFAULT_REVIEW_DATASET = PROJECT_ROOT / "evals" / "datasets" / "review" / "phrase_lists.jsonl"
DEFAULT_REVIEW_PREDICTIONS = (
    PROJECT_ROOT / "evals" / "datasets" / "fixtures" / "review_predictions.jsonl"
)
DEFAULT_EXTRACT_DATASET = PROJECT_ROOT / "evals" / "datasets" / "extract" / "gold_phrases.jsonl"
DEFAULT_EXTRACT_PREDICTIONS = (
    PROJECT_ROOT / "evals" / "datasets" / "fixtures" / "extract_predictions.jsonl"
)
DEFAULT_TRANSLATION_DATASET = PROJECT_ROOT / "evals" / "datasets" / "translation" / "phrases.jsonl"
DEFAULT_TRANSLATION_PREDICTIONS = (
    PROJECT_ROOT / "evals" / "datasets" / "fixtures" / "translation_judge_predictions.jsonl"
)
DEFAULT_SEARCH_DATASET = PROJECT_ROOT / "evals" / "datasets" / "search" / "gold_urls.jsonl"
DEFAULT_SEARCH_PREDICTIONS = (
    PROJECT_ROOT / "evals" / "datasets" / "fixtures" / "search_predictions.jsonl"
)

DEFAULT_PIPELINE_QUALITY_FIXTURE = (
    PROJECT_ROOT / "evals" / "datasets" / "fixtures" / "sample_pipeline_output.json"
)

SUITE_DEFAULTS = {
    "quote_faithfulness": DEFAULT_PIPELINE_FIXTURE,
    "filter_classification": DEFAULT_FILTER_DATASET,
    "review_actions": DEFAULT_REVIEW_DATASET,
    "extract_phrase_recall": DEFAULT_EXTRACT_DATASET,
    "translation_quality": DEFAULT_TRANSLATION_DATASET,
    "search_url_recall": DEFAULT_SEARCH_DATASET,
    "pipeline_quality": DEFAULT_PIPELINE_QUALITY_FIXTURE,
}

SUITE_PREDICTION_DEFAULTS = {
    "filter_classification": DEFAULT_FILTER_PREDICTIONS,
    "review_actions": DEFAULT_REVIEW_PREDICTIONS,
    "extract_phrase_recall": DEFAULT_EXTRACT_PREDICTIONS,
    "translation_quality": DEFAULT_TRANSLATION_PREDICTIONS,
    "search_url_recall": DEFAULT_SEARCH_PREDICTIONS,
}

LIVE_SUITES = {
    "filter_classification",
    "review_actions",
    "extract_phrase_recall",
    "translation_quality",
    "search_url_recall",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run study-article-pipeline evals")
    parser.add_argument(
        "--suite",
        required=True,
        choices=sorted(SUITE_DEFAULTS),
        help="Evaluation suite to run",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Input dataset path (defaults depend on suite)",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        default=None,
        help="Cached predictions for offline runs that require --predictions",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call the live agent or judge for suites that support live scoring",
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
        help="Minimum score required for the suite to pass",
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
    predictions_path: Path | None = None,
    live: bool = False,
):
    if suite == "quote_faithfulness":
        pipeline_output = load_pipeline_output(input_path)
        evaluator = QuoteFaithfulnessEvaluator(pass_threshold=pass_threshold)
        return evaluator.run(pipeline_output, case_id=input_path.stem)

    if suite == "filter_classification":
        cases = load_filter_dataset(input_path)
        evaluator = FilterClassificationEvaluator(pass_threshold=pass_threshold)

        if live:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY is required for --live filter_classification runs."
                )
            client = anthropic.Anthropic(api_key=api_key)
            predictions = collect_filter_live_predictions(cases, client)
        else:
            if predictions_path is None:
                raise ValueError(
                    "filter_classification requires --predictions unless --live is set."
                )
            predictions = load_filter_predictions(predictions_path)

        return evaluator.run(cases, predictions)

    if suite == "review_actions":
        cases = load_review_dataset(input_path)
        evaluator = ReviewActionsEvaluator(pass_threshold=pass_threshold)

        if live:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is required for --live review_actions runs.")
            client = anthropic.Anthropic(api_key=api_key)
            predictions = collect_review_live_predictions(cases, client)
        else:
            if predictions_path is None:
                raise ValueError("review_actions requires --predictions unless --live is set.")
            predictions = load_review_predictions(predictions_path)

        return evaluator.run(cases, predictions)

    if suite == "extract_phrase_recall":
        cases = load_extract_recall_dataset(input_path)
        evaluator = ExtractPhraseRecallEvaluator(pass_threshold=pass_threshold)

        if live:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY is required for --live extract_phrase_recall runs."
                )
            client = anthropic.Anthropic(api_key=api_key)
            predictions = collect_extract_live_predictions(cases, client)
        else:
            if predictions_path is None:
                raise ValueError(
                    "extract_phrase_recall requires --predictions unless --live is set."
                )
            predictions = load_extract_predictions(predictions_path)

        return evaluator.run(cases, predictions)

    if suite == "translation_quality":
        cases = load_translation_dataset(input_path)
        evaluator = TranslationQualityEvaluator(pass_threshold=pass_threshold)

        if live:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY is required for --live translation_quality runs."
                )
            client = anthropic.Anthropic(api_key=api_key)
            predictions = collect_translation_live_predictions(cases, client)
        else:
            if predictions_path is None:
                raise ValueError("translation_quality requires --predictions unless --live is set.")
            predictions = load_translation_predictions(predictions_path)

        return evaluator.run(cases, predictions)

    if suite == "search_url_recall":
        cases = load_search_recall_dataset(input_path)
        evaluator = SearchUrlRecallEvaluator(pass_threshold=pass_threshold)

        if live:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY is required for --live search_url_recall runs.")
            client = anthropic.Anthropic(api_key=api_key)
            predictions = collect_search_live_predictions(cases, client)
        else:
            if predictions_path is None:
                raise ValueError("search_url_recall requires --predictions unless --live is set.")
            predictions = load_search_predictions(predictions_path)

        return evaluator.run(cases, predictions)

    if suite == "pipeline_quality":
        pipeline_output = load_pipeline_output(input_path)
        evaluator = PipelineQualityEvaluator(pass_threshold=pass_threshold)
        return evaluator.run(pipeline_output, case_id=input_path.stem)

    raise ValueError(f"Unsupported suite: {suite}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = (args.input or SUITE_DEFAULTS[args.suite]).resolve()
    if not input_path.exists():
        parser.error(f"Input file not found: {input_path}")

    predictions_path = args.predictions or SUITE_PREDICTION_DEFAULTS.get(args.suite)
    if predictions_path is not None:
        predictions_path = predictions_path.resolve()

    if args.suite in SUITE_PREDICTION_DEFAULTS and not args.live:
        if predictions_path is None or not predictions_path.exists():
            parser.error(
                f"Predictions file not found: {predictions_path}. "
                f"Use --live to score against the live {args.suite} agent."
            )

    try:
        result = run_suite(
            args.suite,
            input_path,
            pass_threshold=args.pass_threshold,
            predictions_path=predictions_path,
            live=args.live,
        )
    except ValueError as exc:
        parser.error(str(exc))

    run_id = args.run_id or new_run_id()
    report = EvalReport(
        run_id=run_id,
        timestamp=new_run_id(),
        git_sha=current_git_sha(),
        config={
            "suite": args.suite,
            "input": str(input_path),
            "pass_threshold": args.pass_threshold,
            "live": args.live,
        },
        results=[result],
    )
    if predictions_path is not None:
        report.config["predictions"] = str(predictions_path)
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
