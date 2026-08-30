"""
Tests for the evaluation harness (deterministic, no API calls).
"""

import json
from pathlib import Path

import pytest

from evals.evaluators.base import EvalReport, load_pipeline_output
from evals.evaluators.quote_faithfulness import QuoteFaithfulnessEvaluator
from evals.runners.run_evals import run_suite

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "datasets"
    / "fixtures"
    / "sample_pipeline_output.json"
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
