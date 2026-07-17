"""pr_curve — Precision-Recall curve + average precision."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class PrCurveStep(Step):
    def execute_polars(self, inputs: dict[str, pl.DataFrame], params: dict[str, Any], ctx: PolarsContext | None = None) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.metrics import precision_recall_curve, average_precision_score
        import numpy as np

        df = inputs["in"]
        actual = params["actualColumn"]; proba = params["probaColumn"]
        title = params.get("title") or "Precision-Recall Curve"
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 1000); height = int(params.get("height") or 800)

        clean = df.drop_nulls(subset=[actual, proba])
        y_true = np.asarray([int(bool(v)) for v in clean[actual].to_list()])
        y_score = np.asarray([float(v) for v in clean[proba].to_list()])
        if len(set(y_true.tolist())) < 2:
            raise ValueError("pr_curve: actual column must contain both classes (0 and 1)")

        precision, recall, _ = precision_recall_curve(y_true, y_score)
        ap = float(average_precision_score(y_true, y_score))
        baseline = float((y_true == 1).sum()) / max(1, len(y_true))

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        ax.plot(recall, precision, color="#10b981", linewidth=2, label=f"AP = {ap:.3f}")
        ax.fill_between(recall, precision, alpha=0.1, color="#10b981")
        ax.axhline(baseline, color="#9ca3af", linestyle="--", linewidth=1,
                    label=f"Baseline (rate of positives = {baseline:.3f})")
        ax.set_xlim([0.0, 1.0]); ax.set_ylim([0.0, 1.05])
        ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
        ax.set_title(title); ax.legend(loc="lower left"); ax.grid(True, alpha=0.3)

        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height, "chart": "pr_curve",
            "title": title, "average_precision": ap,
        }])


step = PrCurveStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
