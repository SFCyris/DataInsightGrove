"""Domain-aware dataset explanation.

Given a dataset's column schema + lineage signals (filename, connector,
top-N sample values), the LLM returns:
  1. A short narrative — what this dataset appears to represent.
  2. A per-column meaning map — short plain-English descriptions for
     each "key" column (we cap at ~12 to keep the prompt small).
  3. A confidence rating ("high" | "medium" | "low").

Mirrors the design of `suggest_visualizations.py` so signals are
processed the same way (filename > connector > sample values >
column names + types).

Empty-message recovery: same two-phase chat as the viz suggestor —
try with response_format=json_object, on empty retry without, and
if both empty surface a graceful "no suggestion" result.
"""
from __future__ import annotations

from typing import Any

from dig.ai.client import AiConfig, AiError, chat
from dig.ai.parsing import parse_json_lenient
from dig.ai.prompts import TOKEN_BUDGETS


_SYSTEM = """\
You are a domain-aware data-explainer for DataInsightGrove (DIG).

Given a dataset's columns + sample values + provenance hints, you must:
  1. Infer what this dataset represents (one short narrative paragraph,
     2-4 sentences, plain English — like explaining to a smart colleague
     who hasn't seen the file).
  2. Give a one-line meaning for the most important columns (cap at 12
     columns; if there are more, pick the most informative — typically
     identifiers, primary measurements, dimensional attributes, dates).
  3. Rate your confidence (high | medium | low).

Rules:
  - Don't hallucinate provenance. If the columns are generic (id, name,
     value), say so and rate confidence "low".
  - Use the data, not your imagination. Refer to actual sample values
    when the meaning is non-obvious from the column name.
  - Keep column descriptions to one short sentence each.
  - The narrative should NOT just paraphrase column names back — it
    should infer the *real-world thing* the rows represent.

  - **DERIVED-CONTEXT RULE.** When the prompt includes an "Applied steps"
    block, the rows you're describing are NOT the raw dataset — they are
    the result of running those steps over it. Frame the narrative as:
    "given the original dataset and these transformations, what's left
    and what does it represent?". The first paragraph should still name
    the real-world thing the rows represent (now post-transform), the
    second sentence should briefly call out what changed (rows filtered,
    columns aggregated, time bucketed, etc.). Sample values shown ARE
    the post-transform values — trust them over your assumptions about
    what the upstream dataset looked like.

Output JSON only — no Markdown, no code fences:

{
  "narrative": "<2-4 sentence paragraph>",
  "domain": "<short domain phrase, e.g. 'exoplanet observations'>",
  "confidence": "high" | "medium" | "low",
  "columns": [
    { "name": "<column name>", "meaning": "<one-line meaning>" }
  ]
}

If no confident interpretation is possible, return:
{ "narrative": "", "domain": "", "confidence": "low", "columns": [] }
"""


def _format_schema(schema: dict[str, str]) -> str:
    return "\n".join(f"  {n}: {t}" for n, t in sorted(schema.items())) or "  (empty)"


async def explain_dataset(
    cfg: AiConfig,
    *,
    dataset_name: str,
    project_name: str,
    schema: dict[str, str],
    sample_values: dict[str, list[str]] | None = None,
    source_uri: str | None = None,
    connector: str | None = None,
    applied_steps: list[str] | None = None,
    is_derived: bool = False,
) -> dict[str, Any]:
    """Returns parsed JSON: {narrative, domain, confidence, columns: [...]}.

    Same lineage signal hierarchy as suggest_visualizations:
      1. sample_values (most direct)
      2. source_uri (filename / URL is often telling)
      3. connector (clinical-trials JDBC vs marketing CSV)
      4. dataset_name + project_name
      5. column names + types

    `applied_steps` (optional) — for derived contexts, a compact text
    list describing each step from dataset to focused node. Triggers
    the "what's left after these transforms?" framing in the prompt.
    `is_derived` is the explicit signal that the schema/samples reflect
    a post-transform output rather than the raw dataset.
    """
    if not schema:
        return {"narrative": "", "domain": "(no columns)", "confidence": "low", "columns": []}

    schema_block = _format_schema(schema)

    # Provenance block — see suggest_visualizations for the rationale.
    provenance_lines: list[str] = []
    if source_uri:
        from pathlib import Path
        try:
            tail = Path(source_uri).name
            provenance_lines.append(f"  source filename: {tail}")
            if "/" in source_uri or source_uri.startswith(("file:", "http", "jdbc:")):
                provenance_lines.append(f"  full source: {source_uri[:200]}")
        except Exception:
            provenance_lines.append(f"  source: {source_uri[:200]}")
    if connector:
        provenance_lines.append(f"  connector: {connector}")
    provenance_block = ""
    if provenance_lines:
        provenance_block = "\n\nUpstream dataset provenance:\n" + "\n".join(provenance_lines)

    samples_block = ""
    if sample_values:
        rows = [
            f"  {n}: {', '.join(str(x) for x in v[:3])}"
            for n, v in sample_values.items() if v
        ]
        if rows:
            samples_label = (
                "Sample values from this step's actual output (first 3 per column):"
                if is_derived else
                "Sample values (first 3 per column):"
            )
            samples_block = f"\n\n{samples_label}\n" + "\n".join(rows)

    # Applied-steps chain — only present when focused on a derived node.
    # The block lists each step from dataset to focused node so the LLM
    # knows what transformations have been applied. Without this, the
    # explainer would see post-aggregation rows and try to describe them
    # as if they were the raw dataset (wrong framing).
    applied_block = ""
    if applied_steps:
        applied_block = (
            "\n\nApplied steps (dataset → focused node):\n"
            + "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(applied_steps[:12]))
        )
        if len(applied_steps) > 12:
            applied_block += f"\n  … (+{len(applied_steps) - 12} more)"

    derived_hint = ""
    if is_derived:
        derived_hint = (
            "\n\nNote: rows you are describing are the OUTPUT of the applied steps "
            "above, not the raw upstream dataset. Frame the narrative as "
            "'given the original dataset + these steps, what's left?'."
        )

    user_msg = (
        f"Project / pipeline name: {project_name or '(unnamed)'}\n"
        f"Upstream dataset name: {dataset_name or '(unnamed)'}"
        f"{provenance_block}"
        f"{applied_block}"
        f"{derived_hint}\n\n"
        f"Schema at the focused node:\n{schema_block}{samples_block}\n\n"
        "Return the JSON object now."
    )

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    last_err: AiError | None = None
    resp = None
    for use_json_format in (True, False):
        try:
            resp = await chat(
                cfg,
                messages=messages,
                response_format="json_object" if use_json_format else None,
                temperature=0.2,
                max_tokens=TOKEN_BUDGETS["explain_dataset"],
            )
            break
        except AiError as e:
            last_err = e
            if "empty message" not in str(e).lower():
                raise
    if resp is None:
        return {
            "narrative": "",
            "domain": "(no suggestion)",
            "confidence": "low",
            "columns": [],
            "model": cfg.model,
            "reason": str(last_err) if last_err else "AI returned no content",
        }

    parsed = parse_json_lenient(resp.text)
    if parsed is None:
        raise AiError(f"AI returned non-JSON: {resp.text[:300]}")

    # Filter columns to those that actually exist in the schema; drop
    # hallucinations. Cap at 12 to keep the UI compact.
    valid_cols = set(schema.keys())
    cols_in = parsed.get("columns") or []
    cols_out: list[dict[str, str]] = []
    if isinstance(cols_in, list):
        for c in cols_in[:12]:
            if not isinstance(c, dict):
                continue
            n = c.get("name")
            m = c.get("meaning")
            if isinstance(n, str) and n in valid_cols and isinstance(m, str):
                cols_out.append({"name": n, "meaning": m.strip()})

    return {
        "narrative": str(parsed.get("narrative", "")).strip(),
        "domain": str(parsed.get("domain", "")).strip() or "(unknown)",
        "confidence": str(parsed.get("confidence", "low")),
        "columns": cols_out,
        "model": resp.model,
    }
