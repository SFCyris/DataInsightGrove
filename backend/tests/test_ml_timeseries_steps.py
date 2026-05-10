"""Smoke tests for the ML + time-series steps.

These don't compare against golden parquet files — sklearn / statsmodels
output isn't byte-stable across versions. Instead they assert shape,
column membership, and that artifacts (PNGs) actually get written.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from dig.engine.registry import steps
from dig.engine.step import PolarsContext


@pytest.fixture
def out_ctx(tmp_path: Path) -> PolarsContext:
    return PolarsContext(run_id="test", out_dir=tmp_path)


@pytest.fixture
def numeric_df() -> pl.DataFrame:
    rng = np.random.default_rng(7)
    n = 300
    return pl.DataFrame({
        "a": rng.normal(0, 1, n),
        "b": rng.normal(0, 1, n) * 2 + 1,
        "c": rng.normal(0, 1, n) * 0.5 - 1,
        "label": rng.choice(["x", "y", "z"], size=n),
    })


@pytest.fixture
def time_series_df() -> pl.DataFrame:
    n = 200
    base = np.arange(n)
    trend = base * 0.05
    season = np.sin(base * 2 * np.pi / 7) * 2
    noise = np.random.default_rng(0).normal(0, 0.2, n)
    values = 10 + trend + season + noise
    times = pl.datetime_range(
        pl.datetime(2025, 1, 1), pl.datetime(2025, 1, 1), interval="1d", eager=True,
    )
    # Generate n daily timestamps from a fixed start.
    import datetime as dt
    times_list = [dt.datetime(2025, 1, 1) + dt.timedelta(days=i) for i in range(n)]
    return pl.DataFrame({"t": times_list, "v": values})


def test_correlation_matrix(numeric_df, out_ctx):
    s = steps().get("correlation_matrix")
    res = s.execute_polars({"in": numeric_df}, {"columns": ["a", "b", "c"]}, out_ctx)
    assert {"col_a", "col_b", "r"} <= set(res.output.columns)
    assert res.output.height == 9  # 3 × 3
    img = next((a for a in res.artifacts if a["kind"] == "image"), None)
    assert img is not None
    assert Path(img["path"]).exists()


def test_pca(numeric_df, out_ctx):
    s = steps().get("pca")
    res = s.execute_polars({"in": numeric_df}, {"columns": ["a", "b", "c"], "n_components": 2}, out_ctx)
    assert "PC1" in res.output.columns
    assert "PC2" in res.output.columns
    assert res.output.height == numeric_df.height


def test_kmeans(numeric_df, out_ctx):
    s = steps().get("kmeans")
    res = s.execute_polars({"in": numeric_df}, {"columns": ["a", "b", "c"], "k": 3}, out_ctx)
    assert "cluster" in res.output.columns


def test_dbscan(numeric_df, out_ctx):
    s = steps().get("dbscan")
    res = s.execute_polars({"in": numeric_df}, {"columns": ["a", "b"], "eps": 0.7, "min_samples": 5}, out_ctx)
    assert "cluster" in res.output.columns


def test_linear_regression(numeric_df, out_ctx):
    s = steps().get("linear_regression")
    res = s.execute_polars(
        {"in": numeric_df},
        {"y": "b", "x_columns": ["a", "c"]},
        out_ctx,
    )
    assert "predicted" in res.output.columns
    assert "residual" in res.output.columns


def test_tsne(numeric_df, out_ctx):
    s = steps().get("tsne")
    res = s.execute_polars(
        {"in": numeric_df},
        {"columns": ["a", "b", "c"], "perplexity": 10, "max_rows": 200},
        out_ctx,
    )
    assert "tSNE_1" in res.output.columns
    assert "tSNE_2" in res.output.columns


def test_umap(numeric_df, out_ctx):
    s = steps().get("umap")
    res = s.execute_polars(
        {"in": numeric_df},
        {"columns": ["a", "b", "c"], "n_neighbors": 10},
        out_ctx,
    )
    assert "UMAP_1" in res.output.columns
    assert "UMAP_2" in res.output.columns


def test_resample(time_series_df, out_ctx):
    s = steps().get("resample")
    res = s.execute_polars(
        {"in": time_series_df},
        {
            "time_column": "t",
            "interval": "7d",
            "aggregations": [{"column": "v", "fn": "mean", "as": "v_mean"}],
        },
        out_ctx,
    )
    assert {"t", "v_mean"} <= set(res.output.columns)
    assert res.output.height < time_series_df.height


def test_rolling(time_series_df, out_ctx):
    s = steps().get("rolling")
    res = s.execute_polars(
        {"in": time_series_df},
        {
            "time_column": "t",
            "windows": [{"column": "v", "fn": "mean", "window": 7, "as": "v_ma7"}],
        },
        out_ctx,
    )
    assert "v_ma7" in res.output.columns


def test_seasonal_decompose(time_series_df, out_ctx):
    s = steps().get("seasonal_decompose")
    res = s.execute_polars(
        {"in": time_series_df},
        {"time_column": "t", "value_column": "v", "period": 7},
        out_ctx,
    )
    assert {"trend", "seasonal", "residual"} <= set(res.output.columns)
    img = next((a for a in res.artifacts if a["kind"] == "image"), None)
    assert img is not None
    assert Path(img["path"]).exists()


def test_forecast(time_series_df, out_ctx):
    s = steps().get("forecast")
    res = s.execute_polars(
        {"in": time_series_df},
        {"time_column": "t", "value_column": "v", "horizon": 14, "method": "holt_winters", "seasonal_period": 7},
        out_ctx,
    )
    # Output should be longer than input by horizon.
    assert res.output.height >= time_series_df.height + 1
    assert "forecast" in res.output.columns
    assert "is_forecast" in res.output.columns
