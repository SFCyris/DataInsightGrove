"""column_lineage_report — per-column profile + provenance hint."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ColumnLineageReportStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        stage = (params.get("stageLabel") or "post-pipeline").strip()
        rows: list[dict] = []
        for col in df.columns:
            dtype = str(df.schema[col])
            distinct = df[col].n_unique() if df.height > 0 else 0
            nulls = df[col].null_count() if df.height > 0 else 0
            row = {
                "column": col, "dtype": dtype,
                "distinct_count": int(distinct), "null_count": int(nulls),
                "null_pct": round(100 * nulls / max(1, df.height), 2),
            }
            if dtype.startswith(("Int", "Float", "Decimal")):
                non_null = df[col].drop_nulls()
                if non_null.len() > 0:
                    try:
                        row["min"] = float(non_null.min())
                        row["max"] = float(non_null.max())
                        row["mean"] = float(non_null.mean())
                    except Exception:
                        pass
            rows.append(row)
        report_df = pl.DataFrame(rows)

        artifact = {
            "kind": "metrics", "label": f"Lineage report — {stage}",
            "data": {
                "stage": stage, "n_rows": df.height, "n_columns": df.width,
                "columns": rows,
            },
        }
        return PolarsResult(output=df, artifacts=[artifact])


step = ColumnLineageReportStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
