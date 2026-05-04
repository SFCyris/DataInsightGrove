"""AI Pipeline Reviewer.

Asks the configured LLM to review a whole pipeline structurally and produce
severity-ranked findings — the first AI feature that asks "what should I do
*differently*?" instead of "what should I do next?".

Findings are typed JSON; the model's response is parsed against this schema
and any non-conforming entry is dropped. The frontend renders them as a
panel of cards with [Apply] buttons that re-use the Pipeline Diff component.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from dig.ai.client import AiConfig, chat


_SYSTEM = """\
You are reviewing a DataInsightGrove (DIG) data-preparation pipeline. Your
goal is to surface concrete, actionable improvements — not generic advice.

Output: a single JSON object matching this exact schema:

{
  "findings": [
    {
      "severity": "info" | "warn" | "high",
      "category": "performance" | "correctness" | "quality" | "lineage" | "ergonomics",
      "title": "Short one-line summary",
      "explanation": "1-3 sentences. Plain English. Reference column names and step labels, not IDs.",
      "affected_nodes": ["node_id_1", ...],
      "confidence": 0.0 to 1.0
    },
    ...
  ]
}

Rules:
- Output JSON only. No prose before or after the object. No markdown code fences.
- Every node ID in `affected_nodes` MUST exist in the pipeline document. If
  you cannot reference a real node, omit the finding.
- Prefer fewer high-confidence findings over many speculative ones. If you
  have nothing to say, return {"findings": []}.
- Categories:
  * performance: filter-after-join, redundant casts, missing indexes, etc.
  * correctness: type mismatches, ambiguous group-by, off-by-one window sizes.
  * quality: missing expectations on critical outputs, no null checks where
    nulls are likely.
  * lineage: trackLineage off when output sinks to a downstream system.
  * ergonomics: 3+ similar steps that could be a sub-pipeline; very long names.
- Severities:
  * high — pipeline likely produces wrong results or wastes >50% of work.
  * warn — pipeline works but has a real problem worth fixing.
  * info — improvement opportunity, no bug.
- Confidence < 0.5 means "I'm guessing"; the UI hides Apply buttons there.
"""


def _format_pipeline(doc: dict[str, Any]) -> str:
    cleaned: dict[str, Any] = {
        "name": doc.get("name"),
        "datasets": doc.get("datasets") or [],
        "nodes": [
            {
                "id": n.get("id"),
                "step": n.get("step"),
                "inputs": n.get("inputs") or {},
                "params": n.get("params") or {},
            }
            for n in (doc.get("nodes") or [])
        ],
        "outputs": doc.get("outputs") or [],
        "metadata": doc.get("metadata") or {},
    }
    return json.dumps(cleaned, indent=2)


def _format_step_catalog(manifests: list[dict[str, Any]], used_ids: set[str]) -> str:
    """Only include steps actually used in the pipeline — saves tokens on
    pipelines that use 8 of 51 steps."""
    lines = []
    for m in manifests:
        sid = m.get("id", "?")
        if sid not in used_ids:
            continue
        label = m.get("label", sid)
        desc = (m.get("description") or "").strip().split("\n")[0][:120]
        lines.append(f"  {sid}: {label} — {desc}")
    return "\n".join(lines)


def _format_profiles(profiles: dict[str, Any] | None) -> str:
    """Compact column-profile summary per dataset. Helps the model spot
    type-mismatch issues without ballooning the prompt."""
    if not profiles:
        return ""
    lines: list[str] = []
    for ds_id, p in profiles.items():
        cols = (p or {}).get("columns") or []
        col_lines: list[str] = []
        for c in cols[:30]:
            null_pct = (c.get("nullFraction") or 0) * 100
            col_lines.append(
                f"    {c.get('name')}: type={c.get('type')} null={null_pct:.1f}% "
                f"distinct={c.get('distinctCount')}"
            )
        if col_lines:
            lines.append(f"  {ds_id}:\n" + "\n".join(col_lines))
    return "\n".join(lines)


SEVERITY = ("info", "warn", "high")
CATEGORY = ("performance", "correctness", "quality", "lineage", "ergonomics")


def _validate_finding(f: Any, valid_node_ids: set[str]) -> dict[str, Any] | None:
    if not isinstance(f, dict):
        return None
    sev = f.get("severity")
    cat = f.get("category")
    title = f.get("title")
    expl = f.get("explanation")
    nodes = f.get("affected_nodes") or []
    conf = f.get("confidence")
    if sev not in SEVERITY:
        return None
    if cat not in CATEGORY:
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(expl, str) or not expl.strip():
        return None
    if not isinstance(nodes, list):
        return None
    nodes = [n for n in nodes if isinstance(n, str) and n in valid_node_ids]
    if not nodes:
        return None
    try:
        c = float(conf)
    except (TypeError, ValueError):
        c = 0.5
    c = max(0.0, min(1.0, c))
    return {
        "severity": sev,
        "category": cat,
        "title": title.strip()[:200],
        "explanation": expl.strip()[:1500],
        "affected_nodes": nodes,
        "confidence": c,
    }


async def review_pipeline(
    cfg: AiConfig,
    pipeline_doc: dict[str, Any],
    step_manifests: list[dict[str, Any]],
    profiles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Returns {"findings": [ReviewFinding, ...], "model": str, "rawText": str}.

    Findings are validated; entries that reference unknown node IDs or have
    invalid categories are dropped silently (the model can't break the UI).
    """
    nodes = pipeline_doc.get("nodes") or []
    valid_node_ids = {n.get("id") for n in nodes if n.get("id")}
    used_step_ids = {n.get("step") for n in nodes if n.get("step")}

    prompt_parts = [
        "Here is the catalog of steps used in this pipeline:",
        _format_step_catalog(step_manifests, used_step_ids),
        "",
        "Here is the pipeline document:",
        f"```json\n{_format_pipeline(pipeline_doc)}\n```",
    ]
    profile_text = _format_profiles(profiles)
    if profile_text:
        prompt_parts.extend(["", "Column profiles per dataset (sampled):", profile_text])
    prompt_parts.extend([
        "",
        "Review this pipeline. Return JSON matching the schema in the system prompt.",
    ])
    prompt = "\n".join(prompt_parts)

    resp = await chat(
        cfg,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        # Lower temperature → fewer hallucinated node IDs, more conservative findings.
        temperature=0.1,
        max_tokens=2048,
        # `chat()` accepts the literal string "json_object"; passing a dict
        # silently dropped the hint and providers like OpenAI/Anthropic
        # returned prose, breaking parse for every cloud-backed review.
        response_format="json_object",
    )

    text = resp.text.strip()
    findings: list[dict[str, Any]] = []
    parse_failed = False
    try:
        parsed = json.loads(text)
        raw = parsed.get("findings") if isinstance(parsed, dict) else None
        if isinstance(raw, list):
            for f in raw:
                v = _validate_finding(f, valid_node_ids)
                if v is not None:
                    findings.append(v)
    except (json.JSONDecodeError, AttributeError):
        # Model returned non-JSON; surface the raw text so the user can see
        # what came back instead of an empty drawer.
        parse_failed = True

    # Sort by severity desc, then confidence desc.
    sev_rank = {"high": 2, "warn": 1, "info": 0}
    findings.sort(
        key=lambda f: (sev_rank.get(f["severity"], 0), f["confidence"]),
        reverse=True,
    )

    return {
        "findings": findings,
        "model": cfg.model,
        # Only set on actual parse failure — a clean `{"findings": []}`
        # response would otherwise be mis-rendered as a parse error.
        "rawText": text if parse_failed else None,
    }
