"""pipeline_snapshot_test — content hash + shape snapshot regression guard."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class PipelineSnapshotTestStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        # Hash: sorted-column-name list + per-column dtype + row count + sha of frame bytes (stable order via sort).
        cols = sorted(df.columns)
        dtypes = [str(df.schema[c]) for c in cols]
        try:
            sorted_df = df.select(cols).sort(cols[:1] if cols else [])
            payload = sorted_df.write_csv(include_header=True).encode("utf-8")
        except Exception:
            payload = df.write_csv(include_header=True).encode("utf-8")
        h = hashlib.sha256(payload).hexdigest()[:16]
        actual = {"rows": df.height, "cols": df.width, "hash": h, "columns": cols, "dtypes": dtypes}

        expected_raw = (params.get("expectedSnapshot") or "").strip()
        tolerance_pct = float(params.get("tolerance") or 0.0)
        if not expected_raw:
            # First run — emit snapshot for the user to copy back.
            return PolarsResult(output=df, artifacts=[{
                "kind": "metrics", "label": "Snapshot (paste into expectedSnapshot param)",
                "data": {"snapshot": actual, "instruction":
                          "Copy the JSON above into the step's expectedSnapshot param to lock it in."},
            }])
        try:
            expected = json.loads(expected_raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"pipeline_snapshot_test: expectedSnapshot is not valid JSON: {e}") from e
        diffs = []
        if actual["cols"] != expected.get("cols"):
            diffs.append(f"cols: expected {expected.get('cols')} got {actual['cols']}")
        if expected.get("columns") and set(expected["columns"]) != set(actual["columns"]):
            missing = set(expected["columns"]) - set(actual["columns"])
            extra = set(actual["columns"]) - set(expected["columns"])
            if missing: diffs.append(f"missing columns: {sorted(missing)}")
            if extra: diffs.append(f"new columns: {sorted(extra)}")
        exp_rows = expected.get("rows")
        if exp_rows is not None:
            allowed = exp_rows * (tolerance_pct / 100.0)
            if abs(actual["rows"] - exp_rows) > allowed:
                diffs.append(f"rows: expected {exp_rows} ±{tolerance_pct:.1f}%, got {actual['rows']}")
        if expected.get("hash") and actual["hash"] != expected["hash"] and not diffs:
            diffs.append(f"content hash drift: expected {expected['hash']} got {actual['hash']}")
        if diffs:
            raise ValueError("pipeline_snapshot_test FAILED:\n  " + "\n  ".join(diffs))
        return PolarsResult(output=df, artifacts=[{
            "kind": "metrics", "label": "Snapshot match",
            "data": {"status": "PASS", "snapshot": actual},
        }])


step = PipelineSnapshotTestStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
