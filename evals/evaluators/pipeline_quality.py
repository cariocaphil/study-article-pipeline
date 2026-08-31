"""
Composite pipeline quality evaluator.

Scores a saved PipelineOutput with structural checks plus quote faithfulness,
translation validity, and CEFR level-floor compliance.
"""

from __future__ import annotations

from src.schemas.article import PipelineOutput
from src.tools.validate_translation import validate_translation

from evals.evaluators.base import EvalFailure, EvalResult
from evals.evaluators.quote_faithfulness import QuoteFaithfulnessEvaluator
from evals.evaluators.utils import safe_divide

DEFAULT_PASS_THRESHOLD = 1.0
MIN_ARTICLES = 3
MIN_PHRASES_PER_ARTICLE = 1


class PipelineQualityEvaluator:
    name = "pipeline_quality"

    def __init__(
        self,
        pass_threshold: float = DEFAULT_PASS_THRESHOLD,
        *,
        min_articles: int = MIN_ARTICLES,
        min_phrases_per_article: int = MIN_PHRASES_PER_ARTICLE,
    ) -> None:
        self.pass_threshold = pass_threshold
        self.min_articles = min_articles
        self.min_phrases_per_article = min_phrases_per_article

    def run(
        self,
        pipeline_output: PipelineOutput,
        *,
        case_id: str = "pipeline-output",
    ) -> EvalResult:
        failures: list[EvalFailure] = []
        subscores: dict[str, float] = {}

        article_count = len(pipeline_output.articles)
        structure_passed = article_count >= self.min_articles
        subscores["structure"] = 1.0 if structure_passed else 0.0

        if not structure_passed:
            failures.append(
                EvalFailure(
                    case_id=case_id,
                    category="insufficient_articles",
                    message="Pipeline output has fewer than the minimum required articles",
                    details={
                        "article_count": article_count,
                        "min_articles": self.min_articles,
                    },
                )
            )

        articles_with_enough_phrases = 0
        for article_index, article in enumerate(pipeline_output.articles, start=1):
            phrase_count = len(article.phrases)
            if phrase_count >= self.min_phrases_per_article:
                articles_with_enough_phrases += 1
                continue

            failures.append(
                EvalFailure(
                    case_id=f"{case_id}:article-{article_index}",
                    category="insufficient_phrases",
                    message="Article has fewer phrases than the minimum required",
                    details={
                        "article_title": article.title,
                        "phrase_count": phrase_count,
                        "min_phrases_per_article": self.min_phrases_per_article,
                    },
                )
            )

        if pipeline_output.articles:
            phrase_coverage = articles_with_enough_phrases / len(pipeline_output.articles)
        else:
            phrase_coverage = 0.0
        subscores["phrase_coverage"] = phrase_coverage

        quote_result = QuoteFaithfulnessEvaluator(
            pass_threshold=self.pass_threshold
        ).run(pipeline_output, case_id=case_id)
        subscores["quote_faithfulness"] = quote_result.score
        failures.extend(quote_result.failures)

        total_phrases = 0
        valid_translations = 0
        level_compliant_phrases = 0

        for article_index, article in enumerate(pipeline_output.articles, start=1):
            for phrase in article.phrases:
                total_phrases += 1

                if validate_translation(phrase.phrase, phrase.translation, quiet=True):
                    valid_translations += 1
                else:
                    failures.append(
                        EvalFailure(
                            case_id=f"{case_id}:article-{article_index}",
                            category="invalid_translation",
                            message="Phrase translation failed basic validation",
                            details={
                                "article_title": article.title,
                                "phrase": phrase.phrase,
                                "translation": phrase.translation,
                            },
                        )
                    )

                if phrase.estimated_level >= pipeline_output.user_level:
                    level_compliant_phrases += 1
                else:
                    failures.append(
                        EvalFailure(
                            case_id=f"{case_id}:article-{article_index}",
                            category="below_user_level",
                            message="Phrase estimated level is below the pipeline user level",
                            details={
                                "article_title": article.title,
                                "phrase": phrase.phrase,
                                "estimated_level": phrase.estimated_level.value,
                                "user_level": pipeline_output.user_level.value,
                            },
                        )
                    )

        subscores["translation_validity"] = safe_divide(
            valid_translations, total_phrases
        )
        subscores["level_floor_compliance"] = safe_divide(
            level_compliant_phrases, total_phrases
        )

        score = sum(subscores.values()) / len(subscores)

        metrics = {
            "article_count": article_count,
            "min_articles": self.min_articles,
            "min_phrases_per_article": self.min_phrases_per_article,
            "total_phrases": total_phrases,
            "subscores": subscores,
            "quote_faithfulness": quote_result.metrics,
            "pass_threshold": self.pass_threshold,
        }

        return EvalResult(
            evaluator=self.name,
            passed=score >= self.pass_threshold,
            score=score,
            metrics=metrics,
            failures=failures,
        )
