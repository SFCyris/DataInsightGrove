"""Observability primitives — structured logs, error codes, in-process metrics.

Three independent layers:

  - `logging_setup`: optional JSON log formatter (off by default) behind
    `DIG_LOG_FORMAT=json`. Preserves the friendly dev experience as default;
    flips to JSON for production deployments that pipe logs into Loki /
    Datadog / Splunk.
  - `error_codes`: a vocabulary of stable `DIG_E_NNNN` codes that surface
    in logs and in API error responses. Lets operators grep for a known
    failure mode without parsing free-text messages.
  - `metrics`: a small in-process counter / gauge / histogram registry
    served at `/metrics` in Prometheus text format. No external deps —
    `prometheus-client` is an optional install for the full SDK if a
    deployment wants histograms with quantile estimators.

All three are designed to be safe no-ops when their feature isn't enabled,
so the OSS single-user install pays zero overhead for any of them.
"""
from __future__ import annotations

from dig.observability.error_codes import DigError, ErrorCode
from dig.observability.logging_setup import configure_logging, is_json_logging
from dig.observability.metrics import (
    counter,
    gauge,
    histogram_observe,
    inc,
    render_prometheus,
    set_gauge,
)

__all__ = [
    "DigError",
    "ErrorCode",
    "configure_logging",
    "counter",
    "gauge",
    "histogram_observe",
    "inc",
    "is_json_logging",
    "render_prometheus",
    "set_gauge",
]
