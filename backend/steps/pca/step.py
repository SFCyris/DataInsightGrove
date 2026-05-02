"""PCA step — sklearn-backed dimensionality reduction.

Adds PC1..PCK columns to the data and surfaces variance-explained per
component as a JSON artifact. Renders a 2-D scatter of PC1 × PC2 by default.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


def _is_numeric(dtype: pl.DataType) -> bool:
    name = str(dtype).lower()
    return any(t in name for t in ("int", "float", "double", "decimal"))


class PCAStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        df = inputs["in"]
        cols = params.get("columns") or [c for c, t in df.schema.items() if _is_numeric(t)]
        cols = [c for c in cols if c in df.columns]
        if len(cols) < 2:
            raise ValueError("pca: need at least 2 numeric columns")

        n_components = int(params.get("n_components") or 2)
        n_components = max(2, min(n_components, len(cols)))

        # Drop rows containing any null in the input columns — PCA can't
        # interpolate, and silently filling with 0 distorts the projection.
        sub = df.select(cols).drop_nulls()
        x_raw = sub.to_numpy()

        # Save the fitted scaler so we transform the full data with the same
        # mean/std the PCA was fit on. Previously we were re-fitting a fresh
        # scaler on the already-scaled data, producing subtly wrong PC values
        # for rows that had nulls but were re-projected (P1 review finding).
        scale = bool(params.get("scale", True))
        scaler = StandardScaler().fit(x_raw) if scale else None
        x_fit = scaler.transform(x_raw) if scaler is not None else x_raw

        pca = PCA(n_components=n_components, random_state=42)
        pca.fit(x_fit)

        # Project the *full* original df: rows with nulls in input cols receive
        # null PC values rather than disappearing.
        full_x = df.select(cols).to_numpy()
        from numpy import isfinite, full as np_full, nan
        mask = isfinite(full_x).all(axis=1)
        full_proj = np_full((full_x.shape[0], n_components), nan)
        if mask.any():
            x_to_project = (
                scaler.transform(full_x[mask]) if scaler is not None else full_x[mask]
            )
            full_proj[mask] = pca.transform(x_to_project)

        out = df.clone()
        for i in range(n_components):
            out = out.with_columns(pl.Series(f"PC{i+1}", full_proj[:, i]))

        artifacts: list[dict[str, Any]] = []
        artifacts.append({
            "kind": "stats",
            "label": "Variance explained per component",
            "data": {
                "explained_variance_ratio": [float(v) for v in pca.explained_variance_ratio_],
                "cumulative": [float(v) for v in pca.explained_variance_ratio_.cumsum()],
                "components": [f"PC{i+1}" for i in range(n_components)],
                "n_input_cols": len(cols),
                "n_rows_used": int(mask.sum()),
            },
        })

        if bool(params.get("render", True)) and ctx is not None:
            artifacts.append(self._render_scatter(out, params, pca.explained_variance_ratio_, ctx))

        return PolarsResult(output=out, artifacts=artifacts)

    def _render_scatter(self, df: pl.DataFrame, params: dict[str, Any], evr, ctx: PolarsContext) -> dict[str, Any]:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import seaborn as sns

        sns.set_theme(style="whitegrid", context="notebook")

        title = params.get("title") or "PCA"
        color_by = params.get("color_by")

        sub = df.select([c for c in ("PC1", "PC2", color_by) if c and c in df.columns]).drop_nulls()
        if sub.height == 0:
            # Nothing to plot; return an empty placeholder.
            fig, ax = plt.subplots(figsize=(6, 4), dpi=144)
            ax.text(0.5, 0.5, "no rows after PCA", ha="center", va="center")
            out_path = ctx.out_dir / f"{self.id}.png"
            fig.savefig(out_path, format="png", dpi=144, bbox_inches="tight")
            plt.close(fig)
            return {"kind": "image", "format": "png", "path": str(out_path), "chart": "scatter", "title": title}

        # Sample down for plotting only.
        if sub.height > 50_000:
            sub = sub.sample(n=50_000, seed=42)

        fig, ax = plt.subplots(figsize=(7, 5), dpi=144)
        xs = sub.get_column("PC1").to_numpy()
        ys = sub.get_column("PC2").to_numpy()
        if color_by and color_by in sub.columns:
            cs = sub.get_column(color_by)
            if _is_numeric(cs.dtype):
                sc = ax.scatter(xs, ys, c=cs.to_numpy(), cmap="viridis", alpha=0.7, s=18)
                cb = fig.colorbar(sc, ax=ax)
                cb.set_label(color_by)
            else:
                # Categorical → palette of distinct colors.
                cats = cs.cast(pl.Utf8).to_list()
                uniq = list(dict.fromkeys(cats))
                palette = sns.color_palette("tab20", n_colors=len(uniq))
                color_index = {c: palette[i] for i, c in enumerate(uniq)}
                for c in uniq:
                    mask = [k == c for k in cats]
                    ax.scatter(
                        [xs[i] for i, m in enumerate(mask) if m],
                        [ys[i] for i, m in enumerate(mask) if m],
                        label=c, alpha=0.7, s=18, color=color_index[c],
                    )
                ax.legend(title=color_by, fontsize=8, loc="best")
        else:
            ax.scatter(xs, ys, alpha=0.6, s=18)

        ax.set_xlabel(f"PC1 ({evr[0]*100:.1f}% var)")
        ax.set_ylabel(f"PC2 ({evr[1]*100:.1f}% var)")
        ax.set_title(title)
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


step = PCAStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
