"""Domain-aware visualization suggestions for the Hints panel.

Given a dataset's column schema + the project / pipeline name, ask
the LLM to:
  1. Infer the data domain (astronomy, finance, marketing, healthcare, …)
  2. Suggest 1-3 visualizations that domain experts typically reach for
  3. Pre-populate the params for each, picking columns by name match

The output drops cleanly into the Hints panel as actionable cards —
each has a step_id, params, and rationale; the frontend's existing
visualize_as machinery applies them.
"""
from __future__ import annotations

from typing import Any

from dig.ai.client import AiConfig, AiError, chat
from dig.ai.parsing import parse_json_lenient
from dig.ai.prompts import PRINCIPLES_BLOCK, TOKEN_BUDGETS, format_step_for_catalog


_SYSTEM = f"""\
You are a domain-aware data-visualization assistant for DataInsightGrove (DIG).

Given a dataset's columns + names + the project/pipeline name, you must:
  1. Infer the data domain in one short phrase (e.g. "stock-market OHLC",
     "exoplanet observations", "e-commerce funnel", "healthcare claims").
  2. Pick 1 to 3 visualizations from the available step catalog that
     domain experts typically reach for with this kind of data.
  3. Pre-populate the params for each suggestion, choosing columns by
     name match (e.g. for box plot of revenue by category: value=revenue,
     group=category).

Rules:
  - Use ONLY step IDs from the supplied catalog (visualization steps).
  - Use ONLY column names that appear in the supplied schema.
  - If a step needs a numeric column, pick a numeric one from the schema.
    If it needs a categorical, pick a low-cardinality non-numeric one.
  - Prefer the *less obvious* / *more domain-specific* visualization
    over a generic histogram if a specialised one fits better.
  - Skip a suggestion entirely if the schema doesn't have what it needs.
  - If the schema looks generic and no domain-specific suggestion fits,
    pick the most useful 1-2 generic visualizations and say so in `why`.

{PRINCIPLES_BLOCK}

Output JSON only — no Markdown, no code fences, no prose:

{{
  "domain": "<short domain phrase>",
  "domain_confidence": "high" | "medium" | "low",
  "suggestions": [
    {{
      "step_id": "<id from catalog>",
      "params": {{ "<param>": <value>, ... }},
      "title": "<one short sentence — appears as the card title>",
      "why": "<one sentence — what this chart reveals about THIS data>",
      "confidence": "high" | "medium" | "low"
    }}
  ]
}}

Empty `suggestions` is valid when the schema has nothing chartable.
"""


def _format_catalog(manifests: list[dict[str, Any]]) -> str:
    """Compact catalog of visualize-category steps only.

    Each step lists its params with type / units / range / default so
    the LLM can't fall back to training-prior defaults (e.g. matplotlib
    `figsize=(6, 4)` inches when the manifest expects pixels). See
    `format_step_for_catalog` in dig.ai.prompts.
    """
    blocks: list[str] = []
    for m in manifests:
        if m.get("category") != "visualize":
            continue
        blocks.append(format_step_for_catalog(m))
    return "\n".join(blocks) if blocks else "  (no visualization steps available)"


def _format_schema(schema: dict[str, str]) -> str:
    return "\n".join(f"  {n}: {t}" for n, t in sorted(schema.items())) or "  (empty)"


async def suggest_visualizations(
    cfg: AiConfig,
    *,
    dataset_name: str,
    project_name: str,
    schema: dict[str, str],
    sample_values: dict[str, list[str]] | None = None,
    source_uri: str | None = None,
    connector: str | None = None,
    step_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    """Returns parsed JSON: {domain, domain_confidence, suggestions: [...]}.

    Domain inference signals — strongest to weakest:
      1. `sample_values` — actual cell contents are the most direct
         signal. Same column name "code" can be ISO countries, ICD-10s,
         airport codes, SKUs — the values disambiguate.
      2. `source_uri` — the filename / URL is often the smoking gun
         (`exoplanet-survey.csv`, `claims_2024_q3.parquet`).
      3. `connector` — JDBC from a clinical-trials DB hints differently
         than a Sheets export of marketing OKRs.
      4. `dataset_name` + `project_name` — operator-supplied labels.
      5. `schema` — column names + types as a baseline.

    All inputs are optional; we drop empty blocks from the prompt so the
    LLM doesn't waste context on placeholder text.
    """
    if not schema:
        return {"domain": "(no columns)", "domain_confidence": "low", "suggestions": []}

    catalog_block = _format_catalog(step_catalog)
    schema_block = _format_schema(schema)

    # ── Lineage / provenance block ────────────────────────────────
    # The user pointed out that "what the data is" is often clearer
    # from where it CAME from than from the columns themselves. We
    # surface the source URI (often a telling filename), connector
    # type, and a few representative cell values per column.
    provenance_lines: list[str] = []
    if source_uri:
        # Strip the path prefix; the filename is the part with domain
        # signal (e.g. "exoplanet_2026.parquet").
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
        # Cap at 3 values per column, and skip columns with no observed
        # values to keep the block tight.
        rows = [
            f"  {n}: {', '.join(str(x) for x in v[:3])}"
            for n, v in sample_values.items() if v
        ]
        if rows:
            samples_block = "\n\nSample values (first 3 per column):\n" + "\n".join(rows)

    user_msg = (
        f"Project / pipeline name: {project_name or '(unnamed)'}\n"
        f"Dataset name: {dataset_name or '(unnamed)'}"
        f"{provenance_block}\n\n"
        f"Schema:\n{schema_block}{samples_block}\n\n"
        f"Available visualization steps:\n{catalog_block}\n\n"
        "Return the JSON suggestions object now."
    )

    # Two-phase chat. Some local models (notably older Ollama quantizations)
    # return an empty message when `response_format=json_object` is requested
    # — the structured-output enforcement clashes with their generation
    # state. We try with the constraint first (cleaner JSON), and on empty
    # we retry without it; if both return empty, surface a graceful
    # "nothing suggested" rather than a hard error.
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
                max_tokens=TOKEN_BUDGETS["suggest_visualizations"],
            )
            break
        except AiError as e:
            last_err = e
            # Retry only on empty-message; other errors (timeout, auth,
            # 5xx) shouldn't be silently masked.
            if "empty message" not in str(e).lower():
                raise
    if resp is None:
        # Both attempts yielded empty content → return the neutral
        # "nothing identified" result. Frontend renders a friendly
        # "No suitable domain or visualization identified" surface.
        return {
            "domain": "(no suggestion)",
            "domain_confidence": "low",
            "suggestions": [],
            "model": cfg.model,
            "reason": str(last_err) if last_err else "AI returned no content",
        }

    parsed = parse_json_lenient(resp.text)
    if parsed is None:
        raise AiError(f"AI returned non-JSON: {resp.text[:300]}")

    suggestions = parsed.get("suggestions") or []
    if not isinstance(suggestions, list):
        raise AiError(f"AI response missing 'suggestions' list: {resp.text[:300]}")

    valid_ids = {m["id"] for m in step_catalog if m.get("category") == "visualize" and "id" in m}
    valid_cols = set(schema.keys())
    cleaned: list[dict[str, Any]] = []
    for s in suggestions:
        if not isinstance(s, dict):
            continue
        sid = s.get("step_id")
        if sid not in valid_ids:
            continue
        # Strip params that reference non-existent columns. Param spec
        # for column_ref can be a single string or a list of strings;
        # both are filtered here.
        params = s.get("params") if isinstance(s.get("params"), dict) else {}
        clean_params: dict[str, Any] = {}
        for k, v in params.items():
            if isinstance(v, str) and v in valid_cols:
                clean_params[k] = v
            elif isinstance(v, list) and all(isinstance(x, str) for x in v):
                clean_params[k] = [x for x in v if x in valid_cols]
            elif not isinstance(v, str):
                clean_params[k] = v
        cleaned.append({
            "step_id": str(sid),
            "params": clean_params,
            "title": str(s.get("title", "")),
            "why": str(s.get("why", "")),
            "confidence": str(s.get("confidence", "medium")),
        })

    return {
        "domain": str(parsed.get("domain", "(unknown)")),
        "domain_confidence": str(parsed.get("domain_confidence", "low")),
        "suggestions": cleaned,
        "model": resp.model,
    }
