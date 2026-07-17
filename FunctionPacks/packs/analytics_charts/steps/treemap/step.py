"""treemap — area-proportional rectangle chart via squarify."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class TreemapStep(Step):
    def execute_polars(self, inputs: dict[str, pl.DataFrame], params: dict[str, Any], ctx: PolarsContext | None = None) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import squarify

        df = inputs["in"]
        label_col = params["labelColumn"]; val_col = params["valueColumn"]
        color_col = params.get("colorColumn")
        title = params.get("title") or "Treemap"
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 1400); height = int(params.get("height") or 900)

        clean = df.drop_nulls(subset=[label_col, val_col]).filter(pl.col(val_col) > 0)
        if clean.height == 0:
            raise ValueError("treemap: no rows with positive value")
        # Sort by value desc so squarify packs the largest rect upper-left.
        clean = clean.sort(val_col, descending=True)
        labels = [str(v) for v in clean[label_col].to_list()]
        values = [float(v) for v in clean[val_col].to_list()]

        if color_col and color_col in clean.columns:
            cats = [str(v) for v in clean[color_col].to_list()]
            uniq = sorted(set(cats))
            cmap = cm.tab10 if len(uniq) <= 10 else cm.tab20
            cat_to_color = {c: cmap(i / max(1, len(uniq) - 1)) for i, c in enumerate(uniq)}
            colors = [cat_to_color[c] for c in cats]
        else:
            cmap = cm.viridis
            colors = [cmap(i / max(1, len(values) - 1)) for i in range(len(values))]

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        normed = squarify.normalize_sizes(values, width, height)
        rects = squarify.squarify(normed, 0, 0, width, height)
        for r, lab, val, color in zip(rects, labels, values, colors):
            ax.add_patch(plt.Rectangle((r["x"], r["y"]), r["dx"], r["dy"],
                                        facecolor=color, edgecolor="white", linewidth=1.5))
            # Label only if rect is large enough to read.
            if r["dx"] > 50 and r["dy"] > 30:
                ax.text(r["x"] + r["dx"] / 2, r["y"] + r["dy"] / 2,
                        f"{lab}\n{val:,.0f}", ha="center", va="center",
                        fontsize=10, color="white",
                        bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.3, linewidth=0))
        ax.set_xlim(0, width); ax.set_ylim(0, height)
        ax.invert_yaxis(); ax.set_aspect("equal")
        ax.axis("off"); ax.set_title(title)

        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height, "chart": "treemap",
            "title": title, "n_rectangles": len(values),
        }])


step = TreemapStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
