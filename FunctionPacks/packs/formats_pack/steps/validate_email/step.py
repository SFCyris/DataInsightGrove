from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ValidateEmailStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from email_validator import validate_email, EmailNotValidError

        df = inputs["in"]
        col = params["email_column"]
        check_dns = bool(params.get("check_dns", False))
        prefix = params.get("output_column", "email")

        valid: list[bool] = []
        normalized: list[str | None] = []
        for raw in df[col].to_list():
            if raw is None or raw == "":
                valid.append(False)
                normalized.append(None)
                continue
            try:
                result = validate_email(str(raw), check_deliverability=check_dns)
                valid.append(True)
                normalized.append(result.normalized.lower())
            except EmailNotValidError:
                valid.append(False)
                normalized.append(None)

        return PolarsResult(output=df.with_columns([
            pl.Series(name=f"{prefix}_valid", values=valid),
            pl.Series(name=f"{prefix}_normalized", values=normalized),
        ]))


step = ValidateEmailStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
