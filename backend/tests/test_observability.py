"""Tests for the observability layer: JSON logs, error codes, metrics.

Covers:
  - JSON formatter shape + extras forwarding
  - configure_logging idempotency
  - ErrorCode vocabulary stability
  - DigError carries code + context
  - Metrics counter / gauge / histogram + Prometheus render
"""
from __future__ import annotations

import io
import json
import logging

import pytest

from dig.observability import (
    DigError,
    ErrorCode,
    configure_logging,
    inc,
    is_json_logging,
    render_prometheus,
    set_gauge,
    histogram_observe,
)
from dig.observability.logging_setup import JsonFormatter
from dig.observability.metrics import _reset_for_tests


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class TestJsonFormatter:
    def test_basic_shape(self):
        fmt = JsonFormatter()
        rec = logging.LogRecord(
            name="dig.test", level=logging.INFO, pathname=__file__, lineno=1,
            msg="hello", args=(), exc_info=None,
        )
        out = fmt.format(rec)
        payload = json.loads(out)
        assert payload["level"] == "INFO"
        assert payload["logger"] == "dig.test"
        assert payload["message"] == "hello"
        assert "time" in payload
        # No 'error' / 'extra' keys when nothing was supplied.
        assert "error" not in payload
        assert "extra" not in payload

    def test_message_args_interpolated(self):
        fmt = JsonFormatter()
        rec = logging.LogRecord(
            name="x", level=logging.INFO, pathname=__file__, lineno=1,
            msg="hello %s", args=("world",), exc_info=None,
        )
        assert json.loads(fmt.format(rec))["message"] == "hello world"

    def test_extras_forwarded(self):
        fmt = JsonFormatter()
        rec = logging.LogRecord(
            name="x", level=logging.WARNING, pathname=__file__, lineno=1,
            msg="oops", args=(), exc_info=None,
        )
        rec.run_id = "01ABC"
        rec.node_id = "filter_emails"
        payload = json.loads(fmt.format(rec))
        assert payload["extra"]["run_id"] == "01ABC"
        assert payload["extra"]["node_id"] == "filter_emails"

    def test_error_code_promoted_to_top_level(self):
        fmt = JsonFormatter()
        rec = logging.LogRecord(
            name="x", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="cast broke", args=(), exc_info=None,
        )
        rec.error_code = "DIG_E_1004"
        rec.run_id = "01ABC"
        payload = json.loads(fmt.format(rec))
        # error_code is a top-level key for easy grep, not buried in `extra`.
        assert payload["error_code"] == "DIG_E_1004"
        assert payload["extra"]["run_id"] == "01ABC"

    def test_exception_formatted_as_list_of_lines(self):
        fmt = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            rec = logging.LogRecord(
                name="x", level=logging.ERROR, pathname=__file__, lineno=1,
                msg="exception happened", args=(), exc_info=sys.exc_info(),
            )
        payload = json.loads(fmt.format(rec))
        assert isinstance(payload["error"], list)
        assert any("ValueError" in line for line in payload["error"])


class TestConfigureLogging:
    def test_idempotent_handler_replacement(self, monkeypatch: pytest.MonkeyPatch):
        """Repeated configure_logging calls must NOT pile up handlers."""
        monkeypatch.delenv("DIG_LOG_FORMAT", raising=False)
        for _ in range(5):
            configure_logging()
        managed = [h for h in logging.getLogger().handlers if getattr(h, "_dig_managed", False)]
        assert len(managed) == 1

    def test_json_logging_flag(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("DIG_LOG_FORMAT", "json")
        assert is_json_logging() is True
        monkeypatch.setenv("DIG_LOG_FORMAT", "text")
        assert is_json_logging() is False
        monkeypatch.delenv("DIG_LOG_FORMAT")
        assert is_json_logging() is False


# ---------------------------------------------------------------------------
# Error codes
# ---------------------------------------------------------------------------


class TestErrorCodes:
    def test_codes_are_stable_strings_starting_with_DIG_E_(self):
        for code in ErrorCode:
            assert isinstance(code.value, str)
            assert code.value.startswith("DIG_E_")

    def test_dig_error_carries_code_and_context(self):
        err = DigError(
            ErrorCode.E_1004_CAST_FAILURE,
            "could not parse '$' as number",
            context={"column": "price", "row_index": 7},
        )
        assert err.code is ErrorCode.E_1004_CAST_FAILURE
        assert err.code.value == "DIG_E_1004"
        assert err.context == {"column": "price", "row_index": 7}
        # str(err) includes the code prefix.
        assert "DIG_E_1004" in str(err)

    def test_codes_groupable_by_first_digit(self):
        # The first digit groups the area — verify the documented contract.
        # Engine codes start with 1, storage with 2, etc.
        engine = [c for c in ErrorCode if c.value.startswith("DIG_E_1")]
        storage = [c for c in ErrorCode if c.value.startswith("DIG_E_2")]
        assert len(engine) >= 5  # sanity: engine group is the populated one
        assert len(storage) >= 3

    def test_no_duplicate_codes(self):
        values = [c.value for c in ErrorCode]
        assert len(values) == len(set(values)), "duplicate ErrorCode value detected"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    """Wipe the metrics registry between tests so order doesn't matter."""
    _reset_for_tests()
    yield
    _reset_for_tests()


class TestMetrics:
    def test_counter_inc_and_render(self):
        inc("test_counter", labels={"status": "succeeded"})
        inc("test_counter", labels={"status": "succeeded"})
        inc("test_counter", labels={"status": "failed"})
        out = render_prometheus()
        assert "# TYPE test_counter counter" in out
        assert 'test_counter{status="succeeded"} 2' in out
        assert 'test_counter{status="failed"} 1' in out

    def test_counter_no_labels(self):
        inc("simple_counter", value=5)
        out = render_prometheus()
        assert "simple_counter 5" in out

    def test_gauge_overwrites(self):
        set_gauge("test_gauge", 3.0)
        set_gauge("test_gauge", 7.0)
        out = render_prometheus()
        assert "test_gauge 7.0" in out
        assert "test_gauge 3.0" not in out

    def test_histogram_buckets(self):
        for v in [0.001, 0.005, 0.5, 5.0, 100.0]:
            histogram_observe("test_hist", v)
        out = render_prometheus()
        # +Inf bucket has the total count
        assert 'test_hist_bucket{le="+Inf"} 5' in out
        assert "test_hist_sum " in out
        assert "test_hist_count 5" in out
        # 0.005 bucket includes 0.001 + 0.005 = 2
        assert 'test_hist_bucket{le="0.005"} 2' in out

    def test_empty_registry_rendered_safely(self):
        out = render_prometheus()
        # Even with no metrics, output is non-empty and a valid string
        # (the placeholder comment makes it visible the endpoint is alive).
        assert isinstance(out, str)
        assert out.endswith("\n")

    def test_label_escaping(self):
        # Quotes and backslashes inside label values must be escaped or
        # Prometheus's parser blows up the entire scrape.
        inc("c", labels={"path": 'a"b\\c'})
        out = render_prometheus()
        # The escaped form: backslash before " and \\
        assert 'path="a\\"b\\\\c"' in out
