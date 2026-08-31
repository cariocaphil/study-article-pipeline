"""
Shared helpers for parsing JSON out of LLM text responses.

Claude sometimes emits otherwise-valid JSON where a string value contains a
literal, unescaped double quote (e.g. an article quoting a film title:
"...que filmou o \"Entroncamento\"..."). That breaks json.loads with errors
like `Expecting ',' delimiter`. extract_json() strips markdown fences and
typographic quote variants, then falls back to escaping stray inner quotes
before parsing.
"""

import json
import re

# Matches the start of a JSON object key, e.g. `"full_text":` — used to tell
# a real closing quote apart from an embedded one followed by a comma.
_KEY_START_RE = re.compile(r'\s*"[A-Za-z_][A-Za-z0-9_]*"\s*:')
# Matches the start of a new array element (nested object/array).
_NEW_ELEMENT_RE = re.compile(r"\s*[\{\[]")


def _strip_wrapper_text(text: str, open_char: str, close_char: str) -> str:
    clean = text.strip()
    clean = clean.replace("```json", "").replace("```", "").strip()
    # Normalize typographic/curly quotes so they can't be mistaken for
    # JSON string delimiters.
    clean = clean.replace("\u201c", "'").replace("\u201d", "'")
    clean = clean.replace("\u2018", "'").replace("\u2019", "'")
    clean = clean.replace("\u00ab", "'").replace("\u00bb", "'")
    start = clean.index(open_char)
    end = clean.rindex(close_char) + 1
    return clean[start:end]


def _is_real_closing_quote(remainder: str) -> bool:
    """
    Decide whether a `"` found while inside a JSON string actually closes
    that string, based on what comes after it.

    A naive check (e.g. "next non-whitespace char is a comma") is not
    enough: prose routinely contains a quoted phrase followed by a comma
    and more lowercase text, e.g. `"...pensarfazer?", com o ruído...`. That
    comma isn't a JSON delimiter, so treating it as one desyncs the parser
    for the rest of the document. Instead, a trailing comma only counts as
    a real delimiter if what follows it actually looks like the start of a
    new JSON key (`"key":`) or a new array element (`{`/`[`).
    """
    stripped = remainder.lstrip(" \t\r\n")
    if stripped == "":
        return True
    ch = stripped[0]
    if ch in "}]:":
        return True
    if ch == ",":
        after_comma = stripped[1:]
        return bool(_KEY_START_RE.match(after_comma) or _NEW_ELEMENT_RE.match(after_comma))
    return False


def _escape_stray_inner_quotes(json_str: str) -> str:
    """
    Escape `"` characters that appear inside JSON string values but are not
    actually closing/opening that string (a common artifact of LLM output,
    e.g. quoted dialogue or titles embedded in extracted article text).

    Walks the text tracking whether we're inside a string. Any unescaped
    quote encountered while inside a string is only treated as a real
    closing quote if what follows it looks like valid JSON continuation
    (see `_is_real_closing_quote`); otherwise it's an embedded quote and
    gets escaped.
    """
    result = []
    in_string = False
    n = len(json_str)
    i = 0
    while i < n:
        ch = json_str[i]
        if ch == "\\" and i + 1 < n:
            result.append(ch)
            result.append(json_str[i + 1])
            i += 2
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
            elif _is_real_closing_quote(json_str[i + 1 :]):
                in_string = False
                result.append(ch)
            else:
                result.append('\\"')
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def extract_json(text: str, open_char: str = "[", close_char: str = "]"):
    """
    Extract and parse a JSON array/object embedded in an LLM text response.

    Raises ValueError (with the original response attached) if parsing
    fails even after attempting to repair stray unescaped quotes.
    """
    try:
        candidate = _strip_wrapper_text(text, open_char, close_char)
    except ValueError as e:
        raise ValueError(
            f"Could not find {open_char!r}...{close_char!r} JSON block in response.\n"
            f"Raw response: {text}\nError: {e}"
        )

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    repaired = _escape_stray_inner_quotes(candidate)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse JSON from response.\nRaw response: {text}\nError: {e}")
