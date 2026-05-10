"""Per-row lineage tracking — end-to-end smoke test."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
from ulid import ULID

from dig.engine.executor import LINEAGE_COL_PREFIX, execute
from dig.engine.pipeline import (
    DatasetSpec,
    Node,
    OutputSpec,
    Pipeline,
    Reference,
)


@pytest.fixture
def csv_path(tmp_path) -> Path:
    p = tmp_path / "tiny.csv"
    p.write_text(
        "id,name,country\n"
        "1,Alice,US\n"
        "2,Bob,UK\n"
        "3,Carol,DE\n"
        "4,Dan,US\n"
        "5,Eli,UK\n"
    )
    return p


def test_lineage_flows_through_filter_sort(csv_path, monkeypatch, tmp_path):
    # Re-route the data dir so output goes under tmp.
    from dig.storage import files as files_mod
    monkeypatch.setattr(files_mod, "data_dir", lambda: tmp_path)

    p = Pipeline(
        id=str(ULID()),
        name="lineage-smoke",
        datasets=[DatasetSpec(id="ds", connector="csv", uri=f"file://{csv_path}")],
        nodes=[
            Node(
                id="n_filter",
                step="filter_rows",
                stepVersion="1.0.0",
                inputs={"in": Reference(ref="ds")},
                params={"predicate": "country = 'US'"},
            ),
            Node(
                id="n_sort",
                step="sort_rows",
                stepVersion="1.0.0",
                inputs={"in": Reference(ref="n_filter")},
                params={"sortBy": [{"column": "id", "descending": False}]},
            ),
        ],
        outputs=[
            OutputSpec(
                id="o", name="out",
                **{"from": Reference(ref="n_sort", port="out")},
            )
        ],
        metadata={"trackLineage": True},
    )

    res = execute(p, run_id=str(ULID()))
    out = pl.read_parquet(next(iter(res.outputs.values())))

    lineage_cols = [c for c in out.columns if c.startswith(LINEAGE_COL_PREFIX)]
    assert lineage_cols, "lineage column missing — flag not honored"

    # Both US rows from the source should survive the filter, sorted by id.
    assert out.height == 2
    assert out.get_column("id").to_list() == [1, 4]
    # Source row indices are 1-based: Alice is row 1, Dan is row 4.
    assert out.get_column(lineage_cols[0]).to_list() == [1, 4]
