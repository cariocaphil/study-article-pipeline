"""Pydantic models for filter-agent structured outputs."""

from __future__ import annotations

from pydantic import BaseModel


class FilterArticleVerdict(BaseModel):
    """Structured output for a single filter-agent URL assessment."""

    is_review: bool
    is_correct_language: bool
    title: str = ""
    author: str | None = None
    source_name: str = ""
    full_text: str = ""
