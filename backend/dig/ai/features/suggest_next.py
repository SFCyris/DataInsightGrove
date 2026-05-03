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


_SYSTEM = """\
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

Output JSON only — no Markdown, no code fences, no prose:

{
  "suggestions": [
    {
      "step_id": "<id from the catalog>",
      "params": { "<param>": <value>, ... },
      "why": "<one short sentence explaining why this step matches the goal>",
      "confidence": "high" | "medium" | "low"
    }
  ]
}

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

    resp = await chat(
        cfg,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        response_format="json_object",
        temperature=0.2,
        max_tokens=1024,
    )

    text = resp.text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise AiError(f"AI returned non-JSON: {text[:300]}") from e

    suggestions = parsed.get("suggestions")
    if not isinstance(suggestions, list):
        raise AiError(f"AI response missing 'suggestions' list: {text[:300]}")

    # Validate each suggestion's step_id exists in the catalog.
    valid_ids = {m["id"] for m in step_catalog if "id" in m}
    cleaned: list[dict[str, Any]] = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        sid = s.get("step_id")
        if sid not in valid_ids:
            continue
        cleaned.append({
            "step_id": str(sid),
            "params": s.get("params") if isinstance(s.get("params"), dict) else {},
            "why": str(s.get("why", "")),
            "confidence": str(s.get("confidence", "medium")),
        })

    return {"suggestions": cleaned, "model": resp.model}
