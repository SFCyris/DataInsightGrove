"""roc_curve — ROC curve + AUC chart for binary classifiers."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class RocCurveStep(Step):
    def execute_polars(self, inputs: dict[str, pl.DataFrame], params: dict[str, Any], ctx: PolarsContext | None = None) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import roc_curve, auc
        import numpy as np

        df = inputs["in"]
        actual = params["actualColumn"]; proba = params["probaColumn"]
        title = params.get("title") or "ROC Curve"
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 1000); height = int(params.get("height") or 800)

        clean = df.drop_nulls(subset=[actual, proba])
        y_true = np.asarray([int(bool(v)) for v in clean[actual].to_list()])
        y_score = np.asarray([float(v) for v in clean[proba].to_list()])
        if len(set(y_true.tolist())) < 2:
            raise ValueError("roc_curve: actual column must contain both classes (0 and 1) — got only one")

        fpr, tpr, _ = roc_curve(y_true, y_score)
        auc_val = float(auc(fpr, tpr))

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        ax.plot(fpr, tpr, color="#10b981", linewidth=2, label=f"AUC = {auc_val:.3f}")
        ax.plot([0, 1], [0, 1], color="#9ca3af", linestyle="--", linewidth=1, label="Chance (AUC = 0.5)")
        ax.fill_between(fpr, tpr, alpha=0.1, color="#10b981")
        ax.set_xlim([0.0, 1.0]); ax.set_ylim([0.0, 1.05])
        ax.set_xlabel("False Positive Rate"); ax.set_ylabel("True Positive Rate")
        ax.set_title(title); ax.legend(loc="lower right"); ax.grid(True, alpha=0.3)

        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height, "chart": "roc_curve",
            "title": title, "auc": auc_val,
        }])


step = RocCurveStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
