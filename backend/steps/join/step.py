"""Join step — combine two inputs on matching key columns.

Six join kinds:
  - inner       — only matching rows
  - left        — all left rows; right columns NULL when unmatched
  - right       — all right rows; left columns NULL when unmatched
  - full        — all rows from both sides; NULLs where unmatched
  - anti_left   — rows on the left that DON'T match (set difference)
  - anti_right  — mirror of anti_left

The SQL is built in-process from a small spec so the join params are
1:1 with what the live grid renders. Anti-joins use the standard
`LEFT JOIN ... WHERE r.<key> IS NULL` form (and the right-mirror).

Column collision resolution rules (param `columnCollisions`):
  - keep_both    columns present on both sides get suffixed (defaults
                 `_left` / `_right`; configurable). Key columns are
                 collapsed to a single output column (the left side's
                 value) since they're tautologically equal post-join.
  - keep_left    only the left side's copy survives.
  - keep_right   only the right side's copy survives.
  - coalesce     `COALESCE(left.<col>, right.<col>)` — useful when the
                 column means the same thing on both sides and you
                 want a fallback.

Result columns (param `outputColumns`) lets the user prune + rename
the projected columns without changing the join shape. The widget
keys on a stable provenance ID per column (so a rename survives
suffix/collision changes), then maps:
  - `L:<src>`  → projected from left
  - `R:<src>`  → projected from right
  - `C:<src>`  → coalesced (only when rule = coalesce)
SQL emission honours `excluded` (skip the column) and `renames`
(rewrite the AS alias).

Back-compat: pipelines saved before v1.1 used `how` + `on` instead of
`kind` + `keys`. We accept both names; new docs use `kind` / `keys`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


_VALID_KINDS = {"inner", "left", "right", "full", "anti_left", "anti_right", "cross"}
_VALID_OPS = {"=", "<", "<=", ">", ">=", "≈", "between"}


def _normalise_keys(raw: Any) -> list[dict[str, str]]:
    """Coerce the `keys` (or legacy `on`) param into a list of
    `{left, right, op[, rightHigh]}` dicts. Tolerates string keys +
    missing op (defaults to `=`).

    Special ops:
      - `≈`        fuzzy match (LOWER(TRIM(CAST(... AS VARCHAR))))
      - `between`  range key — needs `rightHigh` set; falls back to `=`
                   silently if rightHigh missing (SQL would otherwise
                   reference an empty identifier and fail).
    """
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for k in raw:
        if not isinstance(k, dict):
            continue
        left = k.get("left")
        right = k.get("right")
        if not (isinstance(left, str) and isinstance(right, str) and left and right):
            continue
        op = k.get("op", "=")
        if op not in _VALID_OPS:
            op = "="
        entry: dict[str, str] = {"left": left, "right": right, "op": op}
        if op == "between":
            right_high = k.get("rightHigh")
            if isinstance(right_high, str) and right_high:
                entry["rightHigh"] = right_high
            else:
                # Malformed BETWEEN — degrade to `=` so the join still
                # runs. The frontend's match-quality bar surfaces the
                # underlying issue (no overlap) so the user notices.
                entry["op"] = "="
        out.append(entry)
    return out


def _key_predicate(k: dict[str, str]) -> str:
    """SQL ON-clause fragment for one normalised key entry."""
    op = k.get("op", "=")
    left_q = quote_ident(k["left"])
    right_q = quote_ident(k["right"])
    if op == "≈":
        # Cast both sides to VARCHAR so non-string columns (numeric IDs
        # stored as ints on one side, strings on the other) still
        # compare. LOWER+TRIM normalise whitespace + case — common
        # join-key issue when one side comes from a CSV.
        return (
            f"LOWER(TRIM(CAST(l.{left_q} AS VARCHAR))) "
            f"= LOWER(TRIM(CAST(r.{right_q} AS VARCHAR)))"
        )
    if op == "between":
        right_high_q = quote_ident(k["rightHigh"])
        return f"l.{left_q} BETWEEN r.{right_q} AND r.{right_high_q}"
    return f"l.{left_q} {op} r.{right_q}"


def _normalise_output_diff(raw: Any) -> tuple[set[str], dict[str, str]]:
    """Coerce `outputColumns` into (excluded_provenance_ids, renames).
    Tolerates missing / malformed entries — drift on upstream schema
    changes is silent (a stale exclude becomes a no-op).
    """
    if not isinstance(raw, dict):
        return set(), {}
    excluded_raw = raw.get("excluded") or []
    renames_raw = raw.get("renames") or {}
    excluded: set[str] = set()
    if isinstance(excluded_raw, list):
        for x in excluded_raw:
            if isinstance(x, str) and x:
                excluded.add(x)
    renames: dict[str, str] = {}
    if isinstance(renames_raw, dict):
        for k, v in renames_raw.items():
            if isinstance(k, str) and isinstance(v, str) and k and v:
                renames[k] = v
    return excluded, renames


def _build_select_clause(
    left_cols: list[str],
    right_cols: list[str],
    keys: list[dict[str, str]],
    rule: str,
    suffixes: list[str],
    output_diff: tuple[set[str], dict[str, str]] = (set(), {}),
) -> str:
    """Build the column-projection SELECT list, handling collisions
    per the rule. Key columns from the right side are dropped since
    they're tautologically equal to the left's match (when op is `=`).
    Non-equality keys (range joins) keep both because the values can
    legitimately differ within the inequality bound.

    `output_diff` is a (excluded, renames) pair keyed by provenance ID:
      - "L:<src>" — left input's column
      - "R:<src>" — right input's column
      - "C:<src>" — coalesced (only when rule = coalesce)
    Excluded provenance IDs are skipped; renames replace the AS alias.
    """
    left_keys = {k["left"] for k in keys if k.get("op", "=") == "="}
    right_keys = {k["right"] for k in keys if k.get("op", "=") == "="}
    left_set = set(left_cols)
    right_set = set(right_cols)
    suffix_l = suffixes[0] if len(suffixes) > 0 else "_left"
    suffix_r = suffixes[1] if len(suffixes) > 1 else "_right"
    excluded, renames = output_diff

    parts: list[str] = []

    def _emit(prov_id: str, sql_expr: str, default_alias: str) -> None:
        if prov_id in excluded:
            return
        alias = renames.get(prov_id, default_alias)
        if alias == default_alias and sql_expr.endswith(quote_ident(default_alias)):
            # Bare column ref like `l.id` — don't repeat the alias.
            parts.append(sql_expr)
        else:
            parts.append(f"{sql_expr} AS {quote_ident(alias)}")

    # Left side: emit every column not equality-key-collapsed.
    for col in left_cols:
        if col in right_set and col not in left_keys:
            # Collision — apply rule.
            if rule == "keep_left":
                _emit(f"L:{col}", f"l.{quote_ident(col)}", col)
            elif rule == "keep_right":
                pass  # right side will emit it
            elif rule == "coalesce":
                _emit(
                    f"C:{col}",
                    f"COALESCE(l.{quote_ident(col)}, r.{quote_ident(col)})",
                    col,
                )
            else:  # keep_both (default)
                _emit(f"L:{col}", f"l.{quote_ident(col)}", col + suffix_l)
        else:
            _emit(f"L:{col}", f"l.{quote_ident(col)}", col)

    # Right side: emit non-key non-collision columns + suffixed
    # collisions when keep_both.
    for col in right_cols:
        if col in right_keys:
            # Equality-key right-side column collapsed away.
            continue
        if col in left_set:
            if rule == "keep_left":
                pass  # already emitted by the left loop
            elif rule == "keep_right":
                _emit(f"R:{col}", f"r.{quote_ident(col)}", col)
            elif rule == "coalesce":
                pass  # already emitted via COALESCE in the left loop
            else:  # keep_both
                _emit(f"R:{col}", f"r.{quote_ident(col)}", col + suffix_r)
        else:
            _emit(f"R:{col}", f"r.{quote_ident(col)}", col)

    return ", ".join(parts) if parts else "l.*, r.*"


class JoinStep(Step):
    def to_sql(
        self,
        params: dict[str, Any],
        inputs: dict[str, str],
        input_schemas: dict[str, dict[str, str]] | None = None,
    ) -> str:
        # Both ports are required. If a user partially wired the join
        # (e.g. dragged from an upstream into `left` and never wired
        # `right`), the compile path used to surface a raw Python
        # KeyError. Replace that with a clear, actionable error so the
        # editor's per-node status banner reads sensibly.
        missing = [p for p in ("left", "right") if p not in inputs]
        if missing:
            ports = ", ".join(f"'{p}'" for p in missing)
            raise ValueError(
                f"join: missing input port {ports}. "
                "Wire both sides in the Inputs panel before previewing."
            )
        left = inputs["left"]
        right = inputs["right"]

        # Back-compat: accept either new (`kind` / `keys`) or legacy
        # (`how` / `on`) param names.
        kind = (params.get("kind") or params.get("how") or "inner").lower()
        if kind not in _VALID_KINDS:
            kind = "inner"

        if kind == "cross":
            return f"SELECT l.*, r.* FROM {left} AS l CROSS JOIN {right} AS r"

        keys = _normalise_keys(params.get("keys") or params.get("on"))
        if not keys:
            raise ValueError(
                "join: no key columns specified. Add at least one (left, right) "
                "key pair in the keys-builder, or set kind='cross' for a Cartesian product."
            )

        # Build the ON clause: AND-combined per-key predicates. Each
        # predicate is rendered op-aware (fuzzy → LOWER(TRIM(CAST)),
        # between → BETWEEN, others → bare `op`).
        on_clause = " AND ".join(_key_predicate(k) for k in keys)

        # Schemas for collision resolution. When the dispatcher passes
        # `input_schemas` we use it; otherwise fall back to `*` (which
        # produces DuckDB's auto-suffix-on-collision — usable but
        # inferior to the explicit per-column rules below).
        left_cols: list[str] = []
        right_cols: list[str] = []
        if input_schemas:
            left_cols = list(input_schemas.get("left", {}).keys())
            right_cols = list(input_schemas.get("right", {}).keys())

        rule = (params.get("columnCollisions") or "keep_both").lower()
        suffixes = params.get("suffixes")
        if not isinstance(suffixes, list) or len(suffixes) < 2:
            suffixes = ["_left", "_right"]
        output_diff = _normalise_output_diff(params.get("outputColumns"))
        excluded, renames = output_diff

        # Anti-joins: the result schema only includes the surviving
        # side's columns. We translate to LEFT JOIN + IS NULL on the
        # other side's keys (the standard set-difference pattern).
        if kind in ("anti_left", "anti_right"):
            if kind == "anti_left":
                # rows on left WITHOUT a match → keep left's columns,
                # drop right's entirely (no collision concerns).
                if left_cols:
                    parts: list[str] = []
                    for c in left_cols:
                        prov = f"L:{c}"
                        if prov in excluded:
                            continue
                        alias = renames.get(prov, c)
                        if alias == c:
                            parts.append(f"l.{quote_ident(c)}")
                        else:
                            parts.append(f"l.{quote_ident(c)} AS {quote_ident(alias)}")
                    projection = ", ".join(parts) if parts else "l.*"
                else:
                    projection = "l.*"
                # WHERE r.<first-right-key> IS NULL is enough — if the
                # left row matched ANY right row that key would be set.
                anchor = quote_ident(keys[0]["right"])
                return (
                    f"SELECT {projection} FROM {left} AS l "
                    f"LEFT JOIN {right} AS r ON {on_clause} "
                    f"WHERE r.{anchor} IS NULL"
                )
            # anti_right
            if right_cols:
                parts = []
                for c in right_cols:
                    prov = f"R:{c}"
                    if prov in excluded:
                        continue
                    alias = renames.get(prov, c)
                    if alias == c:
                        parts.append(f"r.{quote_ident(c)}")
                    else:
                        parts.append(f"r.{quote_ident(c)} AS {quote_ident(alias)}")
                projection = ", ".join(parts) if parts else "r.*"
            else:
                projection = "r.*"
            anchor = quote_ident(keys[0]["left"])
            return (
                f"SELECT {projection} FROM {right} AS r "
                f"LEFT JOIN {left} AS l ON {on_clause} "
                f"WHERE l.{anchor} IS NULL"
            )

        # inner / left / right / full
        sql_kind = {
            "inner": "INNER", "left": "LEFT",
            "right": "RIGHT", "full": "FULL OUTER",
        }[kind]

        # If no schemas supplied, fall back to `l.*, r.*` — DuckDB
        # auto-suffixes collisions with `_1`. Less ideal than our
        # explicit rule but always correct.
        if not (left_cols or right_cols):
            return (
                f"SELECT l.*, r.* FROM {left} AS l "
                f"{sql_kind} JOIN {right} AS r ON {on_clause}"
            )

        select_clause = _build_select_clause(
            left_cols, right_cols, keys, rule, suffixes, output_diff,
        )
        return (
            f"SELECT {select_clause} FROM {left} AS l "
            f"{sql_kind} JOIN {right} AS r ON {on_clause}"
        )

    def infer_schema(self, input_schemas, params):
        left = input_schemas.get("left", {}) or {}
        right = input_schemas.get("right", {}) or {}
        kind = (params.get("kind") or params.get("how") or "inner").lower()
        if kind not in _VALID_KINDS:
            kind = "inner"
        excluded, renames = _normalise_output_diff(params.get("outputColumns"))

        def _apply(prov_id: str, default_name: str, t: str, out: dict[str, str]) -> None:
            if prov_id in excluded:
                return
            out[renames.get(prov_id, default_name)] = t

        if kind == "cross":
            out: dict[str, str] = {}
            for k, v in left.items():
                _apply(f"L:{k}", k, v, out)
            for k, v in right.items():
                default = f"{k}_1" if k in left else k
                _apply(f"R:{k}", default, v, out)
            return out

        keys = _normalise_keys(params.get("keys") or params.get("on"))
        if kind == "anti_left":
            out = {}
            for k, v in left.items():
                _apply(f"L:{k}", k, v, out)
            return out
        if kind == "anti_right":
            out = {}
            for k, v in right.items():
                _apply(f"R:{k}", k, v, out)
            return out

        rule = (params.get("columnCollisions") or "keep_both").lower()
        suffixes = params.get("suffixes")
        if not isinstance(suffixes, list) or len(suffixes) < 2:
            suffixes = ["_left", "_right"]

        left_keys_eq = {k["left"] for k in keys if k.get("op", "=") == "="}
        right_keys_eq = {k["right"] for k in keys if k.get("op", "=") == "="}
        left_set = set(left.keys())
        right_set = set(right.keys())

        out = {}
        for col, t in left.items():
            if col in right_set and col not in left_keys_eq:
                if rule == "keep_left":
                    _apply(f"L:{col}", col, t, out)
                elif rule == "keep_right":
                    pass  # right loop will emit
                elif rule == "coalesce":
                    _apply(f"C:{col}", col, t, out)
                else:  # keep_both
                    _apply(f"L:{col}", col + suffixes[0], t, out)
            else:
                _apply(f"L:{col}", col, t, out)
        for col, t in right.items():
            if col in right_keys_eq:
                continue
            if col in left_set:
                if rule == "keep_right":
                    _apply(f"R:{col}", col, t, out)
                elif rule == "keep_both":
                    _apply(f"R:{col}", col + suffixes[1], t, out)
                # keep_left / coalesce: skip
            else:
                _apply(f"R:{col}", col, t, out)
        return out


step = JoinStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
