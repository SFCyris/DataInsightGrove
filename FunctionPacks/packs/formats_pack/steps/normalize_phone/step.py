from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class NormalizePhoneStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        import phonenumbers

        df = inputs["in"]
        col = params["phone_column"]
        default_country = (params.get("default_country") or "US").upper()
        out_col = params.get("output_column", "phone_e164")

        normalized: list[str | None] = []
        valid: list[bool] = []
        for raw in df[col].to_list():
            if raw is None or raw == "":
                normalized.append(None)
                valid.append(False)
                continue
            try:
                parsed = phonenumbers.parse(str(raw), default_country)
                ok = phonenumbers.is_valid_number(parsed)
                if ok:
                    normalized.append(phonenumbers.format_number(
                        parsed, phonenumbers.PhoneNumberFormat.E164,
                    ))
                else:
                    normalized.append(None)
                valid.append(ok)
            except phonenumbers.NumberParseException:
                normalized.append(None)
                valid.append(False)

        return PolarsResult(output=df.with_columns([
            pl.Series(name=out_col, values=normalized),
            pl.Series(name=f"{out_col}_valid", values=valid),
        ]))


step = NormalizePhoneStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
