"""Meta-types: logical types layered on top of physical storage.

A meta-type adds *semantic* information to a column without changing
how DIG stores it. A `url` column is still a `string` on disk, but
DIG knows it's a URL and can:

  - render values as clickable links in the grid
  - flag malformed values in red
  - skip the "is this valid?" inference next time

This module is the **type registry**. Every meta-type DIG knows about
is a `TypeDescriptor` in the `TYPES` list below, with a detector
function that says "given this column's profile, how confidently does
my type fit?"

When a dataset is profiled, every detector runs against every column.
The top-scoring candidate becomes the column's primary type;
remaining candidates with score ≥ 0.5 are surfaced to the UI as
*alternates* so the user can see "DIG thinks this is a URL but it
could also be just a plain string" and re-cast at will.

──────────────────────────────────────────────────────────────────
Adding a new meta-type — the recipe:

  1. Append a TypeDescriptor to TYPES (id, label, base, sql_type, …)
  2. Write a detector function that returns a TypeCandidate or None.
     Detectors get the column's profile dict (name, type, min, max,
     distinctCount, nullCount, sampledRows, topValues).
  3. Add the type to backend/steps/cast_type/manifest.json's enum.
  4. Add a frontend formatter in components/grid/live-grid.tsx:fmt().
  5. Add an emoji to TYPE_EMOJI in the same file.

That's it — auto-detection, the cast dropdown, the smart-picks UX,
and the profile drawer all derive from the registry.
──────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable

# Re-exported for backwards-compat (callers used to import these directly).
INDEX_MIN_DISTINCT_FRACTION = 0.999
INDEX_MIN_NON_NULL_FRACTION = 0.999
TIMEZONE_MIN_VALID_FRACTION = 0.80
SCIENTIFIC_LOW = 1e-3
SCIENTIFIC_HIGH = 1e6


# ── Public dataclasses ────────────────────────────────────────────


@dataclass
class TypeCandidate:
    """One detected possibility for a column's logical type."""
    type_id: str
    score: float        # 0..1 — how confident the detector is
    reason: str         # one-line, human-readable, e.g. "97% of values match URL pattern"


@dataclass
class TypeDescriptor:
    """Static metadata about a meta-type."""
    id: str             # snake_case, used as the value in cast_type.targetType
    label: str          # short display label with emoji ("📊 Percentage")
    base: str           # physical type: "string" | "integer" | "double" | …
    sql_type: str       # for cast_type's SQL emit ("DOUBLE", "VARCHAR", …)
    description: str    # one-line tooltip for the cast dropdown
    detector: Callable[[dict[str, Any]], TypeCandidate | None] = field(repr=False)


# ── IANA timezone set (cached) ────────────────────────────────────


@lru_cache(maxsize=1)
def iana_timezones() -> frozenset[str]:
    try:
        from zoneinfo import available_timezones
        zones = set(available_timezones())
    except Exception:
        zones = set()
    zones |= {"UTC", "GMT", "Z"}
    return frozenset(zones)


def is_valid_timezone(value: str | None) -> bool:
    if not isinstance(value, str) or not value:
        return False
    return value in iana_timezones()


# ── ISO 3166 country codes (subset; cached) ───────────────────────
# Full list is ~250 entries. We hardcode the subset rather than depend
# on pycountry to keep the install lean. If you need exotic codes,
# install pycountry and swap the implementation.

_ISO_3166_ALPHA2 = frozenset({
    "AD","AE","AF","AG","AI","AL","AM","AO","AQ","AR","AS","AT","AU","AW","AX","AZ",
    "BA","BB","BD","BE","BF","BG","BH","BI","BJ","BL","BM","BN","BO","BQ","BR","BS","BT","BV","BW","BY","BZ",
    "CA","CC","CD","CF","CG","CH","CI","CK","CL","CM","CN","CO","CR","CU","CV","CW","CX","CY","CZ",
    "DE","DJ","DK","DM","DO","DZ",
    "EC","EE","EG","EH","ER","ES","ET",
    "FI","FJ","FK","FM","FO","FR",
    "GA","GB","GD","GE","GF","GG","GH","GI","GL","GM","GN","GP","GQ","GR","GS","GT","GU","GW","GY",
    "HK","HM","HN","HR","HT","HU",
    "ID","IE","IL","IM","IN","IO","IQ","IR","IS","IT",
    "JE","JM","JO","JP",
    "KE","KG","KH","KI","KM","KN","KP","KR","KW","KY","KZ",
    "LA","LB","LC","LI","LK","LR","LS","LT","LU","LV","LY",
    "MA","MC","MD","ME","MF","MG","MH","MK","ML","MM","MN","MO","MP","MQ","MR","MS","MT","MU","MV","MW","MX","MY","MZ",
    "NA","NC","NE","NF","NG","NI","NL","NO","NP","NR","NU","NZ",
    "OM",
    "PA","PE","PF","PG","PH","PK","PL","PM","PN","PR","PS","PT","PW","PY",
    "QA",
    "RE","RO","RS","RU","RW",
    "SA","SB","SC","SD","SE","SG","SH","SI","SJ","SK","SL","SM","SN","SO","SR","SS","ST","SV","SX","SY","SZ",
    "TC","TD","TF","TG","TH","TJ","TK","TL","TM","TN","TO","TR","TT","TV","TW","TZ",
    "UA","UG","UM","US","UY","UZ",
    "VA","VC","VE","VG","VI","VN","VU",
    "WF","WS",
    "YE","YT",
    "ZA","ZM","ZW",
})


# ── Regex helpers ─────────────────────────────────────────────────


_URL_RE   = re.compile(r"^https?://[^\s<>'\"]+$", re.IGNORECASE)
_EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.IGNORECASE)
_UUID_RE  = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_IPV4_RE  = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
_IPV6_RE  = re.compile(r"^[0-9a-f:]+$", re.IGNORECASE)  # loose; full IPv6 is messy
_HEX_RE   = re.compile(r"^0x[0-9a-f]+$", re.IGNORECASE)
_PHONE_RE = re.compile(r"^\+?[1-9]\d{6,14}$")  # E.164: + then 7-15 digits
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$", re.IGNORECASE)
_RGB_COLOR_RE = re.compile(r"^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(,\s*[\d.]+\s*)?\)$", re.IGNORECASE)
_NAMED_COLORS = frozenset({
    "black","white","red","green","blue","yellow","purple","orange","pink","cyan","magenta",
    "gray","grey","brown","navy","teal","olive","lime","aqua","silver","gold","maroon","fuchsia",
    "transparent","none",
})


def _is_url(s: str) -> bool:        return isinstance(s, str) and bool(_URL_RE.match(s))
def _is_email(s: str) -> bool:      return isinstance(s, str) and bool(_EMAIL_RE.match(s))
def _is_uuid(s: str) -> bool:       return isinstance(s, str) and bool(_UUID_RE.match(s))
def _is_ipv4(s: str) -> bool:
    if not isinstance(s, str) or not _IPV4_RE.match(s): return False
    return all(0 <= int(p) <= 255 for p in s.split("."))
def _is_ipv6(s: str) -> bool:
    if not isinstance(s, str): return False
    return ":" in s and bool(_IPV6_RE.match(s)) and 2 <= s.count(":") <= 7
def _is_ip(s: str) -> bool:         return _is_ipv4(s) or _is_ipv6(s)
def _is_hex(s: str) -> bool:        return isinstance(s, str) and bool(_HEX_RE.match(s))
def _is_phone(s: str) -> bool:      return isinstance(s, str) and bool(_PHONE_RE.match(s))
def _is_color(s: str) -> bool:
    if not isinstance(s, str): return False
    s_low = s.strip().lower()
    return (bool(_HEX_COLOR_RE.match(s_low))
            or bool(_RGB_COLOR_RE.match(s_low))
            or s_low in _NAMED_COLORS)
def _is_country(s: str) -> bool:
    if not isinstance(s, str): return False
    return s.upper() in _ISO_3166_ALPHA2


# ── Common detector helpers ───────────────────────────────────────


def _topvalues_pattern_score(top_values: list[dict], predicate: Callable[[Any], bool]) -> tuple[float, int, int]:
    """For string-pattern detectors: count-weighted fraction of top values
    matching `predicate`. Returns (score, valid_rows, total_rows)."""
    valid_rows = 0
    total_rows = 0
    for tv in top_values or []:
        v = tv.get("value")
        n = int(tv.get("count") or 0)
        if not isinstance(v, str):
            continue
        total_rows += n
        if predicate(v):
            valid_rows += n
    if total_rows == 0:
        return (0.0, 0, 0)
    return (valid_rows / total_rows, valid_rows, total_rows)


def _name_match(col_name: str | None, keywords: tuple[str, ...]) -> bool:
    """Cheap name-based hint. True if any keyword appears in the column name."""
    if not isinstance(col_name, str):
        return False
    low = col_name.lower()
    return any(kw in low for kw in keywords)


# ── Detectors ────────────────────────────────────────────────────


def _detect_index(p: dict[str, Any]) -> TypeCandidate | None:
    if p.get("type") != "integer":
        return None
    sampled = p.get("sampledRows") or 0
    distinct = p.get("distinctCount")
    nulls = p.get("nullCount") or 0
    non_null = sampled - nulls
    if not sampled or distinct is None or non_null < 2:
        return None
    if non_null / sampled < INDEX_MIN_NON_NULL_FRACTION:
        return None
    if distinct / non_null < INDEX_MIN_DISTINCT_FRACTION:
        return None
    return TypeCandidate("index", 0.95, f"{distinct}/{non_null} values are unique")


def _detect_scientific(p: dict[str, Any]) -> TypeCandidate | None:
    if p.get("type") != "double":
        return None
    mn, mx = p.get("min"), p.get("max")
    try:
        abs_min = abs(float(mn)) if isinstance(mn, (int, float)) else None
        abs_max = abs(float(mx)) if isinstance(mx, (int, float)) else None
    except Exception:
        return None
    if abs_max is not None and abs_max >= SCIENTIFIC_HIGH:
        return TypeCandidate("scientific", 0.85, f"max |value| = {abs_max:.2e}")
    if abs_min is not None and 0 < abs_min < SCIENTIFIC_LOW:
        return TypeCandidate("scientific", 0.85, f"min |value| = {abs_min:.2e}")
    return None


def _detect_percentage(p: dict[str, Any]) -> TypeCandidate | None:
    if p.get("type") != "double":
        return None
    mn, mx = p.get("min"), p.get("max")
    if not isinstance(mn, (int, float)) or not isinstance(mx, (int, float)):
        return None
    in_range = (-0.001 <= mn <= 1.001) and (-0.001 <= mx <= 1.001)
    if not in_range:
        return None
    name_hint = _name_match(p.get("name"), ("pct", "percent", "rate", "ratio", "_pc", "fraction"))
    if name_hint:
        return TypeCandidate("percentage", 0.92, f"in [0,1] and name suggests percentage")
    return TypeCandidate("percentage", 0.65, f"all values in [0,1]")


def _detect_currency(p: dict[str, Any]) -> TypeCandidate | None:
    if p.get("type") not in ("double", "integer"):
        return None
    if not _name_match(p.get("name"),
                       ("price", "amount", "cost", "revenue", "balance",
                        "fee", "salary", "income", "expense", "total",
                        "value", "_usd", "_eur", "_gbp")):
        return None
    return TypeCandidate("currency", 0.75, "name suggests monetary value")


def _detect_timezone(p: dict[str, Any]) -> TypeCandidate | None:
    if p.get("type") != "string":
        return None
    score, _, _ = _topvalues_pattern_score(p.get("topValues") or [], is_valid_timezone)
    if score >= TIMEZONE_MIN_VALID_FRACTION:
        return TypeCandidate("timezone", min(score, 0.95), f"{int(score*100)}% IANA-valid zones")
    return None


def _string_pattern_detector(type_id: str, predicate: Callable[[str], bool],
                             reason_word: str, threshold: float = 0.85, max_score: float = 0.95):
    """Factory for "is the column N% of values matching this regex?" detectors."""
    def detect(p: dict[str, Any]) -> TypeCandidate | None:
        if p.get("type") != "string":
            return None
        score, _, total = _topvalues_pattern_score(p.get("topValues") or [], predicate)
        if score >= threshold and total > 0:
            return TypeCandidate(type_id, min(score, max_score),
                                 f"{int(score*100)}% of values are {reason_word}-shaped")
        return None
    return detect


def _detect_hex(p: dict[str, Any]) -> TypeCandidate | None:
    """Hex applies to either string ('0xCAFE') or string-encoded integers."""
    if p.get("type") not in ("string", "integer"):
        return None
    score, _, total = _topvalues_pattern_score(p.get("topValues") or [], _is_hex)
    if score >= 0.85 and total > 0:
        return TypeCandidate("hex", min(score, 0.95),
                             f"{int(score*100)}% of values are hex-formatted")
    return None


# ── The registry ─────────────────────────────────────────────────
#
# Order matters slightly: entries higher in the list act as tiebreakers
# when two detectors return the same score. We put more specific types
# above more general ones (e.g. uuid before hex; email before url).


TYPES: list[TypeDescriptor] = [
    # Numeric meta-types
    TypeDescriptor("index",       "🔑 Index (unique)",      "integer", "BIGINT",   "Integer column where every value should be unique. Duplicates are flagged in the grid.",
                   detector=_detect_index),
    TypeDescriptor("percentage",  "📊 Percentage",          "double",  "DOUBLE",   "Decimal in the [0, 1] range, displayed as a percent (0.15 → 15%).",
                   detector=_detect_percentage),
    TypeDescriptor("currency",    "💵 Currency",            "double",  "DOUBLE",   "Monetary value, displayed with thousands separator and 2 decimal places.",
                   detector=_detect_currency),
    TypeDescriptor("scientific",  "🔬 Scientific (IEEE)",   "double",  "DOUBLE",   "IEEE 754 double formatted in scientific notation (1.234e+10). Useful for physics, astronomy, very small probabilities.",
                   detector=_detect_scientific),
    TypeDescriptor("hex",         "🔢 Hex",                 "string",  "VARCHAR",  "Number written in hexadecimal notation (0xCAFE, 0xFF00FF).",
                   detector=_detect_hex),
    # String meta-types — most specific first
    TypeDescriptor("uuid",        "🆔 UUID",                "string",  "VARCHAR",  "RFC 4122 universally-unique identifier (8-4-4-4-12 hex).",
                   detector=_string_pattern_detector("uuid", _is_uuid, "UUID")),
    TypeDescriptor("email",       "📧 Email",               "string",  "VARCHAR",  "Email address. Invalid entries are flagged in red.",
                   detector=_string_pattern_detector("email", _is_email, "email")),
    TypeDescriptor("url",         "🔗 URL",                 "string",  "VARCHAR",  "HTTP/HTTPS URL. Rendered as a clickable link in the grid.",
                   detector=_string_pattern_detector("url", _is_url, "URL")),
    TypeDescriptor("ip",          "🌐 IP address",          "string",  "VARCHAR",  "IPv4 or IPv6 address.",
                   detector=_string_pattern_detector("ip", _is_ip, "IP-address")),
    TypeDescriptor("phone",       "📞 Phone (E.164)",       "string",  "VARCHAR",  "Phone number in E.164 international format (+12025551234).",
                   detector=_string_pattern_detector("phone", _is_phone, "E.164 phone")),
    TypeDescriptor("country",     "🌍 Country code",        "string",  "VARCHAR",  "ISO 3166-1 alpha-2 country code (US, GB, JP, …).",
                   detector=_string_pattern_detector("country", _is_country, "ISO country code")),
    TypeDescriptor("color",       "🎨 Color",               "string",  "VARCHAR",  "CSS color: hex (#1a2b3c), rgb(), or named (red, blue, …).",
                   detector=_string_pattern_detector("color", _is_color, "CSS color")),
    TypeDescriptor("timezone",    "🌍 Timezone",            "string",  "VARCHAR",  "IANA timezone name (America/New_York, Europe/Berlin, …).",
                   detector=_detect_timezone),
]


def descriptor(type_id: str) -> TypeDescriptor | None:
    for t in TYPES:
        if t.id == type_id:
            return t
    return None


# ── Top-level detection entry point ──────────────────────────────


# Threshold for surfacing as an "alternate" candidate in the UI. Below
# this we consider the match too weak to bother the user with.
ALTERNATE_MIN_SCORE = 0.50


def detect_candidates(col_profile: dict[str, Any]) -> list[TypeCandidate]:
    """Run every detector against a column's profile, return ranked list.

    The first item is the highest-scoring candidate (DIG's pick). Any
    additional items with score ≥ ALTERNATE_MIN_SCORE are surfaced as
    alternates in the UI so the user can re-cast easily.
    """
    out: list[TypeCandidate] = []
    for t in TYPES:
        try:
            cand = t.detector(col_profile)
        except Exception:
            cand = None
        if cand is not None:
            out.append(cand)
    out.sort(key=lambda c: c.score, reverse=True)
    return out


# ── Backwards-compat shims ───────────────────────────────────────
# Earlier callers imported these directly. Keep them working.


def detect_index(*, distinct: int | None, non_null: int | None,
                 sampled: int | None) -> bool:
    """Legacy wrapper — prefer detect_candidates() on the col profile."""
    if not sampled or distinct is None or non_null is None or non_null < 2:
        return False
    return (
        non_null / sampled >= INDEX_MIN_NON_NULL_FRACTION
        and distinct / non_null >= INDEX_MIN_DISTINCT_FRACTION
    )


def detect_scientific(*, abs_min: float | None, abs_max: float | None) -> bool:
    if abs_max is not None and abs_max >= SCIENTIFIC_HIGH:
        return True
    if abs_min is not None and 0 < abs_min < SCIENTIFIC_LOW:
        return True
    return False


def detect_timezone_from_top(top_values: list[dict]) -> bool:
    score, _, _ = _topvalues_pattern_score(top_values, is_valid_timezone)
    return score >= TIMEZONE_MIN_VALID_FRACTION
