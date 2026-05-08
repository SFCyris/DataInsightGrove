"""Domain-aware multi-step transform suggestions.

Given a dataset's columns + lineage signals, the LLM returns 1-3
"routes" — each a small ordered sequence of steps that together yield
a meaningful derived dataset (vectorize → similarity → cluster, or
parse_dates → resample → forecast, etc.).

This is a sibling of suggest_visualizations: same provenance signals,
same picker philosophy ("ask the user, don't auto-apply"), same
two-phase chat with json_object fallback.

The frontend renders each route as a card with its step chain
(step_id + params + rationale per step) and an "Apply route" button
that inserts the steps into the pipeline in order.
"""
from __future__ import annotations

from typing import Any

from dig.ai.client import AiConfig, AiError, chat
from dig.ai.parsing import parse_json_lenient
from dig.ai.prompts import PRINCIPLES_BLOCK, TOKEN_BUDGETS, format_step_for_catalog
from dig.ai.repair import (
    strip_unknown_columns,
    validate_and_repair_step,
)



_SYSTEM = f"""\
You are a domain-aware data-analytics assistant for DataInsightGrove (DIG).

Given a dataset's columns + provenance hints + the available step
catalog, you must:
  1. Infer the dataset's domain in one short phrase.
  2. Suggest 1 to 3 multi-step transformation ROUTES that yield
     interesting derived datasets for that domain. A route is an
     ordered chain of 1-4 steps. Earlier steps' outputs feed later
     steps; pick params accordingly.
  3. For each step in the route, choose appropriate column refs from
     the schema and reasonable param defaults.

Examples of good multi-step routes:
  - For text columns with similarity-search potential:
      embed → vector_similarity → derived score column
  - For time-series with seasonality:
      parse_dates → resample → forecast
  - For high-cardinality categoricals before ML:
      one_hot_encode → standardize → cluster
  - For text classification:
      tokenize → tfidf → cluster

Rules:
  - Use ONLY step IDs from the supplied catalog.
  - Use ONLY column names that appear in the supplied schema.
  - Match types: numeric ops on numeric columns, temporal on dates.
  - Skip a route if the schema doesn't have the required types.
  - Each route must do something genuinely useful — don't pad with
     filler steps like 'sort_rows' just to look longer.
  - Prefer DOMAIN-SPECIFIC routes over generic ones when domain
     signals are strong.

{PRINCIPLES_BLOCK}

Output JSON only — no Markdown, no code fences:

{{
  "domain": "<short domain phrase>",
  "routes": [
    {{
      "title": "<one short sentence — what this route accomplishes>",
      "why": "<one sentence — why it matters for THIS data>",
      "confidence": "high" | "medium" | "low",
      "steps": [
        {{
          "step_id": "<id from catalog>",
          "params": {{ "<param>": <value>, ... }},
          "right_ref": "<only for `join` — id from 'Other in-scope inputs'; omit for any other step>",
          "rationale": "<one short sentence — why this step here>",
          "outcome": "<one short phrase — what the output looks like>"
        }}
      ]
    }}
  ]
}}

Empty `routes` is valid if nothing useful comes to mind.
"""


def _format_catalog(manifests: list[dict[str, Any]]) -> str:
    """Compact catalog of NON-visualization steps. Visualization steps
    have their own AI feature; this one is for transforms only.

    Each step lists its params with type / units / range / default so
    the LLM gets unambiguous specs for numeric fields (e.g. window
    sizes, periods, percentages).
    """
    blocks: list[str] = []
    for m in manifests:
        cat = m.get("category")
        if cat in ("visualize", "output"):
            continue
        blocks.append(format_step_for_catalog(m))
    return "\n".join(blocks) if blocks else "  (no transform steps available)"


def _format_schema(schema: dict[str, str]) -> str:
    return "\n".join(f"  {n}: {t}" for n, t in sorted(schema.items())) or "  (empty)"


async def suggest_pipeline_steps(
    cfg: AiConfig,
    *,
    dataset_name: str,
    project_name: str,
    schema: dict[str, str],
    sample_values: dict[str, list[str]] | None = None,
    source_uri: str | None = None,
    connector: str | None = None,
    goal: str | None = None,
    step_catalog: list[dict[str, Any]],
    other_inputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Returns parsed JSON: {domain, routes: [...]}.

    ``other_inputs`` is the list of every dataset + every non-descendant
    node in the pipeline. Each entry is ``{ref, label, schema}`` where
    ``ref`` is the id used for wiring (e.g. ``ds_orders`` or a node id),
    ``label`` is operator-supplied display text, and ``schema`` is the
    column → type map at that ref's output. When supplied, the prompt
    surfaces these as candidate join sources and the validator can fill
    in `params.keys` for any join the LLM proposes.
    """
    if not schema:
        return {"domain": "(no columns)", "routes": [], "model": cfg.model}

    catalog_block = _format_catalog(step_catalog)
    schema_block = _format_schema(schema)
    # Index of available right-side schemas, keyed by ref id, used by
    # validate_and_repair_step's join branch.
    other_schemas: dict[str, dict[str, str]] = {
        oi["ref"]: oi.get("schema") or {}
        for oi in (other_inputs or [])
        if isinstance(oi, dict) and oi.get("ref")
    }

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
        provenance_block = "\n\nProvenance:\n" + "\n".join(provenance_lines)

    samples_block = ""
    if sample_values:
        rows = [
            f"  {n}: {', '.join(str(x) for x in v[:3])}"
            for n, v in sample_values.items() if v
        ]
        if rows:
            samples_block = "\n\nSample values (first 3 per column):\n" + "\n".join(rows)

    goal_block = ""
    if goal and goal.strip():
        goal_block = f"\n\nUser goal: {goal.strip()[:500]}"

    other_inputs_block = ""
    if other_inputs:
        oi_lines: list[str] = []
        for oi in other_inputs:
            ref = oi.get("ref")
            if not isinstance(ref, str) or not ref:
                continue
            label = oi.get("label") or ref
            sch = oi.get("schema") or {}
            cols = ", ".join(f"{n}:{t}" for n, t in list(sch.items())[:8])
            if len(sch) > 8:
                cols += f", +{len(sch) - 8}"
            oi_lines.append(f"  {ref} ({label}) → {cols}")
        if oi_lines:
            other_inputs_block = (
                "\n\nOther in-scope inputs (eligible right sides for a `join` step):\n"
                + "\n".join(oi_lines)
                + "\nWhen you propose a join, set `right_ref` to one of the ids "
                "above. Leave `params.keys` empty — the validator will fill them "
                "from name+type overlap."
            )

    user_msg = (
        f"Project / pipeline name: {project_name or '(unnamed)'}\n"
        f"Dataset name: {dataset_name or '(unnamed)'}"
        f"{provenance_block}\n\n"
        f"Schema:\n{schema_block}{samples_block}"
        f"{other_inputs_block}"
        f"{goal_block}\n\n"
        f"Available transformation steps:\n{catalog_block}\n\n"
        "Return the JSON routes object now."
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
                # Token budget centralised in dig.ai.prompts.TOKEN_BUDGETS
                # so the strengthened prompt's expected output never gets
                # truncated mid-route.
                max_tokens=TOKEN_BUDGETS["suggest_pipeline_steps"],
            )
            break
        except AiError as e:
            last_err = e
            if "empty message" not in str(e).lower():
                raise
    if resp is None:
        return {
            "domain": "(no suggestion)",
            "routes": [],
            "model": cfg.model,
            "reason": str(last_err) if last_err else "AI returned no content",
        }

    parsed = parse_json_lenient(resp.text)
    if parsed is None:
        raise AiError(f"AI returned non-JSON: {resp.text[:300]}")

    manifests_by_id = {
        m["id"]: m
        for m in step_catalog
        if "id" in m and m.get("category") not in ("visualize", "output")
    }

    routes_in = parsed.get("routes") or []
    routes_out: list[dict[str, Any]] = []
    if isinstance(routes_in, list):
        for r in routes_in:
            if not isinstance(r, dict):
                continue
            steps_in = r.get("steps") or []
            if not isinstance(steps_in, list):
                continue
            steps_out: list[dict[str, Any]] = []
            route_broken = False
            for s in steps_in:
                if not isinstance(s, dict):
                    continue
                sid = s.get("step_id")
                if sid not in manifests_by_id:
                    route_broken = True
                    break
                manifest = manifests_by_id[sid]
                params = s.get("params") if isinstance(s.get("params"), dict) else {}
                # Strip params that reference non-existent columns. For
                # join, the right-side cols belong to the OTHER schema —
                # combine both so right cols aren't stripped.
                strip_schema = dict(schema)
                if sid == "join":
                    for sch in other_schemas.values():
                        strip_schema.update(sch)
                clean_params = strip_unknown_columns(params, strip_schema)
                # The LLM may have hinted at the right side via `right_ref`
                # at the step level (not inside params). Forward it into
                # the params dict under the smuggle-key the validator
                # uses; we'll lift it back out below.
                if sid == "join":
                    hinted = s.get("right_ref")
                    if isinstance(hinted, str) and hinted:
                        clean_params["__ai_right_ref"] = hinted
                # Validate + auto-repair required params. Returns None
                # when the step's required-param needs can't be met from
                # the schema. Pass `other_schemas` so the join branch
                # can fill `keys` from name+type overlap.
                repaired = validate_and_repair_step(
                    sid, clean_params, manifest, schema,
                    route_title=str(r.get("title", "")),
                    other_schemas=other_schemas if sid == "join" else None,
                )
                if repaired is None:
                    # Whole route is broken — better to drop it than to
                    # serve a "Apply (3 steps)" button that errors out.
                    route_broken = True
                    break
                # For joins, lift the smuggled right-ref back out of
                # params and onto the step entry so the frontend can
                # wire the right input port.
                right_ref_out: str | None = None
                if sid == "join":
                    rr = repaired.pop("__ai_right_ref", None)
                    if isinstance(rr, str):
                        right_ref_out = rr
                step_entry: dict[str, Any] = {
                    "step_id": str(sid),
                    "params": repaired,
                    "rationale": str(s.get("rationale", "")),
                    "outcome": str(s.get("outcome", "")) or None,
                }
                if right_ref_out:
                    step_entry["right_ref"] = right_ref_out
                steps_out.append(step_entry)
            if route_broken or not steps_out:
                continue
            routes_out.append({
                "title": str(r.get("title", "")),
                "why": str(r.get("why", "")),
                "confidence": str(r.get("confidence", "medium")),
                "steps": steps_out,
            })

    return {
        "domain": str(parsed.get("domain", "(unknown)")),
        "routes": routes_out,
        "model": resp.model,
    }
