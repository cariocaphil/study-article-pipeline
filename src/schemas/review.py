"""Pydantic models for review-agent structured outputs."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ReviewAction(str, Enum):
    keep = "keep"
    review = "review"
    remove = "remove"


class ReviewVerdict(BaseModel):
    phrase: str
    action: ReviewAction
    reason: str = ""


class ReviewVerdicts(BaseModel):
    """Structured output wrapper — Anthropic output_format requires an object schema."""

    verdicts: list[ReviewVerdict] = Field(default_factory=lambda: [])
