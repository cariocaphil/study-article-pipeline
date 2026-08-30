"""
Tests for src/tools/validate_translation.py.
"""

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


def test_validate_translation_logs_valid(capsys):
    validate_translation("turbulento", "turbulent")

    captured = capsys.readouterr()
    assert "[translation_validator] turbulento → turbulent → valid" in captured.out


def test_validate_translation_logs_invalid(capsys):
    validate_translation("turbulento", "turbulento")

    captured = capsys.readouterr()
    assert "[translation_validator] turbulento → turbulento → invalid" in captured.out
