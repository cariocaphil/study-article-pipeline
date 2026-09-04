"""
Search URL recall evaluator.

Scores search agent output against human-labeled gold URLs for fixed topics.
Primary metric is URL recall: did search surface the known-good links?
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlparse, urlunparse

import anthropic

from evals.evaluators.base import EvalFailure, EvalResult
from evals.evaluators.utils import safe_divide

DEFAULT_PASS_THRESHOLD = 1.0


@dataclass
class SearchRecallCase:
    id: str
    topic: str
    source_language: str
    n_articles: int
    gold_urls: list[str]
    topic_type: str | None = None
    forbidden_urls: list[str] | None = None
    forbidden_url_substrings: list[str] | None = None


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        path=parsed.path.rstrip("/") or "/",
        fragment="",
    )
    return urlunparse(normalized)


def _match_url(gold_url: str, predicted_urls: set[str]) -> bool:
    return _normalize_url(gold_url) in predicted_urls


def _predicted_url_set(urls: list[str]) -> set[str]:
    return {_normalize_url(url) for url in urls}


def _url_contains_forbidden_substring(url: str, substring: str) -> bool:
    needle = substring.casefold()
    candidates = (url.casefold(), unquote(url).casefold())
    return any(needle in candidate for candidate in candidates)


class SearchUrlRecallEvaluator:
    name = "search_url_recall"

    def __init__(self, pass_threshold: float = DEFAULT_PASS_THRESHOLD) -> None:
        self.pass_threshold = pass_threshold

    def run(
        self,
        cases: list[SearchRecallCase],
        predictions: dict[str, list[str]],
    ) -> EvalResult:
        failures: list[EvalFailure] = []
        matched_gold = 0
        total_gold = 0

        for case in cases:
            case_predictions = predictions.get(case.id)
            if case_predictions is None:
                failures.append(
                    EvalFailure(
                        case_id=case.id,
                        category="missing_prediction",
                        message="No prediction recorded for labeled search case",
                        details={"topic": case.topic},
                    )
                )
                continue

            predicted_urls = _predicted_url_set(case_predictions)

            for gold_url in case.gold_urls:
                total_gold += 1
                matched = _match_url(gold_url, predicted_urls)

                if matched:
                    matched_gold += 1
                else:
                    failures.append(
                        EvalFailure(
                            case_id=case.id,
                            category="missed_gold_url",
                            message="Gold URL was not returned by search",
                            details={
                                "gold_url": gold_url,
                                "topic": case.topic,
                                "predicted_urls": case_predictions,
                            },
                        )
                    )

            for forbidden_url in case.forbidden_urls or []:
                if _match_url(forbidden_url, predicted_urls):
                    failures.append(
                        EvalFailure(
                            case_id=case.id,
                            category="forbidden_url",
                            message=(
                                "Search returned a URL for a different work that must "
                                "not be treated as a match for this topic"
                            ),
                            details={
                                "forbidden_url": forbidden_url,
                                "topic": case.topic,
                                "predicted_urls": case_predictions,
                            },
                        )
                    )

            for substring in case.forbidden_url_substrings or []:
                matching_urls = [
                    url
                    for url in case_predictions
                    if _url_contains_forbidden_substring(url, substring)
                ]
                if matching_urls:
                    failures.append(
                        EvalFailure(
                            case_id=case.id,
                            category="forbidden_url",
                            message=(
                                "Search returned a URL whose path/title matches a "
                                "forbidden alternate-work marker for this topic"
                            ),
                            details={
                                "forbidden_substring": substring,
                                "matching_urls": matching_urls,
                                "topic": case.topic,
                                "predicted_urls": case_predictions,
                            },
                        )
                    )

        recall = safe_divide(matched_gold, total_gold)
        forbidden_hits = sum(1 for failure in failures if failure.category == "forbidden_url")

        metrics: dict[str, Any] = {
            "total_gold_urls": total_gold,
            "matched_gold_urls": matched_gold,
            "forbidden_hits": forbidden_hits,
            "recall": recall,
            "pass_threshold": self.pass_threshold,
        }

        return EvalResult(
            evaluator=self.name,
            passed=recall >= self.pass_threshold and forbidden_hits == 0,
            score=recall,
            metrics=metrics,
            failures=failures,
        )


def collect_live_predictions(
    cases: list[SearchRecallCase],
    client: anthropic.Anthropic,
    *,
    search_fn: Callable[[str, str, int, anthropic.Anthropic], list[str]] | None = None,
) -> dict[str, list[str]]:
    from src.agents.search_agent import search_articles
    from src.schemas.article import TopicType

    predictions: dict[str, list[str]] = {}

    for case in cases:
        if search_fn is not None:
            predictions[case.id] = search_fn(
                case.topic,
                case.source_language,
                case.n_articles,
                client,
            )
            continue

        topic_type = TopicType(case.topic_type) if case.topic_type else TopicType.film
        predictions[case.id] = search_articles(
            case.topic,
            case.source_language,
            case.n_articles,
            client,
            topic_type=topic_type,
        )

    return predictions
