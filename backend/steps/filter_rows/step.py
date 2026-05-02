from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, assert_safe_expr


class FilterRowsStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        predicate = assert_safe_expr(params["predicate"], kind="predicate")
        return f'SELECT * FROM {src} WHERE ({predicate})'


step = FilterRowsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
