"""lift_chart — bucketed lift over random baseline."""
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


class LiftChartStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        df = inputs["in"]
        actual = params["actualColumn"]; proba = params["probaColumn"]
        buckets = int(params.get("buckets", 10))
        title = params.get("title", "Lift chart")

        clean = df.drop_nulls(subset=[actual, proba])
        y = np.asarray([int(bool(v)) for v in clean[actual].to_list()])
        s = np.asarray([float(v) for v in clean[proba].to_list()])
        if y.sum() == 0:
            raise ValueError("lift_chart: actual must contain at least one positive class")
        order = np.argsort(-s)
        y_sorted = y[order]
        n = len(y); base_rate = y.sum() / n

        # Per-bucket lift = (positives in this bucket / bucket size) / base_rate.
        bucket_size = n / buckets
        per_bucket: list[float] = []
        for b in range(buckets):
            lo = int(b * bucket_size); hi = int((b + 1) * bucket_size) if b < buckets - 1 else n
            chunk = y_sorted[lo:hi]
            if len(chunk) == 0:
                per_bucket.append(0); continue
            chunk_rate = chunk.sum() / len(chunk)
            per_bucket.append(chunk_rate / base_rate if base_rate > 0 else 0)
        # Cumulative lift.
        cum_pos = np.cumsum(y_sorted) / y.sum()
        cum_pop = np.arange(1, n + 1) / n
        cum_lift = cum_pos / cum_pop

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), dpi=144)
        # Per-bucket bars.
        x_buckets = np.arange(1, buckets + 1)
        bars = ax1.bar(x_buckets, per_bucket, color="#10b981", edgecolor="white")
        ax1.axhline(1.0, color="#9ca3af", linestyle="--", linewidth=1, label="Random (lift = 1)")
        ax1.set_xlabel(f"Bucket (1 = top {100 / buckets:.0f}%)")
        ax1.set_ylabel("Lift over random")
        ax1.set_title(f"{title} — per-bucket lift")
        ax1.set_xticks(x_buckets)
        ax1.legend(); ax1.grid(True, alpha=0.3, axis="y")
        # Cumulative.
        ax2.plot(cum_pop * 100, cum_lift, color="#10b981", linewidth=2)
        ax2.axhline(1.0, color="#9ca3af", linestyle="--", linewidth=1)
        ax2.set_xlabel("Cumulative % of population (sorted by probability)")
        ax2.set_ylabel("Cumulative lift")
        ax2.set_title(f"{title} — cumulative lift")
        ax2.grid(True, alpha=0.3)
        fig.tight_layout()

        out = _resolve_out(ctx, params.get("output_path"), self.id)
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": "png", "path": str(out),
            "chart": "lift_chart", "title": title, "n_samples": n, "buckets": buckets,
        }])


step = LiftChartStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
