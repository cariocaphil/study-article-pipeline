"""Load version-controlled prompt templates from ``src/prompts/``."""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(name: str, **kwargs: object) -> str:
    """
    Load ``src/prompts/{name}.txt`` and optionally interpolate with ``str.format``.

    Prompt files use ``{variable}`` for dynamic fields and doubled braces
    (``{{`` / ``}}``) for literal curly braces in JSON examples.
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    text = path.read_text(encoding="utf-8")
    if kwargs:
        return text.format(**kwargs)
    return text
