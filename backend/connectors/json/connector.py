from __future__ import annotations

import json as _json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import polars as pl

from dig.engine.connector import Connector


class JsonConnector(Connector):
    def _path(self, uri: str) -> Path:
        # Reject file:// URIs that escape the data dir / samples dir.
        # See dig.engine.uri_safety for the full rationale (round-2
        # pen-tester finding: arbitrary local file read).
        from dig.engine.uri_safety import assert_local_path_safe
        return assert_local_path_safe(uri)

    def _detect_ndjson(self, path: Path) -> bool:
        # Cheap heuristic: read first non-whitespace char. NDJSON starts with '{' or '['
        # on each line; a JSON array starts with '['. If the first significant char is
        # '[' we assume regular JSON; otherwise NDJSON.
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                stripped = chunk.lstrip()
                if stripped:
                    return not stripped.startswith(b"[")
        return False

    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        path = self._path(uri)
        fmt = options.get("format") or "auto"
        if fmt == "auto":
            fmt = "ndjson" if self._detect_ndjson(path) else "json"
        if fmt == "ndjson":
            return pl.scan_ndjson(path)
        # Plain JSON array — Polars eager only.
        return pl.read_json(path).lazy()

    def write(self, frame: pl.DataFrame, uri: str, options: dict[str, Any]) -> None:
        path = self._path(uri)
        path.parent.mkdir(parents=True, exist_ok=True)
        fmt = options.get("format") or "auto"
        if fmt == "auto":
            fmt = "ndjson" if path.suffix.lower() in (".jsonl", ".ndjson") else "json"
        if fmt == "ndjson":
            frame.write_ndjson(path)
        else:
            path.write_text(_json.dumps(frame.to_dicts(), indent=2, default=str))


_manifest_path = Path(__file__).parent / "manifest.json"
connector = JsonConnector(_json.loads(_manifest_path.read_text()))
