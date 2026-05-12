"""Sandboxed variable templating for pipeline strings.

Supports `{{ variable }}` and `{{ variable | filter[(...)] }}` substitution
in dataset URIs, output sink URIs, and any string-typed cell-content
expressions that opt in. Resolved once per run (at pipeline-load /
execution-start time) so every node sees consistent timestamps.

Design lock per `internal/proposals/NULL_AND_NAN_DISPLAY.md`-style
sandbox philosophy: no control flow (`{% if %}`, `{% for %}`),
no arbitrary attribute access (`{{ vars.__class__ }}`), no Python
expression evaluation. Only `name | filter | filter('arg')` chains
against a fixed built-in namespace + the user-defined `vars` namespace.

Built-in namespace
==================

Time / date (all explicit about UTC vs local):

  {{ today }}           UTC date, ISO 8601                   "2026-05-11"
  {{ today_local }}     Host-local date                      "2026-05-11"
  {{ now }}             UTC timestamp, ISO 8601 with Z       "2026-05-11T14:23:07Z"
  {{ now_local }}       Host-local ISO timestamp w/ offset   "2026-05-11T07:23:07-07:00"
  {{ year }}            UTC year, 4-digit                    "2026"
  {{ month }}           UTC month, 2-digit                   "05"
  {{ day }}             UTC day-of-month, 2-digit            "11"
  {{ year_local }}      Host-local year                      "2026"
  {{ month_local }}     Host-local month                     "05"
  {{ day_local }}       Host-local day                       "11"
  {{ hour }}            UTC hour, 2-digit                    "14"
  {{ minute }}          UTC minute, 2-digit                  "23"
  {{ second }}          UTC second, 2-digit                  "07"
  {{ utime }}           UTC HH:MM:SS                         "14:23:07"
  {{ ltime }}           Host-local HH:MM:SS                  "07:23:07"
  {{ epoch }}           Unix seconds (UTC)                   "1778415787"

Run / pipeline context:

  {{ run_id }}            ULID of this run
  {{ run_started_at }}    UTC ISO of run start
  {{ pipeline_id }}       ULID of the pipeline
  {{ pipeline_name }}     Slugified pipeline name
  {{ node_id }}           DAG node id (only inside per-step contexts)
  {{ user }}              "local" in OSS; OIDC sub in enterprise
  {{ env }}               "dev" / "preview" / "run"

User-defined namespace:

  {{ vars.region }}  → reads pipeline.metadata.variables.region

Filters
=======

  | upper                      ASCII uppercase
  | lower                      ASCII lowercase
  | strftime('%Y/%m/%d')       Reformat a date/timestamp variable
  | replace('-', '/')          Substring replace
  | default('us-east-1')       Used when the variable is missing/empty
  | slug                       Filesystem-safe lowercase slug
  | safe                       Path-safety check (raises on traversal)

Path safety
===========

`render_path` is the entry point for any rendered string that lands in
a filesystem / URI. It rejects:

  - characters forbidden in cross-platform filenames: `:` `*` `?` `"`
    `<` `>` `|` and ASCII control bytes
  - `..` path segments (traversal)
  - absolute paths unless explicitly opted in (`expand_absolute=True`)
  - empty rendered output

`render_value` is the entry point for rendered cell content; it skips
path-safety and only enforces the no-control-bytes rule.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from typing import Any

# --------------------------------------------------------------------------- #
# Built-in namespace                                                          #
# --------------------------------------------------------------------------- #


def _slug(s: str) -> str:
    """Filesystem-safe lowercase slug — alphanumerics + hyphen only."""
    out = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(s)).strip("-").lower()
    return out or "unnamed"


def _safe_path_segment(s: str) -> str:
    """Strip cross-OS-forbidden characters from a rendered string used as a path segment.

    Does NOT touch path separators — caller may legitimately want `2026/05/11`.
    """
    return re.sub(r'[<>:"|?*\x00-\x1f]+', "_", str(s))


def build_namespace(
    *,
    run_id: str | None = None,
    run_started_at: datetime | None = None,
    pipeline_id: str | None = None,
    pipeline_name: str | None = None,
    node_id: str | None = None,
    user: str | None = None,
    env: str = "run",
    user_vars: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Snapshot the built-in variable namespace at one instant.

    Every variable resolved against this namespace is consistent — a run
    that uses `{{ year }}/{{ month }}/{{ day }}` will not straddle
    midnight even if the actual rendering happens microseconds apart.
    """
    now_utc = run_started_at or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_local = now_utc.astimezone()  # uses host timezone

    return {
        # UTC components
        "today":     now_utc.strftime("%Y-%m-%d"),
        "now":       now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "year":      now_utc.strftime("%Y"),
        "month":     now_utc.strftime("%m"),
        "day":       now_utc.strftime("%d"),
        "hour":      now_utc.strftime("%H"),
        "minute":    now_utc.strftime("%M"),
        "second":    now_utc.strftime("%S"),
        "utime":     now_utc.strftime("%H:%M:%S"),
        "epoch":     str(int(now_utc.timestamp())),
        # Local-time components
        "today_local": now_local.strftime("%Y-%m-%d"),
        "now_local":   now_local.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "year_local":  now_local.strftime("%Y"),
        "month_local": now_local.strftime("%m"),
        "day_local":   now_local.strftime("%d"),
        "ltime":       now_local.strftime("%H:%M:%S"),
        # Context
        "run_id":         run_id or "",
        "run_started_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline_id":    pipeline_id or "",
        "pipeline_name":  _slug(pipeline_name or ""),
        "node_id":        node_id or "",
        "user":           user or "local",
        "env":            env,
        # User-defined
        "vars": dict(user_vars or {}),
    }


# --------------------------------------------------------------------------- #
# Filters                                                                     #
# --------------------------------------------------------------------------- #


def _filter_upper(v: Any, _arg: list[str] | None = None) -> str:
    return str(v).upper()


def _filter_lower(v: Any, _arg: list[str] | None = None) -> str:
    return str(v).lower()


def _filter_strftime(v: Any, arg: list[str] | None = None) -> str:
    """Reformat a date / timestamp string. Parses ISO 8601 then applies strftime."""
    if not arg or not arg[0]:
        raise TemplateError("strftime filter requires a format argument, e.g. {{ today | strftime('%Y/%m/%d') }}")
    fmt = arg[0]
    s = str(v)
    # Try a few likely shapes; ISO date + ISO datetime + epoch seconds.
    parsed: datetime | None = None
    for parse_fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(s, parse_fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            # Try interpreting as Unix epoch seconds. Catch OverflowError + OSError
            # in addition to ValueError — `int(s)` for "99999999999999999" parses
            # but `fromtimestamp` overflows (silently OK on 64-bit *nix, raises
            # OverflowError on Windows / 32-bit). We also bound the int range so
            # the error message doesn't echo back arbitrarily-large user input.
            try:
                epoch_int = int(s)
                if not (-1 << 53) <= epoch_int <= (1 << 53):
                    raise OverflowError("epoch out of representable range")
                parsed = datetime.fromtimestamp(epoch_int, tz=timezone.utc)
            except (ValueError, OSError, OverflowError) as e:
                # Truncate echoed value so a poisoned user-var doesn't bloat logs.
                truncated = s[:64] + ("…" if len(s) > 64 else "")
                raise TemplateError(
                    f"strftime: cannot parse {truncated!r} as date/timestamp",
                ) from e
    return parsed.strftime(fmt)


def _filter_replace(v: Any, arg: list[str] | None = None) -> str:
    if not arg or len(arg) < 2:
        raise TemplateError("replace filter requires two args: {{ x | replace('old', 'new') }}")
    return str(v).replace(arg[0], arg[1])


def _filter_default(v: Any, arg: list[str] | None = None) -> str:
    # `None` (= unknown/missing var lookup result) → use default.
    # Empty STRING is also defaulted (matches Jinja2's truthy-default).
    # `0`, `False`, `0.0` are NOT defaulted — they're valid values.
    if v is None:
        return (arg[0] if arg else "") or ""
    if isinstance(v, str) and v == "":
        return (arg[0] if arg else "") or ""
    return str(v)


def _filter_slug(v: Any, _arg: list[str] | None = None) -> str:
    return _slug(str(v))


def _filter_safe(v: Any, _arg: list[str] | None = None) -> str:
    """Path-safety check — raises if the rendered value contains traversal or forbidden bytes."""
    s = str(v)
    if ".." in s.split("/"):
        raise TemplateError(f"safe: path traversal detected in {s!r}")
    if re.search(r'[<>:"|?*\x00-\x1f]', s):
        raise TemplateError(f"safe: cross-OS-forbidden character in {s!r}")
    return s


_FILTERS = {
    "upper":    _filter_upper,
    "lower":    _filter_lower,
    "strftime": _filter_strftime,
    "replace":  _filter_replace,
    "default":  _filter_default,
    "slug":     _filter_slug,
    "safe":     _filter_safe,
}


# --------------------------------------------------------------------------- #
# Parser + renderer                                                           #
# --------------------------------------------------------------------------- #


class TemplateError(ValueError):
    """Raised on any template syntax / sandbox / lookup violation."""


# `{{ name }}` or `{{ name | filter }}` or `{{ name | filter('arg') }}`.
# Variable name allows dotted attribute access (one level only — for `vars.x`).
_TEMPLATE_RE = re.compile(
    r"\{\{\s*"
    r"(?P<name>[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?)"
    r"(?P<filters>(?:\s*\|\s*[a-z_][a-z0-9_]*(?:\([^)]*\))?)*)"
    r"\s*\}\}",
    re.IGNORECASE,
)

_FILTER_RE = re.compile(
    r"\|\s*(?P<name>[a-z_][a-z0-9_]*)(?:\((?P<arg>[^)]*)\))?",
    re.IGNORECASE,
)


def _resolve_name(name: str, ns: dict[str, Any]) -> Any:
    """Resolve `foo` or `vars.bar` against the namespace.

    Only one level of dotted access is supported — `vars.foo` works,
    `vars.foo.bar` does not. This blocks attribute-walking attacks
    (`{{ vars.__class__.__base__ }}`).
    """
    if "." in name:
        head, rest = name.split(".", 1)
        if "." in rest:
            raise TemplateError(f"only single-dot access is allowed; got {name!r}")
        if head not in ns:
            raise TemplateError(f"unknown variable {head!r}")
        bag = ns[head]
        if not isinstance(bag, dict):
            raise TemplateError(f"variable {head!r} is not a namespace")
        if rest not in bag:
            # default-friendly: empty string, filter chain may rescue with `| default`.
            return ""
        return bag[rest]
    if name not in ns:
        raise TemplateError(f"unknown variable {name!r}")
    return ns[name]


_QUOTED_ARG_RE = re.compile(r"""['"]([^'"]*)['"]""")


def _parse_filter_args(raw: str) -> list[str]:
    """Split a filter's parenthesised arg list into a list of strings.

    Accepts: `'a'`, `'a', 'b'`, `"a"`, `"a", "b"`, plus bare unquoted single
    arg (treated as one string). Returns [] for empty input.

    Defensive: a bare unquoted arg containing `,` is REJECTED with a
    TemplateError. Previously the bare-arg fallback would silently treat
    `replace(a, b)` (forgotten quotes) as a single-string `replace`
    target `"a, b"`, which is sneaky-wrong. Force the user to quote.
    """
    raw = (raw or "").strip()
    if not raw:
        return []
    matches = _QUOTED_ARG_RE.findall(raw)
    if matches:
        return matches
    # Bare unquoted single arg fallback — but reject if it contains a
    # comma (almost certainly forgotten quotes around multi-arg call).
    if "," in raw:
        raise TemplateError(
            f"filter argument {raw!r} looks like multiple unquoted args; "
            f"quote each one, e.g. replace('a', 'b')",
        )
    return [raw]


def _apply_filters(value: Any, raw_filters: str) -> str:
    for m in _FILTER_RE.finditer(raw_filters):
        fname = m.group("name")
        if fname not in _FILTERS:
            raise TemplateError(
                f"unknown filter {fname!r}; allowed: {', '.join(sorted(_FILTERS))}"
            )
        args = _parse_filter_args(m.group("arg") or "")
        value = _FILTERS[fname](value, args)
    return str(value)


def render_value(template: str, namespace: dict[str, Any]) -> str:
    """Render a string template against the namespace, no path-safety enforced.

    Use for cell-content expressions. The output may legitimately contain
    `:`, `/`, etc. — those are valid in column values.
    """
    if template is None:
        return ""
    if not isinstance(template, str):
        return str(template)
    if "{{" not in template:
        return template

    def _sub(m: re.Match[str]) -> str:
        name = m.group("name")
        raw_filters = m.group("filters") or ""
        try:
            value = _resolve_name(name, namespace)
        except TemplateError:
            # Re-raise — TemplateError is the contract.
            raise
        rendered = _apply_filters(value, raw_filters)
        # Strip TRULY-bad control bytes (NUL, SOH-BEL, BS, FF, SO-US) but
        # preserve `\t` (0x09), `\n` (0x0a), `\r` (0x0d) — these are
        # legitimate in cell-content templates (multi-line addresses,
        # tab-separated values inside a quoted column, etc.). For path
        # rendering, `assert_path_safe` rejects any control byte separately.
        return re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f]", "", rendered)

    out = _TEMPLATE_RE.sub(_sub, template)
    # Catch templates whose body did not match the substitution regex —
    # e.g. `{{ vars.region.upper }}` (double-dot, only single-dot supported)
    # or `{{ Today }}` (uppercase, var names are lowercase). Without this
    # the offending chunk would pass through as literal text and surface
    # as a less clear connector error downstream.
    if "{{" in out and "}}" in out:
        # Find the first leftover token for the error message.
        unrendered = re.search(r"\{\{[^}]*\}\}", out)
        bad = unrendered.group(0) if unrendered else "{{ ... }}"
        raise TemplateError(
            f"template chunk {bad!r} did not match the substitution grammar — "
            f"only `{{{{ name }}}}` and `{{{{ name | filter }}}}` (single-dot for vars.*) are supported"
        )
    return out


def render_path(template: str, namespace: dict[str, Any], *, expand_absolute: bool = False) -> str:
    """Render a template intended to land in a filesystem path / URI.

    Adds path-safety on top of render_value:
      - rejects `..` traversal segments
      - rejects cross-OS-forbidden filename characters (`:` `*` `?` `"` `<` `>` `|`)
        outside of the URI-scheme prefix
      - rejects empty output
      - by default, rejects absolute paths (caller-allow via expand_absolute=True)
    """
    rendered = render_value(template, namespace)
    if not rendered.strip():
        raise TemplateError("rendered path is empty")
    return assert_path_safe(rendered, expand_absolute=expand_absolute)


# Strict scheme allow-list — only these can prefix a rendered path. Pen-tester
# round-N: a lax `[a-z][a-z0-9+.-]*://` regex let `vars.target = "fake-scheme:///etc/passwd"`
# slip past the absolute-path gate, the body looking clean to the post-scheme check.
# The bypass is closed by REJECTING any scheme not on this list.
_URI_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_ALLOWED_URI_SCHEMES = frozenset({
    "file", "http", "https", "s3", "gs", "gcs", "azure", "az",
    "ftp", "ftps", "sftp",
})


def assert_path_safe(rendered: str, *, expand_absolute: bool = False) -> str:
    """Reject path-traversal + cross-OS-forbidden characters in a rendered path.

    URI schemes on the allow-list (`s3://...`, `file://...`, etc.) are exempt
    from the absolute-path check; their host/path parts are still scanned for
    traversal + forbidden characters. Unknown schemes are rejected — this
    closes the `fake-scheme:///etc/passwd` bypass that lets a templated URI
    bury an absolute path under a fake scheme prefix.
    """
    scheme_match = _URI_SCHEME_RE.match(rendered)
    if scheme_match:
        scheme = rendered[: scheme_match.end() - 3].lower()  # strip `://`
        if scheme not in _ALLOWED_URI_SCHEMES:
            raise TemplateError(
                f"unknown URI scheme {scheme!r} in {rendered!r}; "
                f"allowed schemes: {sorted(_ALLOWED_URI_SCHEMES)}"
            )
        body = rendered[scheme_match.end():]
    else:
        body = rendered

    # Reject path-traversal segments anywhere in the body.
    segments = body.replace("\\", "/").split("/")
    if any(seg == ".." for seg in segments):
        raise TemplateError(f"path traversal `..` detected in {rendered!r}")
    # Reject cross-OS-forbidden chars. URI scheme already stripped, so colon
    # inside the body would now be illegal (Windows can't have it in a
    # filename even as part of a drive letter when used as a relative path).
    if re.search(r'[<>:"|?*\x00-\x1f]', body):
        raise TemplateError(
            f"path contains a cross-OS-forbidden character "
            f"(any of < > : \" | ? * or a control byte): {rendered!r}"
        )
    # Absolute-path gate. Allowed for URIs; gated for bare local paths.
    if not scheme_match and not expand_absolute:
        if body.startswith("/") or (len(body) >= 2 and body[1] == ":"):
            raise TemplateError(
                f"rendered path is absolute (use expand_absolute=True if intentional): {rendered!r}"
            )
    return rendered


def has_template(s: Any) -> bool:
    """Cheap pre-check: does this string contain any `{{ }}` markers worth rendering?"""
    return isinstance(s, str) and "{{" in s and "}}" in s
