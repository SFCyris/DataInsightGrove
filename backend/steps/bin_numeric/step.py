from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident, quote_str


class BinNumericStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = quote_ident(params["column"])
        alias = quote_ident(params.get("as") or "bin")
        mode = params.get("mode") or "equal_width"
        if mode == "custom_breaks":
            raw = (params.get("breaks") or "").strip()
            if not raw:
                raise ValueError("breaks required when mode=custom_breaks")
            try:
                points = [float(x.strip()) for x in raw.split(",") if x.strip()]
            except ValueError as e:
                raise ValueError(f"invalid breakpoints: {raw}") from e
            # Build a CASE expression: WHEN col < b1 THEN '< b1' WHEN col < b2 THEN '[b1, b2)' …
            cases: list[str] = []
            for i, p in enumerate(points):
                if i == 0:
                    cases.append(f"WHEN {col} < {p} THEN {quote_str(f'< {p}')}")
                else:
                    cases.append(
                        f"WHEN {col} < {p} THEN {quote_str(f'[{points[i - 1]}, {p})')}"
                    )
            cases.append(f"ELSE {quote_str(f'>= {points[-1]}')}")
            expr = "CASE " + " ".join(cases) + " END"
        else:
            n = int(params.get("bins") or 5)
            # Use DuckDB's ntile() over numeric ordering — equal-frequency is a
            # cheaper proxy for equal-width; for true equal-width we'd need min/max.
            # Equal-width via FLOOR((x - min) / width):
            expr = (
                "(SELECT 'bin ' || (1 + LEAST(CAST(FLOOR("
                f"({col} - mn) * {n} / NULLIF(mx - mn, 0)) AS INTEGER), {n - 1}))"
                f" FROM (SELECT MIN({col}) AS mn, MAX({col}) AS mx FROM {src}) AS __r__)"
            )
        return f"SELECT *, {expr} AS {alias} FROM {src}"

    def infer_schema(self, input_schemas, params):
        if "in" not in input_schemas:
            return {}
        s = dict(input_schemas["in"])
        s[params.get("as") or "bin"] = "string"
        return s


step = BinNumericStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
