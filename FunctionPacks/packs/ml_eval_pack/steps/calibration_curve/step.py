"""calibration_curve — reliability diagram for probabilistic classifier."""
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


class CalibrationCurveStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from sklearn.calibration import calibration_curve as skl_cal
        import numpy as np

        df = inputs["in"]
        actual = params["actualColumn"]; proba = params["probaColumn"]
        bins = int(params.get("bins", 10))
        strategy = (params.get("strategy") or "uniform").lower()
        title = params.get("title", "Calibration curve")

        clean = df.drop_nulls(subset=[actual, proba])
        y = np.asarray([int(bool(v)) for v in clean[actual].to_list()])
        s = np.asarray([float(v) for v in clean[proba].to_list()])
        if y.sum() == 0:
            raise ValueError("calibration_curve: actual must contain at least one positive class")

        prob_true, prob_pred = skl_cal(y, s, n_bins=bins, strategy=strategy)
        # Brier score for the legend.
        brier = float(np.mean((s - y) ** 2))

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 8), dpi=144,
                                          gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
        ax1.plot([0, 1], [0, 1], color="#9ca3af", linestyle="--", linewidth=1, label="Perfect calibration")
        ax1.plot(prob_pred, prob_true, marker="o", color="#10b981", linewidth=2,
                  label=f"Brier score = {brier:.3f}")
        ax1.set_ylabel("Fraction of positives (actual)")
        ax1.set_xlim([0, 1]); ax1.set_ylim([0, 1])
        ax1.set_title(title); ax1.legend(loc="upper left"); ax1.grid(True, alpha=0.3)
        # Histogram of predicted probabilities.
        ax2.hist(s, bins=bins, color="#10b981", alpha=0.6, edgecolor="white")
        ax2.set_xlabel("Predicted probability")
        ax2.set_ylabel("Count"); ax2.grid(True, alpha=0.2)
        fig.tight_layout()

        out = _resolve_out(ctx, params.get("output_path"), self.id)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": "png", "path": str(out),
            "chart": "calibration_curve", "title": title, "n_samples": len(y),
            "brier_score": brier, "bins": bins, "strategy": strategy,
        }])


step = CalibrationCurveStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
