from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _resolve(raw: Any, pc) -> tuple[str | None, str | None, str | None]:
    if raw is None:
        return (None, None, None)
    s = str(raw).strip()
    if not s:
        return (None, None, None)
    for finder in (
        lambda v: pc.currencies.get(alpha_3=v.upper()) if len(v) == 3 else None,
        lambda v: pc.currencies.get(numeric=v.zfill(3)) if v.isdigit() else None,
        lambda v: pc.currencies.get(name=v),
    ):
        try:
            r = finder(s)
            if r:
                return (r.alpha_3, r.name, getattr(r, "numeric", None))
        except Exception:
            pass
    return (None, None, None)


class CurrencyLookupStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import pycountry

        df = inputs["in"]
        col = params["currency_column"]

        code: list[str | None] = []
        name: list[str | None] = []
        num: list[str | None] = []
        for raw in df[col].to_list():
            r = _resolve(raw, pycountry)
            code.append(r[0]); name.append(r[1]); num.append(r[2])

        return PolarsResult(output=df.with_columns([
            pl.Series(name="currency_code", values=code),
            pl.Series(name="currency_name", values=name),
            pl.Series(name="currency_numeric", values=num),
        ]))


step = CurrencyLookupStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
