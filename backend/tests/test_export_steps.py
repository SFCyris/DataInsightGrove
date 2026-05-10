"""End-to-end tests for the three export steps (export_to_file/_db/_image)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import polars as pl
import pytest

from dig.engine.executor import execute
from dig.engine.pipeline import (
    DatasetSpec, Node, OutputSpec, Pipeline, Reference,
)


@pytest.fixture
def src(tmp_path: Path) -> Path:
    """A small parquet fixture every export test uses as its source."""
    p = tmp_path / "src.parquet"
    pl.DataFrame({
        "id":       [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "country":  ["US", "UK", "DE", "US", "UK", "FR", "DE", "US", "UK", "FR"],
        "revenue":  [100.0, 80.0, 60.0, 250.0, 30.0, 45.0, 120.0, 75.0, 22.0, 88.0],
        "balance":  [1000.5, 800.0, 200.5, 3000.0, 50.5, 400.0, 1200.0, 900.0, 100.0, 250.0],
    }).write_parquet(p)
    return p


def _pipeline_with_terminal(src: Path, terminal_node: Node, out_id: str = "o") -> Pipeline:
    return Pipeline(
        id="t",
        name="test",
        datasets=[DatasetSpec(id="ds", connector="parquet", uri=f"file://{src}")],
        nodes=[terminal_node],
        outputs=[OutputSpec.model_validate({"id": out_id, "name": "out", "from": {"ref": terminal_node.id}})],
    )


# ---- export_to_file ----

def test_export_to_file_csv(src: Path, tmp_path: Path):
    out = tmp_path / "exported.csv"
    node = Node(
        id="n_export", step="export_to_file", stepVersion="1.0.0",
        inputs={"in": Reference(ref="ds")}, outputs=["out"],
        params={"format": "csv", "path": str(out)},
    )
    p = _pipeline_with_terminal(src, node)
    res = execute(p, run_id="t-csv")
    assert out.exists()
    df = pl.read_csv(out)
    assert df.height == 10
    assert "country" in df.columns
    arts = res.artifacts["o"]
    assert arts and arts[0]["kind"] == "file"
    assert arts[0]["format"] == "csv"


def test_export_to_file_parquet_default_path(src: Path):
    """No path given → step writes under the run's output dir, derived name."""
    node = Node(
        id="n_export", step="export_to_file", stepVersion="1.0.0",
        inputs={"in": Reference(ref="ds")}, outputs=["out"],
        params={"format": "parquet"},
    )
    p = _pipeline_with_terminal(src, node)
    res = execute(p, run_id="t-parquet-auto")
    arts = res.artifacts["o"]
    assert arts[0]["kind"] == "file"
    assert arts[0]["format"] == "parquet"
    assert Path(arts[0]["path"]).exists()


# ---- export_to_db ----

def test_export_to_db_sqlite(src: Path, tmp_path: Path):
    db = tmp_path / "out.sqlite"
    node = Node(
        id="n_export", step="export_to_db", stepVersion="1.0.0",
        inputs={"in": Reference(ref="ds")}, outputs=["out"],
        params={
            "uri": f"sqlite:///{db}",
            "table": "exported_rows",
            "if_exists": "replace",
        },
    )
    p = _pipeline_with_terminal(src, node)
    try:
        execute(p, run_id="t-db")
    except (RuntimeError, ModuleNotFoundError) as e:
        if "missing driver" in str(e).lower() or "ModuleNotFoundError" in type(e).__name__:
            pytest.skip(f"no DB driver installed: {e}")
        raise

    assert db.exists()
    con = sqlite3.connect(db)
    try:
        rows = con.execute("SELECT count(*) FROM exported_rows").fetchone()[0]
        assert rows == 10
    finally:
        con.close()


# ---- export_to_image ----

def test_export_to_image_scatter(src: Path, tmp_path: Path):
    out = tmp_path / "scatter.png"
    node = Node(
        id="n_img", step="export_to_image", stepVersion="1.0.0",
        inputs={"in": Reference(ref="ds")}, outputs=["out"],
        params={
            "kind": "scatter", "x": "revenue", "y": "balance",
            "format": "png", "path": str(out),
            "width": 600, "height": 400, "dpi": 96,
        },
    )
    p = _pipeline_with_terminal(src, node)
    res = execute(p, run_id="t-img-scatter")
    assert out.exists()
    assert out.stat().st_size > 1024  # at least a few KB
    arts = res.artifacts["o"]
    assert arts[0]["kind"] == "image"
    assert arts[0]["chart"] == "scatter"
    assert arts[0]["format"] == "png"


def test_export_to_image_histogram_auto(src: Path, tmp_path: Path):
    """One-numeric-column input + kind='auto' should pick histogram."""
    out = tmp_path / "hist.png"
    node = Node(
        id="n_img", step="export_to_image", stepVersion="1.0.0",
        inputs={"in": Reference(ref="ds")}, outputs=["out"],
        params={
            "kind": "auto", "x": "revenue",
            "format": "png", "path": str(out),
            "width": 600, "height": 300, "dpi": 96,
        },
    )
    p = _pipeline_with_terminal(src, node)
    res = execute(p, run_id="t-img-hist")
    assert out.exists()
    assert res.artifacts["o"][0]["chart"] == "histogram"


def test_export_to_image_heatmap(src: Path, tmp_path: Path):
    out = tmp_path / "heat.png"
    node = Node(
        id="n_img", step="export_to_image", stepVersion="1.0.0",
        inputs={"in": Reference(ref="ds")}, outputs=["out"],
        params={
            "kind": "heatmap", "x": "country", "y4": "country", "value": "revenue",
            "format": "png", "path": str(out),
            "width": 500, "height": 400, "dpi": 96,
        },
    )
    p = _pipeline_with_terminal(src, node)
    # Heatmap with x==y is degenerate but should still render (1×N matrix).
    res = execute(p, run_id="t-img-heat")
    assert out.exists()
    assert res.artifacts["o"][0]["chart"] == "heatmap"


def test_export_to_image_bar_counts_for_categorical(src: Path, tmp_path: Path):
    out = tmp_path / "bar.png"
    node = Node(
        id="n_img", step="export_to_image", stepVersion="1.0.0",
        inputs={"in": Reference(ref="ds")}, outputs=["out"],
        params={
            "kind": "auto", "x": "country",
            "format": "png", "path": str(out),
            "width": 500, "height": 400, "dpi": 96,
        },
    )
    p = _pipeline_with_terminal(src, node)
    res = execute(p, run_id="t-img-bar")
    assert out.exists()
    assert res.artifacts["o"][0]["chart"] == "bar_counts"


# ---- chained: filter then export ----

def test_filter_then_export_to_image(src: Path, tmp_path: Path):
    """SQL filter step feeds a Polars terminal step — exercises the
    materialise-SQL-then-call-Polars path in the executor."""
    out = tmp_path / "filtered.png"
    nodes = [
        Node(
            id="n_filter", step="filter_rows", stepVersion="1.0.0",
            inputs={"in": Reference(ref="ds")}, outputs=["out"],
            params={"predicate": "country = 'US'"},
        ),
        Node(
            id="n_img", step="export_to_image", stepVersion="1.0.0",
            inputs={"in": Reference(ref="n_filter")}, outputs=["out"],
            params={"kind": "scatter", "x": "revenue", "y": "balance",
                    "format": "png", "path": str(out),
                    "width": 600, "height": 400, "dpi": 96},
        ),
    ]
    p = Pipeline(
        id="t", name="filter then img",
        datasets=[DatasetSpec(id="ds", connector="parquet", uri=f"file://{src}")],
        nodes=nodes,
        outputs=[OutputSpec.model_validate({"id": "o", "name": "out", "from": {"ref": "n_img"}})],
    )
    res = execute(p, run_id="t-chain")
    assert out.exists()
    art = res.artifacts["o"][0]
    assert art["chart"] == "scatter"
    # Only 3 US rows in the fixture.
    assert art["rows_plotted"] == 3
