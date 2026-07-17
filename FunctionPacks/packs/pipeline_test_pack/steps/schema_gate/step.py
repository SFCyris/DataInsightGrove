"""schema_gate — assert columns + dtypes match a contract."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class SchemaGateStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        required = [c.strip() for c in (params.get("requiredColumns") or "").split(",") if c.strip()]
        if not required:
            raise ValueError("schema_gate: requiredColumns is empty")
        types_raw = (params.get("expectedTypes") or "").strip()
        allow_extra = bool(params.get("allowExtraColumns", True))

        expected_types = {}
        if types_raw:
            for entry in types_raw.split(","):
                entry = entry.strip()
                if ":" not in entry: continue
                col, t = entry.split(":", 1)
                expected_types[col.strip()] = t.strip()

        present = set(df.columns)
        required_set = set(required)
        missing = required_set - present
        if missing:
            raise ValueError(f"schema_gate: missing required columns: {sorted(missing)}")
        if not allow_extra:
            extras = present - required_set
            if extras:
                raise ValueError(f"schema_gate: unexpected extra columns: {sorted(extras)}")

        type_diffs = []
        for col, expected_t in expected_types.items():
            actual_t = str(df.schema.get(col, "<missing>"))
            if expected_t.lower() not in actual_t.lower():
                type_diffs.append(f"{col}: expected {expected_t!r}, got {actual_t!r}")
        if type_diffs:
            raise ValueError("schema_gate: dtype mismatches:\n  " + "\n  ".join(type_diffs))

        return PolarsResult(output=df, artifacts=[{
            "kind": "metrics", "label": "Schema gate",
            "data": {"status": "PASS", "n_columns": df.width, "n_rows": df.height,
                     "checked_columns": required, "checked_types": expected_types or "(none)"},
        }])


step = SchemaGateStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
