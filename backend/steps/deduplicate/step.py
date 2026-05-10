from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


class DeduplicateStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        key = params.get("key") or []
        if not key:
            return f"SELECT DISTINCT * FROM {src}"
        # DISTINCT ON returns first row per key group (DuckDB syntax).
        cols = ", ".join(quote_ident(c) for c in key)
        return f"SELECT DISTINCT ON ({cols}) * FROM {src}"


step = DeduplicateStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
