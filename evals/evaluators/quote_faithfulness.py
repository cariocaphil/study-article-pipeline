"""
Quote faithfulness evaluator.

Checks that every extracted phrase's sentence_context appears verbatim in
the article full_text it was attributed to.
"""

from __future__ import annotations

from evals.evaluators.base import EvalFailure, EvalResult
from src.schemas.article import PipelineOutput
from src.tools.verify_quote import verify_quote

DEFAULT_PASS_THRESHOLD = 1.0


class QuoteFaithfulnessEvaluator:
    name = "quote_faithfulness"

    def __init__(self, pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> None:
        self.pass_threshold = pass_threshold

    def run(
        self,
        pipeline_output: PipelineOutput,
        *,
        case_id: str = "pipeline-output",
    ) -> EvalResult:
        total_phrases = 0
        verified_phrases = 0
        failures: list[EvalFailure] = []

        for article_index, article in enumerate(pipeline_output.articles, start=1):
            for phrase in article.phrases:
                total_phrases += 1
                verified = verify_quote(
                    phrase.sentence_context,
                    article.full_text,
                    quiet=True,
                )
                if verified:
                    verified_phrases += 1
                    continue

                failures.append(
                    EvalFailure(
                        case_id=f"{case_id}:article-{article_index}",
                        category="unverified_quote",
                        message="sentence_context is not a verbatim quote from full_text",
                        details={
                            "article_title": article.title,
                            "phrase": phrase.phrase,
                            "sentence_context": phrase.sentence_context,
                        },
                    )
                )

        if total_phrases == 0:
            score = 1.0
        else:
            score = verified_phrases / total_phrases

        metrics = {
            "total_phrases": total_phrases,
            "verified_phrases": verified_phrases,
            "unverified_phrases": total_phrases - verified_phrases,
            "faithfulness_rate": score,
            "pass_threshold": self.pass_threshold,
        }

        return EvalResult(
            evaluator=self.name,
            passed=score >= self.pass_threshold,
            score=score,
            metrics=metrics,
            failures=failures,
        )
