"""confusion_matrix — heatmap of actual × predicted class counts."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ConfusionMatrixStep(Step):
    def execute_polars(self, inputs: dict[str, pl.DataFrame], params: dict[str, Any], ctx: PolarsContext | None = None) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import confusion_matrix as sk_cm
        import numpy as np

        df = inputs["in"]
        actual = params["actualColumn"]; pred = params["predictedColumn"]
        normalize = (params.get("normalize") or "counts").lower()
        title = params.get("title") or "Confusion Matrix"
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 900); height = int(params.get("height") or 800)

        clean = df.drop_nulls(subset=[actual, pred])
        y_true = clean[actual].to_list()
        y_pred = clean[pred].to_list()
        # Cast everything to a comparable type — string is safest when
        # mixed types or labels appear.
        y_true_s = [str(v) for v in y_true]
        y_pred_s = [str(v) for v in y_pred]
        labels = sorted(set(y_true_s) | set(y_pred_s))
        cm = sk_cm(y_true_s, y_pred_s, labels=labels)
        cm_f = cm.astype(float)

        if normalize == "row_percent":
            row_sums = cm_f.sum(axis=1, keepdims=True); row_sums[row_sums == 0] = 1
            display = cm_f / row_sums * 100
            cell_fmt = lambda v, raw: f"{v:.1f}%\n({int(raw)})"
        elif normalize == "column_percent":
            col_sums = cm_f.sum(axis=0, keepdims=True); col_sums[col_sums == 0] = 1
            display = cm_f / col_sums * 100
            cell_fmt = lambda v, raw: f"{v:.1f}%\n({int(raw)})"
        elif normalize == "all_percent":
            total = cm_f.sum()
            display = cm_f / max(1, total) * 100
            cell_fmt = lambda v, raw: f"{v:.1f}%\n({int(raw)})"
        else:
            display = cm_f
            cell_fmt = lambda v, raw: f"{int(v)}"

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        im = ax.imshow(display, cmap="Blues", aspect="auto")
        ax.set_xticks(range(len(labels))); ax.set_yticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right")
        ax.set_yticklabels(labels)
        ax.set_xlabel("Predicted"); ax.set_ylabel("Actual"); ax.set_title(title)
        # Per-cell annotation. Black on light cells, white on dark.
        thresh = display.max() / 2.0
        for i in range(len(labels)):
            for j in range(len(labels)):
                color = "white" if display[i, j] > thresh else "black"
                ax.text(j, i, cell_fmt(display[i, j], cm[i, j]),
                        ha="center", va="center", color=color, fontsize=10)
        fig.colorbar(im, ax=ax, shrink=0.8)
        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)

        accuracy = float(np.trace(cm) / max(1, cm.sum()))
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height, "chart": "confusion_matrix",
            "title": title, "accuracy": accuracy, "labels": labels,
        }])


step = ConfusionMatrixStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
