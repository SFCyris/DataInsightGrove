from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _resolve(raw: Any, pc) -> tuple[str | None, str | None, str | None, str | None, str | None]:
    if raw is None:
        return (None, None, None, None, None)
    s = str(raw).strip()
    if not s:
        return (None, None, None, None, None)
    # Try in order: alpha-2, alpha-3, numeric, fuzzy-search by name.
    for finder in (
        lambda v: pc.countries.get(alpha_2=v.upper()) if len(v) == 2 else None,
        lambda v: pc.countries.get(alpha_3=v.upper()) if len(v) == 3 else None,
        lambda v: pc.countries.get(numeric=v.zfill(3)) if v.isdigit() else None,
        lambda v: pc.countries.get(name=v),
        lambda v: pc.countries.get(common_name=v),
    ):
        try:
            r = finder(s)
            if r:
                return (
                    r.alpha_2,
                    r.alpha_3,
                    r.name,
                    getattr(r, "numeric", None),
                    getattr(r, "official_name", None),
                )
        except Exception:
            pass
    # Fuzzy fallback — tolerate typos.
    try:
        matches = pc.countries.search_fuzzy(s)
        if matches:
            r = matches[0]
            return (
                r.alpha_2,
                r.alpha_3,
                r.name,
                getattr(r, "numeric", None),
                getattr(r, "official_name", None),
            )
    except LookupError:
        pass
    return (None, None, None, None, None)


class CountryLookupStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import pycountry

        df = inputs["in"]
        col = params["country_column"]

        a2: list[str | None] = []
        a3: list[str | None] = []
        name: list[str | None] = []
        num: list[str | None] = []
        official: list[str | None] = []
        for raw in df[col].to_list():
            r = _resolve(raw, pycountry)
            a2.append(r[0]); a3.append(r[1]); name.append(r[2]); num.append(r[3]); official.append(r[4])

        return PolarsResult(output=df.with_columns([
            pl.Series(name="country_alpha2", values=a2),
            pl.Series(name="country_alpha3", values=a3),
            pl.Series(name="country_name", values=name),
            pl.Series(name="country_numeric", values=num),
            pl.Series(name="country_official", values=official),
        ]))


step = CountryLookupStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
