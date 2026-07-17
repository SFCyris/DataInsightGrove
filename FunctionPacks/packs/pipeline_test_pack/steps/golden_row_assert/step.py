"""golden_row_assert — assert specific rows match expected values."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class GoldenRowAssertStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        id_col = params["idColumn"]
        if id_col not in df.columns:
            raise ValueError(f"golden_row_assert: idColumn {id_col!r} not in input")
        try:
            expectations = json.loads(params["expectations"])
        except json.JSONDecodeError as e:
            raise ValueError(f"golden_row_assert: expectations is not valid JSON: {e}") from e
        if not isinstance(expectations, list):
            raise ValueError("golden_row_assert: expectations must be a JSON array")
        tolerance = float(params.get("tolerance") or 0.0)

        failures: list[str] = []
        passed = 0
        for exp in expectations:
            if id_col not in exp:
                failures.append(f"expectation entry missing {id_col!r}: {exp}")
                continue
            id_val = exp[id_col]
            row = df.filter(pl.col(id_col) == id_val)
            if row.height == 0:
                failures.append(f"id={id_val!r}: not found in input")
                continue
            if row.height > 1:
                failures.append(f"id={id_val!r}: matched {row.height} rows (expected unique)")
                continue
            for col, exp_val in exp.items():
                if col == id_col: continue
                if col not in df.columns:
                    failures.append(f"id={id_val!r}: column {col!r} missing"); continue
                actual = row[col][0]
                if isinstance(exp_val, (int, float)) and isinstance(actual, (int, float)):
                    if abs(float(actual) - float(exp_val)) > tolerance:
                        failures.append(f"id={id_val!r} {col}: expected {exp_val}, got {actual}")
                elif actual != exp_val:
                    failures.append(f"id={id_val!r} {col}: expected {exp_val!r}, got {actual!r}")
            else:
                passed += 1

        if failures:
            raise ValueError(f"golden_row_assert: {len(failures)} failure(s):\n  " +
                              "\n  ".join(failures[:20]) +
                              (f"\n  … +{len(failures) - 20} more" if len(failures) > 20 else ""))
        return PolarsResult(output=df, artifacts=[{
            "kind": "metrics", "label": "Golden row asserts",
            "data": {"status": "PASS", "checked": len(expectations), "passed": passed},
        }])


step = GoldenRowAssertStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
