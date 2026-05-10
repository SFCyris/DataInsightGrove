"""Parity tests for the 6 Phase-2 steps.

For each step, we compile a small SQL using the step's `to_sql()` and execute
it against an in-memory DuckDB. The expected output is golden — defined inline.
This is the load-bearing test for browser/backend parity: the same SQL runs
unchanged in DuckDB-WASM, so if the backend matches the golden hash, the
browser will too.
"""

from __future__ import annotations

import duckdb
import pytest

from dig.engine.registry import steps


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    c.execute("""
        CREATE TABLE customers AS SELECT * FROM (VALUES
          (1, 'Alice', 'US', 34, true,  1234.50),
          (2, 'Bob',   'UK', 28, true,   890.00),
          (3, 'Carol', 'DE', 41, false, NULL),
          (4, 'Dan',   'US', 52, true,  3300.99),
          (5, 'Eli',   'UK', 19, true,    15.00)
        ) AS t(id, name, country, age, is_active, balance)
    """)
    return c


def _run(con: duckdb.DuckDBPyConnection, step_id: str, params: dict, src: str = "customers") -> list[tuple]:
    step = steps().get(step_id)
    sql = step.to_sql(params, {"in": f'"{src}"'})
    return con.execute(sql).fetchall()


def test_filter_rows(con):
    rows = _run(con, "filter_rows", {"predicate": "is_active = true AND age >= 30"})
    ids = sorted(r[0] for r in rows)
    assert ids == [1, 4]


def test_select_columns(con):
    rows = _run(con, "select_columns", {"columns": ["id", "name", "country"]})
    assert rows[0] == (1, "Alice", "US")
    assert len(rows[0]) == 3


def test_rename_columns(con):
    sql = steps().get("rename_columns").to_sql(
        {"mapping": [{"from": "name", "to": "customer_name"}, {"from": "country", "to": "iso"}]},
        {"in": '"customers"'},
    )
    desc = con.execute(sql).description
    cols = [d[0] for d in desc]
    assert "customer_name" in cols
    assert "iso" in cols
    assert "name" not in cols


def test_cast_type_string(con):
    sql = steps().get("cast_type").to_sql(
        {"column": "age", "targetType": "string", "strict": False},
        {"in": '"customers"'},
    )
    desc = con.execute(sql).description
    age_type = next(d[1] for d in desc if d[0] == "age")
    # DuckDB reports VARCHAR; in some versions STRING. Accept either.
    assert age_type in ("STRING", "VARCHAR")


def test_derive_column(con):
    rows = _run(con, "derive_column", {"name": "tax", "expression": "balance * 0.07"})
    by_id = {r[0]: r for r in rows}
    # Row 1 balance 1234.50 -> tax 86.415. DuckDB returns Decimal for NUMERIC * literal.
    assert float(by_id[1][-1]) == pytest.approx(86.415, rel=1e-9)
    # NULL balance propagates to NULL tax.
    assert by_id[3][-1] is None


def test_sort_rows_desc(con):
    rows = _run(con, "sort_rows", {"by": [{"column": "balance", "direction": "desc"}]})
    # NULLs land at the end with default DuckDB ordering ('NULLS LAST' for DESC).
    non_null_balances = [r[5] for r in rows if r[5] is not None]
    assert non_null_balances == sorted(non_null_balances, reverse=True)


@pytest.fixture(scope="module")
def abcd_con():
    """Mixed-type table for reorder_columns: integer, string, double, date.

    Kept separate from `customers` so the column names match what the user-facing
    docs and the `order: ["c", "a"]` example in the step manifest reference."""
    c = duckdb.connect(":memory:")
    c.execute("""
        CREATE TABLE abcd AS SELECT * FROM (VALUES
          (1,  'alpha',   1.5,  DATE '2026-01-01'),
          (2,  'bravo',   2.5,  DATE '2026-01-02'),
          (3,  'charlie', 3.5,  DATE '2026-01-03'),
          (4,  'delta',   4.5,  DATE '2026-01-04'),
          (5,  'echo',    5.5,  DATE '2026-01-05'),
          (6,  'foxtrot', 6.5,  DATE '2026-01-06'),
          (7,  'golf',    7.5,  DATE '2026-01-07'),
          (8,  'hotel',   8.5,  DATE '2026-01-08'),
          (9,  'india',   9.5,  DATE '2026-01-09'),
          (10, 'juliet', 10.5,  DATE '2026-01-10')
        ) AS t(a, b, c, d)
    """)
    return c


def test_reorder_columns(abcd_con):
    """`order: ["c", "a"]` on an [a, b, c, d] table -> [c, a, b, d].

    Listed columns appear first in the listed order; unlisted columns are
    appended in their original input order (DuckDB `* EXCLUDE (...)` semantics).
    """
    sql = steps().get("reorder_columns").to_sql(
        {"order": ["c", "a"]},
        {"in": '"abcd"'},
    )
    cur = abcd_con.execute(sql)
    cols = [d[0] for d in cur.description]
    assert cols == ["c", "a", "b", "d"]
    rows = cur.fetchall()
    assert len(rows) == 10
    # Spot-check first row reflects the new column order: c=1.5, a=1, b='alpha', d=2026-01-01.
    import datetime as _dt
    assert rows[0] == (1.5, 1, "alpha", _dt.date(2026, 1, 1))


def test_reorder_columns_empty_order_passes_through(abcd_con):
    """An empty `order` is a no-op: original column order preserved."""
    sql = steps().get("reorder_columns").to_sql({"order": []}, {"in": '"abcd"'})
    cols = [d[0] for d in abcd_con.execute(sql).description]
    assert cols == ["a", "b", "c", "d"]


def test_reorder_columns_browser_parity(tmp_path):
    """Backend (`compile_to_sql`) and browser (`compile_for_browser`) must
    produce byte-identical output for a pipeline that includes reorder_columns.

    Same shape as `test_backend_vs_browser_compile_parity` but exercises the
    new step. The two paths only differ in how dataset CTEs are formed, so any
    divergence here would point at reorder_columns' SQL emission."""
    import polars as pl

    from dig.engine.compile import compile_for_browser
    from dig.engine.executor import compile_to_sql
    from dig.engine.pipeline import (
        DatasetSpec, Node, OutputSpec, Pipeline, Reference,
    )

    fixture = tmp_path / "abcd.parquet"
    pl.DataFrame({
        "a": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "b": ["alpha", "bravo", "charlie", "delta", "echo",
              "foxtrot", "golf", "hotel", "india", "juliet"],
        "c": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5],
        "d": pl.date_range(
            __import__("datetime").date(2026, 1, 1),
            __import__("datetime").date(2026, 1, 10),
            interval="1d",
            eager=True,
        ),
    }).write_parquet(fixture)

    p = Pipeline(
        id="reorder_parity_test",
        name="ReorderParity",
        datasets=[DatasetSpec(id="ds", connector="parquet", uri=f"file://{fixture}")],
        nodes=[
            Node(id="n_reorder", step="reorder_columns", stepVersion="1.0.0",
                 inputs={"in": Reference(ref="ds")}, outputs=["out"],
                 params={"order": ["c", "a"]}),
        ],
        outputs=[OutputSpec.model_validate(
            {"id": "o", "name": "x", "from": {"ref": "n_reorder"}}
        )],
    )

    backend_sql = compile_to_sql(p)
    browser = compile_for_browser(p)
    browser_sql_runnable = browser.sql.replace(
        "'ds.parquet'", f"'{fixture}'"
    )

    backend_cur = duckdb.connect().execute(backend_sql)
    browser_cur = duckdb.connect().execute(browser_sql_runnable)
    backend_cols = [d[0] for d in backend_cur.description]
    browser_cols = [d[0] for d in browser_cur.description]
    backend_rows = backend_cur.fetchall()
    browser_rows = browser_cur.fetchall()

    assert backend_cols == browser_cols == ["c", "a", "b", "d"]
    assert backend_rows == browser_rows, "backend and browser-target SQL diverged"


def test_chained_pipeline(con):
    """Chain filter -> derive -> select -> sort, verify final shape and ordering."""
    s_filter = steps().get("filter_rows")
    s_derive = steps().get("derive_column")
    s_select = steps().get("select_columns")
    s_sort = steps().get("sort_rows")

    cust = '"customers"'
    a = '"a"'
    b = '"b"'
    c = '"c"'
    body_a = s_filter.to_sql({"predicate": "is_active = true AND age >= 25"}, {"in": cust})
    body_b = s_derive.to_sql({"name": "tax", "expression": "balance * 0.07"}, {"in": a})
    body_c = s_select.to_sql({"columns": ["id", "name", "balance", "tax"]}, {"in": b})
    body_d = s_sort.to_sql({"by": [{"column": "balance", "direction": "desc"}]}, {"in": c})
    sql = (
        f"WITH a AS ({body_a}), "
        f"     b AS ({body_b}), "
        f"     c AS ({body_c}), "
        f"     d AS ({body_d}) "
        f"SELECT * FROM d"
    )
    rows = con.execute(sql).fetchall()
    # 1, 2, 4 are active and >=25 (5 is 19, 3 inactive). 3 expected.
    assert len(rows) == 3
    # Sorted desc by balance: 4 (3300.99), 1 (1234.50), 2 (890.00)
    assert [r[0] for r in rows] == [4, 1, 2]
    # tax of row 4 (balance 3300.99) -> 231.0693
    assert float(rows[0][3]) == pytest.approx(231.0693, rel=1e-9)


def test_backend_vs_browser_compile_parity(tmp_path):
    """The SQL produced by compile_to_sql (backend) and compile_for_browser
    (DuckDB-WASM target) must produce byte-identical results when run on the
    same dataset. The two paths only differ in how dataset CTEs are formed
    (real path vs virtual file name)."""
    import polars as pl

    from dig.engine.compile import compile_for_browser
    from dig.engine.executor import compile_to_sql
    from dig.engine.pipeline import (
        DatasetSpec, Node, OutputSpec, Pipeline, Reference,
    )

    # Materialize a small fixture parquet.
    fixture = tmp_path / "fixture.parquet"
    pl.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "value": [10.0, 20.0, 30.0, 40.0, 50.0],
        "tag": ["a", "a", "b", "b", "c"],
    }).write_parquet(fixture)

    p = Pipeline(
        id="parity_test",
        name="Parity",
        datasets=[DatasetSpec(id="ds", connector="parquet", uri=f"file://{fixture}")],
        nodes=[
            Node(id="n_filter", step="filter_rows", stepVersion="1.0.0",
                 inputs={"in": Reference(ref="ds")}, outputs=["out"],
                 params={"predicate": "value >= 20"}),
            Node(id="n_derive", step="derive_column", stepVersion="1.0.0",
                 inputs={"in": Reference(ref="n_filter")}, outputs=["out"],
                 params={"name": "v2", "expression": "value * 2"}),
            Node(id="n_sort", step="sort_rows", stepVersion="1.0.0",
                 inputs={"in": Reference(ref="n_derive")}, outputs=["out"],
                 params={"by": [{"column": "id", "direction": "asc"}]}),
        ],
        outputs=[OutputSpec.model_validate(
            {"id": "o", "name": "x", "from": {"ref": "n_sort"}}
        )],
    )

    backend_sql = compile_to_sql(p)
    browser = compile_for_browser(p)
    # Substitute the virtual filename with the real fixture path so we can run
    # the "browser" SQL through native DuckDB and compare to the backend output.
    browser_sql_runnable = browser.sql.replace(
        "'ds.parquet'", f"'{fixture}'"
    )

    backend_rows = duckdb.connect().execute(backend_sql).fetchall()
    browser_rows = duckdb.connect().execute(browser_sql_runnable).fetchall()
    assert backend_rows == browser_rows, "backend and browser-target SQL diverged"


def test_compile_for_browser_smoke():
    """compile_for_browser should produce SQL that's runnable as-is on DuckDB."""
    from dig.engine.compile import compile_for_browser
    from dig.engine.pipeline import (
        DatasetSpec, Node, OutputSpec, Pipeline, Reference,
    )

    p = Pipeline(
        id="x",
        name="t",
        datasets=[
            DatasetSpec(
                id="ds",
                connector="parquet",
                uri="file:///tmp/__no_such_file__.parquet",
            )
        ],
        nodes=[
            Node(
                id="n_filter", step="filter_rows", stepVersion="1.0.0",
                inputs={"in": Reference(ref="ds")}, outputs=["out"],
                params={"predicate": "id > 0"},
            )
        ],
        outputs=[OutputSpec.model_validate({"id": "o", "name": "x", "from": {"ref": "n_filter"}})],
    )
    res = compile_for_browser(p)
    # SQL must reference the virtual filename, and be a valid SELECT.
    assert "ds.parquet" in res.sql
    assert "WITH" in res.sql
    assert res.terminal == "n_filter"
    assert len(res.files) == 1
    assert res.files[0].format == "parquet"
