"""add_runtime_column — append a column whose value is rendered from a `{{ template }}`.

Templates resolve against the run's variable namespace (today, now, run_id,
pipeline_name, vars.*, plus filters like `strftime`, `replace`, `default`).
The template is rendered ONCE per run; every row in the output frame
receives the same rendered value. See `backend/dig/engine/templates.py`.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step
from dig.engine.templates import TemplateError, build_namespace, render_value


# Datetime is UTC-aware so a coerced `{{ now }}` (which renders as
# `2026-05-11T14:23:07Z` — tz-aware) doesn't blow up against Polars'
# default tz-naive Datetime. Round-2 UX-tester finding: previously
# `pl.Datetime` (tz-naive) + tz-aware Python value made the whole
# variables demo crash on first click.
_TYPE_MAP: dict[str, pl.DataType] = {
    "string":   pl.Utf8,
    "integer":  pl.Int64,
    "double":   pl.Float64,
    "boolean":  pl.Boolean,
    "date":     pl.Date,
    "datetime": pl.Datetime(time_zone="UTC"),
}


def _coerce(rendered: str, column_type: str) -> Any:
    """Convert the rendered string to the target type. Empty → None."""
    if not rendered:
        return None
    if column_type == "string":
        return rendered
    if column_type == "integer":
        return int(rendered)
    if column_type == "double":
        return float(rendered)
    if column_type == "boolean":
        v = rendered.strip().lower()
        if v in {"true", "1", "yes"}:
            return True
        if v in {"false", "0", "no"}:
            return False
        raise ValueError(f"add_runtime_column: cannot coerce {rendered!r} to boolean")
    if column_type == "date":
        return date.fromisoformat(rendered)
    if column_type == "datetime":
        # `{{ now }}` renders as `2026-05-11T14:23:07Z` (tz-aware UTC).
        # Convert to a tz-aware datetime; Polars' tz=UTC dtype above
        # accepts it directly. If the input is naive (e.g. user-supplied
        # `vars.x` without offset), assume UTC so we never silently get
        # a different wall-clock from the rendered template.
        from datetime import timezone as _tz
        dt = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz.utc)
        return dt
    raise ValueError(f"add_runtime_column: unknown columnType {column_type!r}")


class AddRuntimeColumnStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        name = params["name"]
        template = params["template"]
        column_type = params.get("columnType", "string")
        position = params.get("position", "end")

        # Build a per-run namespace. The executor renders pipeline-level
        # path templates with the same shape (see _render_pipeline_paths in
        # executor.py); cell-content rendering here uses the same builder
        # so the variable surface stays uniform — pipeline_name + vars.*
        # included so docs/VARIABLES.md examples like
        # `{{ pipeline_name }}` and `{{ vars.region }}` actually resolve.
        ns = build_namespace(
            run_id=(ctx.run_id if ctx else ""),
            pipeline_id=(ctx.pipeline_id if ctx else ""),
            pipeline_name=(ctx.pipeline_name if ctx else ""),
            node_id=(ctx.node_id if ctx else ""),
            user_vars=(ctx.pipeline_variables if ctx else None),
            env="run",
        )
        try:
            rendered = render_value(template, ns)
        except TemplateError as te:
            raise ValueError(f"add_runtime_column: {te}") from te

        coerced = _coerce(rendered, column_type)
        target_dtype = _TYPE_MAP[column_type]
        new_col = pl.Series(name, [coerced] * df.height, dtype=target_dtype)

        if position == "start":
            out = df.with_columns(new_col).select([name, *df.columns])
        else:
            out = df.with_columns(new_col)
        return PolarsResult(output=out)


step = AddRuntimeColumnStep(
    json.loads((Path(__file__).parent / "manifest.json").read_text())
)
