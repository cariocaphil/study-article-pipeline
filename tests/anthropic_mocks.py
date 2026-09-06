"""
Shared Anthropic API response mocks for agent unit tests.

Real Message responses always include usage metadata; mocks should too.
"""

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any

from anthropic.types import Usage


def mock_message(
    content: Sequence[Any],
    stop_reason: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        content=list(content),
        stop_reason=stop_reason,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def mock_parsed_message(
    parsed_output: Any,
    *,
    stop_reason: str = "end_turn",
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> SimpleNamespace:
    """Mock for client.messages.parse responses (includes parsed_output)."""
    return SimpleNamespace(
        content=[],
        stop_reason=stop_reason,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        parsed_output=parsed_output,
    )
