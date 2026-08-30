"""
Shared types and helpers for the evaluation harness.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


@dataclass
class EvalFailure:
    case_id: str
    category: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    evaluator: str
    passed: bool
    score: float
    metrics: dict[str, Any]
    failures: list[EvalFailure] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluator": self.evaluator,
            "passed": self.passed,
            "score": self.score,
            "metrics": self.metrics,
            "failures": [asdict(failure) for failure in self.failures],
        }


@dataclass
class EvalReport:
    run_id: str
    timestamp: str
    git_sha: str | None
    config: dict[str, Any]
    results: list[EvalResult]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "git_sha": self.git_sha,
            "config": self.config,
            "passed": self.passed,
            "results": [result.to_dict() for result in self.results],
        }

    def save(self, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)

        report_path = output_dir / "report.json"
        scores_path = output_dir / "scores.json"
        failures_path = output_dir / "failures.jsonl"

        report_path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        scores_path.write_text(
            json.dumps(
                {
                    "run_id": self.run_id,
                    "timestamp": self.timestamp,
                    "git_sha": self.git_sha,
                    "passed": self.passed,
                    "scores": {
                        result.evaluator: {
                            "passed": result.passed,
                            "score": result.score,
                            "metrics": result.metrics,
                        }
                        for result in self.results
                    },
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with failures_path.open("w", encoding="utf-8") as handle:
            for result in self.results:
                for failure in result.failures:
                    record = {
                        "evaluator": result.evaluator,
                        **asdict(failure),
                    }
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")

        return output_dir


class Evaluator(Protocol):
    name: str

    def run(self, **kwargs: Any) -> EvalResult: ...


def current_git_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_pipeline_output(path: Path):
    from src.schemas.article import PipelineOutput

    data = json.loads(path.read_text(encoding="utf-8"))
    return PipelineOutput.model_validate(data)
