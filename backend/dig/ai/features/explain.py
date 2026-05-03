"""Explain a pipeline in plain English.

Feeds the pipeline document + the catalog of step manifests into the
configured LLM and asks for a 2-4 paragraph narrative. Useful for:
  - Documentation handoff (paste the explanation into a wiki / runbook)
  - Onboarding ("what does this pipeline I inherited actually do?")
  - Sanity-checking ("the explanation should match what I think I built")

Returns Markdown. The frontend renders it in a side drawer with a
copy-to-clipboard button.
"""

from __future__ import annotations

import json
from typing import Any

from dig.ai.client import AiConfig, chat


_SYSTEM = """\
You are explaining a DataInsightGrove (DIG) data-preparation pipeline to a
colleague who has not seen it before. Your audience is a data analyst who
understands SQL but does not know DIG.

Output format: plain Markdown. 2 to 4 short paragraphs. No code blocks,
no bullet lists unless the pipeline genuinely splits into independent
branches. No mention of internal IDs (ULIDs, node ids); refer to steps by
their human label and the columns they touch.

Structure:
  1. The first paragraph names the inputs (datasets), names the outputs,
     and the high-level intent in one sentence.
  2. The middle paragraph(s) walk through the transformations in execution
     order, focusing on what changes about the data (rows filtered,
     columns added, aggregations performed) rather than the mechanics.
  3. The closing sentence describes the shape of the output.

Be concrete: if the pipeline filters to active customers, say so. If it
joins on customer_id, say so. Do NOT speculate about business intent
beyond what the steps clearly say.
"""


def _format_step_catalog(manifests: list[dict[str, Any]]) -> str:
    """Compact step-catalog summary the LLM uses to interpret step IDs."""
    lines = []
    for m in manifests:
        sid = m.get("id", "?")
        label = m.get("label", sid)
        desc = (m.get("description") or "").strip().split("\n")[0][:120]
        lines.append(f"  {sid}: {label} — {desc}")
    return "\n".join(lines)


def _format_pipeline(doc: dict[str, Any]) -> str:
    """Render the pipeline document into a compact text form. We strip
    UI-only fields (positions, labels) since they're not semantically
    interesting for an explanation."""
    cleaned: dict[str, Any] = {
        "name": doc.get("name"),
        "description": doc.get("description"),
        "datasets": doc.get("datasets") or [],
        "nodes": [
            {
                "id": n.get("id"),
                "step": n.get("step"),
                "inputs": n.get("inputs") or {},
                "outputs": n.get("outputs") or [],
                "params": n.get("params") or {},
            }
            for n in (doc.get("nodes") or [])
        ],
        "outputs": doc.get("outputs") or [],
    }
    return json.dumps(cleaned, indent=2)


async def explain_pipeline(
    cfg: AiConfig,
    pipeline_doc: dict[str, Any],
    step_manifests: list[dict[str, Any]],
) -> str:
    """Generate a Markdown explanation of the pipeline. Returns the
    raw model text — caller renders it as Markdown."""
    prompt = (
        "Here is the step catalog (id: label — short description):\n"
        f"{_format_step_catalog(step_manifests)}\n\n"
        "Here is the pipeline document:\n"
        f"```json\n{_format_pipeline(pipeline_doc)}\n```\n\n"
        "Explain what this pipeline does, following the format the system "
        "message specified."
    )
    resp = await chat(
        cfg,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        # Prose, so a small temperature helps it read naturally.
        temperature=0.3,
        max_tokens=1024,
    )
    return resp.text.strip()
