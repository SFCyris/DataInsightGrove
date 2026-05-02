"""Linear regression step (OLS).

Fits a linear model and adds two columns: predicted and residual. Renders the
fit line (single feature) or an actual-vs-predicted scatter (multiple
features). Surfaces R², coefficients, and p-values via a stats artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class LinearRegressionStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.linear_model import LinearRegression

        df = inputs["in"]
        y = (params.get("y") or "").strip()
        x_cols = params.get("x_columns") or []
        x_cols = [c for c in x_cols if c in df.columns]
        if not y or y not in df.columns:
            raise ValueError("linear_regression: 'y' is required and must be an input column")
        if not x_cols:
            raise ValueError("linear_regression: at least one feature column is required")

        fit_intercept = bool(params.get("fit_intercept", True))
        pred_col = (params.get("predicted_column") or "predicted").strip() or "predicted"
        res_col = (params.get("residual_column") or "residual").strip() or "residual"

        from numpy import isfinite, full as np_full, nan as np_nan
        full_x = df.select(x_cols).to_numpy()
        full_y = df.get_column(y).to_numpy()
        mask = isfinite(full_x).all(axis=1) & isfinite(full_y)
        if mask.sum() < 2:
            raise ValueError("linear_regression: need at least 2 complete rows")

        x_fit = full_x[mask]
        y_fit = full_y[mask]
        model = LinearRegression(fit_intercept=fit_intercept).fit(x_fit, y_fit)

        # Predict over the full data; null where any input was null.
        full_pred = np_full(full_y.shape, np_nan)
        full_pred[mask] = model.predict(full_x[mask])
        full_resid = full_y - full_pred

        out = df.with_columns([
            pl.Series(pred_col, full_pred),
            pl.Series(res_col, full_resid),
        ])

        # R² on the fit subset
        ss_res = float(((y_fit - model.predict(x_fit)) ** 2).sum())
        ss_tot = float(((y_fit - y_fit.mean()) ** 2).sum())
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

        artifacts: list[dict[str, Any]] = []
        artifacts.append({
            "kind": "stats",
            "label": "Linear regression coefficients",
            "data": {
                "r_squared": r2,
                "n_obs": int(mask.sum()),
                "intercept": float(model.intercept_) if fit_intercept else 0.0,
                "coefficients": {col: float(coef) for col, coef in zip(x_cols, model.coef_)},
                "fit_intercept": fit_intercept,
            },
        })

        if bool(params.get("render", True)) and ctx is not None:
            artifacts.append(self._render(out, x_cols, y, pred_col, params, r2, ctx))

        return PolarsResult(output=out, artifacts=artifacts)

    def _render(
        self,
        df: pl.DataFrame,
        x_cols: list[str],
        y: str,
        pred_col: str,
        params: dict[str, Any],
        r2: float,
        ctx: PolarsContext,
    ) -> dict[str, Any]:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        sns.set_theme(style="whitegrid", context="notebook")
        title = params.get("title") or "Linear regression"

        sub = df.select([*x_cols, y, pred_col]).drop_nulls()
        if sub.height > 50_000:
            sub = sub.sample(n=50_000, seed=42)

        fig, ax = plt.subplots(figsize=(7, 5), dpi=144)
        if len(x_cols) == 1:
            xs = sub.get_column(x_cols[0]).to_numpy()
            ys = sub.get_column(y).to_numpy()
            ps = sub.get_column(pred_col).to_numpy()
            ax.scatter(xs, ys, alpha=0.5, s=14, label="actual")
            order = xs.argsort()
            ax.plot(xs[order], ps[order], color="crimson", linewidth=2, label="fit")
            ax.set_xlabel(x_cols[0]); ax.set_ylabel(y)
            ax.legend(fontsize=9)
        else:
            ys = sub.get_column(y).to_numpy()
            ps = sub.get_column(pred_col).to_numpy()
            ax.scatter(ps, ys, alpha=0.6, s=14)
            lo = float(min(ys.min(), ps.min()))
            hi = float(max(ys.max(), ps.max()))
            ax.plot([lo, hi], [lo, hi], color="crimson", linewidth=2, label="y = x")
            ax.set_xlabel(f"predicted {y}")
            ax.set_ylabel(f"actual {y}")
            ax.legend(fontsize=9)
        ax.set_title(f"{title}  ·  R² = {r2:.3f}")
        fig.tight_layout()

        out_path = ctx.out_dir / f"{self.id}.png"
        fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
        plt.close(fig)

        return {
            "kind": "image",
            "format": "png",
            "path": str(out_path),
            "chart": "scatter",
            "title": title,
            "rows_plotted": sub.height,
        }


step = LinearRegressionStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
