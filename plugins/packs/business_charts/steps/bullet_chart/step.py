"""bullet_chart — Tufte's target-vs-actual exec dashboard chart."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _resolve_out(ctx, custom, step_id):
    if custom:
        p = Path(custom)
        if ctx is not None and not p.is_absolute():
            return ctx.out_dir / p
        return p
    base = ctx.out_dir if ctx is not None else Path.cwd()
    return base / f"{step_id}.png"


class BulletChartStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        df = inputs["in"]
        l_col = params["labelColumn"]
        a_col = params["actualColumn"]
        t_col = params["targetColumn"]
        poor_col = params.get("poorMaxColumn")
        ok_col = params.get("okMaxColumn")
        good_col = params.get("goodMaxColumn")
        title = params.get("title", "Performance vs target")

        clean = df.drop_nulls(subset=[l_col, a_col, t_col])
        labels = [str(v) for v in clean[l_col].to_list()]
        actuals = [float(v) for v in clean[a_col].to_list()]
        targets = [float(v) for v in clean[t_col].to_list()]
        n = len(labels)
        if n == 0:
            raise ValueError("bullet_chart: no rows after drop_nulls")

        def _col_or_default(col_name: str | None, default: float) -> list[float]:
            if col_name and col_name in clean.columns:
                return [float(v) if v is not None else default for v in clean[col_name].to_list()]
            return [default] * n

        # Default bands: poor up to 60% of target, ok up to target, good 40% above target.
        poor_max = _col_or_default(poor_col, max(targets) * 0.6 if targets else 0)
        ok_max = _col_or_default(ok_col, max(targets) if targets else 0)
        good_max = _col_or_default(good_col, max(targets) * 1.4 if targets else 0)

        fig, ax = plt.subplots(figsize=(11, 0.7 * n + 1.5), dpi=144)
        for i in range(n):
            y = n - 1 - i
            # Bands.
            ax.barh(y, good_max[i], color="#e5e7eb", height=0.8)
            ax.barh(y, ok_max[i], color="#cbd5e1", height=0.8)
            ax.barh(y, poor_max[i], color="#9ca3af", height=0.8)
            # Actual.
            color = "#10b981" if actuals[i] >= targets[i] else "#ef4444" if actuals[i] < poor_max[i] else "#f59e0b"
            ax.barh(y, actuals[i], color=color, height=0.4)
            # Target marker.
            ax.plot([targets[i], targets[i]], [y - 0.35, y + 0.35], color="#111827", linewidth=2.5)
        ax.set_yticks(range(n))
        ax.set_yticklabels(labels[::-1])
        ax.set_xlabel("value")
        ax.set_title(title)
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": "png", "path": str(out_path),
            "chart": "bullet", "title": title, "n_bullets": n,
        }])


step = BulletChartStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
