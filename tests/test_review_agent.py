"""
Tests for src/agents/review_agent.py.

These make real calls to the Anthropic API, so they're marked slow.
Run `uv run pytest -m "not slow"` to skip them.
"""

import pytest

from src.agents.review_agent import review_phrases


@pytest.mark.slow
def test_review_removes_proper_nouns(anthropic_client, sample_phrases):
    reviewed = review_phrases(sample_phrases, topic="Entroncamento", client=anthropic_client)

    reviewed_text = [p.phrase for p in reviewed]
    assert "Entroncamento" not in reviewed_text
    assert len(reviewed) < len(sample_phrases)


@pytest.mark.slow
def test_review_flags_duplicates(anthropic_client, sample_phrases, capsys):
    review_phrases(sample_phrases, topic="Entroncamento", client=anthropic_client)

    captured = capsys.readouterr()
    flagged_lines = [
        line for line in captured.out.splitlines() if "Flagged for review" in line
    ]

    assert len(flagged_lines) >= 1
    assert any(
        phrase in line
        for line in flagged_lines
        for phrase in ("comunidades marginalizadas", "marginalização")
    )
