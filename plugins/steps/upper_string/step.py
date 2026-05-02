"""Hello-world DIG plugin step.

Drop this folder under `plugins/steps/<id>/` and DIG auto-discovers it on
backend startup. The folder must contain `manifest.json` (validated against
shared/schemas/step-manifest.schema.json) and this `step.py` exporting
`step` (an instance of dig.engine.step.Step).

See `docs/PLUGIN_AUTHORING.md` for the full reference.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


class UpperStringStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        col = quote_ident(params["column"])
        # DuckDB's REPLACE clause on SELECT * keeps every other column intact.
        return f"SELECT * REPLACE (UPPER({col}) AS {col}) FROM {src}"


step = UpperStringStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
