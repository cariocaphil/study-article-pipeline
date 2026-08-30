"""
Tests for the evaluation harness (deterministic, no API calls).
"""

import json
from pathlib import Path

import pytest

from evals.evaluators.base import (
    EvalReport,
    load_filter_dataset,
    load_filter_predictions,
    load_pipeline_output,
    load_review_dataset,
    load_review_predictions,
)
from evals.evaluators.filter_classification import FilterClassificationEvaluator
from evals.evaluators.quote_faithfulness import QuoteFaithfulnessEvaluator
from evals.evaluators.review_actions import ReviewActionsEvaluator
from evals.runners.run_evals import run_suite

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "datasets"
    / "fixtures"
    / "sample_pipeline_output.json"
)
FILTER_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "evals" / "datasets" / "filter" / "urls.jsonl"
)
FILTER_PREDICTIONS_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "datasets"
    / "fixtures"
    / "filter_predictions.jsonl"
)
REVIEW_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "evals" / "datasets" / "review" / "phrase_lists.jsonl"
)
REVIEW_PREDICTIONS_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "datasets"
    / "fixtures"
    / "review_predictions.jsonl"
)


class TestQuoteFaithfulnessEvaluator:
    def test_scores_mixed_fixture_at_fifty_percent(self):
        pipeline_output = load_pipeline_output(FIXTURE_PATH)
        result = QuoteFaithfulnessEvaluator(pass_threshold=1.0).run(
            pipeline_output,
            case_id="sample",
        )

        assert result.metrics["total_phrases"] == 2
        assert result.metrics["verified_phrases"] == 1
        assert result.metrics["unverified_phrases"] == 1
        assert result.score == pytest.approx(0.5)
        assert result.passed is False
        assert len(result.failures) == 1
        assert result.failures[0].category == "unverified_quote"

    def test_passes_when_all_quotes_are_verified(self):
        pipeline_output = load_pipeline_output(FIXTURE_PATH)
        article = pipeline_output.articles[0]
        article.phrases = [article.phrases[0]]

        result = QuoteFaithfulnessEvaluator().run(pipeline_output)

        assert result.score == 1.0
        assert result.passed is True
        assert result.failures == []

    def test_empty_phrase_list_passes_with_perfect_score(self):
        pipeline_output = load_pipeline_output(FIXTURE_PATH)
        pipeline_output.articles[0].phrases = []

        result = QuoteFaithfulnessEvaluator().run(pipeline_output)

        assert result.score == 1.0
        assert result.metrics["total_phrases"] == 0
        assert result.passed is True


class TestEvalReport:
    def test_save_writes_report_scores_and_failures(self, tmp_path):
        report = EvalReport(
            run_id="test-run",
            timestamp="2026-08-30T12:00:00Z",
            git_sha="abc1234",
            config={"suite": "quote_faithfulness"},
            results=[
                QuoteFaithfulnessEvaluator().run(
                    load_pipeline_output(FIXTURE_PATH),
                )
            ],
        )

        output_dir = report.save(tmp_path / "test-run")

        assert (output_dir / "report.json").exists()
        assert (output_dir / "scores.json").exists()
        assert (output_dir / "failures.jsonl").exists()

        saved_report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
        assert saved_report["run_id"] == "test-run"
        assert saved_report["passed"] is False


class TestRunEvalsCLI:
    def test_run_suite_returns_result_for_fixture(self):
        result = run_suite("quote_faithfulness", FIXTURE_PATH)

        assert result.evaluator == "quote_faithfulness"
        assert result.metrics["faithfulness_rate"] == pytest.approx(0.5)


class TestFilterClassificationEvaluator:
    def test_scores_cached_predictions_with_one_misclassification(self):
        cases = load_filter_dataset(FILTER_DATASET_PATH)
        predictions = load_filter_predictions(FILTER_PREDICTIONS_PATH)

        result = FilterClassificationEvaluator(pass_threshold=1.0).run(cases, predictions)

        assert result.metrics["total_cases"] == 12
        assert result.metrics["correct"] == 11
        assert result.score == pytest.approx(11 / 12)
        assert result.metrics["false_positive"] == 1
        assert result.metrics["precision"] == pytest.approx(2 / 3)
        assert result.metrics["recall"] == pytest.approx(1.0)
        assert result.passed is False
        assert len(result.failures) == 1
        assert result.failures[0].case_id == "filter-009"
        assert result.failures[0].category == "false_accept"

    def test_passes_when_all_predictions_match_labels(self):
        cases = load_filter_dataset(FILTER_DATASET_PATH)
        predictions = {
            case.id: case.expected_accept
            for case in cases
        }

        result = FilterClassificationEvaluator().run(cases, predictions)

        assert result.score == 1.0
        assert result.passed is True
        assert result.failures == []

    def test_run_suite_offline_filter_classification(self):
        result = run_suite(
            "filter_classification",
            FILTER_DATASET_PATH,
            predictions_path=FILTER_PREDICTIONS_PATH,
        )

        assert result.evaluator == "filter_classification"
        assert result.metrics["accuracy"] == pytest.approx(11 / 12)


class TestReviewActionsEvaluator:
    def test_scores_cached_predictions_with_intentional_errors(self):
        cases = load_review_dataset(REVIEW_DATASET_PATH)
        predictions = load_review_predictions(REVIEW_PREDICTIONS_PATH)

        result = ReviewActionsEvaluator(pass_threshold=1.0).run(cases, predictions)

        assert result.metrics["total_phrases"] == 12
        assert result.metrics["action_correct"] == 10
        assert result.metrics["action_accuracy"] == pytest.approx(10 / 12)
        assert result.metrics["removal_true_positive"] == 2
        assert result.metrics["removal_false_positive"] == 1
        assert result.metrics["removal_false_negative"] == 1
        assert result.score == pytest.approx(2 / 3)
        assert result.metrics["removal_precision"] == pytest.approx(2 / 3)
        assert result.metrics["removal_recall"] == pytest.approx(2 / 3)
        assert result.passed is False
        assert len(result.failures) == 2
        failure_categories = {failure.category for failure in result.failures}
        assert failure_categories == {"false_remove", "missed_remove"}

    def test_passes_when_all_predictions_match_labels(self):
        cases = load_review_dataset(REVIEW_DATASET_PATH)
        predictions = {
            case.id: case.expected_actions
            for case in cases
        }

        result = ReviewActionsEvaluator().run(cases, predictions)

        assert result.score == 1.0
        assert result.passed is True
        assert result.failures == []

    def test_run_suite_offline_review_actions(self):
        result = run_suite(
            "review_actions",
            REVIEW_DATASET_PATH,
            predictions_path=REVIEW_PREDICTIONS_PATH,
        )

        assert result.evaluator == "review_actions"
        assert result.metrics["removal_f1"] == pytest.approx(2 / 3)
