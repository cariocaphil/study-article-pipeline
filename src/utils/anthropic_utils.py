"""Helpers for typed Anthropic API interactions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from anthropic.types import Message, ToolParam


def message_text(response: Message) -> str:
    """Join text blocks from a Message response."""
    return " ".join(block.text for block in response.content if block.type == "text")


def require_str_field(data: object, field: str) -> str:
    """Return a required string field from a tool-use input dict."""
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict tool input, got {type(data).__name__}")
    mapping = cast(Mapping[str, object], data)
    value = mapping.get(field)
    if not isinstance(value, str):
        raise TypeError(f"Expected string {field!r} in tool input")
    return value


def as_tool_param(schema: dict[str, object]) -> ToolParam:
    """Cast a client-side tool schema to Anthropic's ToolParam type."""
    return cast(ToolParam, schema)
