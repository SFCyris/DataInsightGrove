"""Suggest a corrected expression when the user is stuck.

The "expression" mini-language DIG accepts is a SQL fragment usable as a
predicate (filter_rows) or a derivation (derive_column). Common failure
modes:

  - Wrong column name (typo, case mismatch)
  - String literal not quoted
  - SQL function name from a different dialect (NVL vs COALESCE, …)
  - Predicate vs scalar confusion

This feature builds a tight prompt with the user's expression, the
schema, and (optionally) their natural-language intent, and asks the
LLM for a corrected version. We force JSON output for parseability.
"""

from __future__ import annotations

import json
from typing import Any

from dig.ai.client import AiConfig, AiError, chat


_SYSTEM = """\
You correct SQL expression fragments for a data preparation tool called DIG.

DIG expressions are SQL snippets that compile into a DuckDB SQL clause:
  - For filter_rows.predicate: a boolean expression (e.g. status = 'active')
  - For derive_column.expression: a scalar expression (e.g. amount * 1.07)

Available SQL functions: standard DuckDB functions (LOWER, UPPER, COALESCE,
SUBSTR, REGEXP_MATCHES, CAST, TRY_CAST, etc.). Identifiers may be
double-quoted to allow spaces or reserved-word names: "Customer ID".

You are given:
  - The user's current (broken or unclear) expression
  - The available column names and their types
  - Optionally, an error message from DuckDB
  - Optionally, the user's natural-language description of intent

Output JSON only — no prose, no Markdown, no code fences. Schema:

{
  "fixed": "<the corrected SQL fragment>",
  "explanation": "<one short sentence explaining what changed and why>",
  "confidence": "high" | "medium" | "low"
}

If you cannot determine a correct fix, return confidence=low and explain
what additional information you need in the explanation field. Never
return SQL that contains semicolons, comments, or DDL/DML keywords —
DIG strips them out for safety, so suggesting them won't work.
"""


async def fix_expression(
    cfg: AiConfig,
    *,
    expression: str,
    columns: list[dict[str, str]],
    intent: str | None = None,
    error: str | None = None,
    kind: str = "predicate",
) -> dict[str, Any]:
    """Ask the LLM to correct an expression. Returns a dict with keys
    `fixed`, `explanation`, `confidence`. Raises AiError on failure to
    get a parseable response.
    """
    schema_lines = "\n".join(
        f"  {c.get('name', '?')}  {c.get('type', '?')}"
        for c in columns
    ) or "  (no columns supplied)"

    user_msg_parts = [
        f"Expression kind: {kind}",
        f"Available columns:\n{schema_lines}",
        f"Current expression:\n  {expression or '(empty)'}",
    ]
    if error:
        user_msg_parts.append(f"DuckDB error:\n  {error}")
    if intent:
        user_msg_parts.append(f"User intent (plain English):\n  {intent}")

    user_msg = "\n\n".join(user_msg_parts) + "\n\nReturn the JSON object now."

    resp = await chat(
        cfg,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        response_format="json_object",
        temperature=0.0,
        max_tokens=512,
    )

    text = resp.text.strip()
    # Some local models still wrap JSON in code fences despite instructions.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise AiError(
            f"AI returned non-JSON: {text[:300]} ({e})",
        ) from e

    if not isinstance(parsed, dict) or "fixed" not in parsed:
        raise AiError(f"AI response missing required keys: {text[:300]}")

    return {
        "fixed": str(parsed.get("fixed", "")),
        "explanation": str(parsed.get("explanation", "")),
        "confidence": str(parsed.get("confidence", "medium")),
    }
