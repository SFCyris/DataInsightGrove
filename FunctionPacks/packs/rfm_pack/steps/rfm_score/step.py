"""rfm_score — per-customer R/F/M scores + segment string."""
from __future__ import annotations
import json
from datetime import date, datetime
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


def _qbin(series: pl.Series, n: int, ascending: bool = True) -> pl.Series:
    """Quantile-bin into 1..n. ascending=True means high values get high
    bins (good for monetary/frequency). ascending=False inverts (good
    for recency where smaller days = better)."""
    import numpy as np
    arr = series.to_numpy().astype(float)
    if len(arr) == 0:
        return pl.Series(name=series.name, values=[])
    quantiles = np.linspace(0, 1, n + 1)[1:-1]
    breaks = np.quantile(arr, quantiles)
    bins = np.digitize(arr, breaks) + 1  # 1..n
    if not ascending:
        bins = (n + 1) - bins
    return pl.Series(name=series.name, values=bins.tolist())


class RfmScoreStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        c = params["customerColumn"]; d = params["dateColumn"]; a = params["amountColumn"]
        bins = int(params.get("bins", 5))
        as_of_raw = (params.get("asOfDate") or "").strip()
        as_of = datetime.fromisoformat(as_of_raw).date() if as_of_raw else date.today()

        clean = df.drop_nulls(subset=[c, d, a]).filter(pl.col(a) > 0)
        if clean.height == 0:
            raise ValueError("rfm_score: no rows with positive amount + non-null customer/date")

        # Aggregate per customer.
        agg = clean.group_by(c).agg([
            pl.col(d).max().alias("last_purchase"),
            pl.col(a).count().alias("frequency"),
            pl.col(a).sum().alias("monetary"),
        ])
        # Recency in days.
        agg = agg.with_columns([
            (pl.lit(as_of).cast(pl.Date) - pl.col("last_purchase").cast(pl.Date))
                .dt.total_days().alias("recency_days"),
        ])
        # Score per axis. Recency: smaller days = higher score.
        r_scores = _qbin(agg["recency_days"], bins, ascending=False)
        f_scores = _qbin(agg["frequency"], bins, ascending=True)
        m_scores = _qbin(agg["monetary"], bins, ascending=True)
        out = agg.with_columns([
            pl.Series("r_score", r_scores.to_list()),
            pl.Series("f_score", f_scores.to_list()),
            pl.Series("m_score", m_scores.to_list()),
        ])
        out = out.with_columns(
            pl.format("{}-{}-{}", pl.col("r_score"), pl.col("f_score"), pl.col("m_score")).alias("rfm_segment")
        )
        return PolarsResult(output=out)


step = RfmScoreStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
