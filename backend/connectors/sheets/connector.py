"""Google Sheets reverse-ETL sink connector.

Writes a DataFrame to a worksheet in a Google Sheets spreadsheet. Auth via
service-account JSON. The service account email must have editor access to
the target spreadsheet (share the sheet with the service account address).
"""

from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import polars as pl

from dig.engine.connector import Connector


class SheetsConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        raise NotImplementedError(
            "sheets connector: source mode not implemented in this iteration."
        )

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        if not uri.startswith("sheets://"):
            raise ValueError(
                f"sheets connector: URI must start with sheets:// (got: {uri[:24]}…)"
            )

        try:
            import gspread  # type: ignore
            from google.oauth2.service_account import Credentials  # type: ignore
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "sheets connector: missing dependency. Install with "
                "`pip install gspread google-auth` and try again."
            ) from e

        parsed = urlparse(uri)
        spreadsheet_id = parsed.hostname or ""
        if not spreadsheet_id:
            raise ValueError(
                "sheets connector: URI must be sheets://<spreadsheet-id>"
            )
        qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        credentials_path = qs.get("credentials")
        if not credentials_path:
            raise ValueError(
                "sheets connector: ?credentials=<path-to-service-account-json> required"
            )

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ]
        creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)
        gc = gspread.authorize(creds)
        ss = gc.open_by_key(spreadsheet_id)

        sheet_name = (options.get("sheet") or "Sheet1").strip()
        mode = (options.get("mode") or "overwrite").lower()
        include_header = bool(options.get("include_header", True))

        if mode not in ("append", "overwrite", "clear_first"):
            raise ValueError(
                f"sheets connector: mode must be append/overwrite/clear_first (got {mode!r})"
            )

        try:
            ws = ss.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            rows_estimate = max(frame.height + 5, 100)
            cols_estimate = max(frame.width, 10)
            ws = ss.add_worksheet(title=sheet_name, rows=rows_estimate, cols=cols_estimate)

        # Sheets enforces a per-request payload limit (~10 MB) and per-minute
        # write quotas; a single 100K-row update will hit one or the other.
        # Cap rows-per-write conservatively and chunk the upload by 5K rows.
        max_rows = int(options.get("max_rows") or 250_000)
        if frame.height > max_rows:
            raise ValueError(
                f"sheets connector: {frame.height:,} rows exceeds max_rows={max_rows:,}. "
                "Pass `max_rows` to override or pre-aggregate the frame."
            )

        rows = frame.rows()
        # Sheets API expects pure-Python types; convert any datetimes to ISO strings.
        rendered = [[_render_cell(c) for c in r] for r in rows]
        if include_header:
            rendered = [list(frame.columns)] + rendered

        chunk_size = 5000

        if mode == "clear_first" or mode == "overwrite":
            if mode == "clear_first":
                ws.clear()
            # Start at row 1; each chunk advances the row-offset.
            row_off = 1
            for start in range(0, len(rendered), chunk_size):
                chunk = rendered[start : start + chunk_size]
                ws.update(values=chunk, range_name=f"A{row_off}")
                row_off += len(chunk)
        else:  # append
            for start in range(0, len(rendered), chunk_size):
                chunk = rendered[start : start + chunk_size]
                ws.append_rows(chunk, value_input_option="USER_ENTERED")


def _render_cell(v: Any) -> Any:
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


_manifest_path = Path(__file__).parent / "manifest.json"
connector = SheetsConnector(_json.loads(_manifest_path.read_text()))
