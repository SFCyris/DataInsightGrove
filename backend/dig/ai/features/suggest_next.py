"""Suggest the next pipeline step(s) to add.

Given:
  - The current pipeline doc (already-built steps + their connections)
  - The schema at the focused node (column names + types)
  - A natural-language goal from the user
  - The full step catalog (manifest IDs + descriptions)

Asks the LLM for 1-3 concrete next-step proposals, each as
`{step_id, params, why}`. The frontend renders these as
clickable cards that drop a step into the pipeline on click.

Output is JSON to keep parsing predictable across model providers.
"""

from __future__ import annotations

import json
from typing import Any

from dig.ai.client import AiConfig, AiError, chat
from dig.ai.parsing import parse_json_lenient
from dig.ai.prompts import PRINCIPLES_BLOCK, TOKEN_BUDGETS
from dig.ai.repair import strip_unknown_columns, validate_and_repair_step


_SYSTEM = f"""\
You suggest the next step(s) to add to a DataInsightGrove (DIG) data
pipeline. The user has built a pipeline up to a focused node and stated
what they want to do next. You propose 1 to 3 concrete next steps from
the available step catalog.

Rules:
  1. Use ONLY step IDs that appear in the supplied catalog.
  2. Refer to columns by their actual names from the focused-node schema.
  3. Prefer the simplest step that does the job. Don't suggest a 5-step
     refactor when 1 step suffices.
  4. If the goal genuinely requires multiple steps, propose them as
     separate suggestions in execution order — the user picks one,
     then can re-ask for the next.
  5. Only suggest a step if you can fully populate its required params.
     If you'd need to ask the user for more info, say so in the `why`
     field instead of guessing.

{PRINCIPLES_BLOCK}

Output JSON only — no Markdown, no code fences, no prose:

{{
  "suggestions": [
    {{
      "step_id": "<id from the catalog>",
      "params": {{ "<param>": <value>, ... }},
      "why": "<one short sentence explaining why this step matches the goal>",
      "confidence": "high" | "medium" | "low"
    }}
  ]
}}

Empty `suggestions` array is valid — return it when the goal is unclear
or no catalog step fits.
"""


def _format_catalog(manifests: list[dict[str, Any]]) -> str:
    """Compact catalog: id, label, one-line desc, key params."""
    lines: list[str] = []
    for m in manifests:
        sid = m.get("id", "?")
        label = m.get("label", sid)
        desc = (m.get("description") or "").strip().split("\n")[0][:120]
        params = m.get("params") or {}
        param_keys = sorted(
            k for k, v in params.items()
            if isinstance(v, dict) and v.get("required")
        )
        param_hint = f" (required: {', '.join(param_keys)})" if param_keys else ""
        lines.append(f"  {sid}: {label} — {desc}{param_hint}")
    return "\n".join(lines)


async def suggest_next_step(
    cfg: AiConfig,
    *,
    pipeline_doc: dict[str, Any],
    focused_schema: dict[str, str],
    goal: str,
    step_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    """Returns parsed JSON: {suggestions: [{step_id, params, why, confidence}]}."""
    if not goal.strip():
        raise AiError("goal must be a non-empty natural-language description")

    # Schema as compact text — model parses better than nested JSON.
    schema_text = "\n".join(
        f"  {name}: {type_}"
        for name, type_ in sorted(focused_schema.items())
    ) or "  (no columns visible)"

    # Pipeline doc — strip UI-only fields for token economy.
    cleaned_doc = {
        "name": pipeline_doc.get("name"),
        "datasets": pipeline_doc.get("datasets") or [],
        "nodes": [
            {
                "id": n.get("id"),
                "step": n.get("step"),
                "inputs": n.get("inputs") or {},
                "params": n.get("params") or {},
            }
            for n in (pipeline_doc.get("nodes") or [])
        ],
    }

    user_msg = (
        f"Step catalog:\n{_format_catalog(step_catalog)}\n\n"
        f"Pipeline so far:\n```json\n{json.dumps(cleaned_doc, indent=2)[:6000]}\n```\n\n"
        f"Schema at focused node:\n{schema_text}\n\n"
        f"User's goal:\n  {goal.strip()}\n\n"
        "Return the JSON suggestions object now."
    )

    # Two-phase chat — same fallback as the other AI features so older
    # local models that emit empty content under json_object can still
    # produce something parseable on the second try.
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
                max_tokens=TOKEN_BUDGETS["suggest_next_step"],
            )
            break
        except AiError as e:
            last_err = e
            if "empty message" not in str(e).lower():
                raise
    if resp is None:
        return {
            "suggestions": [],
            "model": cfg.model,
            "reason": str(last_err) if last_err else "AI returned no content",
        }

    parsed = parse_json_lenient(resp.text)
    if parsed is None:
        raise AiError(f"AI returned non-JSON: {resp.text[:300]}")

    suggestions = parsed.get("suggestions")
    if not isinstance(suggestions, list):
        raise AiError(f"AI response missing 'suggestions' list: {resp.text[:300]}")

    # Validate + repair each suggestion. step_id must exist in the
    # catalog AND the step's required params must be fillable from the
    # focused-node schema; suggestions that fail either gate are dropped.
    manifests_by_id = {m["id"]: m for m in step_catalog if "id" in m}
    cleaned: list[dict[str, Any]] = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        sid = s.get("step_id")
        if sid not in manifests_by_id:
            continue
        manifest = manifests_by_id[sid]
        params = s.get("params") if isinstance(s.get("params"), dict) else {}
        clean_params = strip_unknown_columns(params, focused_schema)
        repaired = validate_and_repair_step(
            sid, clean_params, manifest, focused_schema,
        )
        if repaired is None:
            continue
        cleaned.append({
            "step_id": str(sid),
            "params": repaired,
            "why": str(s.get("why", "")),
            "confidence": str(s.get("confidence", "medium")),
        })

    return {"suggestions": cleaned, "model": resp.model}
