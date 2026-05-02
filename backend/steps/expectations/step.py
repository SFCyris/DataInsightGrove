"""Data quality expectations step.

Inline rules — each rule is checked against the input frame; violations are
reported as an artifact (kind=expectations). Optionally fails the run when
any rule reports a violation.

Rule kinds:
  - unique:           {column: <col>}                    — column values are unique
  - not_null:         {column: <col>}                    — no nulls
  - between:          {column: <col>, min: <n>, max: <n>}— numeric range
  - in:               {column: <col>, values: [...]}     — membership in a list
  - regex_match:      {column: <col>, pattern: <re>}     — string regex match
  - row_count_between:{min: <n>, max: <n>}               — overall row count
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ExpectationsStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        rules = params.get("rules") or []
        fail_on_violation = bool(params.get("fail_on_violation", False))

        results: list[dict[str, Any]] = []
        for rule in rules:
            kind = (rule.get("kind") or "").lower()
            if kind == "row_count_between":
                lo = rule.get("min")
                hi = rule.get("max")
                ok = (lo is None or df.height >= lo) and (hi is None or df.height <= hi)
                results.append({
                    "rule": rule,
                    "passed": ok,
                    "observed": df.height,
                })
                continue

            col = rule.get("column")
            if col not in df.columns:
                results.append({"rule": rule, "passed": False, "error": f"column '{col}' missing"})
                continue
            series = df.get_column(col)

            if kind == "unique":
                dup = series.value_counts().filter(pl.col("count") > 1).height
                results.append({"rule": rule, "passed": dup == 0, "duplicates": dup})

            elif kind == "not_null":
                nulls = int(series.null_count())
                results.append({"rule": rule, "passed": nulls == 0, "nulls": nulls})

            elif kind == "between":
                lo = rule.get("min")
                hi = rule.get("max")
                expr = pl.col(col)
                cond = pl.lit(True)
                if lo is not None:
                    cond = cond & (expr >= lo)
                if hi is not None:
                    cond = cond & (expr <= hi)
                bad = df.filter(~cond & expr.is_not_null()).height
                results.append({"rule": rule, "passed": bad == 0, "violations": bad})

            elif kind == "in":
                allowed = rule.get("values") or []
                bad = df.filter(~pl.col(col).is_in(allowed) & pl.col(col).is_not_null()).height
                results.append({"rule": rule, "passed": bad == 0, "violations": bad})

            elif kind == "regex_match":
                pattern = rule.get("pattern") or ".*"
                try:
                    re.compile(pattern)
                except re.error as e:
                    results.append({"rule": rule, "passed": False, "error": f"bad regex: {e}"})
                    continue
                bad = df.filter(
                    pl.col(col).is_not_null() & ~pl.col(col).cast(pl.Utf8).str.contains(pattern)
                ).height
                results.append({"rule": rule, "passed": bad == 0, "violations": bad})

            else:
                results.append({"rule": rule, "passed": False, "error": f"unknown kind '{kind}'"})

        n_failed = sum(1 for r in results if not r.get("passed"))

        artifacts = [{
            "kind": "expectations",
            "label": "Data quality checks",
            "n_rules": len(results),
            "n_failed": n_failed,
            "results": results,
        }]

        if fail_on_violation and n_failed > 0:
            failed = [r for r in results if not r.get("passed")]
            raise ValueError(
                f"expectations: {n_failed}/{len(results)} rule(s) failed; first: {failed[0]}"
            )

        return PolarsResult(output=df, artifacts=artifacts)


step = ExpectationsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
