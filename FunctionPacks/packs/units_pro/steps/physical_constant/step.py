from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class PhysicalConstantStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import pint

        df = inputs["in"]
        const = params["constant"]
        out_col = params["output_column"]

        ureg = pint.UnitRegistry()
        try:
            # Pint exposes constants as attributes on the registry.
            value = float(getattr(ureg, const).magnitude)
        except (AttributeError, pint.errors.UndefinedUnitError) as e:
            raise ValueError(f"physical_constant: unknown constant {const!r}") from e

        return PolarsResult(output=df.with_columns(pl.lit(value).alias(out_col)))


step = PhysicalConstantStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
