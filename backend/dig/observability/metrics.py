"""In-process metrics registry — Prometheus text format on `/metrics`.

No external dependencies. The implementation is intentionally minimal
because the OSS single-user case doesn't need quantile estimators or
exemplars; deployments that want the full Prometheus SDK can install
`prometheus-client` and swap in `prometheus_client.REGISTRY` via the
adapter pattern (not shipped here — yet).

Thread-safety: counters use atomic-ish update via a single lock that
protects the registry dict. Throughput is plenty for typical DIG
workloads (a few thousand counter increments per second per process).
"""
from __future__ import annotations

import logging
import math
import threading
from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

log = logging.getLogger(__name__)


_LOCK = threading.Lock()
_COUNTERS: dict[tuple[str, frozenset[tuple[str, str]]], float] = defaultdict(float)
_GAUGES: dict[tuple[str, frozenset[tuple[str, str]]], float] = {}
_HISTOGRAMS: dict[tuple[str, frozenset[tuple[str, str]]], list[float]] = defaultdict(list)
_HELP: dict[str, str] = {}
_TYPE: dict[str, Literal["counter", "gauge", "histogram"]] = {}

# Pen-tester / QA finding: per-metric label cardinality is unbounded today,
# which is the canonical Prometheus footgun (e.g. emitting `step_id=foo123`
# as a label on every step execution lets a misbehaving plugin grow the
# in-process dict without bound and OOM the API process). Cap the number
# of distinct label-tuple values per metric. Past the cap, additional
# observations land in an `_overflow` bucket so the count isn't lost,
# but per-label breakdown stops growing.
_PER_METRIC_CARDINALITY_CAP = 10_000
_OVERFLOW_LABEL = (("__overflow__", "1"),)

# Round-4 QA finding: the per-metric cardinality cap stops new label
# tuples per metric, but doesn't cap the metric-NAME space itself. A
# misbehaving plugin emitting millions of distinct names could OOM the
# registry. Cap globally; past this any new metric name lands in a
# single `__metric_overflow__` sentinel and is logged once.
_METRIC_NAME_CAP = 1_000
_NAME_OVERFLOW_SENTINEL = "__metric_overflow__"
_name_overflow_warned = False

# Round-3 pen-tester: a malicious step (or a forged plugin) could pass a
# multi-megabyte string as a label value — `_format_labels` would then
# happily render it into the `/metrics` body, ballooning the response and
# poisoning every Prometheus scrape until the process restarts. Cap label
# names + values defensively. Past the limits, truncate (with an
# unambiguous suffix) so the metric still emits but the abuse is bounded.
_MAX_LABEL_NAME_LEN = 128
_MAX_LABEL_VALUE_LEN = 256


def _gate_metric_name(name: str) -> str:
    """Enforce the global metric-name cap. Returns ``name`` unchanged
    once the metric is registered, returns the overflow sentinel for
    additional new names past the cap. Caller holds _LOCK."""
    global _name_overflow_warned
    if name in _TYPE:
        return name
    if len(_TYPE) >= _METRIC_NAME_CAP:
        if not _name_overflow_warned:
            log.warning(
                "metric-name cap (%d) reached; further new names collapse to %r",
                _METRIC_NAME_CAP, _NAME_OVERFLOW_SENTINEL,
            )
            _name_overflow_warned = True
        return _NAME_OVERFLOW_SENTINEL
    return name


def _truncate_labels(labels: dict[str, str] | None) -> dict[str, str]:
    """Cap label name + value length. Defensive — emitting metrics from a
    plugin should never be able to bloat /metrics indefinitely."""
    if not labels:
        return {}
    out: dict[str, str] = {}
    for k, v in labels.items():
        ks = str(k)
        vs = str(v)
        if len(ks) > _MAX_LABEL_NAME_LEN:
            ks = ks[:_MAX_LABEL_NAME_LEN - 3] + "..."
        if len(vs) > _MAX_LABEL_VALUE_LEN:
            vs = vs[:_MAX_LABEL_VALUE_LEN - 3] + "..."
        out[ks] = vs
    return out

# Histogram buckets, in seconds — exponential out to 60s. Chosen for
# request-latency + step-execution-time use cases.
_DEFAULT_BUCKETS: tuple[float, ...] = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60,
)


def _key(name: str, labels: dict[str, str] | None) -> tuple[str, frozenset[tuple[str, str]]]:
    return name, frozenset((labels or {}).items())


def counter(name: str, help_text: str = "") -> None:
    """Declare a counter (idempotent). Optional — `inc` registers on first use."""
    with _LOCK:
        _TYPE.setdefault(name, "counter")
        if help_text:
            _HELP[name] = help_text


def gauge(name: str, help_text: str = "") -> None:
    """Declare a gauge (idempotent)."""
    with _LOCK:
        _TYPE.setdefault(name, "gauge")
        if help_text:
            _HELP[name] = help_text


def _cap_labels_for_metric(
    name: str, store: dict, requested_key: tuple[str, frozenset[tuple[str, str]]],
) -> tuple[str, frozenset[tuple[str, str]]]:
    """If `name` already has _PER_METRIC_CARDINALITY_CAP distinct label
    tuples and the requested one is new, return the overflow key instead.
    Caller must hold _LOCK."""
    if requested_key in store:
        return requested_key
    distinct = sum(1 for k in store if k[0] == name)
    if distinct >= _PER_METRIC_CARDINALITY_CAP:
        return (name, frozenset(_OVERFLOW_LABEL))
    return requested_key


def inc(name: str, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
    """Increment a counter. Auto-registers the metric on first call.
    Past the per-metric cardinality cap, the increment lands in a single
    `__overflow__="1"` bucket so the total stays accurate but the labels
    don't grow unbounded. Label name/value lengths are truncated.

    Round-4 QA finding: counters are monotonically non-decreasing by
    Prometheus definition. ``inc(name, -5)`` previously silently
    decremented; now it's rejected. NaN/inf are also rejected — they
    poison ``_sum`` rendering and break every scrape.
    """
    if not math.isfinite(value) or value < 0:
        log.warning("metrics.inc(%r) rejected non-finite/negative value %r", name, value)
        return
    safe_labels = _truncate_labels(labels)
    with _LOCK:
        gated = _gate_metric_name(name)
        _TYPE.setdefault(gated, "counter")
        key = _cap_labels_for_metric(gated, _COUNTERS, _key(gated, safe_labels))
        _COUNTERS[key] += value


def set_gauge(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    """Set a gauge to an absolute value. Labels are capped per `inc()`.

    Gauges may be NaN/inf in principle (e.g. ``ratio = a / b`` with
    b=0), but Prometheus text format requires those rendered as ``NaN``
    / ``+Inf`` / ``-Inf``. We accept the value here and let
    ``_format_float`` produce the spec-compliant string.
    """
    safe_labels = _truncate_labels(labels)
    with _LOCK:
        gated = _gate_metric_name(name)
        _TYPE.setdefault(gated, "gauge")
        key = _cap_labels_for_metric(gated, _GAUGES, _key(gated, safe_labels))
        _GAUGES[key] = value


def histogram_observe(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
) -> None:
    """Append an observation to a histogram. Labels are capped per `inc()`.
    Buckets aggregated on render.

    Round-4 QA finding: NaN/inf observations corrupted the rendered
    ``_sum`` line (``sum([5, nan]) == nan``) which violates the
    Prometheus text spec and breaks every downstream scrape. Reject
    here; emit a counter so operators see the dropped count.
    """
    if not math.isfinite(value):
        log.warning("metrics.histogram_observe(%r) rejected non-finite %r", name, value)
        with _LOCK:
            _TYPE.setdefault("dig_metric_observations_dropped_total", "counter")
            drop_key = _key(
                "dig_metric_observations_dropped_total",
                {"metric": name[:64]},
            )
            _COUNTERS[drop_key] += 1
        return
    safe_labels = _truncate_labels(labels)
    with _LOCK:
        gated = _gate_metric_name(name)
        _TYPE.setdefault(gated, "histogram")
        key = _cap_labels_for_metric(gated, _HISTOGRAMS, _key(gated, safe_labels))
        _HISTOGRAMS[key].append(value)


def _format_labels(label_tuples: frozenset[tuple[str, str]]) -> str:
    if not label_tuples:
        return ""
    items = sorted(label_tuples)
    body = ",".join(f'{k}="{_escape(v)}"' for k, v in items)
    return "{" + body + "}"


def _escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_float(v: float) -> str:
    """Prometheus text format: ``+Inf`` / ``-Inf`` / ``NaN`` for special
    values; plain repr otherwise. Round-4 QA finding: Python's ``str(inf)``
    yields ``"inf"`` (lowercase) which scrapers reject. Spec calls for
    the exact casing emitted here.
    """
    if math.isnan(v):
        return "NaN"
    if math.isinf(v):
        return "+Inf" if v > 0 else "-Inf"
    return repr(v) if isinstance(v, float) else str(v)


def render_prometheus() -> str:
    """Serialize the registry into the Prometheus text exposition format.

    Format reference: https://github.com/prometheus/docs/blob/main/content/docs/instrumenting/exposition_formats.md
    """
    lines: list[str] = []
    with _LOCK:
        seen_names: set[str] = set()
        for name, kind in sorted(_TYPE.items()):
            if name in seen_names:
                continue
            seen_names.add(name)
            help_text = _HELP.get(name, "")
            if help_text:
                lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {kind}")
            if kind == "counter":
                for (key_name, label_tuples), val in sorted(
                    ((k, v) for k, v in _COUNTERS.items() if k[0] == name),
                    key=lambda kv: sorted(kv[0][1]),
                ):
                    lines.append(f"{key_name}{_format_labels(label_tuples)} {_format_float(val)}")
            elif kind == "gauge":
                for (key_name, label_tuples), val in sorted(
                    ((k, v) for k, v in _GAUGES.items() if k[0] == name),
                    key=lambda kv: sorted(kv[0][1]),
                ):
                    lines.append(f"{key_name}{_format_labels(label_tuples)} {_format_float(val)}")
            elif kind == "histogram":
                # One bucket line per bucket boundary + _sum + _count.
                for (key_name, label_tuples), samples in sorted(
                    ((k, v) for k, v in _HISTOGRAMS.items() if k[0] == name),
                    key=lambda kv: sorted(kv[0][1]),
                ):
                    cumulative = 0
                    label_str_inner = _label_inner(label_tuples)
                    for upper in _DEFAULT_BUCKETS:
                        cumulative = sum(1 for s in samples if s <= upper)
                        lines.append(
                            f'{key_name}_bucket{{le="{upper}"{label_str_inner}}} {cumulative}'
                        )
                    lines.append(
                        f'{key_name}_bucket{{le="+Inf"{label_str_inner}}} {len(samples)}'
                    )
                    lines.append(
                        f"{key_name}_sum{_format_labels(label_tuples)} {_format_float(sum(samples))}"
                    )
                    lines.append(f"{key_name}_count{_format_labels(label_tuples)} {len(samples)}")
    if not lines:
        return "# DIG metrics registry is empty\n"
    return "\n".join(lines) + "\n"


def _label_inner(label_tuples: frozenset[tuple[str, str]]) -> str:
    """Histogram bucket lines already open `{le="…"…}`; format the rest inline."""
    if not label_tuples:
        return ""
    items = sorted(label_tuples)
    body = ",".join(f'{k}="{_escape(v)}"' for k, v in items)
    return "," + body


def _reset_for_tests() -> None:
    """Test-only — wipe the registry between tests. Not part of the public API."""
    with _LOCK:
        _COUNTERS.clear()
        _GAUGES.clear()
        _HISTOGRAMS.clear()
        _HELP.clear()
        _TYPE.clear()


# Pre-declare the metrics DIG emits today so the registry shape is
# discoverable from `/metrics` even before the first run.
counter("dig_runs_total", "Total pipeline runs by terminal status")
counter("dig_steps_executed_total", "Total step executions by step_id + outcome")
counter("dig_nan_cells_produced_total", "Cells turned NULL via NaN/cast-failure, by cause")
gauge("dig_inflight_runs", "Number of currently-running pipeline runs")
gauge("dig_dig_version", "Running DIG version (1=this build)")
