"""
Quote verifier.
Checks whether a sentence appears verbatim in the source article text.
"""

import re
import unicodedata


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def verify_quote(sentence: str, article_text: str, *, quiet: bool = False) -> bool:
    """
    Return True if sentence appears verbatim in article_text.

    Whitespace is normalized in both strings before comparison so minor
    line-break or spacing differences do not cause false negatives.
    """
    normalized_sentence = _normalize(sentence)
    if not normalized_sentence:
        verified = False
    else:
        normalized_article = _normalize(article_text)
        verified = normalized_sentence in normalized_article

    if not quiet:
        status_label = "verified" if verified else "not found"
        print(f"[quote_verifier] {sentence} → {status_label}")
    return verified
