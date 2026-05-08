"""Shared prompt fragments + token budgets for AI features.

Centralising these makes it easy to update the global rules in one
place. Every AI feature that emits structured output for the editor
should include `PRINCIPLES_BLOCK` in its system prompt.

The four global principles every AI interaction in DIG follows
(documented in docs/AI_FEATURES.md and codified as cross-session
memory):

  1. **Better prompt** — explicit rules in the system message so the
     LLM produces complete, schema-aware output the first time.
  2. **Validate + repair** — every emitted suggestion runs through
     `dig.ai.repair.validate_and_repair_step` before reaching the user.
     Unfixable suggestions are dropped silently.
  3. **Robust parsing** — `dig.ai.parsing.parse_json_lenient` handles
     prose-around-JSON, code fences, and trailing commas. Token
     budgets sized for the prompt (3000+ for multi-route output).
  4. **Backend covers all paths** — the dispatcher's runtime handles
     polars/SQL/chained execution transparently so a "valid"
     suggestion always renders.
"""
from __future__ import annotations

from typing import Any


# Principle block — included in every system prompt that emits step
# suggestions or column-level metadata. Tightens output quality
# upstream so the validator + repair layers have less to fix.
PRINCIPLES_BLOCK = """\
Output principles (apply to every suggestion you make):

  • **Fill EVERY required param.** If a step needs `expression`,
    `predicate`, `aggregates`, `groupBy`, etc., you MUST supply
    concrete values drawn from the schema — never blanks. Empty
    arrays, empty strings, and missing keys are all unacceptable.
  • **Use meaningful, data-aware names** for every output_column /
    `name` / `as` / alias field. Build them from the input columns
    + the operation. Examples that are good:
        cl_to_cd_ratio, revenue_rolling_7d, temperature_zscore
    Examples that are bad:
        derived_0, column_1, output, value, "" (empty)
    The user reads these names long after you're gone — make them
    speak for themselves.
  • **Use meaningful, data-aware titles + rationales.** Reference
    the actual columns and the operation in plain English.
    Good: "Lift coefficient (cl) vs angle of attack (alpha) — fit
    a line and surface the residuals."
    Bad: "Linear regression."
  • **Match types.** Numeric ops on numeric columns, temporal on
    dates, categorical on low-cardinality strings. If the schema
    doesn't have what a suggestion needs, skip the suggestion
    entirely instead of plugging in the wrong column.
"""


def format_param_hint(pname: str, pspec: dict[str, Any]) -> str:
    """One-line param description for the prompt's catalog block.

    Surfaces type + label (units!) + range + default so the LLM can't
    fall back to its training-prior defaults (e.g. matplotlib's
    `figsize=(6, 4)` inches when the manifest expects pixels).

    Output examples:
        width: integer (Width (px); default 1600; range 200..4000)
        kind: enum {inner, left, right, full, anti_left, anti_right} (default inner)
        predicate: string (REQUIRED) — SQL expression
    """
    label = pspec.get("label") or pname
    ptype = pspec.get("type", "any")
    parts: list[str] = []
    parts.append(f"{label}")

    if ptype == "enum":
        vals = pspec.get("enumValues") or []
        if vals:
            parts.append("values: " + ", ".join(str(v) for v in vals))

    rng_lo = pspec.get("min")
    rng_hi = pspec.get("max")
    if rng_lo is not None or rng_hi is not None:
        if rng_lo is not None and rng_hi is not None:
            parts.append(f"range {rng_lo}..{rng_hi}")
        elif rng_lo is not None:
            parts.append(f"min {rng_lo}")
        else:
            parts.append(f"max {rng_hi}")

    default = pspec.get("default")
    if default is not None and not isinstance(default, (list, dict)):
        parts.append(f"default {default!r}")

    if pspec.get("required"):
        parts.append("REQUIRED")

    help_text = pspec.get("help")
    body = "; ".join(parts)
    line = f"{pname}: {ptype} ({body})"
    if help_text:
        # Trim aggressively — the help fields can run long, and the
        # catalog block is already substantial. Keep just the first
        # sentence (or 100 chars) so the LLM gets the gist without
        # blowing the context budget.
        h = help_text.strip().split("\n")[0]
        if len(h) > 100:
            h = h[:97] + "..."
        line += f" — {h}"
    return line


def format_step_for_catalog(manifest: dict[str, Any]) -> str:
    """Render one manifest entry for an AI catalog block.

    Replaces the older `params: a, b, c` one-liner with a multi-line
    block that includes per-param type, units (label), range, and
    default. The improvement matters most for steps with numeric
    params whose units the LLM can't infer from the param name alone
    (`width`, `height`, `dpi`, `period`, `window`).
    """
    sid = manifest.get("id", "?")
    label = manifest.get("label", sid)
    desc = (manifest.get("description") or "").strip().split("\n")[0][:160]
    params = manifest.get("params") or {}
    if not params:
        return f"  {sid}: {label} — {desc}\n    (no params)"
    lines = [f"  {sid}: {label} — {desc}"]
    for pname in sorted(params.keys()):
        lines.append(f"    - {format_param_hint(pname, params[pname])}")
    return "\n".join(lines)


# Token budgets per feature, sized to fit the strengthened prompts.
# Lower budgets cause truncated JSON which the lenient parser can't
# always rescue. Sizes here are minimums.
TOKEN_BUDGETS = {
    "suggest_pipeline_steps": 3000,
    "suggest_visualizations": 1500,
    "suggest_next_step": 1500,
    "explain_dataset": 1500,
    "explain_pipeline": 1024,
    "review_pipeline": 2000,
    "fix_expression": 600,
    # Code-gen features emit a manifest + a full plugin .py source —
    # need significantly more headroom than suggestion JSON.
    "generate_step": 4096,
    "generate_connector": 4096,
}
