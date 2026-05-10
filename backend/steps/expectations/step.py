"""Data quality expectations step (v1.1).

Inline rules — each rule is checked against the input frame; violations are
reported as an artifact (kind=expectations). Supports per-rule severity
(error | warning), webhook notifications, and a richer set of rule kinds.

Rule kinds:
  - unique:               {column}                              — values are unique
  - not_null:             {column}                              — no nulls
  - between:              {column, min?, max?}                  — numeric range
  - in:                   {column, values: [...]}               — membership in a list
  - regex_match:          {column, pattern}                     — string regex match
  - row_count_between:    {min?, max?}                          — overall row count
  - null_fraction:        {column, max: 0.05}                   — at most max% nulls
  - cardinality_between:  {column, min?, max?}                  — distinct count in range

Each rule may carry:
  - severity: "error" (default) | "warning"
  - label:    human-readable name shown in artifacts + notifications

Notification webhook:
  When notify_webhook_url is set + any rule fails (per notify_on policy),
  the step POSTs a Slack-compatible payload (`{text, attachments}`) to
  the URL. Works with Slack incoming webhooks, Discord, Mattermost,
  generic HTTP receivers.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step

log = logging.getLogger(__name__)


def _check_unique(df: pl.DataFrame, col: str) -> dict[str, Any]:
    series = df.get_column(col)
    dup = series.value_counts().filter(pl.col("count") > 1).height
    return {"passed": dup == 0, "duplicates": dup}


def _check_not_null(df: pl.DataFrame, col: str) -> dict[str, Any]:
    nulls = int(df.get_column(col).null_count())
    return {"passed": nulls == 0, "nulls": nulls}


def _check_between(df: pl.DataFrame, rule: dict[str, Any]) -> dict[str, Any]:
    col = rule["column"]
    lo = rule.get("min")
    hi = rule.get("max")
    expr = pl.col(col)
    cond = pl.lit(True)
    if lo is not None:
        cond = cond & (expr >= lo)
    if hi is not None:
        cond = cond & (expr <= hi)
    bad = df.filter(~cond & expr.is_not_null()).height
    return {"passed": bad == 0, "violations": bad}


def _check_in(df: pl.DataFrame, rule: dict[str, Any]) -> dict[str, Any]:
    col = rule["column"]
    allowed = rule.get("values") or []
    if not isinstance(allowed, list):
        return {"passed": False, "error": "'values' must be a list"}
    bad = df.filter(~pl.col(col).is_in(allowed) & pl.col(col).is_not_null()).height
    return {"passed": bad == 0, "violations": bad}


def _check_regex(df: pl.DataFrame, rule: dict[str, Any]) -> dict[str, Any]:
    col = rule["column"]
    pattern = rule.get("pattern") or ".*"
    try:
        re.compile(pattern)
    except re.error as e:
        return {"passed": False, "error": f"bad regex: {e}"}
    bad = df.filter(
        pl.col(col).is_not_null() & ~pl.col(col).cast(pl.Utf8).str.contains(pattern),
    ).height
    return {"passed": bad == 0, "violations": bad}


def _check_row_count(df: pl.DataFrame, rule: dict[str, Any]) -> dict[str, Any]:
    lo = rule.get("min")
    hi = rule.get("max")
    n = df.height
    ok = (lo is None or n >= lo) and (hi is None or n <= hi)
    return {"passed": ok, "observed": n}


def _check_null_fraction(df: pl.DataFrame, rule: dict[str, Any]) -> dict[str, Any]:
    col = rule["column"]
    max_frac = rule.get("max")
    if max_frac is None:
        return {"passed": False, "error": "null_fraction requires 'max' (e.g. 0.05 = ≤5%)"}
    n = df.height
    if n == 0:
        return {"passed": True, "fraction": 0.0}
    nulls = int(df.get_column(col).null_count())
    frac = nulls / n
    return {"passed": frac <= max_frac, "fraction": round(frac, 6), "nulls": nulls}


def _check_cardinality(df: pl.DataFrame, rule: dict[str, Any]) -> dict[str, Any]:
    col = rule["column"]
    lo = rule.get("min")
    hi = rule.get("max")
    distinct = int(df.get_column(col).n_unique())
    ok = (lo is None or distinct >= lo) and (hi is None or distinct <= hi)
    return {"passed": ok, "distinct": distinct}


_KIND_HANDLERS: dict[str, Any] = {
    "unique":              lambda df, r: _check_unique(df, r["column"]),
    "not_null":            lambda df, r: _check_not_null(df, r["column"]),
    "between":             _check_between,
    "in":                  _check_in,
    "regex_match":         _check_regex,
    "row_count_between":   _check_row_count,
    "null_fraction":       _check_null_fraction,
    "cardinality_between": _check_cardinality,
}


def _validate_webhook_url(url: str) -> str | None:
    """Return the URL if it's safe to POST to, else None (with a logged
    reason). Webhooks shouldn't be allowed to point at internal services
    — that's both an SSRF channel and a way to leak rule data to the
    wrong place. Same DIG_REST_ALLOW_PRIVATE escape hatch as the REST
    connector for trusted-host setups."""
    import os as _os
    from urllib.parse import urlsplit as _urlsplit

    parts = _urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        log.warning("expectations webhook: scheme %r not allowed (http/https only)", parts.scheme)
        return None
    if not parts.hostname:
        log.warning("expectations webhook: no host in URL")
        return None
    if _os.environ.get("DIG_REST_ALLOW_PRIVATE") == "1":
        return url

    # Lazy-import to avoid cost when no webhook configured.
    try:
        # Reuse the REST connector's resolver to keep the policy single-source.
        from connectors.rest_api.connector import _is_private_address
    except ImportError:
        return url  # connector missing — be permissive rather than block

    if _is_private_address(parts.hostname):
        log.warning(
            "expectations webhook: host %r resolves private/loopback; "
            "set DIG_REST_ALLOW_PRIVATE=1 to allow",
            parts.hostname,
        )
        return None
    return url


def _send_webhook(url: str, summary: dict[str, Any]) -> None:
    """POST a Slack-compatible payload. Best-effort: failures are logged
    but don't cascade — the step shouldn't fail because Slack is down.

    Catches narrow exception classes only — programming errors (TypeError
    on a malformed payload) should still surface in tests.
    """
    safe_url = _validate_webhook_url(url)
    if safe_url is None:
        return

    try:
        import httpx
    except ImportError:
        log.warning("expectations: httpx missing — webhook skipped")
        return

    failed = [r for r in summary.get("results", []) if not r.get("passed")]
    n_failed = summary.get("n_failed", len(failed))
    n_rules = summary.get("n_rules", len(summary.get("results", [])))

    text = f"⚠️ DIG data-quality: {n_failed}/{n_rules} rule(s) failed"
    fields = []
    for r in failed[:10]:  # cap to first 10 to keep Slack messages readable
        rule = r.get("rule", {})
        kind = rule.get("kind", "?")
        col = rule.get("column", "")
        sev = r.get("severity", "error")
        emoji = "🔴" if sev == "error" else "🟡"
        details = []
        for k in ("violations", "nulls", "duplicates", "fraction", "distinct", "observed", "error"):
            if r.get(k) is not None:
                details.append(f"{k}={r[k]}")
        fields.append({
            "title": f"{emoji} {rule.get('label') or kind}{' · ' + col if col else ''}",
            "value": ", ".join(details) or "failed",
            "short": True,
        })
    payload = {
        "text": text,
        "attachments": [{
            "color": "danger" if any((r.get("severity") or "error") == "error" for r in failed) else "warning",
            "fields": fields,
        }],
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(safe_url, json=payload)
            if not r.is_success:
                log.warning(
                    "expectations webhook returned HTTP %d (host %s)",
                    r.status_code, _safe_host(safe_url),
                )
    except (httpx.HTTPError, httpx.RequestError, ValueError) as e:
        # Narrow catch: don't swallow MemoryError / KeyboardInterrupt /
        # programming errors. ValueError covers httpx's CRLF rejection.
        log.warning("expectations webhook failed (host %s): %s", _safe_host(safe_url), e)


def _safe_host(url: str) -> str:
    """Return only the hostname for log lines — never the full URL with
    userinfo or query params (which can contain secrets)."""
    from urllib.parse import urlsplit as _urlsplit
    return _urlsplit(url).hostname or "?"


class ExpectationsStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        df = inputs["in"]
        rules = params.get("rules") or []
        fail_on_violation = bool(params.get("fail_on_violation", False))
        notify_url = (params.get("notify_webhook_url") or "").strip()
        notify_on = params.get("notify_on") or "any_failure"

        results: list[dict[str, Any]] = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            kind = (rule.get("kind") or "").lower()
            severity = rule.get("severity") if rule.get("severity") in ("error", "warning") else "error"
            label = rule.get("label")

            handler = _KIND_HANDLERS.get(kind)
            if handler is None:
                results.append({
                    "rule": rule, "passed": False, "severity": severity, "label": label,
                    "error": f"unknown kind '{kind}'",
                })
                continue

            # Column-required kinds need a present column; row_count_between doesn't.
            col_required = kind not in {"row_count_between"}
            col = rule.get("column")
            if col_required:
                if not isinstance(col, str) or not col:
                    results.append({
                        "rule": rule, "passed": False, "severity": severity, "label": label,
                        "error": "column is required",
                    })
                    continue
                if col not in df.columns:
                    results.append({
                        "rule": rule, "passed": False, "severity": severity, "label": label,
                        "error": f"column '{col}' missing from input",
                    })
                    continue

            try:
                result = handler(df, rule)
            except Exception as e:  # noqa: BLE001 — surface as a per-rule failure
                result = {"passed": False, "error": f"{type(e).__name__}: {e}"}

            result.setdefault("rule", rule)
            result["severity"] = severity
            result["label"] = label
            results.append(result)

        n_failed = sum(1 for r in results if not r.get("passed"))
        n_failed_error = sum(1 for r in results if not r.get("passed") and r.get("severity") == "error")

        artifacts = [{
            "kind": "expectations",
            "label": "Data quality checks",
            "n_rules": len(results),
            "n_failed": n_failed,
            "n_failed_error": n_failed_error,
            "results": results,
        }]

        # Notify per policy.
        should_notify = notify_url and notify_on != "never" and (
            (notify_on == "any_failure" and n_failed > 0) or
            (notify_on == "error_only" and n_failed_error > 0)
        )
        if should_notify:
            _send_webhook(notify_url, artifacts[0])

        # Fail the run only on error-severity violations (warnings never fail).
        if fail_on_violation and n_failed_error > 0:
            failed_errors = [r for r in results if not r.get("passed") and r.get("severity") == "error"]
            raise ValueError(
                f"expectations: {n_failed_error}/{len(results)} error-severity rule(s) failed; "
                f"first: {failed_errors[0]}",
            )

        return PolarsResult(output=df, artifacts=artifacts)


step = ExpectationsStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
