"""Meta-types: logical types layered on top of physical storage.

DIG's physical types are the standard SQL/Polars set (integer, double,
string, boolean, date, datetime). Meta-types add semantic constraints that
tools like the grid can use to flag bad data at a glance:

  - **index**:    integer column where every value should be unique. The
                  grid renders duplicates in red.
  - **timezone**: string column constrained to IANA zone names (e.g.
                  "America/New_York"). The grid renders invalid entries
                  in red.

Detection is best-effort and probabilistic — see profile.py for the
auto-detection pass that promotes columns to meta-types when their
distribution clearly fits.
"""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def iana_timezones() -> frozenset[str]:
    """Return the canonical IANA timezone set.

    Uses Python 3.9+'s `zoneinfo` (system tzdata). Adds a couple of common
    aliases (UTC, GMT) that everyone expects to validate even though the
    formal IANA db classifies them slightly differently.
    """
    try:
        from zoneinfo import available_timezones
        zones = set(available_timezones())
    except Exception:
        zones = set()
    zones |= {"UTC", "GMT", "Z"}
    return frozenset(zones)


def is_valid_timezone(value: str | None) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return value in iana_timezones()


# Detection thresholds. Tuned conservatively — we'd rather miss a few than
# over-promote columns into meta-types that the user didn't ask for.
INDEX_MIN_DISTINCT_FRACTION = 0.999  # ≥99.9% unique → call it an index
INDEX_MIN_NON_NULL_FRACTION = 0.999  # ≥99.9% non-null
TIMEZONE_MIN_VALID_FRACTION = 0.80   # ≥80% IANA-valid strings → timezone


def detect_index(*, distinct: int | None, non_null: int | None, sampled: int | None) -> bool:
    """Should an integer column be promoted to 'index'?"""
    if not sampled or distinct is None or non_null is None:
        return False
    if non_null < 2:  # not enough signal
        return False
    return (
        non_null / sampled >= INDEX_MIN_NON_NULL_FRACTION
        and distinct / non_null >= INDEX_MIN_DISTINCT_FRACTION
    )


def detect_timezone_from_top(top_values: list[dict]) -> bool:
    """Should a string column be promoted to 'timezone'?

    We only have top_k values from the profile, not every cell. Count-weight
    the validity check — a column that's 99% IANA-valid by row count but
    has one stray bad value in its top_values shouldn't be disqualified
    just because the long-tail bad value happens to be visible.
    """
    if not top_values:
        return False
    valid_rows = 0
    total_rows = 0
    for tv in top_values:
        v = tv.get("value")
        n = int(tv.get("count") or 0)
        if not isinstance(v, str):
            continue
        total_rows += n
        if is_valid_timezone(v):
            valid_rows += n
    if total_rows == 0:
        return False
    return valid_rows / total_rows >= TIMEZONE_MIN_VALID_FRACTION
