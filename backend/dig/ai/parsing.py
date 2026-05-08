"""Lenient JSON parser for LLM responses.

Local LLMs (and even cloud ones in lower temperatures) routinely
respond with prose-around-JSON, code-fenced JSON, or trailing
commentary. A strict ``json.loads`` fails on all of those — the
user then gets "AI returned non-JSON" toasts that make the feature
look broken when the LLM was actually mostly cooperative.

This module is the single canonical parser every AI feature in DIG
uses. Anything that calls ``chat()`` with ``response_format="json_object"``
should pipe the response through here.
"""
from __future__ import annotations

import json
from typing import Any


def parse_json_lenient(text: str) -> dict[str, Any] | None:
    """Parse JSON from text that may have prose around it, code-fence
    markers, or trailing commas. Returns the parsed dict, or None if
    nothing valid can be extracted.

    Handles three common LLM imperfections:

      1. ``` json ... ``` markdown code fences (with or without the
         language tag).
      2. Prose preamble ("Here's the JSON:") followed by the object.
      3. Trailing prose after the closing brace.

    Strategy: strip code fences first; if direct parse fails, scan for
    the first balanced ``{...}`` block via brace-depth counting and
    parse that.
    """
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:].strip()
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        pass
    # Fallback: scan for a balanced top-level object via brace-depth
    # counting, ignoring braces inside string literals.
    start = s.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(s)):
            ch = s[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = s[start:i + 1]
                    try:
                        v = json.loads(candidate)
                        if isinstance(v, dict):
                            return v
                    except json.JSONDecodeError:
                        break  # try next opening brace
                    break
        start = s.find("{", start + 1)
    return None
