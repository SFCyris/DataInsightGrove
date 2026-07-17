"""kpi_card — one card per row with big-number + label + delta."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


def _format_value(v: float, kind: str) -> str:
    if v is None:
        return "—"
    if kind == "thousands":
        return f"{v / 1_000:,.1f}K"
    if kind == "millions":
        return f"{v / 1_000_000:,.2f}M"
    if kind == "percent":
        return f"{v * 100:.1f}%"
    if kind == "currency_usd":
        return f"${v:,.0f}"
    if kind == "currency_eur":
        return f"€{v:,.0f}"
    if abs(v) >= 10_000:
        return f"{v:,.0f}"
    return f"{v:,.2f}" if abs(v) < 100 else f"{v:,.0f}"


class KpiCardStep(Step):
    def execute_polars(self, inputs: dict[str, pl.DataFrame], params: dict[str, Any], ctx: PolarsContext | None = None) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        df = inputs["in"]
        l_col = params["labelColumn"]; v_col = params["valueColumn"]
        b_col = params.get("baselineColumn")
        value_kind = (params.get("format_value") or "raw").lower()
        title = params.get("title") or ""
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 1600); height = int(params.get("height") or 400)

        clean = df.drop_nulls(subset=[l_col, v_col])
        labels = [str(v) for v in clean[l_col].to_list()]
        values = [float(v) for v in clean[v_col].to_list()]
        baselines = ([float(v) if v is not None else None for v in clean[b_col].to_list()]
                      if b_col and b_col in clean.columns
                      else [None] * len(values))

        n = len(labels)
        if n == 0:
            raise ValueError("kpi_card: no rows")

        fig, axes = plt.subplots(1, n, figsize=(width / 100, height / 100), dpi=100, squeeze=False)
        for ax, lab, val, base in zip(axes[0], labels, values, baselines):
            ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
            # Label.
            ax.text(0.5, 0.85, lab, ha="center", va="top", fontsize=12,
                     color="#6b7280", weight="bold")
            # Big value.
            ax.text(0.5, 0.45, _format_value(val, value_kind), ha="center", va="center",
                     fontsize=36, weight="bold", color="#111827")
            # Delta vs baseline.
            if base is not None and base != 0:
                pct = (val - base) / abs(base) * 100
                arrow = "▲" if pct >= 0 else "▼"
                color = "#10b981" if pct >= 0 else "#ef4444"
                ax.text(0.5, 0.12, f"{arrow} {pct:+.1f}% vs baseline ({_format_value(base, value_kind)})",
                         ha="center", va="bottom", fontsize=11, color=color)
            # Frame.
            ax.add_patch(plt.Rectangle((0.02, 0.02), 0.96, 0.96, facecolor="white",
                                          edgecolor="#e5e7eb", linewidth=1.5, zorder=-1))
        if title:
            fig.suptitle(title, fontsize=14, weight="bold", y=1.02)
        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height, "chart": "kpi_card",
            "title": title, "n_cards": n,
        }])


step = KpiCardStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
