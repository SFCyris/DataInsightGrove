"""Round a numeric column to N decimal places.

Worked example from docs/AUTHORING_GUIDE.md (Tutorial 1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


class RoundToNStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = quote_ident(params["column"])
        decimals = int(params["decimals"])
        return f"SELECT * REPLACE (ROUND({col}, {decimals}) AS {col}) FROM {src}"


step = RoundToNStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
