"""Compile a pipeline document to a standalone Python (Polars) script.

The output is a self-contained script that:
  - imports polars
  - reads each dataset as a LazyFrame
  - applies the equivalent transform per node
  - writes outputs to the configured sinks (or to <output_name>.parquet by default)

This is "show as Python" — pedagogical, copy-pastable. It deliberately uses
Polars (not DuckDB SQL) so a user gets a fluent, idiomatic dataframe script.

Coverage is best-effort: unsupported steps emit a clearly marked
`# TODO: unsupported step '<id>' — drop-in your own transform here` comment
with the original params printed for the reader to pick up.
"""

from __future__ import annotations

from textwrap import dedent
from typing import Any

from dig.engine.dag import topo_sort, validate
from dig.engine.pipeline import Pipeline


def _q(s: str) -> str:
    return repr(s)


def _polars_for_node(step_id: str, params: dict[str, Any], inputs: dict[str, str]) -> str:
    """Best-effort Polars expression for a single node.

    Returns a Python expression that, given variables already bound to upstream
    LazyFrames, produces this node's LazyFrame.
    """
    if step_id == "filter_rows":
        # The predicate is SQL — for a Python script, surface it as a SQL passthrough
        # via .sql_context. Polars supports running SQL queries on a frame.
        pred = params.get("predicate", "true")
        return (
            f"pl.SQLContext(t={inputs['in']}).execute("
            f"f'SELECT * FROM t WHERE ({pred})').lazy()"
        )
    if step_id == "select_columns":
        cols = params.get("columns") or []
        if not cols:
            return inputs["in"]
        return f"{inputs['in']}.select({cols!r})"
    if step_id == "reorder_columns":
        order = params.get("order") or []
        if not order:
            return inputs["in"]
        # Mirrors the SQL `SELECT a, b, * EXCLUDE (a, b) FROM t` semantic:
        # listed columns first (in the user's order), then any remaining
        # input columns (in their original order). pl.exclude() handles the
        # auto-append so new upstream columns flow through without requiring
        # the user to update the step.
        col_exprs = ", ".join(f"pl.col({c!r})" for c in order)
        return (
            f"{inputs['in']}.select([{col_exprs}, pl.exclude({order!r})])"
        )
    if step_id == "sort_rows":
        # Manifest name is `by`, items are {column, direction: asc|desc}.
        sort_by = params.get("by") or []
        cols = [s.get("column") for s in sort_by if s.get("column")]
        desc = [(s.get("direction") or "asc").lower() == "desc" for s in sort_by if s.get("column")]
        if not cols:
            return inputs["in"]
        return f"{inputs['in']}.sort(by={cols!r}, descending={desc!r})"
    if step_id == "rename_columns":
        mapping = {m["from"]: m["to"] for m in (params.get("mapping") or [])}
        return f"{inputs['in']}.rename({mapping!r})"
    if step_id == "cast_type":
        casts = params.get("casts") or []
        type_map = {c["column"]: c["to"] for c in casts}
        if not type_map:
            return inputs["in"]
        # Polars cast names are slightly different — keep this readable rather
        # than perfectly mapped.
        return (
            f"{inputs['in']}.with_columns(["
            + ", ".join(f"pl.col({c!r}).cast(pl.{t.capitalize()})" for c, t in type_map.items())
            + "])"
        )
    if step_id == "derive_column":
        new = params.get("name") or "new_col"
        expr = params.get("expression") or "0"
        return (
            f"pl.SQLContext(t={inputs['in']}).execute("
            f"f'SELECT *, ({expr}) AS \"{new}\" FROM t').lazy()"
        )
    if step_id == "convert_units":
        # Linear conversion to a category-base unit:
        #   x_b = ((x_a * factor_a + offset_a) - offset_b) / factor_b
        # All non-temperature categories have offset=0 so the constants
        # collapse to a single multiplier; temperature is the only family
        # that needs the full form.
        from dig.engine.unit_conversions import conversion_factors
        col = params.get("column") or ""
        from_u = params.get("from_unit") or ""
        to_u = params.get("to_unit") or ""
        out = (params.get("output_column") or "").strip() or col
        try:
            fa, oa, fb, ob = conversion_factors(from_u, to_u)
        except ValueError:
            # Bad params — emit a TODO comment so the user notices when
            # they run the exported script. Don't crash codegen.
            return f"{inputs['in']}  # TODO: convert_units {from_u!r} -> {to_u!r} (unit pair invalid)"
        if oa == 0.0 and ob == 0.0:
            ratio = fa / fb
            if ratio == 1.0:
                expr = f"pl.col({col!r})"
            else:
                expr = f"(pl.col({col!r}) * {ratio!r})"
        else:
            expr = (
                f"((pl.col({col!r}) * {fa!r} + {oa!r}) - {ob!r}) / {fb!r}"
            )
        return f"{inputs['in']}.with_columns({expr}.alias({out!r}))"
    if step_id == "add_column":
        # Build a typed-default expression. Polars accepts pl.lit(...) for
        # the literal and .cast(pl.Type) to coerce — same UX as the SQL
        # CAST in step.py. NULL when the user left defaultValue blank.
        new = params.get("name") or "new_col"
        col_type = (params.get("columnType") or "string").lower()
        default = params.get("defaultValue")
        position = (params.get("position") or "end").lower()
        reference = params.get("reference")
        pl_type = {
            "integer": "Int64", "double": "Float64", "string": "Utf8",
            "boolean": "Boolean", "date": "Date", "datetime": "Datetime",
        }.get(col_type, "Utf8")
        if default is None or default == "":
            value_expr = f"pl.lit(None).cast(pl.{pl_type})"
        else:
            value_expr = f"pl.lit({default!r}).cast(pl.{pl_type})"
        # We can construct the full select list when position is start or
        # end — those don't depend on the upstream schema. For before/after
        # we'd need to know the column order at codegen time (we don't), so
        # fall back to with_columns (appends at end) plus an inline note for
        # the user to splice the column manually if exact placement matters.
        if position == "start":
            return (
                f"{inputs['in']}.with_columns({value_expr}.alias({new!r}))"
                f".select([{new!r}] + [c for c in {inputs['in']}.collect_schema().names() if c != {new!r}])"
            )
        if position in ("before", "after") and reference:
            return (
                f"{inputs['in']}.with_columns({value_expr}.alias({new!r}))  "
                f"# ⚠️  Position={position!r} {reference!r} — Polars codegen "
                f"appends at end; reorder manually if exact placement matters."
            )
        # default: end
        return f"{inputs['in']}.with_columns({value_expr}.alias({new!r}))"
    if step_id == "math_equation":
        # Same shape as derive_column — the equation runs through SQLContext.
        # Position is best-effort here: start works without schema; before/
        # after fall back to end with an inline comment.
        new = params.get("resultName") or "result"
        expr = params.get("equation") or "0"
        position = (params.get("position") or "end").lower()
        reference = params.get("reference")
        derived = (
            f"pl.SQLContext(t={inputs['in']}).execute("
            f"f'SELECT *, ({expr}) AS \"{new}\" FROM t').lazy()"
        )
        if position == "start":
            return (
                f"({derived}).select(["
                f"{new!r}] + [c for c in ({derived}).collect_schema().names() if c != {new!r}])"
            )
        if position in ("before", "after") and reference:
            return (
                f"{derived}  # ⚠️  Position={position!r} {reference!r} — "
                f"Polars codegen appends at end; reorder manually if exact "
                f"placement matters."
            )
        return derived
    if step_id == "deduplicate":
        subset = params.get("columns") or None
        keep = params.get("keep", "first")
        if subset:
            return f"{inputs['in']}.unique(subset={subset!r}, keep={keep!r})"
        return f"{inputs['in']}.unique(keep={keep!r})"
    if step_id == "sample_rows":
        n = params.get("n")
        frac = params.get("fraction")
        seed = params.get("seed", 42)
        if n is not None:
            return f"{inputs['in']}.collect().sample(n={int(n)}, seed={int(seed)}).lazy()"
        if frac is not None:
            return f"{inputs['in']}.collect().sample(fraction={float(frac)}, seed={int(seed)}).lazy()"
        return inputs["in"]
    if step_id == "join":
        on = params.get("on") or []
        left_on = [c["left"] for c in on]
        right_on = [c["right"] for c in on]
        how = params.get("how") or "inner"
        return (
            f"{inputs['left']}.join({inputs['right']}, "
            f"left_on={left_on!r}, right_on={right_on!r}, how={how!r})"
        )
    if step_id == "union":
        srcs = list(inputs.values())
        return f"pl.concat([{', '.join(srcs)}], how='diagonal_relaxed')"
    if step_id == "group_aggregate":
        # Step manifest names: groupBy + aggregates (NOT by + aggregations).
        # Mismatch here meant exported .py was broken for every group_aggregate
        # step (P1 review finding). Same shape used in backend/steps/group_aggregate/step.py.
        by = params.get("groupBy") or []
        aggs = params.get("aggregates") or []
        agg_exprs = []
        for a in aggs:
            col = a.get("column")
            fn = a.get("fn", "sum")
            alias = a.get("as") or (f"{col}_{fn}" if col else f"{fn}_value")
            if col is None and fn == "count":
                agg_exprs.append(f"pl.len().alias({alias!r})")
            else:
                agg_exprs.append(f"pl.col({col!r}).{fn}().alias({alias!r})")
        return f"{inputs['in']}.group_by({by!r}).agg([{', '.join(agg_exprs)}])"
    # NOTE: `rename_columns`, `cast_type`, `deduplicate`, `sample_rows` are
    # all handled above. A second copy of these branches used to live here
    # with parameter names that drifted from the live step manifests
    # (`column`/`targetType` instead of `casts`); they were unreachable but
    # would silently activate via reordering or paste — removed to avoid
    # the trap.
    if step_id == "rolling":
        # Limited form — single window. Multiple windows not codegen'd.
        wins = params.get("windows") or []
        if wins:
            w = wins[0]
            col = w.get("column")
            fn = w.get("fn", "mean")
            window = w.get("window", 7)
            alias = w.get("as") or f"{col}_rolling"
            return (
                f"{inputs['in']}.with_columns("
                f"pl.col({col!r}).rolling_{fn}(window_size={window!r}).alias({alias!r}))"
            )
    if step_id == "export_to_file":
        fmt = (params.get("format") or "csv").lower()
        path = params.get("path") or f"{step_id}.{fmt}"
        method = {"csv": "write_csv", "parquet": "write_parquet", "json": "write_json",
                  "ndjson": "write_ndjson"}.get(fmt, "write_csv")
        return f"{inputs['in']}.collect().{method}({_q(path)})  # writes to disk"
    # Steps with no Python codegen — emit a stub the user can fill in.
    return (
        f"{inputs['in']}  "
        f"# ⚠️  Step '{step_id}' has no Python codegen yet — "
        f"fill in the equivalent transform here. Params: {params!r}"
    )


# Steps known to have full Python codegen — used by the warning list.
_SUPPORTED_STEPS = frozenset({
    "filter_rows", "select_columns", "reorder_columns", "sort_rows",
    "rename_columns", "cast_type", "derive_column", "add_column",
    "math_equation", "deduplicate", "sample_rows", "rolling", "join",
    "union", "group_aggregate", "export_to_file",
})


def unsupported_steps(p: Pipeline) -> list[str]:
    """Return the set of step ids in this pipeline that codegen can't handle.

    Used by the API to surface a clear warning before download — the user
    sees "9 steps in your pipeline can't be exported as Python (PCA, k-means,
    forecast, …)" instead of getting a silently-broken .py file.
    """
    out: list[str] = []
    for n in p.nodes:
        if n.step not in _SUPPORTED_STEPS and n.step not in out:
            out.append(n.step)
    return out


def _dataset_loader(spec) -> str:
    if spec.connector == "csv":
        return f"pl.scan_csv({_q(spec.uri.removeprefix('file://'))})"
    if spec.connector == "parquet":
        return f"pl.scan_parquet({_q(spec.uri.removeprefix('file://'))})"
    if spec.connector == "excel":
        return f"pl.read_excel({_q(spec.uri.removeprefix('file://'))}).lazy()"
    return f"pl.scan_parquet({_q(spec.uri.removeprefix('file://'))})  # TODO: unsupported connector {spec.connector!r}"


def compile_to_python(p: Pipeline) -> str:
    """Compile pipeline to a standalone Polars script (str)."""
    validate(p)
    sorted_nodes = topo_sort(p)

    lines: list[str] = []
    lines.append('"""Auto-generated by DataInsightGrove — Polars equivalent of pipeline:')
    lines.append(f"   {p.name} ({p.id})")
    lines.append('"""')
    lines.append("")
    lines.append("from pathlib import Path")
    lines.append("import polars as pl")
    lines.append("")
    lines.append("# ---- Datasets ----")
    for d in p.datasets:
        lines.append(f"{_safe_var(d.id)} = {_dataset_loader(d)}")
    lines.append("")
    lines.append("# ---- Transforms ----")
    for node in sorted_nodes:
        inputs = {port: _safe_var(ref.ref) for port, ref in node.inputs.items()}
        rhs = _polars_for_node(node.step, node.params, inputs)
        lines.append(f"{_safe_var(node.id)} = {rhs}")
    lines.append("")
    lines.append("# ---- Outputs ----")
    if not p.outputs:
        if sorted_nodes:
            last = sorted_nodes[-1]
            lines.append(f"_result = {_safe_var(last.id)}.collect()")
            lines.append("print(_result.head())")
    for o in p.outputs:
        var = _safe_var(o.from_.ref)
        if o.sink and o.sink.connector == "parquet":
            target = o.sink.uri.removeprefix("file://")
            lines.append(f"{var}.collect().write_parquet({_q(target)}, compression='zstd')")
        elif o.sink and o.sink.connector == "csv":
            target = o.sink.uri.removeprefix("file://")
            lines.append(f"{var}.collect().write_csv({_q(target)})")
        else:
            lines.append(
                f"{var}.collect().write_parquet({_q(f'{o.name}.parquet')}, compression='zstd')"
            )
    return "\n".join(lines) + "\n"


def _safe_var(ref: str) -> str:
    """Turn an arbitrary reference id into a valid Python identifier."""
    return "df_" + "".join(c if c.isalnum() else "_" for c in ref)


def compile_to_notebook(p: Pipeline) -> dict[str, Any]:
    """Compile pipeline to a Jupyter notebook (.ipynb format) document.

    Returns a dict matching the nbformat v4 spec — caller is responsible for
    JSON-serializing it to disk or the wire.
    """
    cells: list[dict[str, Any]] = []

    def md(text: str) -> None:
        cells.append({
            "cell_type": "markdown",
            "metadata": {},
            "source": text + "\n",
        })

    def code(source: str) -> None:
        cells.append({
            "cell_type": "code",
            "metadata": {},
            "outputs": [],
            "execution_count": None,
            "source": source + "\n",
        })

    md(f"# {p.name}\n\n_Auto-generated from DataInsightGrove pipeline `{p.id}`._\n\n"
       "This notebook reproduces the pipeline using **Polars**. Each cell maps to "
       "one node of the pipeline, in topological order.")

    code("from pathlib import Path\nimport polars as pl")

    md("## Datasets")
    for d in p.datasets:
        code(f"{_safe_var(d.id)} = {_dataset_loader(d)}\n{_safe_var(d.id)}.head().collect()")

    sorted_nodes = topo_sort(p)
    if sorted_nodes:
        md("## Transforms")
    for node in sorted_nodes:
        inputs = {port: _safe_var(ref.ref) for port, ref in node.inputs.items()}
        rhs = _polars_for_node(node.step, node.params, inputs)
        ui_label = (node.ui.label if node.ui and node.ui.label else node.id)
        md(f"### {ui_label}\n\n_Step: `{node.step}`_  ·  Node id: `{node.id}`")
        code(f"{_safe_var(node.id)} = {rhs}\n{_safe_var(node.id)}.head().collect()")

    if p.outputs:
        md("## Outputs")
        for o in p.outputs:
            var = _safe_var(o.from_.ref)
            if o.sink and o.sink.connector == "parquet":
                target = o.sink.uri.removeprefix("file://")
                code(f"{var}.collect().write_parquet({_q(target)}, compression='zstd')")
            elif o.sink and o.sink.connector == "csv":
                target = o.sink.uri.removeprefix("file://")
                code(f"{var}.collect().write_csv({_q(target)})")
            else:
                code(
                    f"{var}.collect().write_parquet({_q(f'{o.name}.parquet')}, "
                    "compression='zstd')"
                )

    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "kernelspec": {"name": "python3", "display_name": "Python 3"},
            "language_info": {"name": "python"},
            "dig_pipeline_id": p.id,
            "dig_pipeline_name": p.name,
        },
        "cells": cells,
    }
