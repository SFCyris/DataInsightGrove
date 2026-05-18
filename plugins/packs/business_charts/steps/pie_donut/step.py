"""pie_donut — classic part-to-whole pie or donut chart."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _resolve_out(ctx: PolarsContext | None, custom: str | None, step_id: str) -> Path:
    if custom:
        p = Path(custom)
        if ctx is not None and not p.is_absolute():
            return ctx.out_dir / p
        return p
    base = ctx.out_dir if ctx is not None else Path.cwd()
    return base / f"{step_id}.png"


class PieDonutStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm

        df = inputs["in"]
        label_col = params["labelColumn"]
        value_col = params["valueColumn"]
        variant = params.get("variant", "donut")
        center_label = params.get("centerLabel", "")
        show_pct = bool(params.get("showPercents", True))
        title = params.get("title", "Composition")

        clean = df.drop_nulls(subset=[label_col, value_col]).filter(pl.col(value_col) > 0)
        if clean.height == 0:
            raise ValueError("pie_donut: no rows with positive value")
        # Sort largest-first; collapse very small slices into "Other".
        clean = clean.sort(value_col, descending=True)
        labels = [str(v) for v in clean[label_col].to_list()]
        values = [float(v) for v in clean[value_col].to_list()]
        total = sum(values)
        if total == 0:
            raise ValueError("pie_donut: total value is zero")
        # Combine slices < 2% into Other.
        other_total = 0.0
        keep_labels: list[str] = []
        keep_values: list[float] = []
        for lab, val in zip(labels, values):
            if val / total < 0.02 and len(keep_values) > 6:
                other_total += val
            else:
                keep_labels.append(lab); keep_values.append(val)
        if other_total > 0:
            keep_labels.append("Other"); keep_values.append(other_total)

        cmap = cm.tab20 if len(keep_values) > 10 else cm.tab10
        colors = [cmap(i / max(1, len(keep_values) - 1)) for i in range(len(keep_values))]

        fig, ax = plt.subplots(figsize=(8, 8), dpi=144)
        wedge_kw = {"width": 0.4, "edgecolor": "white", "linewidth": 2} if variant == "donut" else {"edgecolor": "white", "linewidth": 2}
        autopct = "%1.1f%%" if show_pct else None
        wedges, texts, autotexts = ax.pie(
            keep_values, labels=keep_labels, colors=colors,
            wedgeprops=wedge_kw, autopct=autopct, pctdistance=0.78 if variant == "donut" else 0.65,
            startangle=90,
        )
        for at in autotexts:
            at.set_color("white"); at.set_fontweight("bold"); at.set_fontsize(10)
        if variant == "donut" and center_label:
            ax.text(0, 0, center_label, ha="center", va="center", fontsize=14, fontweight="bold")
        ax.set_title(title)

        out_path = _resolve_out(ctx, params.get("output_path"), self.id)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": "png", "path": str(out_path),
            "chart": variant, "title": title, "n_slices": len(keep_values),
        }])


step = PieDonutStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
