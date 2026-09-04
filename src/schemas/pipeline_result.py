"""
Structured result returned when a full pipeline run completes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineRunResult:
    output_path: str
    run_id: str
    elapsed_seconds: float
    stage_seconds: dict[str, float] = field(default_factory=dict[str, float])
    urls_found: int = 0
    articles_kept: int = 0
    phrase_count: int = 0
    token_input: int = 0
    token_output: int = 0
