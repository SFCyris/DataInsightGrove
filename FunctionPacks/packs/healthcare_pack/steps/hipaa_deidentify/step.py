"""hipaa_deidentify — HIPAA Safe-Harbor identifier removal + generalisation."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class HipaaDeidentifyStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        drop_cols = params.get("dropColumns") or []
        zip_col = params.get("zipColumn")
        age_col = params.get("ageColumn")

        # Drop direct identifiers.
        keep = [c for c in df.columns if c not in drop_cols]
        out = df.select(keep)
        # Generalise ZIP to 3-digit.
        if zip_col and zip_col in out.columns:
            out = out.with_columns(
                pl.col(zip_col).cast(pl.Utf8).str.slice(0, 3).alias(zip_col)
            )
        # Cap age at 90+.
        if age_col and age_col in out.columns:
            out = out.with_columns(
                pl.when(pl.col(age_col) >= 90).then(pl.lit("90+"))
                  .otherwise(pl.col(age_col).cast(pl.Utf8))
                  .alias(age_col)
            )
        return PolarsResult(output=out, artifacts=[{
            "kind": "metrics", "label": "HIPAA Safe-Harbor de-identify",
            "data": {"columns_dropped": drop_cols,
                     "zip_generalized": zip_col,
                     "age_capped": age_col,
                     "output_columns": out.columns},
        }])


step = HipaaDeidentifyStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
