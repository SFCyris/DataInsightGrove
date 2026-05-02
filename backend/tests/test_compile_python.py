"""Tests for the show-as-Python / notebook compiler."""

from __future__ import annotations

from ulid import ULID

from dig.engine.compile_python import compile_to_notebook, compile_to_python
from dig.engine.pipeline import (
    DatasetSpec,
    Node,
    OutputSpec,
    Pipeline,
    Reference,
)


def _make_pipeline() -> Pipeline:
    return Pipeline(
        id=str(ULID()),
        name="t",
        datasets=[
            DatasetSpec(id="ds", connector="csv", uri="file:///tmp/t.csv"),
        ],
        nodes=[
            Node(
                id="n1",
                step="filter_rows",
                stepVersion="1.0.0",
                inputs={"in": Reference(ref="ds")},
                params={"predicate": "x > 0"},
            ),
            Node(
                id="n2",
                step="select_columns",
                stepVersion="1.0.0",
                inputs={"in": Reference(ref="n1")},
                params={"columns": ["a", "b"]},
            ),
        ],
        outputs=[
            OutputSpec(id="o", name="out", **{"from": Reference(ref="n2", port="out")})
        ],
    )


def test_compile_python_runs():
    p = _make_pipeline()
    code = compile_to_python(p)
    # The script imports polars, references both nodes, and ends with a write call.
    assert "import polars as pl" in code
    assert "df_n1" in code
    assert "df_n2" in code
    assert "write_parquet" in code


def test_compile_notebook_runs():
    p = _make_pipeline()
    nb = compile_to_notebook(p)
    assert nb["nbformat"] == 4
    assert isinstance(nb["cells"], list)
    assert any(c["cell_type"] == "markdown" for c in nb["cells"])
    assert any(c["cell_type"] == "code" for c in nb["cells"])
    # All code cells must have a `source` (just sanity-check structure).
    for cell in nb["cells"]:
        assert "source" in cell
