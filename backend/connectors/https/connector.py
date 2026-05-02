from __future__ import annotations

import hashlib
import json as _json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import polars as pl

from dig.engine.connector import Connector
from dig.storage.files import data_dir


class HttpsConnector(Connector):
    """Fetch a remote file (CSV/Parquet/JSON) once and read it via Polars.

    The download is cached at `data/cache/url-<sha256>.<ext>` so re-ingesting the
    same URL is a no-op.
    """

    def _cache_path(self, uri: str, ext: str) -> Path:
        h = hashlib.sha256(uri.encode("utf-8")).hexdigest()[:16]
        cache_dir = data_dir() / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"url-{h}.{ext}"

    def _detect_format(self, uri: str, override: str | None) -> str:
        if override and override != "auto":
            return override
        lower = uri.split("?", 1)[0].lower()
        if lower.endswith(".parquet"):
            return "parquet"
        if lower.endswith(".jsonl") or lower.endswith(".ndjson"):
            return "ndjson"
        if lower.endswith(".json"):
            return "json"
        return "csv"

    def _download(self, uri: str, ext: str) -> Path:
        cache = self._cache_path(uri, ext)
        if cache.exists():
            return cache
        req = Request(
            uri,
            headers={"User-Agent": "DataInsightGrove/0.0.1 (https-connector)"},
        )
        with urlopen(req, timeout=60) as resp:
            cache.write_bytes(resp.read())
        return cache

    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        fmt = self._detect_format(uri, options.get("format"))
        ext = "parquet" if fmt == "parquet" else "json" if fmt in ("json", "ndjson") else "csv"
        local = self._download(uri, ext)
        if fmt == "parquet":
            return pl.scan_parquet(local)
        if fmt == "ndjson":
            return pl.scan_ndjson(local)
        if fmt == "json":
            return pl.read_json(local).lazy()
        # CSV
        return pl.scan_csv(local, infer_schema_length=10_000, try_parse_dates=True)

    # write() not supported — sink-side HTTPS PUT is uncommon and varies wildly by host.


_manifest_path = Path(__file__).parent / "manifest.json"
connector = HttpsConnector(_json.loads(_manifest_path.read_text()))
