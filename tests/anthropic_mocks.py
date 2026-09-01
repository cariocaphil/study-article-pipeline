"""
Shared Anthropic API response mocks for agent unit tests.

Real Message responses always include usage metadata; mocks should too.
"""

from types import SimpleNamespace

from anthropic.types import Usage


def mock_message(
    content,
    stop_reason: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )
