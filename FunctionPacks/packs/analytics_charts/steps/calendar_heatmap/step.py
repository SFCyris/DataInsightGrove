"""calendar_heatmap — GitHub-style year-view heatmap of (date, value)."""
from __future__ import annotations
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class CalendarHeatmapStep(Step):
    def execute_polars(self, inputs: dict[str, pl.DataFrame], params: dict[str, Any], ctx: PolarsContext | None = None) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        df = inputs["in"]
        date_col = params["dateColumn"]; val_col = params["valueColumn"]
        title = params.get("title") or "Calendar heatmap"
        scale = params.get("color_scale") or "Greens"
        year_filter = params.get("year")
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 1600); height = int(params.get("height") or 500)

        # Aggregate per-day; coerce date column to python date objects.
        agg = (df.drop_nulls(subset=[date_col, val_col])
                  .group_by(date_col)
                  .agg(pl.col(val_col).sum().alias("__v")))
        date_vals = agg[date_col].to_list()
        values = agg["__v"].to_list()
        # Convert each entry to a python date.
        def _to_date(v):
            if isinstance(v, date) and not isinstance(v, datetime):
                return v
            if isinstance(v, datetime):
                return v.date()
            try:
                return datetime.fromisoformat(str(v)).date()
            except Exception:
                return None
        pairs = [(d, vv) for d, vv in ((_to_date(dv), v) for dv, v in zip(date_vals, values)) if d]
        if not pairs:
            raise ValueError("calendar_heatmap: no valid dates after coercion")

        if year_filter:
            year_filter = int(year_filter)
            pairs = [(d, v) for d, v in pairs if d.year == year_filter]
            if not pairs:
                raise ValueError(f"calendar_heatmap: no rows for year {year_filter}")

        years = sorted({d.year for d, _ in pairs})
        n_years = len(years)
        fig, axes = plt.subplots(n_years, 1, figsize=(width / 100, height / 100 * n_years), dpi=100, squeeze=False)
        for ax, year in zip(axes[:, 0], years):
            year_pairs = [(d, v) for d, v in pairs if d.year == year]
            grid = self._build_year_grid(year, year_pairs)
            im = ax.imshow(grid, cmap=scale, aspect="auto")
            ax.set_yticks(range(7)); ax.set_yticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
            # Month labels on top.
            month_starts = []
            for m in range(1, 13):
                d = date(year, m, 1)
                wk = ((d - date(year, 1, 1)).days + date(year, 1, 1).weekday()) // 7
                month_starts.append((wk, d.strftime("%b")))
            ax.set_xticks([w for w, _ in month_starts])
            ax.set_xticklabels([m for _, m in month_starts])
            ax.set_title(f"{title} — {year}" if n_years > 1 else title)
            for spine in ax.spines.values():
                spine.set_visible(False)
        # One colorbar shared across the figure.
        fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.7, label=val_col)

        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height * n_years, "chart": "calendar_heatmap",
            "title": title, "years": years,
        }])

    def _build_year_grid(self, year: int, pairs: list[tuple[date, float]]):
        """Build a 7-rows × ~53-cols grid for one year. Row = weekday
        (0=Mon), col = week index. Cells outside the year are NaN."""
        import numpy as np
        first = date(year, 1, 1)
        # Week-of-year by ISO would split year boundaries oddly. Use a
        # simple "day-of-year + weekday-offset, divide by 7" for the
        # column. This produces the GitHub-style aligned columns.
        offset = first.weekday()  # 0 = Mon
        n_cols = (offset + 366) // 7 + 1
        grid = np.full((7, n_cols), np.nan)
        lookup = {d: v for d, v in pairs}
        d = first
        while d.year == year:
            wd = d.weekday()
            col = ((d - first).days + offset) // 7
            v = lookup.get(d)
            if v is not None:
                grid[wd, col] = float(v)
            d = d + timedelta(days=1)
        return grid


step = CalendarHeatmapStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
