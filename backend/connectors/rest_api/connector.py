"""Generic REST API connector — one option-driven implementation that
covers the long tail of JSON-returning HTTP APIs without per-source code.

Supported authentication:
  - none
  - bearer        Authorization: Bearer <key>
  - api_key_query ?<name>=<key>
  - api_key_header <name>: <key>
  - basic         Authorization: Basic base64(user:pass)

Supported pagination:
  - none          single fetch
  - cursor        response carries a cursor; next call sends ?<cursor_param>=<cursor>
  - offset_limit  ?offset=<n>&limit=<page_size>
  - page_number   ?page=<n>&per_page=<page_size>
  - link_header   follows RFC 5988 Link: <...>; rel="next"

Records are extracted via a dotted JSONPath (`$.data`, `$.items.list`, …) and
flattened one level into a Polars LazyFrame. For deeper nesting the user can
chain a `json_extract` step downstream.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import logging
import os
import re
import socket
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import polars as pl

from dig.engine.connector import Connector

log = logging.getLogger(__name__)


# Hard ceilings to prevent abuse / runaway loops regardless of options.
_MAX_PAGES_CEILING = 1000
_MAX_RESPONSE_BYTES = 100 * 1024 * 1024  # 100 MB per request

# Allowed URL schemes — block file://, ftp://, etc. to prevent local-file
# disclosure or other connector misuse.
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _is_private_address(host: str) -> bool:
    """Return True if `host` resolves to a loopback / link-local / private
    range (RFC 1918, cloud metadata 169.254.169.254, etc.). The scan is
    SSRF defense — without it, a redirect to http://169.254.169.254/... or
    a paginated `Link: <http://10.0.0.1/...>` header could pivot from a
    public-API connector into the host's internal network.
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, socket.herror, OSError):
        # Resolution failed — treat as private to be safe.
        return True
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return True
    return False


def _assert_url_safe(url: str) -> None:
    """Validate scheme + host before any network call. Raises ValueError
    on a rejected URL. Bypassable via `DIG_REST_ALLOW_PRIVATE=1` for
    legitimate internal-API use cases (set deliberately, never default)."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"REST connector: scheme {parts.scheme!r} not allowed; "
            "only http and https are permitted",
        )
    if not parts.hostname:
        raise ValueError(f"REST connector: no host in URL {url!r}")
    if os.environ.get("DIG_REST_ALLOW_PRIVATE") == "1":
        return
    if _is_private_address(parts.hostname):
        raise ValueError(
            f"REST connector: host {parts.hostname!r} resolves to a private / "
            "loopback / link-local address. Set DIG_REST_ALLOW_PRIVATE=1 to "
            "permit internal-network targets (do this only on a trusted host).",
        )


def _assert_response_peer_safe(response: Any) -> None:
    """Defense-in-depth against DNS rebinding (TOCTOU SSRF).

    ``_assert_url_safe`` resolves the URL's hostname and rejects private
    addresses. But ``httpx.Client.get`` does its OWN DNS lookup against
    the same hostname. A malicious DNS server can return a public IP for
    the safety check (lookup #1) and ``127.0.0.1`` (or ``169.254.169.254``
    for cloud-metadata exfil) for the actual connection (lookup #2). The
    safety check passes, the connection lands on a private IP, and the
    response body — which may be the contents of an internal service —
    flows back to the caller.

    Mitigation: after the response arrives, walk the underlying
    ``network_stream`` extension to read the actual TCP peer address and
    re-validate. If the peer is private, raise BEFORE returning the body
    to the caller. Bypassable via ``DIG_REST_ALLOW_PRIVATE=1`` (same gate
    as the URL-time check).
    """
    if os.environ.get("DIG_REST_ALLOW_PRIVATE") == "1":
        return
    network_stream = response.extensions.get("network_stream")
    if network_stream is None:
        return  # transport doesn't expose it (testing fakes etc.) — best-effort only
    # network_stream.get_extra_info is available on httpcore 1.0+ streams.
    sock = None
    if hasattr(network_stream, "get_extra_info"):
        try:
            sock = network_stream.get_extra_info("socket")
        except Exception:  # noqa: BLE001
            sock = None
    if sock is None:
        return
    try:
        peer = sock.getpeername()
    except OSError:
        return
    if not peer:
        return
    peer_addr = peer[0]
    try:
        peer_ip = ipaddress.ip_address(peer_addr)
    except ValueError:
        return
    if (
        peer_ip.is_loopback
        or peer_ip.is_private
        or peer_ip.is_link_local
        or peer_ip.is_multicast
        or peer_ip.is_reserved
        or peer_ip.is_unspecified
    ):
        raise RuntimeError(
            f"REST connector: connection landed on forbidden IP {peer_addr!r} "
            f"despite a public-looking hostname. Refusing to return the response "
            f"(possible DNS rebinding). Set DIG_REST_ALLOW_PRIVATE=1 to permit "
            f"internal-network targets on a trusted host."
        )


def _extract_path(obj: Any, path: str) -> Any:
    """Walk a dotted JSONPath. '$' = root, '$.foo.bar' = obj['foo']['bar'].
    Returns None on missing keys (instead of raising)."""
    if not path or path == "$":
        return obj
    if not path.startswith("$"):
        raise ValueError(f"json_path must start with '$', got {path!r}")
    parts = path[1:].lstrip(".").split(".")
    cur: Any = obj
    for p in parts:
        if not p:
            continue
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list):
            try:
                cur = cur[int(p)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if cur is None:
            return None
    return cur


def _next_link_from_header(link_header: str | None) -> str | None:
    """Parse RFC 5988 Link header, return the URL with rel="next" or None."""
    if not link_header:
        return None
    # Format: <https://...>; rel="next", <https://...>; rel="prev"
    for part in link_header.split(","):
        m = re.match(r'\s*<([^>]+)>\s*;\s*rel\s*=\s*"?next"?\s*', part)
        if m:
            return m.group(1)
    return None


def _add_query(url: str, params: dict[str, Any]) -> str:
    """Append/override query parameters on a URL."""
    if not params:
        return url
    parts = urlsplit(url)
    existing = dict(p.split("=", 1) if "=" in p else (p, "")
                    for p in parts.query.split("&") if p)
    existing.update({k: str(v) for k, v in params.items()})
    new_query = urlencode(existing)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def _flatten_records(records: list[Any]) -> list[dict[str, Any]]:
    """One-level flatten — turn list-of-dicts into the same. For non-dict
    records (e.g. list of scalars), wrap each as {value: scalar} so the
    DataFrame has at least one column."""
    out: list[dict[str, Any]] = []
    for r in records:
        if isinstance(r, dict):
            out.append(r)
        else:
            out.append({"value": r})
    return out


class RestApiConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        # Lazy-import httpx so the module loads even when httpx is missing
        # in some environments (the connector itself can't run, but the
        # registry scan succeeds).
        import httpx

        auth_kind = options.get("auth_kind", "none")
        auth_value = options.get("auth_value", "") or ""
        auth_param_name = options.get("auth_param_name", "api_key") or "api_key"
        json_path = options.get("json_path", "$") or "$"
        pagination = options.get("pagination", "none")
        cursor_resp_path = options.get("cursor_response_path", "next_cursor") or "next_cursor"
        cursor_param = options.get("cursor_param_name", "cursor") or "cursor"
        # Use explicit None-checks so legitimate 0 / negative values raise
        # rather than silently falling through to the default. Footgun: the
        # `or` operator was treating `0` as "use the default".
        raw_page_size = options.get("page_size")
        page_size = 100 if raw_page_size is None else int(raw_page_size)
        if page_size < 1:
            raise ValueError("page_size must be at least 1")

        raw_max_pages = options.get("max_pages")
        max_pages_req = 50 if raw_max_pages is None else int(raw_max_pages)
        if max_pages_req < 1:
            raise ValueError("max_pages must be at least 1")
        max_pages = min(max_pages_req, _MAX_PAGES_CEILING)

        raw_timeout = options.get("timeout_s")
        timeout_s = 30.0 if raw_timeout is None else float(raw_timeout)
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        extra_headers = options.get("extra_headers") or {}
        if not isinstance(extra_headers, dict):
            raise ValueError("extra_headers must be an object")

        # Build base headers
        headers: dict[str, str] = {
            "User-Agent": "DataInsightGrove-RestApiConnector/1.0",
            "Accept": "application/json",
        }
        for k, v in extra_headers.items():
            headers[str(k)] = str(v)

        # Apply auth
        first_url = uri
        if auth_kind == "bearer" and auth_value:
            headers["Authorization"] = f"Bearer {auth_value}"
        elif auth_kind == "api_key_header" and auth_value:
            headers[auth_param_name] = auth_value
        elif auth_kind == "api_key_query" and auth_value:
            first_url = _add_query(first_url, {auth_param_name: auth_value})
        elif auth_kind == "basic" and auth_value:
            # auth_value expected as user:pass
            b64 = base64.b64encode(auth_value.encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {b64}"
        elif auth_kind == "none":
            pass
        else:
            # Unknown auth_kind — fail loudly
            if auth_kind not in ("none", "bearer", "api_key_query", "api_key_header", "basic"):
                raise ValueError(f"unknown auth_kind: {auth_kind!r}")

        # Initial paged URL
        if pagination == "offset_limit":
            current_url = _add_query(first_url, {"offset": 0, "limit": page_size})
        elif pagination == "page_number":
            current_url = _add_query(first_url, {"page": 1, "per_page": page_size})
        else:
            current_url = first_url

        all_records: list[Any] = []
        pages_fetched = 0
        total_bytes = 0
        # Track cursor values to detect "API echoes the same cursor forever"
        # bugs that would otherwise loop until max_pages.
        seen_cursors: set[str] = set()

        # Validate the FIRST URL before opening the client (cheap fast-fail).
        _assert_url_safe(current_url)

        # follow_redirects=False — we manually re-validate every URL the
        # server hands us, which we can't do if httpx auto-follows. Without
        # this, a 302 to http://169.254.169.254/... would bypass _assert_url_safe.
        with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
            while pages_fetched < max_pages and current_url:
                pages_fetched += 1
                # Re-validate each pagination URL — _next_link_from_header
                # and cursor-derived URLs could otherwise route to private space.
                try:
                    _assert_url_safe(current_url)
                except ValueError as e:
                    raise RuntimeError(f"REST API rejected URL at page {pages_fetched}: {e}") from e
                try:
                    r = client.get(current_url, headers=headers)
                except httpx.RequestError as e:
                    raise RuntimeError(
                        f"REST API request failed (page {pages_fetched}): {e}",
                    ) from e

                # Defense-in-depth: catch DNS rebinding by inspecting the
                # connection's actual peer IP. See `_assert_response_peer_safe`
                # for the attack model.
                _assert_response_peer_safe(r)

                if r.status_code == 429:
                    raise RuntimeError(
                        f"Rate-limited by API at page {pages_fetched} (HTTP 429). "
                        "Reduce page_size or add a delay step downstream.",
                    )
                if not r.is_success:
                    raise RuntimeError(
                        f"REST API returned HTTP {r.status_code} at page {pages_fetched}: "
                        f"{r.text[:300]}",
                    )

                total_bytes += len(r.content)
                if total_bytes > _MAX_RESPONSE_BYTES:
                    raise RuntimeError(
                        f"Response cumulative size exceeded {_MAX_RESPONSE_BYTES // 1024 // 1024} MB "
                        f"at page {pages_fetched}. Tighten the JSONPath or reduce page count.",
                    )

                try:
                    body = r.json()
                except (json.JSONDecodeError, ValueError) as e:
                    raise RuntimeError(
                        f"REST API returned non-JSON at page {pages_fetched}: "
                        f"{r.text[:300]}",
                    ) from e

                records = _extract_path(body, json_path)
                if records is None:
                    # Missing path → no records on this page; treat as end-of-data
                    break
                if isinstance(records, dict):
                    # Single object instead of an array — treat as one row
                    all_records.append(records)
                elif isinstance(records, list):
                    all_records.extend(records)
                    if not records:
                        break  # empty page → no more data
                else:
                    # Scalar — wrap as one row
                    all_records.append({"value": records})

                # Compute next URL based on pagination style
                if pagination == "none":
                    break
                if pagination == "cursor":
                    # Normalize the cursor path to always start with $.
                    norm_path = cursor_resp_path if cursor_resp_path.startswith("$") else f"$.{cursor_resp_path}"
                    next_cursor = _extract_path(body, norm_path)
                    if not next_cursor:
                        break
                    cursor_str = str(next_cursor)
                    # Detect an API that echoes the same cursor — would loop
                    # to max_pages otherwise, wasting requests.
                    if cursor_str in seen_cursors:
                        log.warning(
                            "REST connector: cursor %r repeated — stopping pagination at page %d",
                            cursor_str, pages_fetched,
                        )
                        break
                    seen_cursors.add(cursor_str)
                    current_url = _add_query(first_url, {cursor_param: cursor_str})
                elif pagination == "offset_limit":
                    current_url = _add_query(first_url, {
                        "offset": pages_fetched * page_size,
                        "limit": page_size,
                    })
                elif pagination == "page_number":
                    current_url = _add_query(first_url, {
                        "page": pages_fetched + 1,
                        "per_page": page_size,
                    })
                elif pagination == "link_header":
                    next_url = _next_link_from_header(r.headers.get("Link"))
                    if not next_url:
                        break
                    current_url = next_url

        flat = _flatten_records(all_records)
        if not flat:
            # Return an empty LazyFrame with no columns rather than raising —
            # downstream steps handle empties gracefully.
            return pl.DataFrame().lazy()
        # infer_schema_length=None → use all rows for type inference, more
        # accurate but slower for very large pulls. Bounded by max_pages × page_size.
        return pl.DataFrame(flat, infer_schema_length=None).lazy()
