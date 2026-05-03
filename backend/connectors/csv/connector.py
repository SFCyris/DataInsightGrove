"""CSV / TSV / generic delimited-text connector with auto-detect on
both delimiter and header row.

Behaviours:
  - delimiter='auto' uses the extension as a strong hint for known formats
    (.tsv/.tab → tab, .psv → pipe) and otherwise sniffs the file: reads the
    first ~16KB and picks the candidate (`,`, `\\t`, `;`, `|`, single space)
    that yields the most consistent column count across non-empty lines.
    This makes generic .dat / .data scientific files import correctly
    without the user having to set the delimiter manually.
  - header='auto' samples the first ~50 rows headerlessly and uses the
    type-distinction heuristic in dig.engine.header_detect.detect_header
  - When header is detected as absent, columns are renamed col_1, col_2, …
    (one-indexed snake-case, instead of polars' default column_1)

The user can always override either auto behaviour via explicit options.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector
from dig.engine.header_detect import detect_header, rename_to_col_n


def _path(uri: str) -> Path:
    if uri.startswith("file://"):
        return Path(urlparse(uri).path)
    return Path(uri)


# Candidates checked when sniffing — order matters as a tiebreaker
# (earlier wins on equal score).
_SNIFF_CANDIDATES = (",", "\t", ";", "|", " ")


def _sniff_delimiter(path: Path, encoding: str) -> str:
    """Score each candidate by how consistently it produces the same column
    count across non-empty lines in the first ~16KB. Returns ',' on any
    failure — better to load with a single column than to crash here."""
    polars_encoding = "utf8" if encoding == "utf-8" else encoding
    try:
        with path.open("rb") as f:
            raw = f.read(16 * 1024)
        text = raw.decode(polars_encoding if polars_encoding != "utf8" else "utf-8", errors="replace")
    except Exception:
        return ","
    # Drop the last (likely partial) line so a truncated tail doesn't skew counts.
    lines = [line for line in text.splitlines()[:-1] if line.strip()]
    if len(lines) < 2:
        return ","
    # Skip the first line — when present it's often a header whose delimiter
    # count matches data rows but whose values look different.
    sample = lines[1:51] if len(lines) > 5 else lines

    best_delim = ","
    best_score = -1.0
    for delim in _SNIFF_CANDIDATES:
        counts = [line.count(delim) for line in sample]
        if max(counts) == 0:
            continue
        modal_count, n_with_modal = Counter(counts).most_common(1)[0]
        if modal_count == 0:
            continue
        # Score = consistency × column-count signal. Penalise space lightly
        # because it appears inside fields more often than the others.
        consistency = n_with_modal / len(sample)
        score = consistency * modal_count * (0.7 if delim == " " else 1.0)
        if score > best_score:
            best_score = score
            best_delim = delim
    return best_delim


def _resolve_delimiter(path: Path, raw: str, encoding: str = "utf-8") -> str:
    """'auto' → extension hint for .tsv/.tab/.psv, otherwise content sniff.
    Otherwise pass through (with the \\t escape supported as a literal tab)."""
    if raw == "auto" or not raw:
        ext = path.suffix.lower()
        if ext in (".tsv", ".tab"):
            return "\t"
        if ext == ".psv":
            return "|"
        return _sniff_delimiter(path, encoding)
    if raw == "\\t":
        return "\t"
    return raw


def _resolve_header(
    path: Path, raw: Any, *, delimiter: str, encoding: str,
) -> bool:
    """'auto' → run the header-detect heuristic on a sample. yes/no/True/False
    → that, verbatim."""
    if isinstance(raw, bool):
        return raw
    if raw == "yes" or raw is True:
        return True
    if raw == "no" or raw is False:
        return False
    # raw == "auto" or anything unexpected — sample + detect.
    polars_encoding = "utf8" if encoding == "utf-8" else encoding
    try:
        sample = pl.read_csv(
            path,
            separator=delimiter,
            encoding=polars_encoding,
            has_header=False,
            n_rows=50,
            infer_schema_length=0,  # all-string for shape inspection
            ignore_errors=True,
        )
    except Exception:
        # If we can't even sample, default to True (matches polars'
        # historical default) and let the main read raise if the file's
        # truly unreadable.
        return True
    return detect_header(sample)


class CsvConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        path = _path(uri)
        encoding = options.get("encoding", "utf-8")
        delimiter = _resolve_delimiter(path, options.get("delimiter", "auto"), encoding)
        polars_encoding = "utf8" if encoding == "utf-8" else encoding
        has_header = _resolve_header(
            path, options.get("header", "auto"),
            delimiter=delimiter, encoding=encoding,
        )

        lf = pl.scan_csv(
            path,
            separator=delimiter,
            has_header=has_header,
            encoding=polars_encoding,
            null_values=options.get("nullValues") or None,
            infer_schema_length=10_000,
            try_parse_dates=True,
            ignore_errors=False,
        )
        if not has_header:
            lf = rename_to_col_n(lf)  # column_1 → col_1
        return lf

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        path = _path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        # On write, sniffing doesn't apply (file doesn't exist yet) —
        # only use the extension hint, default comma.
        raw_delim = options.get("delimiter", "auto")
        if raw_delim in ("auto", None, ""):
            ext = path.suffix.lower()
            delimiter = "\t" if ext in (".tsv", ".tab") else "|" if ext == ".psv" else ","
        elif raw_delim == "\\t":
            delimiter = "\t"
        else:
            delimiter = raw_delim
        # On write, "auto" header is treated as yes — nobody wants to
        # write a file with no column names.
        raw_header = options.get("header", "auto")
        write_header = raw_header in ("auto", "yes", True)
        frame.write_csv(
            path,
            separator=delimiter,
            include_header=write_header,
        )


_manifest_path = Path(__file__).parent / "manifest.json"
connector = CsvConnector(json.loads(_manifest_path.read_text()))
