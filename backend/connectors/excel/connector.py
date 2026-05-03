"""Excel reader / writer.

Reading: prefers `calamine` (via `fastexcel`) — pure-Rust, supports both
.xlsx and legacy .xls binary, faster than openpyxl. Falls back to
openpyxl if fastexcel isn't installed (xlsx only — xls reads will raise
a clear error pointing the user at `pip install fastexcel`).

Writing: openpyxl + xlsxwriter through Polars' built-in writer. Writes
.xlsx only — .xls is intentionally not supported (deprecated binary
format; users should pick xlsx for output).

Auto-header: same heuristic as the CSV connector — sample the first
~50 rows headerlessly, vote per-column on whether row 0 looks like a
header. When no header is detected, columns are renamed col_1, col_2,
… for predictable downstream references.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector
from dig.engine.data_islands import (
    detect_data_islands,
    parse_excel_range,
)
from dig.engine.header_detect import detect_header, rename_to_col_n


def _path(uri: str) -> Path:
    if uri.startswith("file://"):
        return Path(urlparse(uri).path)
    return Path(uri)


def _pick_engine(path: Path) -> str:
    """calamine for .xls + .xlsx (when fastexcel installed); openpyxl
    fallback otherwise — but openpyxl doesn't read .xls so we raise a
    clear error in that case."""
    try:
        import fastexcel  # noqa: F401
        return "calamine"
    except ImportError:
        if path.suffix.lower() == ".xls":
            raise RuntimeError(
                "Reading .xls (legacy binary Excel) requires fastexcel. "
                "Install with: pip install fastexcel  — or convert the file "
                "to .xlsx in Excel/Numbers/LibreOffice first.",
            )
        return "openpyxl"


def _resolve_header(path: Path, raw: Any, *, sheet: str | None, engine: str) -> bool:
    """'auto' → sample the sheet headerlessly + run detect_header. yes/no
    → force the choice."""
    if isinstance(raw, bool):
        return raw
    if raw == "yes" or raw is True:
        return True
    if raw == "no" or raw is False:
        return False
    try:
        sample = pl.read_excel(
            path,
            sheet_name=sheet,
            engine=engine,
            has_header=False,
        )
        if sample.height > 50:
            sample = sample.head(50)
    except Exception:
        return True  # fall back to "yes" if we can't sample
    return detect_header(sample)


def list_data_islands(uri: str, sheet: str | None) -> list[dict[str, Any]]:
    """Read a sheet headerlessly and report the rectangular data islands
    found on it. Used by the upload flow to pause + prompt the user when
    a sheet contains multiple disjoint tables.

    Uses fastexcel's lower-level `load_sheet()` directly rather than
    `pl.read_excel`, because the latter silently strips blank rows
    (collapsing two stacked tables into one continuous block before
    detection can run). fastexcel preserves blank rows by default,
    which is what the island detector needs.

    Returns list-of-dicts (asdict() shape) so the caller can JSON-encode
    directly into the dataset row's options.
    """
    path = _path(uri)
    try:
        import fastexcel
    except ImportError:
        # Without fastexcel we can't reliably preserve blank rows. Fall
        # back to the lossy polars path; users with islands separated by
        # blanks won't see the picker but won't error either.
        try:
            df = pl.read_excel(path, sheet_name=sheet, engine="openpyxl", has_header=False)
        except Exception:
            return []
        rows = df.to_numpy().tolist()
        return [i.as_dict() for i in detect_data_islands(rows)]

    try:
        reader = fastexcel.read_excel(str(path))
        # Pick by name when supplied, else first sheet (idx 0).
        loaded = reader.load_sheet(sheet if sheet else 0, header_row=None)
        df = loaded.to_polars()
    except Exception:
        return []
    rows = df.to_numpy().tolist()
    islands = detect_data_islands(rows)
    return [i.as_dict() for i in islands]


def list_sheets(uri: str) -> list[str]:
    """Return the sheet names in the workbook, in the order they appear.
    Used by the upload flow to detect multi-sheet workbooks and prompt
    the user to pick one before ingesting.

    Cheap on .xlsx (just reads the workbook's index XML) and on .xls
    (calamine indexes the workbook in O(1) sheets). Doesn't touch cell
    data, so it's safe to call on huge workbooks before any sheet-level
    materialisation.
    """
    path = _path(uri)
    suffix = path.suffix.lower()
    try:
        if suffix == ".xls":
            # Legacy binary — calamine path only.
            import fastexcel
            wb = fastexcel.read_excel(str(path))
            return list(wb.sheet_names)
        # .xlsx — try fastexcel first, fall back to openpyxl.
        try:
            import fastexcel
            wb = fastexcel.read_excel(str(path))
            return list(wb.sheet_names)
        except ImportError:
            import openpyxl
            wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
            try:
                return list(wb.sheetnames)
            finally:
                wb.close()
    except Exception as e:
        # If we can't even list sheets, return an empty list — the caller
        # treats that as "single-sheet workbook, default behaviour".
        import logging as _log
        _log.getLogger(__name__).warning("list_sheets failed for %s: %s", uri, e)
        return []


class ExcelConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        path = _path(uri)
        sheet = options.get("sheet") or None
        engine = _pick_engine(path)
        island_range = options.get("island_range")  # e.g. "B2:F50"

        if island_range:
            # Scoped read: pull the entire sheet headerlessly, slice to
            # the requested rectangle, then apply header detection
            # against the slice (so the heuristic operates on the actual
            # candidate table, not the whole noisy sheet).
            #
            # Critical: use fastexcel.load_sheet() directly (NOT
            # pl.read_excel) because pl.read_excel strips blank rows,
            # which would shift the user's saved range relative to the
            # actual cell coordinates. fastexcel preserves them.
            try:
                import fastexcel
                reader = fastexcel.read_excel(str(path))
                loaded = reader.load_sheet(sheet if sheet else 0, header_row=None)
                full = loaded.to_polars()
            except ImportError:
                full = pl.read_excel(
                    path, sheet_name=sheet, engine=engine, has_header=False,
                )
            try:
                top, left, bottom, right = parse_excel_range(island_range)
            except ValueError as e:
                raise RuntimeError(f"invalid island_range {island_range!r}: {e}") from e

            # Polars 0-indexed slicing — clamp to actual sheet bounds in
            # case the saved range refers to cells past the live data
            # (e.g. user trimmed the workbook after selecting an island).
            top = max(0, min(top, full.height - 1))
            bottom = max(top, min(bottom, full.height - 1))
            left = max(0, min(left, full.width - 1))
            right = max(left, min(right, full.width - 1))

            cols_in_range = full.columns[left : right + 1]
            slice_df = full.slice(top, bottom - top + 1).select(cols_in_range)

            # Header detection runs on the slice — same heuristic as the
            # whole-sheet path. When detected, take row 0 as column names.
            raw_header = options.get("header", "auto")
            if isinstance(raw_header, bool):
                has_header = raw_header
            elif raw_header in ("yes", True):
                has_header = True
            elif raw_header in ("no", False):
                has_header = False
            else:
                from dig.engine.header_detect import detect_header as _det
                has_header = _det(slice_df.head(50))

            if has_header and slice_df.height > 0:
                new_names = [
                    str(slice_df[c][0]) if slice_df[c][0] is not None else f"col_{i + 1}"
                    for i, c in enumerate(slice_df.columns)
                ]
                # Disambiguate duplicate / blank header cells — append _2, _3, …
                seen: dict[str, int] = {}
                for i, n in enumerate(new_names):
                    n = n or f"col_{i + 1}"
                    if n in seen:
                        seen[n] += 1
                        new_names[i] = f"{n}_{seen[n]}"
                    else:
                        seen[n] = 1
                        new_names[i] = n
                slice_df = slice_df.rename(dict(zip(slice_df.columns, new_names))).slice(1)
            elif not has_header:
                slice_df = rename_to_col_n(slice_df)
            return slice_df.lazy()

        # Whole-sheet path (unchanged behaviour).
        has_header = _resolve_header(
            path, options.get("header", "auto"),
            sheet=sheet, engine=engine,
        )
        df = pl.read_excel(
            path,
            sheet_name=sheet,
            engine=engine,
            has_header=has_header,
        )
        if not has_header:
            df = rename_to_col_n(df)
        return df.lazy()

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        path = _path(uri)
        if path.suffix.lower() == ".xls":
            raise RuntimeError(
                "Writing legacy .xls is not supported — please use .xlsx as the output extension.",
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        sheet = options.get("sheet") or "Sheet1"
        frame.write_excel(path, worksheet=sheet)


_manifest_path = Path(__file__).parent / "manifest.json"
connector = ExcelConnector(json.loads(_manifest_path.read_text()))
