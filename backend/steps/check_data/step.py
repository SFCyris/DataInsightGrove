"""Data quality check step.

Passthrough on the data; the value of the step lives in `validation_sql`,
which counts violations and surfaces them as run artifacts. The frontend
event pipeline turns those artifacts into `data.quality.violation`
notifications via the existing rule engine.

Severity semantics:
  - warn  → emit notification, run continues
  - error → emit notification AND mark the run as failed in post-process

The "fail the run" path is implemented in the executor — this step
itself never raises. The artifact carries `severity` so the executor
can inspect it after running.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, assert_safe_expr, quote_ident, quote_str


def _check_predicate_sql(params: dict[str, Any], col_quoted: str) -> str:
    """Returns a SQL boolean expression that is TRUE for ROWS THAT PASS
    the rule, FALSE for rows that violate it. NULL values follow the
    same rules as the underlying check (e.g. `not_null` rejects them
    explicitly; `between` allows them; `regex` allows them since NULL
    can't match)."""
    kind = params.get("check", "not_null")
    if kind == "not_null":
        return f"{col_quoted} IS NOT NULL"
    if kind == "unique":
        # `unique` is a row-level check encoded as a windowed COUNT.
        # A row passes when there's no other row with the same value.
        return f"COUNT(*) OVER (PARTITION BY {col_quoted}) = 1"
    if kind == "between":
        mn = params.get("min")
        mx = params.get("max")
        clauses: list[str] = []
        if mn is not None:
            clauses.append(f"{col_quoted} >= {float(mn)}")
        if mx is not None:
            clauses.append(f"{col_quoted} <= {float(mx)}")
        if not clauses:
            return "TRUE"  # no bounds → vacuously passes
        # NULLs pass — `between` is a "if present, must be in range" rule.
        return f"({col_quoted} IS NULL OR ({' AND '.join(clauses)}))"
    if kind == "in_set":
        raw = (params.get("set") or "").strip()
        if not raw:
            return "TRUE"
        # Naive split on commas; users with comma-bearing values can use
        # an expression check instead. Each token is quoted as a SQL
        # literal so injection through the values list is impossible.
        items = [s.strip() for s in raw.split(",") if s.strip()]
        if not items:
            return "TRUE"
        quoted = ", ".join(quote_str(s) for s in items)
        return f"({col_quoted} IS NULL OR {col_quoted}::VARCHAR IN ({quoted}))"
    if kind == "regex":
        pat = (params.get("pattern") or "").strip()
        if not pat:
            return "TRUE"
        # DuckDB's regexp_matches() returns BOOLEAN. NULL passes.
        return f"({col_quoted} IS NULL OR regexp_matches({col_quoted}::VARCHAR, {quote_str(pat)}))"
    if kind == "expression":
        # Free-form predicate. Same safety validator the filter_rows step
        # uses — banned tokens (DDL, COPY, etc.) raise immediately.
        expr = (params.get("expression") or "TRUE").strip()
        return assert_safe_expr(expr, kind="predicate")
    # Unknown check kind — treat as vacuously passing so users don't get
    # silent run failures on unrecognised values.
    return "TRUE"


class CheckDataStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        # Passthrough — the data flows through untouched. The QC happens
        # in `validation_sql` against the SAME input CTE.
        return f"SELECT * FROM {inputs['in']}"

    def validation_sql(
        self,
        params: dict[str, Any],
        inputs: dict[str, str],
    ) -> str | None:
        col = params.get("column")
        if not col or not isinstance(col, str):
            return None
        col_q = quote_ident(col)
        passes = _check_predicate_sql(params, col_q)
        # Validation row carries:
        #   total          — total rows (so the UI can show a rate)
        #   violations     — count where the predicate was FALSE
        #   first_bad      — sample of offending values (max 3, comma-joined)
        #   severity       — propagated for the executor's fail-on-violation path
        #   check_kind     — propagated so the notification template can read it
        #   check_name     — friendly label, propagated similarly
        #
        # Materialize the predicate as a scalar column in an inner subquery
        # before aggregating. DuckDB disallows window functions inside
        # aggregate FILTER, and the `unique` check uses
        # `COUNT(*) OVER (PARTITION BY col)` — without the subquery, that
        # raises "window function not allowed in FILTER" at validation time.
        sample_expr = (
            f"string_agg(DISTINCT {col_q}::VARCHAR, ', ') "
            f"FILTER (WHERE _dig_passes = FALSE AND {col_q} IS NOT NULL)"
        )
        severity_lit = quote_str(str(params.get("severity") or "warn"))
        kind_lit = quote_str(str(params.get("check") or "not_null"))
        name_lit = quote_str(str(params.get("name") or ""))
        return (
            f"SELECT "
            f"COUNT(*) AS total, "
            f"COUNT(*) FILTER (WHERE _dig_passes = FALSE) AS violations, "
            f"{sample_expr} AS first_bad, "
            f"{severity_lit} AS severity, "
            f"{kind_lit} AS check_kind, "
            f"{name_lit} AS check_name "
            f"FROM (SELECT {col_q}, ({passes}) AS _dig_passes FROM {inputs['in']})"
        )


step = CheckDataStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
