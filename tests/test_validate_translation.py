"""
Tests for src/tools/validate_translation.py.
"""

import logging

import pytest

from src.tools.validate_translation import validate_translation


def test_validate_translation_accepts_distinct_translation():
    assert validate_translation("turbulento", "turbulent") is True


def test_validate_translation_rejects_empty_translation():
    assert validate_translation("turbulento", "") is False
    assert validate_translation("turbulento", "   ") is False


def test_validate_translation_rejects_identical_copy():
    assert validate_translation("turbulento", "turbulento") is False


def test_validate_translation_rejects_identical_copy_case_insensitive():
    assert validate_translation("Turbulento", "turbulento") is False


def test_validate_translation_logs_valid(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="src.tools.validate_translation"):
        validate_translation("turbulento", "turbulent")

    assert "turbulento → turbulent → valid" in caplog.text


def test_validate_translation_logs_invalid(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="src.tools.validate_translation"):
        validate_translation("turbulento", "turbulento")

    assert "turbulento → turbulento → invalid" in caplog.text
