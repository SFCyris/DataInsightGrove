from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


class SortRowsStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        by = params.get("by") or []
        if not by:
            return f"SELECT * FROM {src}"
        order_clauses = []
        for item in by:
            col = quote_ident(item["column"])
            direction = (item.get("direction") or "asc").upper()
            if direction not in ("ASC", "DESC"):
                direction = "ASC"
            order_clauses.append(f"{col} {direction}")
        order_sql = ", ".join(order_clauses)
        return f"SELECT * FROM {src} ORDER BY {order_sql}"


step = SortRowsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
