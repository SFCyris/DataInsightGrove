from __future__ import annotations

import hashlib
import ipaddress
import json as _json
import os
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import polars as pl

from dig.engine.connector import Connector
from dig.storage.files import data_dir


# Bytes ceiling per download — same shape as the REST connector. Without
# this, a malicious URL could OOM the worker by serving a huge response.
_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


def _is_private_address(host: str) -> bool:
    """Resolve ``host`` and return True if any A/AAAA record is loopback /
    private / link-local / multicast / reserved / unspecified. Mirrors the
    REST connector's ``_is_private_address`` — kept inline here to avoid
    cross-importing between two `connectors/*/connector.py` files (which
    would couple their loading order).
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, socket.herror, OSError):
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_loopback or ip.is_private or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            return True
    return False


class _SafeRedirectHandler(HTTPRedirectHandler):
    """Re-validate the Location header on every 3xx hop.

    Without this guard the initial URL is checked but a malicious server
    can return ``Location: http://169.254.169.254/...`` (cloud metadata)
    or ``http://localhost:8190/...`` (sibling service) and the default
    ``HTTPRedirectHandler`` will silently follow it. Pen-test finding
    round 8.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        _assert_https_uri_safe(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_url(req: Request, timeout: int):
    """``urlopen``-compatible call that re-validates every redirect hop."""
    opener = build_opener(_SafeRedirectHandler())
    return opener.open(req, timeout=timeout)


def _assert_https_uri_safe(uri: str) -> None:
    """Reject schemes other than http/https + private destinations.

    Prior to this guard the connector accepted ``file://`` URIs (read
    arbitrary files via ``urllib.request.urlopen``) AND any HTTP target
    including ``http://localhost:8190/health`` and ``http://169.254.169.254/...``
    (cloud-metadata exfil). Pen-tester finding round 2.

    Bypass: ``DIG_REST_ALLOW_PRIVATE=1`` (same gate as the REST connector
    so operators can opt back into internal-network targets on a trusted
    host).
    """
    parts = urlsplit(uri)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(
            f"https connector: scheme {scheme!r} not allowed; "
            "only http and https are permitted",
        )
    if not parts.hostname:
        raise ValueError(f"https connector: no host in URL {uri!r}")
    if os.environ.get("DIG_REST_ALLOW_PRIVATE") == "1":
        return
    if _is_private_address(parts.hostname):
        raise ValueError(
            f"https connector: host {parts.hostname!r} resolves to a private / "
            "loopback / link-local address. Set DIG_REST_ALLOW_PRIVATE=1 on a "
            "trusted host to allow internal-network targets."
        )


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
        # Validate scheme + host BEFORE any network call.
        _assert_https_uri_safe(uri)
        cache = self._cache_path(uri, ext)
        if cache.exists():
            return cache
        req = Request(
            uri,
            headers={"User-Agent": "DataInsightGrove/0.0.1 (https-connector)"},
        )
        # Cap response size — a 60 GB malicious response would OOM the
        # worker. Read in chunks so we can stop early.
        with _open_url(req, timeout=60) as resp:
            buf = bytearray()
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                buf.extend(chunk)
                if len(buf) > _MAX_DOWNLOAD_BYTES:
                    raise ValueError(
                        f"https connector: response exceeded "
                        f"{_MAX_DOWNLOAD_BYTES // 1024 // 1024} MB cap "
                        "(set in connectors/https/connector.py)."
                    )
            cache.write_bytes(bytes(buf))
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
