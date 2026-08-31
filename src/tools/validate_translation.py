"""
Translation validator.
Checks that a translation is non-empty and not a lazy copy of the source phrase.
"""


def validate_translation(phrase: str, translation: str, *, quiet: bool = False) -> bool:
    """
    Return True if translation is a plausible translation of phrase.

    Rejects empty translations and translations identical to the source phrase
    (a common lazy-model failure mode).
    """
    phrase_stripped = phrase.strip()
    translation_stripped = translation.strip()

    if not translation_stripped:
        valid = False
    elif translation_stripped.casefold() == phrase_stripped.casefold():
        valid = False
    else:
        valid = True

    status_label = "valid" if valid else "invalid"
    if not quiet:
        print(f"[translation_validator] {phrase} → {translation} → {status_label}")
    return valid
