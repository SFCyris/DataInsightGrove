"""impute_forward_backward — fill nulls via prior/next value."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ImputeForwardBackwardStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        cols = params.get("columns") or []
        direction = (params.get("direction") or "forward").lower()
        sort_col = params.get("sortColumn")
        group_col = params.get("groupColumn")

        if sort_col and sort_col in df.columns:
            df = df.sort(sort_col)

        def _fill(frame: pl.DataFrame) -> pl.DataFrame:
            for c in cols:
                if c not in frame.columns: continue
                if direction in ("forward", "both"):
                    frame = frame.with_columns(pl.col(c).forward_fill())
                if direction in ("backward", "both"):
                    frame = frame.with_columns(pl.col(c).backward_fill())
            return frame

        if group_col and group_col in df.columns:
            # Apply per-group; preserve original row order via row index.
            df = df.with_row_index("__rownum")
            chunks = []
            for _, sub in df.group_by(group_col):
                chunks.append(_fill(sub))
            out = pl.concat(chunks).sort("__rownum").drop("__rownum")
        else:
            out = _fill(df)
        return PolarsResult(output=out)


step = ImputeForwardBackwardStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
