from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ConvertUnitsProStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import pint

        df = inputs["in"]
        col = params["value"]
        from_unit = params["from_unit"]
        to_unit = params["to_unit"]
        out_col = params["output_column"]

        ureg = pint.UnitRegistry()
        try:
            # Build a Quantity for the entire numeric array, convert in one go.
            x = df[col].to_numpy()
            q = ureg.Quantity(x, from_unit)
            converted = q.to(to_unit).magnitude
        except (pint.UndefinedUnitError, pint.DimensionalityError) as e:
            raise ValueError(f"convert_units_pro: {e}") from e

        return PolarsResult(output=df.with_columns(pl.Series(name=out_col, values=converted.tolist())))


step = ConvertUnitsProStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
