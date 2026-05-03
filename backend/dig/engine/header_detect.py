"""Heuristic: does this CSV/TSV/Excel sample have a header row?

The trick: read a few dozen rows WITHOUT a header (so polars assigns
positional names) and look at row 0 vs the rest. If row 0 is non-numeric
where the rest of the column is mostly numeric / date-like, that's a
header row. Majority vote across columns; ties default to "no header"
(safer — never silently drop a data row, the user can override).

Limitations:
  - All-string datasets have no signal (header & data both look stringy);
    we can't tell, so we report no header. The user picks manually.
  - Single-row datasets — no comparison possible; report no header.
  - Mixed-type rows where row 0 has numerics in some cells (e.g. an "ID"
    field) confuse the heuristic; the per-column vote helps but not always.

Returns the renamed-frame: when has_header was False, the columns become
`col_1, col_2, …` (one-indexed, snake-case) instead of polars' default
`column_1, column_2, …`. The user gets predictable names regardless.
"""

from __future__ import annotations

import re
from typing import Any

import polars as pl

# Patterns that say "this string is data, not a column name".
_NUMERIC_RE = re.compile(r"^-?\d+(?:[,.]\d+)?(?:[eE][+-]?\d+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?$")
_BOOL_RE = re.compile(r"^(true|false|yes|no|y|n)$", re.IGNORECASE)


def _looks_like_data(s: Any) -> bool:
    """True if the string parses as numeric / date / boolean — i.e. it
    looks like a data value, not a column name."""
    if s is None:
        return False
    if isinstance(s, (int, float, bool)):
        return True
    s_str = str(s).strip()
    if not s_str:
        return False
    return bool(
        _NUMERIC_RE.match(s_str.replace(",", ""))
        or _DATE_RE.match(s_str)
        or _BOOL_RE.match(s_str),
    )


def _looks_like_header(s: Any) -> bool:
    """True if the string looks more like a column name than a data value."""
    if s is None:
        return False
    s_str = str(s).strip()
    if not s_str:
        return False
    if _looks_like_data(s_str):
        return False
    # Field-name shape: not too long, no commas/quotes, mostly identifier chars.
    if len(s_str) > 100:
        return False
    return True


def detect_header(sample_no_header: pl.DataFrame, *, threshold: float = 0.5) -> bool:
    """Given a sample read WITHOUT a header, return True if row 0 looks
    like a header. Vote per-column; majority wins.

    A column votes "header" when row 0 looks header-shaped AND a meaningful
    fraction (>50%) of rows 1+ look data-shaped. Columns where both row 0
    and rows 1+ are strings (no signal) abstain rather than vote.
    """
    if sample_no_header.height < 2 or sample_no_header.width == 0:
        return False

    header_votes = 0
    abstentions = 0
    for col in sample_no_header.columns:
        # Polars returns None for missing values; cast to Utf8 for inspection.
        try:
            series = sample_no_header.get_column(col).cast(pl.Utf8, strict=False)
        except Exception:
            abstentions += 1
            continue
        first = series[0]
        rest = [v for v in series[1:].to_list() if v is not None]
        if not rest:
            abstentions += 1
            continue
        first_is_data = _looks_like_data(first)
        first_is_header = _looks_like_header(first)
        rest_data_frac = sum(1 for v in rest if _looks_like_data(v)) / len(rest)

        if first_is_header and rest_data_frac > 0.7 and not first_is_data:
            # row-0 reads as a name, rest reads as numbers/dates → header
            header_votes += 1
        elif first_is_data and rest_data_frac > 0.7:
            # row-0 is data, rest is data → no header for this column
            pass
        else:
            # ambiguous (all-string, all-blank, type-mixed) — abstain
            abstentions += 1

    voting_cols = sample_no_header.width - abstentions
    if voting_cols == 0:
        return False
    return (header_votes / voting_cols) >= threshold


def rename_to_col_n(df: pl.DataFrame | pl.LazyFrame) -> pl.DataFrame | pl.LazyFrame:
    """Rename columns to col_1, col_2, … — used when the source has no
    header so the user gets predictable names. Polars' default is
    column_1 / column_2, which we override for consistency with DIG's
    docs and to keep names short."""
    schema = df.collect_schema() if isinstance(df, pl.LazyFrame) else df.schema
    mapping = {c: f"col_{i + 1}" for i, c in enumerate(schema.names())}
    return df.rename(mapping)
