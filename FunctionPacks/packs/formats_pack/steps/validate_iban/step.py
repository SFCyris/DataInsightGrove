from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class ValidateIbanStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from schwifty import IBAN
        from schwifty.exceptions import SchwiftyException

        df = inputs["in"]
        col = params["iban_column"]

        valid: list[bool] = []
        country: list[str | None] = []
        bank: list[str | None] = []
        account: list[str | None] = []
        for raw in df[col].to_list():
            if raw is None or raw == "":
                valid.append(False)
                country.append(None)
                bank.append(None)
                account.append(None)
                continue
            try:
                i = IBAN(str(raw))
                valid.append(True)
                country.append(i.country_code)
                bank.append(i.bank_code or None)
                account.append(i.account_code)
            except (SchwiftyException, ValueError):
                valid.append(False)
                country.append(None)
                bank.append(None)
                account.append(None)

        return PolarsResult(output=df.with_columns([
            pl.Series(name="iban_valid", values=valid),
            pl.Series(name="iban_country", values=country),
            pl.Series(name="iban_bank_code", values=bank),
            pl.Series(name="iban_account", values=account),
        ]))


step = ValidateIbanStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
