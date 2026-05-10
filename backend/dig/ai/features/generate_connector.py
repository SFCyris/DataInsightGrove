"""Generate a DIG connector from a URL + sample response.

Workflow:
  1. (frontend) User pastes a URL, optional auth, optional sample response
  2. backend: probe_url() actually fetches the URL once and returns shape
  3. backend: generate() builds a prompt with the URL + sample shape +
     intent, asks the LLM for {manifest_json, connector_py}
  4. backend: lint the connector_py (dig/ai/safety.py)
  5. (frontend) Review diff, click Install
  6. backend: install_pending() moves files into plugins/connectors/

Generated connector contract: read(uri, options) -> pl.LazyFrame.
The model is shown the existing https connector as a few-shot example
to anchor the output format.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.ai.client import AiConfig, AiError, chat
from dig.ai.parsing import parse_json_lenient
from dig.ai.prompts import TOKEN_BUDGETS
from dig.ai.safety import lint_plugin_python


_FEW_SHOT_HTTPS = '''\
# Example connector — a minimal HTTPS reader. Use this as the structural
# template for the connector you generate. Yours can use httpx instead
# of urllib if a custom auth scheme requires it.

# manifest.json
{
  "id": "https",
  "version": "1.0.0",
  "label": "🌐 HTTPS",
  "description": "Read CSV / Parquet / JSON from a public HTTPS URL.",
  "kind": "source",
  "uriSchemes": ["http", "https"],
  "options": {
    "format": {"type": "enum", "enumValues": ["auto", "csv", "json"], "default": "auto"}
  }
}

# connector.py
from __future__ import annotations
import polars as pl
import httpx
from dig.engine.connector import Connector

class HttpsConnector(Connector):
    def read(self, uri: str, options: dict) -> pl.LazyFrame:
        r = httpx.get(uri, timeout=30.0)
        r.raise_for_status()
        data = r.json()
        return pl.LazyFrame(data if isinstance(data, list) else [data])
'''


_SYSTEM = """\
You generate DataInsightGrove (DIG) connector plugins from a URL specification.

A DIG connector is a Python module whose `read(uri, options)` returns a
`polars.LazyFrame`. The user has supplied a target URL and (optionally) the
shape of a sample response. Your job is to emit a plugin folder as JSON.

Output strictly the following JSON (no Markdown, no code fences, no prose):

{
  "id": "<lowercase_snake_case_id_unique_to_this_source>",
  "label": "<emoji + Title Case label, e.g. '⭐ Stars API'>",
  "description": "<one-sentence description>",
  "manifest_json": <the manifest.json content as a JSON object>,
  "connector_py": "<the full connector.py source as a JSON string>"
}

Constraints on connector.py:
  - Allowed imports: json, re, hashlib, base64, datetime, typing, pathlib,
    urllib.parse, urllib.request, polars, httpx, dig.engine.connector.
  - DO NOT import: os, subprocess, shutil, sys, ctypes, socket, ssl, pickle,
    multiprocessing, threading, importlib, runpy, tempfile.
  - DO NOT call: eval, exec, compile, __import__, getattr/setattr/delattr,
    globals/locals/vars, os.system, subprocess.run.
  - Define exactly one class subclassing dig.engine.connector.Connector.
  - Implement `read(self, uri, options) -> pl.LazyFrame`.
  - Use httpx for HTTP. Always set a 30-second timeout. Always raise_for_status.
  - If auth is needed, read it from `options` (e.g. options.get('api_key')).
    Never hardcode credentials.
  - Handle pagination if the sample response shows it (Link header, next_page,
    cursor, offset/limit). Limit total pages fetched to 50 by default; expose
    a `max_pages` option.
  - Convert the JSON response to a polars LazyFrame. Flatten nested objects
    one level if the schema is straightforward.

Constraints on manifest.json:
  - kind must be "source"
  - uriSchemes should match the protocol (e.g. ["https"])
  - options should declare every parameter the connector reads from `options`.
"""


async def probe_url(url: str, *, auth_header: str | None = None, timeout_s: float = 15.0) -> dict[str, Any]:
    """One-shot fetch of `url` to discover its shape. Returns metadata
    the LLM and the user can both look at."""
    import httpx

    # Validate the URL the same way the REST connector does — defense-in-depth
    # against probe-url being used as an SSRF pivot.
    try:
        from connectors.rest_api.connector import _assert_url_safe
        _assert_url_safe(url)
    except (ValueError, ImportError) as e:
        return {"ok": False, "error": f"URL rejected: {e}", "status": None}

    headers = {"User-Agent": "DataInsightGrove-AI-Probe/1.0"}
    if auth_header:
        # Block CRLF injection — otherwise a malicious value like
        # "Bearer x\r\nX-Forwarded-For: ..." could inject extra headers
        # into the outbound request. Also cap length so a runaway value
        # doesn't blow the request budget.
        if len(auth_header) > 1024:
            return {"ok": False, "error": "auth_header too long (max 1024 chars)", "status": None}
        if any(c in auth_header for c in ("\r", "\n", "\x00")):
            return {"ok": False, "error": "auth_header contains illegal control characters", "status": None}
        headers["Authorization"] = auth_header

    try:
        # follow_redirects=False — same SSRF concern as the REST connector
        # (a 302 to a private address would otherwise bypass _assert_url_safe).
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            r = await client.get(url, headers=headers, follow_redirects=False)
            # Defense-in-depth against DNS rebinding TOCTOU — see the REST
            # connector for the attack model. Round-3 pen-tester finding
            # PEN #6: ``_assert_url_safe`` resolves the hostname, then
            # httpx resolves it AGAIN; a malicious DNS server can return a
            # public IP for the first lookup and 127.0.0.1 (or
            # 169.254.169.254) for the second.
            try:
                from connectors.rest_api.connector import _assert_response_peer_safe
                _assert_response_peer_safe(r)
            except RuntimeError as e:
                return {"ok": False, "error": f"URL rejected post-connect: {e}", "status": r.status_code}
    except httpx.RequestError as e:
        return {"ok": False, "error": f"Network error: {e}", "status": None}

    out: dict[str, Any] = {
        "ok": r.is_success,
        "status": r.status_code,
        "content_type": r.headers.get("content-type"),
        "final_url": str(r.url),
        "length": len(r.content),
    }
    if not r.is_success:
        out["error"] = f"HTTP {r.status_code}"
        out["body_preview"] = r.text[:500]
        return out

    body_preview = r.text[:1500]
    out["body_preview"] = body_preview

    # Best-effort JSON shape preview
    try:
        parsed = r.json()
        if isinstance(parsed, list):
            out["json_shape"] = {"type": "array", "length": len(parsed),
                                 "first_keys": sorted((parsed[0] or {}).keys()) if parsed and isinstance(parsed[0], dict) else None}
        elif isinstance(parsed, dict):
            out["json_shape"] = {"type": "object", "keys": sorted(parsed.keys())}
        else:
            out["json_shape"] = {"type": type(parsed).__name__}
    except Exception:
        out["json_shape"] = None

    return out


async def generate_connector(
    cfg: AiConfig,
    *,
    url: str,
    intent: str | None = None,
    sample_shape: dict[str, Any] | None = None,
    auth_kind: str = "none",  # "none" | "bearer" | "api_key_query" | "basic"
) -> dict[str, Any]:
    """Ask the LLM for a connector. Returns:
      {
        "id": str,
        "manifest": dict,
        "connector_py": str,
        "lint_issues": [LintIssue],   # empty when safe
        "model": str,
      }
    Raises AiError on non-parseable response.
    """
    user_parts = [
        f"Target URL: {url}",
        f"Auth kind: {auth_kind}",
    ]
    if intent:
        user_parts.append(f"User intent: {intent}")
    if sample_shape:
        user_parts.append(f"Probe result:\n{json.dumps(sample_shape, indent=2)[:2000]}")

    user_parts.append("\nFew-shot example of the connector contract:")
    user_parts.append(f"```\n{_FEW_SHOT_HTTPS}\n```")
    user_parts.append("\nGenerate the JSON now.")

    # Two-phase chat — same fallback as the suggestor features.
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
    last_err: AiError | None = None
    resp = None
    for use_json_format in (True, False):
        try:
            resp = await chat(
                cfg,
                messages=messages,
                response_format="json_object" if use_json_format else None,
                temperature=0.1,
                max_tokens=TOKEN_BUDGETS["generate_connector"],
            )
            break
        except AiError as e:
            last_err = e
            if "empty message" not in str(e).lower():
                raise
    if resp is None:
        raise AiError(str(last_err) if last_err else "AI returned no content")

    parsed = parse_json_lenient(resp.text)
    if parsed is None:
        raise AiError(f"AI returned non-JSON: {resp.text[:300]}")

    required = {"id", "manifest_json", "connector_py"}
    missing = required - set(parsed.keys())
    if missing:
        raise AiError(f"AI response missing keys: {missing}")

    connector_py = str(parsed["connector_py"])
    issues = lint_plugin_python(connector_py)

    return {
        "id": str(parsed["id"]),
        "label": parsed.get("label"),
        "description": parsed.get("description"),
        "manifest": parsed["manifest_json"],
        "connector_py": connector_py,
        "lint_issues": [
            {"line": i.line, "col": i.col, "rule": i.rule, "message": i.message}
            for i in issues
        ],
        "model": resp.model,
    }


def _validate_connector_id(cid: Any) -> str:
    """Reject anything that isn't safe to use as a single path segment.

    Defends against path traversal — `connector_id` flows from request
    bodies into Path joins for stage / install / discard. Without this
    guard, `..`, `/`, NUL, or absolute paths bypass the _pending/
    confinement and let a caller move/delete arbitrary directories
    inside the repo.
    """
    if not isinstance(cid, str) or not cid:
        raise ValueError("connector_id must be a non-empty string")
    if len(cid) > 64:
        raise ValueError("connector_id too long (max 64 chars)")
    if not cid.replace("_", "").isalnum():
        raise ValueError(
            f"invalid connector id: {cid!r} — must be snake_case "
            "alphanumeric (a-z 0-9 _ only, no dots / slashes / dashes)",
        )
    return cid


def _safe_path_under(root: Path, *segments: str) -> Path:
    """Join segments under root and confirm the resolved path stays
    inside root. Belt-and-braces alongside _validate_connector_id."""
    p = root.joinpath(*segments).resolve()
    root_resolved = root.resolve()
    try:
        p.relative_to(root_resolved)
    except ValueError as e:
        raise ValueError(f"path escapes root: {p} not under {root_resolved}") from e
    return p


def _pending_dir(repo_root: Path, connector_id: str) -> Path:
    cid = _validate_connector_id(connector_id)
    return _safe_path_under(repo_root, "plugins", "_pending", "connectors", cid)


def _installed_dir(repo_root: Path, connector_id: str) -> Path:
    cid = _validate_connector_id(connector_id)
    return _safe_path_under(repo_root, "plugins", "connectors", cid)


def stage_pending(repo_root: Path, connector: dict[str, Any]) -> Path:
    """Write the generated connector to plugins/_pending/connectors/<id>/.
    Caller should have run lint first (or shows the issues alongside).
    Returns the staged path."""
    cid = _validate_connector_id(connector.get("id"))
    pending_dir = _pending_dir(repo_root, cid)
    pending_dir.mkdir(parents=True, exist_ok=True)
    (pending_dir / "manifest.json").write_text(
        json.dumps(connector["manifest"], indent=2),
    )
    (pending_dir / "connector.py").write_text(connector["connector_py"])
    return pending_dir


def install_pending(repo_root: Path, connector_id: str) -> Path:
    """Move plugins/_pending/connectors/<id>/ → plugins/connectors/<id>/.
    Idempotent if the destination already matches; refuses to overwrite
    a different existing folder."""
    src = _pending_dir(repo_root, connector_id)
    dst = _installed_dir(repo_root, connector_id)
    if not src.exists():
        raise FileNotFoundError(f"pending connector {connector_id!r} not found")
    if dst.exists():
        # Only refuse if contents differ — re-installing the same code is fine.
        for fname in ("manifest.json", "connector.py"):
            sf, df = src / fname, dst / fname
            if not df.exists() or sf.read_bytes() != df.read_bytes():
                raise FileExistsError(
                    f"connector {connector_id!r} already installed with different contents — "
                    "uninstall first or pick a new id",
                )
        # Identical — clean up _pending and return existing
        import shutil as _sh
        _sh.rmtree(src)
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)
    return dst


def discard_pending(repo_root: Path, connector_id: str) -> None:
    """Delete the staged connector without installing."""
    src = _pending_dir(repo_root, connector_id)
    if src.exists():
        import shutil as _sh
        _sh.rmtree(src)
