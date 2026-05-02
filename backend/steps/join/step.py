from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


class JoinStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        left = inputs["left"]
        right = inputs["right"]
        how = (params.get("how") or "inner").upper()
        if how not in ("INNER", "LEFT", "RIGHT", "FULL", "CROSS"):
            how = "INNER"
        pairs = params.get("on") or []
        if how == "CROSS":
            return f"SELECT l.*, r.* FROM {left} AS l CROSS JOIN {right} AS r"
        if not pairs:
            # Empty `on` would silently produce a cartesian product (often
            # OOMs the executor on real data). Force the user to either fill
            # in keys or pick how="cross" explicitly. P1 review finding.
            raise ValueError(
                "join: no key columns specified. Set at least one (left, right) "
                "pair in 'on', or set how='cross' for an explicit cross join."
            )
        on_clause = " AND ".join(
            f"l.{quote_ident(p['left'])} = r.{quote_ident(p['right'])}"
            for p in pairs
        )
        # Use SELECT * which DuckDB allows from both tables (right side gets _1 suffix on collisions).
        return f"SELECT l.*, r.* FROM {left} AS l {how} JOIN {right} AS r ON {on_clause}"

    def infer_schema(self, input_schemas, params):
        left = input_schemas.get("left", {})
        right = input_schemas.get("right", {})
        out = dict(left)
        for k, v in right.items():
            if k in out:
                out[f"{k}_1"] = v
            else:
                out[k] = v
        return out


step = JoinStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
