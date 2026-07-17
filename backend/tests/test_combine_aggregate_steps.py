"""Parity tests for the combine/aggregate steps."""

from __future__ import annotations

import duckdb
import pytest

from dig.engine.registry import steps


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    c.execute("""
        CREATE TABLE customers AS SELECT * FROM (VALUES
          (1, 'Alice', 'US'), (2, 'Bob', 'UK'), (3, 'Carol', 'DE'),
          (4, 'Dan', 'US'),  (5, 'Eli', 'UK')
        ) AS t(id, name, country);
        CREATE TABLE orders AS SELECT * FROM (VALUES
          (101, 1, 100.0), (102, 1, 50.0), (103, 2, 200.0),
          (104, 4, 75.0),  (105, 4, 25.0), (106, 99, 1.0)
        ) AS t(order_id, customer_id, amount);
        CREATE TABLE wide AS SELECT * FROM (VALUES
          ('Q1', 1, 10, 20),
          ('Q2', 1, 30, 40),
          ('Q1', 2, 50, 60)
        ) AS t(quarter, region, sales, cost);
    """)
    return c


def test_join_inner(con):
    sql = steps().get("join").to_sql(
        {"how": "inner", "on": [{"left": "id", "right": "customer_id"}]},
        {"left": '"customers"', "right": '"orders"'},
    )
    rows = con.execute(sql).fetchall()
    customer_ids = sorted({r[0] for r in rows})
    # Customers 1 (2 orders), 2 (1), 4 (2) match. 99 in orders has no customer match.
    assert customer_ids == [1, 2, 4]
    assert len(rows) == 5


def test_join_left_includes_unmatched_left(con):
    sql = steps().get("join").to_sql(
        {"how": "left", "on": [{"left": "id", "right": "customer_id"}]},
        {"left": '"customers"', "right": '"orders"'},
    )
    rows = con.execute(sql).fetchall()
    customer_ids = sorted({r[0] for r in rows})
    # All 5 customers appear (3, 5 with NULL right side).
    assert customer_ids == [1, 2, 3, 4, 5]


def test_union_all_stacks(con):
    sql = steps().get("union").to_sql(
        {"distinct": False},
        {"top": '"customers"', "bottom": '"customers"'},
    )
    rows = con.execute(sql).fetchall()
    assert len(rows) == 10  # 5 + 5


def test_union_distinct_dedupes(con):
    sql = steps().get("union").to_sql(
        {"distinct": True},
        {"top": '"customers"', "bottom": '"customers"'},
    )
    rows = con.execute(sql).fetchall()
    assert len(rows) == 5


def test_group_aggregate(con):
    sql = steps().get("group_aggregate").to_sql(
        {
            "groupBy": ["country"],
            "aggregates": [
                {"fn": "count", "column": None, "as": "n"},
                {"fn": "sum", "column": "id", "as": "id_sum"},
            ],
        },
        {"in": '"customers"'},
    )
    rows = con.execute(sql).fetchall()
    by_country = {r[0]: r for r in rows}
    assert by_country["US"][1] == 2
    assert by_country["UK"][1] == 2
    assert by_country["DE"][1] == 1


def test_pivot_wider(con):
    sql = steps().get("pivot_wider").to_sql(
        {"id": ["region"], "names": "quarter", "values": "sales", "agg": "sum"},
        {"in": '"wide"'},
    )
    rows = con.execute(sql).fetchall()
    desc = con.execute(sql).description
    cols = [d[0] for d in desc]
    # Should include region + Q1 + Q2.
    assert "region" in cols
    assert "Q1" in cols and "Q2" in cols


def test_pivot_longer(con):
    sql = steps().get("pivot_longer").to_sql(
        {
            "id": ["quarter", "region"],
            "value_cols": ["sales", "cost"],
            "names_to": "metric",
            "values_to": "amount",
        },
        {"in": '"wide"'},
    )
    rows = con.execute(sql).fetchall()
    desc = con.execute(sql).description
    cols = [d[0] for d in desc]
    assert cols == ["quarter", "region", "metric", "amount"]
    # 3 rows × 2 value cols = 6 long rows
    assert len(rows) == 6
