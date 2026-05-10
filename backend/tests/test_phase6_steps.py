"""Parity tests for the 9 Phase-6 steps added to broaden the toolkit."""

from __future__ import annotations

import duckdb
import pytest

from dig.engine.registry import steps


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(":memory:")
    c.execute("""
        CREATE TABLE customers AS SELECT * FROM (VALUES
          (1, 'Alice  Smith ', 'US,Pro,99', '2024-01-15', 1234.50, 'a'),
          (2, ' Bob ',          'UK,Free,0', '2024-02-20',   89.00, 'b'),
          (3, 'Carol',          'DE,Pro,99', '2024-03-05', NULL,    'a'),
          (4, 'Dan',            'US,Team,499','2024-04-10', 3300.99, 'c'),
          (5, 'Eli',            'UK,Pro,99',  '2024-05-22',   15.00, 'b'),
          (6, 'Alice  Smith ',  'US,Pro,99',  '2024-01-15', 1234.50, 'a')  -- duplicate
        ) AS t(id, name, raw, signup_str, balance, tier);
        CREATE TABLE c2 AS SELECT id, CAST(NULL AS VARCHAR) AS phone, name AS email, name FROM customers;
    """)
    return c


def _run(con, step_id, params, src='"customers"', port="in"):
    step = steps().get(step_id)
    sql = step.to_sql(params, {port: src})
    return con.execute(sql).fetchall()


def test_replace_text_plain(con):
    rows = _run(con, "replace_text",
                {"column": "name", "find": "Alice", "replace": "Alicia"})
    names = [r[1] for r in rows]
    assert any("Alicia" in n for n in names)
    assert not any("Alice" in n and "Alicia" not in n for n in names)


def test_replace_text_regex(con):
    rows = _run(con, "replace_text",
                {"column": "name", "find": r"\s+", "replace": " ", "regex": True})
    names = [r[1] for r in rows if r[1]]
    # Multiple internal spaces should be collapsed by the regex.
    assert all("  " not in n for n in names)


def test_split_column(con):
    sql = steps().get("split_column").to_sql(
        {"column": "raw", "delimiter": ",", "parts": 3, "drop": False},
        {"in": '"customers"'},
    )
    rows = con.execute(sql).fetchall()
    desc = con.execute(sql).description
    cols = [d[0] for d in desc]
    assert "raw_1" in cols and "raw_2" in cols and "raw_3" in cols
    # Verify split values
    by_id = {r[0]: r for r in rows}
    raw_cols_idx = [cols.index(c) for c in ("raw_1", "raw_2", "raw_3")]
    assert tuple(by_id[1][i] for i in raw_cols_idx) == ("US", "Pro", "99")


def test_extract_pattern(con):
    sql = steps().get("extract_pattern").to_sql(
        {"column": "raw", "pattern": "([A-Z]{2})", "group": 1, "as": "country"},
        {"in": '"customers"'},
    )
    rows = con.execute(sql).fetchall()
    desc = con.execute(sql).description
    cols = [d[0] for d in desc]
    assert "country" in cols
    countries = [r[cols.index("country")] for r in rows]
    assert {"US", "UK", "DE"} <= set(countries)


def test_clean_whitespace_trim(con):
    rows = _run(con, "clean_whitespace",
                {"column": "name", "collapse": False, "lowercase": False})
    # Row 2 was ' Bob ', should now be 'Bob'.
    by_id = {r[0]: r for r in rows}
    assert by_id[2][1] == "Bob"


def test_clean_whitespace_collapse_lower(con):
    rows = _run(con, "clean_whitespace",
                {"column": "name", "collapse": True, "lowercase": True})
    by_id = {r[0]: r for r in rows}
    assert by_id[1][1] == "alice smith"


def test_deduplicate_by_key(con):
    rows = _run(con, "deduplicate", {"key": ["name"]})
    names = [r[1] for r in rows]
    assert len(names) == len(set(names)), "duplicates remain after dedupe"


def test_deduplicate_whole_row(con):
    # Run on the SELECT-without-id projection so 1 and 6 are actual duplicates.
    sql = steps().get("deduplicate").to_sql(
        {}, {"in": "(SELECT name, raw, signup_str, balance, tier FROM customers)"},
    )
    rows = con.execute(sql).fetchall()
    # Without the id column, rows 1 and 6 collapse to one.
    assert len(rows) == 5


def test_bin_numeric_custom(con):
    sql = steps().get("bin_numeric").to_sql(
        {"column": "balance", "mode": "custom_breaks",
         "breaks": "0,100,1000,5000", "as": "tier"},
        {"in": '"customers"'},
    )
    rows = con.execute(sql).fetchall()
    desc = con.execute(sql).description
    tier_idx = [d[0] for d in desc].index("tier")
    tiers = [r[tier_idx] for r in rows if r[tier_idx] is not None]
    # We should see at least 2 distinct tiers
    assert len(set(tiers)) >= 2


def test_extract_date_parts(con):
    # cast str to date first
    con.execute("CREATE OR REPLACE TABLE customers_dt AS "
                "SELECT *, CAST(signup_str AS DATE) AS signup FROM customers")
    sql = steps().get("extract_date_parts").to_sql(
        {"column": "signup", "parts": ["year", "month", "dayofweek"]},
        {"in": '"customers_dt"'},
    )
    rows = con.execute(sql).fetchall()
    desc = con.execute(sql).description
    cols = [d[0] for d in desc]
    assert "signup_year" in cols and "signup_month" in cols and "signup_dayofweek" in cols
    yi = cols.index("signup_year")
    assert all(r[yi] == 2024 for r in rows)


def test_sample_rows_head(con):
    rows = _run(con, "sample_rows", {"kind": "head", "n": 3})
    assert len(rows) == 3
    assert [r[0] for r in rows] == [1, 2, 3]


def test_sample_rows_random_n(con):
    rows = _run(con, "sample_rows", {"kind": "random_n", "n3": 4, "seed": 42})
    assert len(rows) == 4


def test_coalesce_columns(con):
    sql = steps().get("coalesce_columns").to_sql(
        {"columns": ["phone", "email"], "as": "contact", "drop": False},
        {"in": '"c2"'},
    )
    rows = con.execute(sql).fetchall()
    desc = con.execute(sql).description
    cols = [d[0] for d in desc]
    ci = cols.index("contact")
    # All rows: phone is NULL, so coalesce should pick email.
    contacts = [r[ci] for r in rows]
    assert all(c is not None for c in contacts)


def test_window_aggregate_running_sum(con):
    sql = steps().get("window_aggregate").to_sql(
        {"fn": "sum", "column": "balance",
         "partitionBy": ["tier"], "orderBy": ["id"],
         "as": "running"},
        {"in": '"customers"'},
    )
    rows = con.execute(sql).fetchall()
    desc = con.execute(sql).description
    ri = [d[0] for d in desc].index("running")
    # For tier 'b' (rows 2 and 5): 89.00, then 89.00 + 15.00 = 104.00
    by_id = {r[0]: r for r in rows}
    assert float(by_id[2][ri]) == pytest.approx(89.0)
    assert float(by_id[5][ri]) == pytest.approx(104.0)


def test_window_aggregate_row_number(con):
    sql = steps().get("window_aggregate").to_sql(
        {"fn": "row_number", "partitionBy": ["tier"], "orderBy": ["id"],
         "as": "rn"},
        {"in": '"customers"'},
    )
    rows = con.execute(sql).fetchall()
    desc = con.execute(sql).description
    ri = [d[0] for d in desc].index("rn")
    by_id = {r[0]: r for r in rows}
    # Tier 'b' has rows 2 and 5; rn should be 1, 2 in id order
    assert by_id[2][ri] == 1 and by_id[5][ri] == 2
