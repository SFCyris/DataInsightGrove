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
# Year names like `2024` are common pivot-export headers — they shouldn't
# get classified as numeric data on the row-0 side. We carve them out with
# a separate pattern so `_looks_like_header` can keep them as candidate
# header tokens while still rejecting longer numeric strings (`2024.5`,
# `1234567`) as data.
_BARE_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?$")
_BOOL_RE = re.compile(r"^(true|false|yes|no|y|n)$", re.IGNORECASE)


def _strip_thousands_separators(s: str) -> str:
    """Strip `,` only when used as a thousands separator (i.e. between
    digit triples). The naive `.replace(",", "")` matched `'1,2,3'` —
    a literal CSV cell with commas — and called it numeric data."""
    if "," not in s:
        return s
    # Match `<digit><,><3 digits>` repeating. If the whole string is shaped
    # like `1,234,567(.89)?`, strip the commas; otherwise leave as-is.
    if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", s):
        return s.replace(",", "")
    return s


def _looks_like_data(s: Any, *, allow_year: bool = True) -> bool:
    """True if the string parses as numeric / date / boolean — i.e. it
    looks like a data value, not a column name.

    `allow_year=False` excludes bare 4-digit years (`2024`) — used when
    we're testing row 0 for header-shape, since pivot-export headers
    commonly look like that.
    """
    if s is None:
        return False
    if isinstance(s, (int, float, bool)):
        return True
    s_str = str(s).strip()
    if not s_str:
        return False
    if not allow_year and _BARE_YEAR_RE.match(s_str):
        return False
    return bool(
        _NUMERIC_RE.match(_strip_thousands_separators(s_str))
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
    # Bare 4-digit years are valid pivot-table headers, so don't reject them
    # as "data" when scoring header-shape.
    if _looks_like_data(s_str, allow_year=False):
        return False
    # Field-name shape: not too long, no commas/quotes, mostly identifier chars.
    if len(s_str) > 100:
        return False
    return True


_DATA_FRAC_THRESHOLD = 0.7  # "rows 1+ look data-shaped" requires this fraction


def detect_header(sample_no_header: pl.DataFrame, *, threshold: float = 0.5) -> bool:
    """Given a sample read WITHOUT a header, return True if row 0 looks
    like a header. Vote per-column; majority wins.

    A column votes "header" when row 0 looks header-shaped AND ≥70% of
    rows 1+ look data-shaped. Columns where both row 0 and rows 1+ are
    strings (no signal) abstain rather than vote.
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
        # Bare-year column names (`2024`) are common in pivot exports; treat
        # them as header candidates by skipping the numeric-as-data check
        # for row 0 specifically.
        first_is_data = _looks_like_data(first, allow_year=False)
        first_is_header = _looks_like_header(first)
        rest_data_frac = sum(1 for v in rest if _looks_like_data(v)) / len(rest)

        if first_is_header and rest_data_frac > _DATA_FRAC_THRESHOLD and not first_is_data:
            # row-0 reads as a name, rest reads as numbers/dates → header
            header_votes += 1
        elif first_is_data and rest_data_frac > _DATA_FRAC_THRESHOLD:
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
