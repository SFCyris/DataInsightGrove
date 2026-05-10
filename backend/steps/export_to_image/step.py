"""Render a Polars DataFrame as a static image (PNG / SVG).

Uses matplotlib + seaborn — both stable, widely-installed, and produce
publication-quality output without the bundle weight of plotly/bokeh.

Chart picking ('auto' kind) is deliberately simple and explicit:
  - 1 numeric column   → histogram
  - 1 categorical col  → bar chart of value counts (top N)
  - 2 num × num        → scatter
  - 2 cat × num        → bar (mean per category)
  - 3 num × num × num  → 3D scatter
  - 3 with one cat key → heatmap (pivot)

The `kind` param overrides this. Frontends can read step.params.kind == 'auto'
and offer the explicit alternatives, or expose a dropdown.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _is_numeric(dtype: pl.DataType) -> bool:
    name = str(dtype).lower()
    return any(t in name for t in ("int", "float", "double", "decimal"))


def _is_temporal(dtype: pl.DataType) -> bool:
    name = str(dtype).lower()
    return "date" in name or "time" in name


def _pick_kind(df: pl.DataFrame, x: str | None, y: str | None, z: str | None, value: str | None) -> str:
    """Heuristic chart picker for kind='auto'.

    Looks at how many of (x, y, z, value) the user actually filled in plus the
    column types to pick a sensible default.
    """
    cols = [c for c in (x, y, z, value) if c]
    schema = df.schema

    # 0 axes filled but data is 1-col → distribution of that col
    if not cols and df.width >= 1:
        only = df.columns[0]
        return "histogram" if _is_numeric(schema[only]) else "bar_counts"

    if len(cols) == 1:
        c = cols[0]
        return "histogram" if _is_numeric(schema[c]) else "bar_counts"

    if len(cols) == 2:
        a, b = cols
        a_num = _is_numeric(schema[a])
        b_num = _is_numeric(schema[b])
        if a_num and b_num:
            return "scatter"
        if (a_num and not b_num) or (not a_num and b_num):
            return "bar_counts"  # treat as cat × num — bar of agg
        return "bar_counts"

    if len(cols) >= 3:
        if x and y and z and all(_is_numeric(schema[c]) for c in (x, y, z)):
            return "scatter3d"
        if x and y and value:
            return "heatmap"
        return "scatter"

    return "histogram"


class ExportToImageStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        # Lazy imports so the rest of the engine doesn't need matplotlib at startup.
        import matplotlib
        matplotlib.use("Agg")  # no display server
        import matplotlib.pyplot as plt
        import seaborn as sns
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401  (registers 3d projection)

        df = inputs["in"]
        kind = (params.get("kind") or "auto").lower()

        # Multi-y aliases in the manifest (visibleWhen-gated) all map to the
        # same logical 'y' axis — collapse to one for the rendering code.
        y = params.get("y") or params.get("y2") or params.get("y3") or params.get("y4") or params.get("y5")
        x = params.get("x")
        z = params.get("z")
        value = params.get("value")

        if kind == "auto":
            kind = _pick_kind(df, x, y, z, value)

        # Sample if needed — matplotlib chokes well below a million points.
        max_points = int(params.get("max_points") or 50_000)
        if df.height > max_points:
            df = df.sample(n=max_points, seed=42)

        title = params.get("title") or self.id

        # Output path. Filename uses ``ctx.node_id`` (per-pipeline DAG
        # identifier), NOT ``self.id`` (the step-class id, shared by every
        # ``export_to_image`` node in the pipeline). With self.id, two
        # chart nodes in the same pipeline silently overwrote each other's
        # PNG, AND the editor's preview-step path showed the WRONG chart
        # when the user switched chart nodes rapidly — both the previous
        # node's preview-step response and the new one were served by
        # FastAPI's FileResponse from the same physical file, so the late
        # writer's bytes ended up in the early reader's HTTP response.
        # Falls back to ``self.id`` when ctx is missing (unit tests).
        path_param = (params.get("path") or "").strip()
        fmt = (params.get("format") or "png").lower()
        if path_param:
            out_path = Path(path_param).expanduser()
            if not out_path.is_absolute() and ctx is not None:
                out_path = ctx.out_dir / out_path
        else:
            base = ctx.out_dir if ctx is not None else Path.cwd()
            stem = (ctx.node_id if ctx is not None and ctx.node_id else self.id)
            out_path = base / f"{stem}.{fmt}"
        if out_path.suffix == "":
            out_path = out_path.with_suffix(f".{fmt}")
        out_path = out_path.resolve()
        # Path-traversal scoping: a malicious pipeline doc with
        # ``path=/tmp/pwn.png`` (or `..` segments) would otherwise let
        # any authenticated user write arbitrary PNG bytes anywhere the
        # backend can reach. Confine to the run output directory.
        # Same shape as ``export_to_file``'s ``DIG_EXPORT_ALLOW_ABSOLUTE``
        # escape hatch — set deliberately on a trusted single-user host.
        import os as _os
        if ctx is not None and _os.environ.get("DIG_EXPORT_ALLOW_ABSOLUTE") != "1":
            base_resolved = Path(ctx.out_dir).resolve()
            try:
                out_path.relative_to(base_resolved)
            except ValueError as e:
                raise ValueError(
                    f"export_to_image: refusing to write outside the run output directory "
                    f"(got {out_path}). Set DIG_EXPORT_ALLOW_ABSOLUTE=1 to override on a "
                    f"trusted host."
                ) from e
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Figure setup
        width = int(params.get("width") or 900)
        height = int(params.get("height") or 600)
        dpi = int(params.get("dpi") or 144)

        # Preview-mode DPI cap. Print-quality DPIs (300+) rendered at
        # the small preview-pane size produce labels that look oversized
        # because the high-density raster gets scaled down to fit. The
        # ✦live editor preview✦ (ctx.run_id == "__preview") caps DPI
        # at ~144 (≈ Retina) which is plenty for screen viewing. Full
        # backend Runs (real run_id) honour the user's DPI as-set so
        # exports stay print-quality.
        if ctx is not None and getattr(ctx, "run_id", None) == "__preview":
            dpi = min(dpi, 144)

        fig_w = width / dpi
        fig_h = height / dpi

        # Font / line / marker scaling — auto-pick seaborn context from
        # figure dimensions when the user hasn't set `font_scale`.
        # Seaborn contexts ladder coherently: 'paper' < 'notebook' <
        # 'talk' < 'poster' — each scales fonts AND axis line widths
        # AND legend marker sizes together so the chart reads well at
        # its target size. Hardcoded "notebook" looked huge for small
        # previews and tiny for large exports; auto fixes both ends.
        font_scale_override = params.get("font_scale")
        if font_scale_override:
            try:
                sns.set_theme(style="whitegrid", font_scale=float(font_scale_override))
            except (TypeError, ValueError):
                sns.set_theme(style="whitegrid", context="notebook")
        else:
            smallest_dim = min(width, height)
            if smallest_dim < 500:
                ctx_name = "paper"      # dense thumbnails
            elif smallest_dim < 1100:
                ctx_name = "notebook"   # default editor previews + standard exports
            else:
                ctx_name = "talk"       # poster-size renders
            sns.set_theme(style="whitegrid", context=ctx_name)

        if kind == "scatter3d":
            fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi)
            ax = fig.add_subplot(111, projection="3d")
            self._render_scatter3d(ax, df, x, y, z, value)
        else:
            fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
            renderer = {
                "histogram":  self._render_histogram,
                "bar_counts": self._render_bar_counts,
                "scatter":    self._render_scatter,
                "line":       self._render_line,
                "hexbin":     self._render_hexbin,
                "heatmap":    self._render_heatmap,
            }.get(kind)
            if renderer is None:
                plt.close(fig)
                raise ValueError(f"export_to_image: unknown kind '{kind}'")
            renderer(ax, df, x, y, value)

        ax.set_title(title)
        fig.tight_layout()

        if fmt == "svg":
            fig.savefig(out_path, format="svg", bbox_inches="tight")
        else:
            fig.savefig(out_path, format="png", dpi=dpi, bbox_inches="tight")
        plt.close(fig)

        return PolarsResult(
            output=df,
            artifacts=[{
                "kind": "image",
                "format": fmt,
                "path": str(out_path),
                "width": width,
                "height": height,
                "chart": kind,
                "rows_plotted": df.height,
                "title": title,
            }],
        )

    # ---- renderers ----

    def _render_histogram(self, ax, df, x, y, value):
        col = x or value or y or df.columns[0]
        import seaborn as sns
        sns.histplot(df.get_column(col).to_numpy(), kde=True, ax=ax)
        ax.set_xlabel(col)
        ax.set_ylabel("count")

    def _render_bar_counts(self, ax, df, x, y, value):
        col = x or y or value or df.columns[0]
        counts = (
            df.group_by(col).len()
              .sort("len", descending=True)
              .head(20)
        )
        labels = counts.get_column(col).cast(pl.Utf8).to_list()
        vals = counts.get_column("len").to_list()
        ax.barh(labels[::-1], vals[::-1])
        ax.set_xlabel("count")
        ax.set_ylabel(col)

    def _render_scatter(self, ax, df, x, y, value):
        if not x or not y:
            raise ValueError("scatter needs both x and y")
        xs = df.get_column(x).to_numpy()
        ys = df.get_column(y).to_numpy()
        kw = {}
        if value and value in df.columns:
            sizes = df.get_column(value).to_numpy()
            kw["s"] = _normalise_sizes(sizes)
            kw["c"] = sizes
            kw["cmap"] = "viridis"
            kw["alpha"] = 0.7
        else:
            kw["alpha"] = 0.6
        sc = ax.scatter(xs, ys, **kw)
        ax.set_xlabel(x); ax.set_ylabel(y)
        _apply_axis_locator(ax)
        if "c" in kw:
            cb = ax.figure.colorbar(sc, ax=ax)
            cb.set_label(value)

    def _render_line(self, ax, df, x, y, value):
        if not x or not y:
            raise ValueError("line needs both x and y")
        sub = df.sort(x)
        ax.plot(sub.get_column(x).to_numpy(), sub.get_column(y).to_numpy())
        ax.set_xlabel(x); ax.set_ylabel(y)
        _apply_axis_locator(ax)

    def _render_hexbin(self, ax, df, x, y, value):
        if not x or not y:
            raise ValueError("hexbin needs both x and y")
        ax.hexbin(df.get_column(x).to_numpy(), df.get_column(y).to_numpy(), gridsize=40, cmap="Greens")
        ax.set_xlabel(x); ax.set_ylabel(y)
        _apply_axis_locator(ax)

    def _render_heatmap(self, ax, df, x, y, value):
        if not (x and y and value):
            raise ValueError("heatmap needs x, y and value")
        import numpy as np
        import seaborn as sns
        # Sort the Y index when it's a numeric column so the thinned
        # tick labels span min→max in order, not row order. Same for
        # the X column. For categorical columns we leave the user's
        # ordering alone (alphabetising "Q1, Q2, Q3, Q4" or region
        # names would be wrong).
        df_for_pivot = df
        if _is_numeric(df.schema[y]):
            df_for_pivot = df_for_pivot.sort(y)
        if _is_numeric(df.schema[x]):
            df_for_pivot = df_for_pivot.sort(x)
        pivot = df_for_pivot.pivot(
            values=value, index=y, on=x, aggregate_function="mean",
        ).fill_null(0)
        # Convert to a NumPy array + extract row/col labels for seaborn.
        labels_y = pivot.get_column(y).cast(pl.Utf8).to_list()
        cols_x = [c for c in pivot.columns if c != y]
        # Sort pivot columns numerically when X is numeric (Polars
        # pivot's column order follows first-seen, not value order).
        if _is_numeric(df.schema[x]):
            try:
                cols_x = sorted(cols_x, key=lambda v: float(v))
                mat = np.asarray(
                    pivot.select([y, *cols_x]).drop(y).to_numpy(), dtype=float,
                )
            except (ValueError, TypeError):
                # Fallback if any column header isn't parseable as float.
                mat = np.asarray(pivot.drop(y).to_numpy(), dtype=float)
        else:
            mat = np.asarray(pivot.drop(y).to_numpy(), dtype=float)
        # Thin tick labels — without this seaborn writes one label per
        # row / column. With a 43K-row pivot that produces an illegible
        # blur on the Y axis (and a similar blur on the X axis when the
        # X dimension is high-cardinality). Showing the first, last, and
        # ~8 evenly-spaced labels in between keeps the data range
        # readable without crowding.
        sns.heatmap(
            mat, ax=ax, cmap="viridis",
            xticklabels=_thin_axis_labels(cols_x, target=10),
            yticklabels=_thin_axis_labels(labels_y, target=10),
            cbar_kws={"label": value},
        )
        ax.set_xlabel(x); ax.set_ylabel(y)

    def _render_scatter3d(self, ax, df, x, y, z, value):
        if not (x and y and z):
            raise ValueError("scatter3d needs x, y and z")
        xs = df.get_column(x).to_numpy()
        ys = df.get_column(y).to_numpy()
        zs = df.get_column(z).to_numpy()
        kw = {"alpha": 0.7}
        if value and value in df.columns:
            cs = df.get_column(value).to_numpy()
            kw["c"] = cs
            kw["cmap"] = "viridis"
        sc = ax.scatter(xs, ys, zs, **kw)
        ax.set_xlabel(x); ax.set_ylabel(y); ax.set_zlabel(z)
        # 3-D needs the Z axis capped too; _apply_axis_locator only
        # touches X+Y, so do Z explicitly here.
        from matplotlib.ticker import MaxNLocator
        ax.xaxis.set_major_locator(MaxNLocator(nbins=8, prune="both"))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=8, prune="both"))
        ax.zaxis.set_major_locator(MaxNLocator(nbins=8, prune="both"))
        if "c" in kw:
            cb = ax.figure.colorbar(sc, ax=ax, shrink=0.7)
            cb.set_label(value)


def _normalise_sizes(arr):
    """Map a numeric array to matplotlib marker sizes (10..200) for scatter."""
    import numpy as np
    a = np.asarray(arr, dtype=float)
    a = a[~np.isnan(a)] if a.dtype.kind == "f" else a
    if a.size == 0:
        return 30
    lo, hi = float(a.min()), float(a.max())
    if hi == lo:
        return 30
    return 10 + (np.asarray(arr, dtype=float) - lo) / (hi - lo) * 190


def _thin_axis_labels(labels: list, target: int = 10) -> list:
    """Return a list of the same length as ``labels`` where most entries
    are blank (``""``) and only ~``target`` evenly-spaced positions show
    their original value. Used for heatmap tick labels — without this
    seaborn writes one tick label per row/column even when there are
    thousands, producing an illegible blur on the axis.

    Always keeps the first and last positions so the user can still read
    the data range; intermediate ticks are spaced as evenly as possible.
    """
    n = len(labels)
    if n <= target:
        return list(labels)
    # Pick `target` evenly-spaced indices including first + last.
    step = (n - 1) / (target - 1)
    keep = {round(i * step) for i in range(target)}
    return [labels[i] if i in keep else "" for i in range(n)]


def _apply_axis_locator(ax, max_ticks: int = 10) -> None:
    """Cap continuous-axis tick density on a matplotlib axes. Idempotent
    and cheap — call from any renderer whose X/Y are numeric. Default
    matplotlib already uses a locator, but it can drift toward 12+ ticks
    on tall figures with high-DPR; capping at ~10 keeps labels legible
    across DPI settings without bespoke spacing code per renderer.
    """
    from matplotlib.ticker import MaxNLocator

    ax.xaxis.set_major_locator(MaxNLocator(nbins=max_ticks, prune="both"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=max_ticks, prune="both"))


step = ExportToImageStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
