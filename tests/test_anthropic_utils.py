"""Tests for src/utils/anthropic_utils.py."""

from typing import cast

import pytest
from anthropic.types.parsed_message import ParsedMessage

from src.schemas.review import ReviewVerdicts
from src.utils.anthropic_utils import require_parsed_output
from tests.anthropic_mocks import mock_parsed_message


def test_require_parsed_output_returns_value():
    response = cast(
        ParsedMessage[ReviewVerdicts],
        mock_parsed_message(ReviewVerdicts(verdicts=[])),
    )
    assert require_parsed_output(response) == ReviewVerdicts(verdicts=[])


def test_require_parsed_output_raises_when_missing():
    response = cast(ParsedMessage[ReviewVerdicts], mock_parsed_message(None))
    with pytest.raises(ValueError, match="parsed structured output"):
        require_parsed_output(response)
