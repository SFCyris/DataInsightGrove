"""Detect rectangular data-islands on a single Excel worksheet.

A "data island" is a contiguous block of non-empty cells separated from
other content by entirely empty rows or columns. Two common shapes:

  - Stacked tables:                     - Side-by-side tables:
      |-------|                            |-------|  |-------|
      | A     |                            | A     |  | B     |
      | A     |                            | A     |  | B     |
      |-------|                            |-------|  |-------|
      (blank row)
      |-------|
      | B     |
      | B     |
      |-------|

Algorithm (intentionally simple — ~20 lines of real logic):

  1. Build a 2-D boolean mask of "cell has content".
  2. Find horizontal cuts: rows that are entirely empty.
  3. Each contiguous run of non-empty rows is one "row band".
  4. Inside each row band, find vertical cuts: columns that are empty
     across the whole band.
  5. Each contiguous run of non-empty columns inside a band is one
     island. Bounding box = (band rows) × (column run).

This handles real-world cases well:
  - Sporadic missing cells inside a table → still one island (the column
    is non-empty across the band even if individual cells are blank).
  - Two tables touching with no gap → ONE island. The user can split
    them downstream with `select_columns` / `slice_rows` if needed —
    no good way to detect this case automatically (looks identical to
    one wide table).
  - Header row (row of labels) directly above a blank row → that label
    row becomes its own tiny island. Filtered out via min-size below.

The minimum-island filter rejects 1-row OR 1-column rectangles by
default — pure-1D ranges are usually a stray label, not a table.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class DataIsland:
    """One detected rectangular block, 0-indexed inclusive bounds."""
    top_row: int
    bottom_row: int
    left_col: int
    right_col: int
    n_rows: int
    n_cols: int
    range_a1: str           # Excel A1 notation, e.g. "B2:F50"
    preview_first_row: list[str | None]  # first row of cells (capped to 12 cols)
    density: float          # filled-cells / bbox-cells, 0..1

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _is_filled(v: Any) -> bool:
    """A cell counts as 'filled' when it's not None and not all whitespace."""
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    return True  # numbers, booleans, dates — all filled


def _col_letter(n: int) -> str:
    """0-indexed column number → Excel letters. 0=A, 25=Z, 26=AA, …"""
    s = ""
    n += 1  # internal 1-indexed for the algorithm
    while n > 0:
        n -= 1
        s = chr(ord("A") + n % 26) + s
        n //= 26
    return s


def excel_range(top: int, left: int, bottom: int, right: int) -> str:
    """0-indexed (row, col) bounds → Excel A1 range, e.g. (1, 1, 49, 5) → 'B2:F50'."""
    return f"{_col_letter(left)}{top + 1}:{_col_letter(right)}{bottom + 1}"


def parse_excel_range(range_str: str) -> tuple[int, int, int, int]:
    """Parse 'B2:F50' → (top_row=1, left_col=1, bottom_row=49, right_col=5).
    All output indices are 0-based inclusive. Raises ValueError on bad input."""
    if not isinstance(range_str, str) or ":" not in range_str:
        raise ValueError(f"invalid range {range_str!r}: expected 'A1:Z99' format")
    left, right = range_str.split(":", 1)
    return (*_parse_a1_cell(left), *_parse_a1_cell(right))[::1]  # type: ignore[return-value]


def _parse_a1_cell(s: str) -> tuple[int, int]:
    """'B2' → (1, 1) — (row, col), 0-indexed."""
    s = s.strip().upper()
    i = 0
    while i < len(s) and s[i].isalpha():
        i += 1
    if i == 0 or i == len(s):
        raise ValueError(f"invalid cell {s!r}")
    col_letters, row_str = s[:i], s[i:]
    try:
        row = int(row_str) - 1
    except ValueError as e:
        raise ValueError(f"invalid row in {s!r}") from e
    col = 0
    for c in col_letters:
        col = col * 26 + (ord(c) - ord("A") + 1)
    return row, col - 1


def detect_data_islands(
    rows: list[list[Any]],
    *,
    min_rows: int = 2,
    min_cols: int = 1,
    min_density: float = 0.0,
) -> list[DataIsland]:
    """Return the list of detected data islands, sorted in reading order
    (top-to-bottom, then left-to-right).

    Filters:
      - min_rows / min_cols: drop islands smaller than this. Default
        rejects 1-row bands (often stray section headings) but keeps
        1-column lists.
      - min_density: drop islands where (filled cells / bbox cells) is
        below this. Default 0 — keep all. Bump to e.g. 0.3 if your
        sheets have lots of decorative whitespace inside tables.
    """
    if not rows:
        return []

    n_rows = len(rows)
    n_cols = max((len(r) for r in rows), default=0)
    if n_cols == 0:
        return []

    # 1. Mask. Pad ragged rows to uniform width so column-wise queries
    #    are O(1) without bounds checks.
    mask = [
        [_is_filled(r[c]) if c < len(r) else False for c in range(n_cols)]
        for r in rows
    ]

    # 2. Horizontal cuts: which rows have at least one filled cell.
    row_has_content = [any(row) for row in mask]

    # 3. Group consecutive content rows into "row bands".
    bands: list[tuple[int, int]] = []  # (start_inclusive, end_inclusive)
    in_band = False
    band_start = 0
    for r in range(n_rows):
        if row_has_content[r]:
            if not in_band:
                band_start = r
                in_band = True
        elif in_band:
            bands.append((band_start, r - 1))
            in_band = False
    if in_band:
        bands.append((band_start, n_rows - 1))

    # 4. Inside each band, find columns that are non-empty SOMEWHERE in
    #    the band, then group consecutive such columns into islands.
    islands: list[DataIsland] = []
    for start_r, end_r in bands:
        col_has_content = [
            any(mask[r][c] for r in range(start_r, end_r + 1))
            for c in range(n_cols)
        ]
        col_run_start: int | None = None
        for c in range(n_cols):
            if col_has_content[c]:
                if col_run_start is None:
                    col_run_start = c
            elif col_run_start is not None:
                _emit_island(islands, mask, rows, start_r, end_r, col_run_start, c - 1)
                col_run_start = None
        if col_run_start is not None:
            _emit_island(islands, mask, rows, start_r, end_r, col_run_start, n_cols - 1)

    # 5. Apply size + density filters.
    out = [
        i for i in islands
        if i.n_rows >= min_rows
        and i.n_cols >= min_cols
        and i.density >= min_density
    ]
    return out


def _emit_island(
    out: list[DataIsland],
    mask: list[list[bool]],
    rows: list[list[Any]],
    top: int, bottom: int, left: int, right: int,
) -> None:
    """Compute the metadata for one bounding rectangle and append it."""
    n_rows_isl = bottom - top + 1
    n_cols_isl = right - left + 1
    filled_cells = 0
    for r in range(top, bottom + 1):
        for c in range(left, right + 1):
            if mask[r][c]:
                filled_cells += 1
    total_cells = n_rows_isl * n_cols_isl
    density = filled_cells / total_cells if total_cells else 0.0

    # Preview the first row, capped to 12 cells so the JSON payload stays
    # small (the picker UI shows it as a sample to help the user choose).
    preview_cells = []
    preview_top_row = rows[top] if top < len(rows) else []
    for c in range(left, min(right + 1, left + 12)):
        if c < len(preview_top_row) and _is_filled(preview_top_row[c]):
            preview_cells.append(str(preview_top_row[c])[:60])
        else:
            preview_cells.append(None)

    out.append(DataIsland(
        top_row=top, bottom_row=bottom,
        left_col=left, right_col=right,
        n_rows=n_rows_isl, n_cols=n_cols_isl,
        range_a1=excel_range(top, left, bottom, right),
        preview_first_row=preview_cells,
        density=round(density, 3),
    ))
