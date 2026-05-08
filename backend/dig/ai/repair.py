"""Step-param validation + auto-repair for LLM-emitted suggestions.

Single canonical home for the per-step repair logic. Every AI feature
that emits step suggestions (suggest_pipeline_steps, suggest_next,
suggest_visualizations) routes its candidates through this module.

Design contract:
  - **Conservative repairs only.** We auto-fill values that are
    semantically safe + meaningful given the schema (default
    aggregations, output column names derived from inputs). We never
    invent free-text fields the user actually has to specify (filter
    predicates, derive expressions).
  - **Drop on uncertainty.** Returning ``None`` from a repair signals
    "this step can't be made workable from the available data — the
    caller should drop the whole route". Better to surface fewer
    working suggestions than many broken ones.
  - **Data-aware default names.** Generated column names use the
    input column + operation (``cl_to_cd_ratio``, ``revenue_rolling_7d``)
    so the user sees intent, not boilerplate (``derived_0``).
"""
from __future__ import annotations

from typing import Any


# Numeric-ish polars/SQL types — used for picking default columns.
_NUMERIC_TYPES = {
    "integer", "double", "number", "float", "i32", "i64", "f32", "f64",
    "decimal", "currency", "percentage", "bignum", "scientific",
}


def is_numeric(col_type: str | None) -> bool:
    if not col_type:
        return False
    t = col_type.lower()
    return any(n in t for n in _NUMERIC_TYPES)


def first_numeric_col(schema: dict[str, str], *, exclude: list[str] | None = None) -> str | None:
    excluded = set(exclude or [])
    for name, type_ in schema.items():
        if name in excluded:
            continue
        if is_numeric(type_):
            return name
    return None


def meaningful_name(prefix: str, *parts: str) -> str:
    """Build a snake_case name from a prefix + meaningful parts.

    Used for default ``output_column`` / ``name`` / ``as`` slots so
    generated columns look like ``cl_to_cd_ratio`` instead of
    ``derived_0`` or empty string.
    """
    out = "_".join(
        p.strip().lower().replace(" ", "_").replace("/", "_per_")
        for p in (prefix, *parts) if p
    )
    return "".join(c if c.isalnum() or c == "_" else "_" for c in out).strip("_") or prefix


def strip_unknown_columns(params: dict[str, Any], schema: dict[str, str]) -> dict[str, Any]:
    """Remove param values that reference columns not in the schema.

    Hands back a sanitised copy. List values keep only the items that
    resolve; non-string scalars pass through unchanged.
    """
    valid_cols = set(schema.keys())
    out: dict[str, Any] = {}
    for k, v in params.items():
        if isinstance(v, str) and v in valid_cols:
            out[k] = v
        elif isinstance(v, list) and all(isinstance(x, str) for x in v):
            kept = [x for x in v if x in valid_cols]
            if kept:
                out[k] = kept
        elif not isinstance(v, str) and not isinstance(v, list):
            out[k] = v
    return out


def _is_type_compatible(left_type: str, right_type: str) -> bool:
    """Mirror of the frontend's type-compat check in match-quality.ts:
    both numeric, OR both string-like. Strings that parse as numbers
    are still strings here — the SQL builder's CAST handles coercion.
    """
    l = (left_type or "").lower()
    r = (right_type or "").lower()
    l_num = is_numeric(l)
    r_num = is_numeric(r)
    if l_num and r_num:
        return True
    if (not l_num) and (not r_num):
        return True
    return False


def _auto_fill_join_keys(
    left_schema: dict[str, str],
    right_schema: dict[str, str],
) -> list[dict[str, str]]:
    """Auto-detect equality keys from two schemas: pick name-matching
    AND type-compatible columns. Mirrors the frontend's `suggestKeys`
    name-match path (case-insensitive exact only — Levenshtein ≤ 2 is
    a UI nicety we skip on the server to avoid surprising the user
    with `customer_id ↔ customer_idx` matches that the LLM didn't
    propose).

    Returns at most 3 keys (composite is fine, but more than 3 is
    almost always a mistake — the user can add more in the panel).
    """
    if not left_schema or not right_schema:
        return []
    right_lc = {k.lower(): k for k in right_schema}
    out: list[dict[str, str]] = []
    for lcol, ltype in left_schema.items():
        rcol = right_lc.get(lcol.lower())
        if rcol is None:
            continue
        rtype = right_schema[rcol]
        if not _is_type_compatible(ltype, rtype):
            continue
        out.append({"left": lcol, "right": rcol, "op": "="})
        if len(out) >= 3:
            break
    return out


def validate_and_repair_step(
    step_id: str,
    params: dict[str, Any],
    manifest: dict[str, Any],
    schema: dict[str, str],
    *,
    route_title: str = "",
    other_schemas: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any] | None:
    """Validate ``params`` against ``manifest``'s required fields and
    try to auto-repair any gaps. Returns the (possibly repaired)
    params dict on success, or ``None`` when the step can't be made
    workable from the available schema.

    None means "drop this step". Callers that hand multi-step routes
    (suggest_pipeline_steps) should also drop the whole route on a
    single ``None`` — partial routes confuse users more than missing
    routes.

    ``other_schemas`` is keyed by ref id (dataset alias or upstream
    node id). Currently only the join step uses it: when the LLM
    proposes a join, we pick whichever schema has the most type-compat
    column-name overlap with the focused (left) schema, fill in
    ``params.keys`` from that overlap, and stash the chosen ref id at
    ``params.__ai_right_ref`` so the caller can wire the right input.
    """
    out = dict(params)
    spec = manifest.get("params") or {}

    if step_id == "group_aggregate":
        group_by = out.get("groupBy")
        if not isinstance(group_by, list) or not group_by:
            return None
        # Empty aggregates → row-count using the first groupBy column
        # (any column works for count; using a real column avoids
        # quoting issues with a literal "*"). Gives the user a useful
        # row-count column they can then customise.
        aggs = out.get("aggregates")
        if not isinstance(aggs, list) or len(aggs) == 0:
            count_col = group_by[0] if isinstance(group_by[0], str) else next(iter(schema), None)
            if count_col:
                out["aggregates"] = [
                    {"column": count_col, "fn": "count", "as": "row_count"},
                ]
            else:
                return None
    elif step_id == "derive_column":
        # Need both a name and an expression. We don't invent the
        # expression (would hallucinate a calculation the user didn't
        # ask for); if missing → drop.
        if not (isinstance(out.get("expression"), str) and out["expression"].strip()):
            return None
        if not (isinstance(out.get("name"), str) and out["name"].strip()):
            # Auto-name from columns referenced in the expression so
            # the resulting column carries meaning instead of "derived_0".
            expr = out["expression"]
            referenced = [c for c in schema if c in expr]
            if referenced:
                out["name"] = meaningful_name("derived", *referenced)
            else:
                return None
    elif step_id == "filter_rows":
        if not (isinstance(out.get("predicate"), str) and out["predicate"].strip()):
            return None
    elif step_id == "rolling":
        wnds = out.get("windows")
        if not isinstance(wnds, list) or not wnds:
            col = first_numeric_col(schema)
            if not col:
                return None
            out["windows"] = [{
                "column": col, "fn": "mean", "window": 7,
                "as": meaningful_name(col, "mean_7"),
            }]
        else:
            repaired_windows = []
            for w in wnds:
                if isinstance(w, dict):
                    if w.get("column") and w.get("fn") and w.get("window"):
                        if not w.get("as"):
                            w = {**w, "as": meaningful_name(
                                str(w["column"]), str(w["fn"]), str(w["window"]),
                            )}
                        repaired_windows.append(w)
                elif isinstance(w, int):
                    col = first_numeric_col(schema)
                    if col:
                        repaired_windows.append({
                            "column": col, "fn": "mean", "window": w,
                            "as": meaningful_name(col, "mean", str(w)),
                        })
            if not repaired_windows:
                return None
            out["windows"] = repaired_windows
    elif step_id == "linear_regression":
        y = out.get("y")
        if not (isinstance(y, str) and y in schema):
            return None
        xs = out.get("x_columns")
        if not isinstance(xs, list) or not xs:
            return None
        if not out.get("predicted_column"):
            out["predicted_column"] = meaningful_name(y, "pred")
        if not out.get("residual_column"):
            out["residual_column"] = meaningful_name(y, "residual")
    elif step_id == "anomaly_zscore":
        if not (isinstance(out.get("value"), str) and out["value"] in schema):
            return None
    elif step_id == "forecast":
        for k in ("time_column", "value_column"):
            v = out.get(k)
            if not (isinstance(v, str) and v in schema):
                return None
        if not isinstance(out.get("horizon"), int) or out["horizon"] <= 0:
            out["horizon"] = 12
    elif step_id == "seasonal_decompose":
        for k in ("time_column", "value_column"):
            v = out.get(k)
            if not (isinstance(v, str) and v in schema):
                return None
        if not isinstance(out.get("period"), int) or out["period"] <= 1:
            out["period"] = 12
    elif step_id == "cast_type":
        if not (isinstance(out.get("column"), str) and out["column"] in schema):
            return None
        if not isinstance(out.get("targetType"), str):
            return None
    elif step_id == "select_columns":
        cols = out.get("columns")
        if not isinstance(cols, list) or not cols:
            return None
    elif step_id == "rename_columns":
        # Renames is a list of {from, to} or a {old: new} map — accept
        # either shape; drop if both missing.
        if not (out.get("renames") or out.get("mapping")):
            return None
    elif step_id == "sort_rows":
        keys = out.get("keys")
        if not isinstance(keys, list) or not keys:
            return None
    elif step_id == "deduplicate":
        # No required fields — dedup-on-all-cols is the default.
        pass
    elif step_id == "join":
        # `kind` defaults to inner via the manifest; the only thing
        # we genuinely need is `keys`. Try to auto-fill from the best
        # overlap with any other in-scope schema.
        keys = out.get("keys") if isinstance(out.get("keys"), list) else []
        usable_keys = [
            k for k in keys
            if isinstance(k, dict) and k.get("left") and k.get("right")
        ]
        right_ref = out.get("__ai_right_ref")
        if not usable_keys:
            # Pick the right schema with the most type-compat name
            # overlap. We search whichever ref the LLM hinted at first
            # (if any), then every other_schemas entry.
            best_ref: str | None = None
            best_keys: list[dict[str, str]] = []
            candidates: list[tuple[str, dict[str, str]]] = []
            if isinstance(right_ref, str) and other_schemas and right_ref in other_schemas:
                candidates.append((right_ref, other_schemas[right_ref]))
            if other_schemas:
                for ref, sch in other_schemas.items():
                    if ref != right_ref:
                        candidates.append((ref, sch))
            for ref, right_schema in candidates:
                cand = _auto_fill_join_keys(schema, right_schema)
                if len(cand) > len(best_keys):
                    best_keys = cand
                    best_ref = ref
            if not best_keys:
                # No compatible right side → the AI can't usefully
                # propose a join here. Drop the step.
                return None
            out["keys"] = best_keys
            out["__ai_right_ref"] = best_ref
        elif right_ref is None and other_schemas:
            # LLM gave keys but no right ref. Keep the keys; pick the
            # ref whose schema actually contains the named right cols.
            wanted = {k["right"] for k in usable_keys if k.get("right")}
            for ref, sch in other_schemas.items():
                if wanted.issubset(set(sch.keys())):
                    out["__ai_right_ref"] = ref
                    break
        # Sane defaults for collisions / suffixes if the model omitted.
        if not isinstance(out.get("kind"), str):
            out["kind"] = "inner"
        if not isinstance(out.get("columnCollisions"), str):
            out["columnCollisions"] = "keep_both"
        if not isinstance(out.get("suffixes"), list) or len(out["suffixes"]) < 2:
            out["suffixes"] = ["_left", "_right"]

    # Generic check: any unfilled required field with no per-step rule
    # above → fill with manifest default if any, else drop.
    for pname, pspec in spec.items():
        if not pspec.get("required"):
            continue
        v = out.get(pname)
        if v is None or v == "" or (isinstance(v, list) and len(v) == 0):
            if pspec.get("default") is not None:
                out[pname] = pspec["default"]
            else:
                return None

    # Generic numeric-range repair: every integer / number param with a
    # `min`/`max` declared in the manifest gets clamped — and if the
    # emitted value is wildly out of range (e.g. the LLM wrote
    # `width: 6` thinking matplotlib inches when the manifest expects
    # 200..4000 px), prefer the manifest default over a clamp so the
    # rendered chart looks sane instead of comically thin/short.
    for pname, pspec in spec.items():
        ptype = pspec.get("type")
        if ptype not in ("integer", "number"):
            continue
        v = out.get(pname)
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        lo = pspec.get("min")
        hi = pspec.get("max")
        default = pspec.get("default")
        if lo is not None and v < lo:
            # If the LLM is FAR below the floor (>2× under), it likely
            # picked the wrong unit. Use the manifest default instead
            # of clamping to `min` (which is just the smallest the user
            # is ever expected to pick — not a sensible default).
            out[pname] = default if (default is not None and v * 2 < lo) else lo
        elif hi is not None and v > hi:
            out[pname] = default if (default is not None and v > hi * 2) else hi

    return out
