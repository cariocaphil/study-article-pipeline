"""Pydantic models for LLM-as-judge structured outputs."""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field, field_validator


class TranslationJudgeVerdict(BaseModel):
    """Structured output for the translation adequacy judge."""

    adequate: bool
    reason: str = ""


class DocumentQualityDimensions(BaseModel):
    """Per-dimension scores for the document quality judge (1–5)."""

    structure_completeness: float = Field(ge=1, le=5)
    topic_relevance: float = Field(ge=1, le=5)
    article_usefulness: float = Field(ge=1, le=5)
    phrase_quality: float = Field(ge=1, le=5)
    translation_quality: float = Field(ge=1, le=5)
    quote_faithfulness: float = Field(ge=1, le=5)
    duplication: float = Field(ge=1, le=5)
    overall_usefulness: float = Field(ge=1, le=5)


class DocumentQualityVerdict(BaseModel):
    """Structured output for the document quality judge."""

    dimensions: DocumentQualityDimensions
    overall: float = Field(ge=1, le=5)
    summary: str
    defects: list[str] = Field(default_factory=lambda: [])

    @field_validator("summary")
    @classmethod
    def summary_must_be_non_empty(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("summary must be a non-empty string")
        return stripped

    @field_validator("defects", mode="before")
    @classmethod
    def clean_defects(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("defects must be an array of strings")
        items = cast(list[object], value)
        return [stripped for item in items if (stripped := str(item).strip())]
