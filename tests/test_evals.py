"""
Tests for the evaluation harness (deterministic, no API calls).
"""

import json
from pathlib import Path

import pytest

from evals.evaluators.base import (
    EvalReport,
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
)
from evals.evaluators.extract_phrase_recall import ExtractPhraseRecallEvaluator
from evals.evaluators.filter_classification import FilterClassificationEvaluator
from evals.evaluators.pipeline_quality import PipelineQualityEvaluator
from evals.evaluators.quote_faithfulness import QuoteFaithfulnessEvaluator
from evals.evaluators.review_actions import ReviewActionsEvaluator
from evals.evaluators.search_url_recall import SearchUrlRecallEvaluator
from evals.evaluators.translation_quality import TranslationQualityEvaluator
from evals.runners.compare_runs import compare_runs
from evals.runners.run_evals import run_suite

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "datasets"
    / "fixtures"
    / "sample_pipeline_output.json"
)
GOOD_PIPELINE_FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "datasets"
    / "fixtures"
    / "pipeline_output_good.json"
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
EXTRACT_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "evals" / "datasets" / "extract" / "gold_phrases.jsonl"
)
EXTRACT_PREDICTIONS_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "datasets"
    / "fixtures"
    / "extract_predictions.jsonl"
)
TRANSLATION_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "evals" / "datasets" / "translation" / "phrases.jsonl"
)
TRANSLATION_PREDICTIONS_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "datasets"
    / "fixtures"
    / "translation_judge_predictions.jsonl"
)
SEARCH_DATASET_PATH = (
    Path(__file__).resolve().parent.parent / "evals" / "datasets" / "search" / "gold_urls.jsonl"
)
SEARCH_PREDICTIONS_PATH = (
    Path(__file__).resolve().parent.parent
    / "evals"
    / "datasets"
    / "fixtures"
    / "search_predictions.jsonl"
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
        predictions = {case.id: case.expected_accept for case in cases}

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
        predictions = {case.id: case.expected_actions for case in cases}

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


class TestExtractPhraseRecallEvaluator:
    def test_scores_cached_predictions_with_intentional_misses(self):
        cases = load_extract_recall_dataset(EXTRACT_DATASET_PATH)
        predictions = load_extract_predictions(EXTRACT_PREDICTIONS_PATH)

        result = ExtractPhraseRecallEvaluator(pass_threshold=1.0).run(cases, predictions)

        assert result.metrics["total_gold_phrases"] == 9
        assert result.metrics["matched_gold_phrases"] == 6
        assert result.score == pytest.approx(6 / 9)
        assert result.passed is False
        assert len(result.failures) == 3
        assert all(failure.category == "missed_gold_phrase" for failure in result.failures)

    def test_passes_when_all_gold_phrases_are_predicted(self):
        cases = load_extract_recall_dataset(EXTRACT_DATASET_PATH)
        predictions = {case.id: case.gold_phrases for case in cases}

        result = ExtractPhraseRecallEvaluator().run(cases, predictions)

        assert result.score == 1.0
        assert result.passed is True
        assert result.failures == []

    def test_run_suite_offline_extract_phrase_recall(self):
        result = run_suite(
            "extract_phrase_recall",
            EXTRACT_DATASET_PATH,
            predictions_path=EXTRACT_PREDICTIONS_PATH,
        )

        assert result.evaluator == "extract_phrase_recall"
        assert result.metrics["recall"] == pytest.approx(6 / 9)


class TestTranslationQualityEvaluator:
    def test_scores_cached_judge_predictions_with_one_misclassification(self):
        cases = load_translation_dataset(TRANSLATION_DATASET_PATH)
        predictions = load_translation_predictions(TRANSLATION_PREDICTIONS_PATH)

        result = TranslationQualityEvaluator(pass_threshold=1.0).run(cases, predictions)

        assert result.metrics["total_cases"] == 10
        assert result.metrics["correct"] == 9
        assert result.score == pytest.approx(0.9)
        assert result.passed is False
        assert len(result.failures) == 1
        assert result.failures[0].case_id == "translation-006"
        assert result.failures[0].category == "false_inadequate"

    def test_passes_when_all_judge_predictions_match_labels(self):
        from evals.evaluators.translation_quality import TranslationJudgment

        cases = load_translation_dataset(TRANSLATION_DATASET_PATH)
        predictions = {
            case.id: TranslationJudgment(adequate=case.expected_adequate) for case in cases
        }

        result = TranslationQualityEvaluator().run(cases, predictions)

        assert result.score == 1.0
        assert result.passed is True
        assert result.failures == []

    def test_run_suite_offline_translation_quality(self):
        result = run_suite(
            "translation_quality",
            TRANSLATION_DATASET_PATH,
            predictions_path=TRANSLATION_PREDICTIONS_PATH,
        )

        assert result.evaluator == "translation_quality"
        assert result.metrics["accuracy"] == pytest.approx(0.9)


class TestSearchUrlRecallEvaluator:
    def test_scores_cached_predictions_with_one_missed_gold_url(self):
        cases = load_search_recall_dataset(SEARCH_DATASET_PATH)
        predictions = load_search_predictions(SEARCH_PREDICTIONS_PATH)

        result = SearchUrlRecallEvaluator(pass_threshold=1.0).run(cases, predictions)

        assert result.metrics["total_gold_urls"] == 4
        assert result.metrics["matched_gold_urls"] == 3
        assert result.metrics["forbidden_hits"] == 0
        assert result.score == pytest.approx(3 / 4)
        assert result.passed is False
        assert len(result.failures) == 1
        assert result.failures[0].case_id == "search-003"
        assert result.failures[0].category == "missed_gold_url"

    def test_normalizes_urls_when_matching(self):
        cases = load_search_recall_dataset(SEARCH_DATASET_PATH)[:1]
        gold_url = cases[0].gold_urls[0]
        predictions = {cases[0].id: [gold_url.rstrip("/") + "/"]}

        result = SearchUrlRecallEvaluator().run(cases, predictions)

        assert result.score == 1.0
        assert result.passed is True

    def test_passes_when_all_gold_urls_are_predicted(self):
        cases = load_search_recall_dataset(SEARCH_DATASET_PATH)
        predictions = {case.id: case.gold_urls for case in cases}

        result = SearchUrlRecallEvaluator().run(cases, predictions)

        assert result.score == 1.0
        assert result.passed is True
        assert result.failures == []

    def test_madre_case_loads_year_topic_type_and_forbidden_urls(self):
        cases = load_search_recall_dataset(SEARCH_DATASET_PATH)
        madre = next(case for case in cases if case.id == "search-004")

        assert madre.topic == "Madre (2017)"
        assert madre.topic_type == "film"
        assert madre.source_language == "spanish"
        assert madre.forbidden_urls is not None
        assert any("mother-review" in url for url in madre.forbidden_urls)
        assert madre.forbidden_url_substrings == ["madre!", "¡madre!", "mother!"]

    def test_madre_regression_fails_when_mother_bang_url_is_predicted(self):
        cases = load_search_recall_dataset(SEARCH_DATASET_PATH)
        madre = next(case for case in cases if case.id == "search-004")
        assert madre.forbidden_urls is not None

        predictions = {
            madre.id: [
                *madre.gold_urls,
                madre.forbidden_urls[0],
            ]
        }

        result = SearchUrlRecallEvaluator(pass_threshold=1.0).run([madre], predictions)

        assert result.metrics["matched_gold_urls"] == 1
        assert result.metrics["forbidden_hits"] == 1
        assert result.score == 1.0
        assert result.passed is False
        assert result.failures[0].category == "forbidden_url"
        assert result.failures[0].case_id == "search-004"

    @pytest.mark.parametrize(
        "wrong_work_url",
        [
            "https://example.com/critica/madre!-aronofsky-2017",
            "https://example.com/cine/%C2%A1madre!-jennifer-lawrence",
            "https://example.com/reviews/mother!-darren-aronofsky",
        ],
    )
    def test_madre_regression_fails_on_spanish_and_english_mother_bang_titles(
        self, wrong_work_url: str
    ):
        cases = load_search_recall_dataset(SEARCH_DATASET_PATH)
        madre = next(case for case in cases if case.id == "search-004")

        predictions = {madre.id: [*madre.gold_urls, wrong_work_url]}
        result = SearchUrlRecallEvaluator(pass_threshold=1.0).run([madre], predictions)

        assert result.passed is False
        assert result.metrics["forbidden_hits"] >= 1
        assert any(failure.category == "forbidden_url" for failure in result.failures)

    def test_madre_gold_url_without_exclamation_is_not_treated_as_forbidden(self):
        cases = load_search_recall_dataset(SEARCH_DATASET_PATH)
        madre = next(case for case in cases if case.id == "search-004")

        predictions = {madre.id: list(madre.gold_urls)}
        result = SearchUrlRecallEvaluator(pass_threshold=1.0).run([madre], predictions)

        assert result.passed is True
        assert result.metrics["forbidden_hits"] == 0

    def test_run_suite_offline_search_url_recall(self):
        result = run_suite(
            "search_url_recall",
            SEARCH_DATASET_PATH,
            predictions_path=SEARCH_PREDICTIONS_PATH,
        )

        assert result.evaluator == "search_url_recall"
        assert result.metrics["recall"] == pytest.approx(3 / 4)
        assert result.metrics["forbidden_hits"] == 0


class TestPipelineQualityEvaluator:
    def test_scores_sample_fixture_with_structural_and_quote_failures(self):
        pipeline_output = load_pipeline_output(FIXTURE_PATH)
        result = PipelineQualityEvaluator(pass_threshold=1.0).run(
            pipeline_output,
            case_id="sample",
        )

        assert result.metrics["article_count"] == 1
        assert result.metrics["total_phrases"] == 2
        assert result.metrics["subscores"]["structure"] == 0.0
        assert result.metrics["subscores"]["phrase_coverage"] == pytest.approx(1.0)
        assert result.metrics["subscores"]["quote_faithfulness"] == pytest.approx(0.5)
        assert result.metrics["subscores"]["translation_validity"] == pytest.approx(1.0)
        assert result.metrics["subscores"]["level_floor_compliance"] == pytest.approx(1.0)
        assert result.score == pytest.approx(0.7)
        assert result.passed is False
        failure_categories = {failure.category for failure in result.failures}
        assert "insufficient_articles" in failure_categories
        assert "unverified_quote" in failure_categories

    def test_passes_good_fixture_with_perfect_subscores(self):
        pipeline_output = load_pipeline_output(GOOD_PIPELINE_FIXTURE_PATH)
        result = PipelineQualityEvaluator().run(pipeline_output)

        assert result.metrics["article_count"] == 3
        assert result.metrics["total_phrases"] == 4
        assert result.score == pytest.approx(1.0)
        assert result.passed is True
        assert result.failures == []

    def test_run_suite_offline_pipeline_quality(self):
        result = run_suite("pipeline_quality", FIXTURE_PATH)

        assert result.evaluator == "pipeline_quality"
        assert result.score == pytest.approx(0.7)


class TestCompareRuns:
    def test_detects_regression_and_improvement(self, tmp_path):
        baseline_dir = tmp_path / "baseline"
        candidate_dir = tmp_path / "candidate"
        baseline_dir.mkdir()
        candidate_dir.mkdir()

        (baseline_dir / "scores.json").write_text(
            json.dumps(
                {
                    "run_id": "baseline-run",
                    "scores": {
                        "filter_classification": {
                            "passed": True,
                            "score": 0.9,
                            "metrics": {},
                        },
                        "translation_quality": {
                            "passed": True,
                            "score": 1.0,
                            "metrics": {},
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        (candidate_dir / "scores.json").write_text(
            json.dumps(
                {
                    "run_id": "candidate-run",
                    "scores": {
                        "filter_classification": {
                            "passed": False,
                            "score": 0.8,
                            "metrics": {},
                        },
                        "translation_quality": {
                            "passed": True,
                            "score": 1.0,
                            "metrics": {},
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        baseline = json.loads((baseline_dir / "scores.json").read_text(encoding="utf-8"))
        candidate = json.loads((candidate_dir / "scores.json").read_text(encoding="utf-8"))
        comparisons = compare_runs(baseline, candidate)

        by_evaluator = {item.evaluator: item for item in comparisons}
        assert by_evaluator["filter_classification"].status == "regressed"
        assert by_evaluator["filter_classification"].delta == pytest.approx(-0.1)
        assert by_evaluator["translation_quality"].status == "unchanged"
