"""Tests for the sandboxed variable templating engine.

Covers:
  - Built-in namespace shape + UTC/local-time consistency
  - Substitution + filter chains
  - Path-safety rejections (traversal, cross-OS chars, absolute paths)
  - Sandbox rejections (attribute walking, unknown filters/vars)
  - Both entry points (render_value vs render_path)
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dig.engine.templates import (
    TemplateError,
    assert_path_safe,
    build_namespace,
    has_template,
    render_path,
    render_value,
)


# A frozen reference instant used across every test that needs deterministic output.
REF = datetime(2026, 5, 11, 14, 23, 7, tzinfo=timezone.utc)


@pytest.fixture
def ns() -> dict:
    return build_namespace(
        run_id="01TESTRUN",
        pipeline_id="01PIPE",
        pipeline_name="Customer Overview",
        node_id="my_node",
        user="alice",
        env="run",
        user_vars={"region": "us-east-1", "bucket": "reports"},
        run_started_at=REF,
    )


# ---------------------------------------------------------------------------
# Built-in namespace
# ---------------------------------------------------------------------------


class TestNamespace:
    def test_utc_components_match_reference_instant(self, ns):
        assert ns["today"] == "2026-05-11"
        assert ns["now"] == "2026-05-11T14:23:07Z"
        assert ns["year"] == "2026"
        assert ns["month"] == "05"
        assert ns["day"] == "11"
        assert ns["hour"] == "14"
        assert ns["minute"] == "23"
        assert ns["second"] == "07"
        assert ns["utime"] == "14:23:07"
        assert ns["epoch"] == str(int(REF.timestamp()))

    def test_local_components_match_reference_instant_in_local_tz(self, ns):
        # We can't assert the wall-clock value (host TZ varies) — but the
        # local namespace must be present + a valid ISO date string.
        assert len(ns["today_local"]) == 10
        assert ns["today_local"][4] == "-"
        assert ns["today_local"][7] == "-"
        # ltime is always 8 chars HH:MM:SS regardless of TZ
        assert len(ns["ltime"]) == 8

    def test_run_context(self, ns):
        assert ns["run_id"] == "01TESTRUN"
        assert ns["pipeline_id"] == "01PIPE"
        assert ns["pipeline_name"] == "customer-overview"  # slugified
        assert ns["node_id"] == "my_node"
        assert ns["user"] == "alice"
        assert ns["env"] == "run"

    def test_user_vars_accessible(self, ns):
        assert ns["vars"]["region"] == "us-east-1"
        assert ns["vars"]["bucket"] == "reports"

    def test_no_run_id_defaults_empty(self):
        ns = build_namespace(run_started_at=REF)
        assert ns["run_id"] == ""
        assert ns["pipeline_id"] == ""
        assert ns["node_id"] == ""
        assert ns["user"] == "local"

    def test_pipeline_name_slugified(self):
        ns = build_namespace(pipeline_name="My Crazy Pipeline / v2!", run_started_at=REF)
        assert ns["pipeline_name"] == "my-crazy-pipeline-v2"


# ---------------------------------------------------------------------------
# Substitution + filters
# ---------------------------------------------------------------------------


class TestSubstitution:
    def test_passthrough_no_template(self, ns):
        assert render_value("hello world", ns) == "hello world"
        assert render_value("", ns) == ""

    def test_basic_substitution(self, ns):
        assert render_value("today is {{ today }}", ns) == "today is 2026-05-11"

    def test_multiple_vars(self, ns):
        out = render_value("{{ year }}/{{ month }}/{{ day }}", ns)
        assert out == "2026/05/11"

    def test_nested_lookup(self, ns):
        assert render_value("region={{ vars.region }}", ns) == "region=us-east-1"

    def test_missing_user_var_renders_empty(self, ns):
        # Missing var in `vars` namespace → empty string (so | default rescues).
        assert render_value("{{ vars.missing }}", ns) == ""

    def test_unknown_top_level_var_raises(self, ns):
        with pytest.raises(TemplateError, match="unknown variable"):
            render_value("{{ secret_key }}", ns)


class TestFilters:
    def test_upper(self, ns):
        assert render_value("{{ vars.region | upper }}", ns) == "US-EAST-1"

    def test_lower(self, ns):
        ns2 = dict(ns)
        ns2["pipeline_name"] = "FOO-BAR"
        assert render_value("{{ pipeline_name | lower }}", ns2) == "foo-bar"

    def test_strftime_reformats(self, ns):
        assert render_value("{{ today | strftime('%Y/%m/%d') }}", ns) == "2026/05/11"

    def test_strftime_from_now(self, ns):
        assert render_value("{{ now | strftime('%Y%m%d_%H%M%S') }}", ns) == "20260511_142307"

    def test_strftime_requires_format(self, ns):
        with pytest.raises(TemplateError, match="requires a format argument"):
            render_value("{{ today | strftime }}", ns)

    def test_replace_two_args(self, ns):
        assert render_value("{{ utime | replace(':', '-') }}", ns) == "14-23-07"

    def test_replace_requires_two_args(self, ns):
        with pytest.raises(TemplateError, match="requires two args"):
            render_value("{{ utime | replace(':') }}", ns)

    def test_default_kicks_in_for_missing(self, ns):
        assert render_value("{{ vars.missing | default('fallback') }}", ns) == "fallback"

    def test_default_passes_through_when_present(self, ns):
        assert render_value("{{ vars.region | default('fallback') }}", ns) == "us-east-1"

    def test_default_passes_through_zero_and_false(self, ns):
        # 0, False, 0.0 are valid values — must not be replaced by default.
        ns2 = dict(ns)
        ns2["vars"] = {**ns["vars"], "count": 0, "active": False}
        assert render_value("{{ vars.count | default('n/a') }}", ns2) == "0"
        assert render_value("{{ vars.active | default('n/a') }}", ns2) == "False"

    def test_replace_unquoted_args_rejected(self, ns):
        # Forgotten quotes around comma-separated args is a common mistake.
        # Reject loudly rather than silently treating as a single string.
        with pytest.raises(TemplateError, match="quote each one"):
            render_value("{{ utime | replace(:, -) }}", ns)

    def test_slug(self, ns):
        ns2 = dict(ns)
        ns2["pipeline_name"] = "Quarterly Report / 2026"
        assert render_value("{{ pipeline_name | slug }}", ns2) == "quarterly-report-2026"

    def test_filter_chain(self, ns):
        # vars.region → us-east-1 → upper → US-EAST-1 → lower → us-east-1
        assert render_value("{{ vars.region | upper | lower }}", ns) == "us-east-1"


# ---------------------------------------------------------------------------
# Path-safety
# ---------------------------------------------------------------------------


class TestPathRendering:
    def test_uri_with_template_renders(self, ns):
        out = render_path(
            "s3://{{ vars.bucket }}/{{ year }}/{{ month }}/{{ day }}/data.csv", ns
        )
        assert out == "s3://reports/2026/05/11/data.csv"

    def test_local_relative_path_renders(self, ns):
        out = render_path("exports/{{ pipeline_name }}/{{ today }}.parquet", ns)
        assert out == "exports/customer-overview/2026-05-11.parquet"

    def test_local_absolute_rejected_by_default(self, ns):
        with pytest.raises(TemplateError, match="absolute"):
            render_path("/exports/{{ today }}.csv", ns)

    def test_local_absolute_allowed_with_flag(self, ns):
        out = render_path("/exports/{{ today }}.csv", ns, expand_absolute=True)
        assert out == "/exports/2026-05-11.csv"

    def test_traversal_rejected(self, ns):
        with pytest.raises(TemplateError, match="traversal"):
            render_path("exports/../../etc/passwd", ns)

    def test_traversal_rejected_inside_uri(self, ns):
        with pytest.raises(TemplateError, match="traversal"):
            render_path("s3://bucket/../escape", ns)

    @pytest.mark.parametrize("bad", ["<", ">", '"', "|", "?", "*", "\x00", "\x1f"])
    def test_forbidden_char_rejected(self, bad, ns):
        with pytest.raises(TemplateError, match="forbidden character"):
            render_path(f"exports/file{bad}name.csv", ns)

    def test_colon_outside_scheme_rejected(self, ns):
        # `:` is the URI-scheme separator; appearing outside the prefix is forbidden.
        with pytest.raises(TemplateError, match="forbidden character"):
            render_path("exports/file:name.csv", ns)

    def test_colon_inside_uri_scheme_ok(self, ns):
        # The `://` of the scheme prefix is fine. (Colons in the BODY of a URI
        # remain rejected — DIG doesn't permit ports / userinfo / scheme-2.)
        assert render_path("s3://bucket/path/file.csv", ns) == "s3://bucket/path/file.csv"

    def test_unknown_uri_scheme_rejected(self, ns):
        # Pen-tester finding: a fake scheme like `fake-scheme:///etc/passwd`
        # used to slip past the absolute-path gate. Now rejected by an
        # explicit allow-list.
        with pytest.raises(TemplateError, match="unknown URI scheme"):
            render_path("fake-scheme:///etc/passwd", ns)
        with pytest.raises(TemplateError, match="unknown URI scheme"):
            render_path("evilcorp://attacker.com/payload", ns)

    def test_known_uri_schemes_accepted(self, ns):
        for scheme in ("file", "http", "https", "s3", "gs", "azure", "ftp"):
            r = render_path(f"{scheme}://host/path/x.csv", ns)
            assert r.startswith(scheme + "://")

    def test_empty_render_rejected(self, ns):
        with pytest.raises(TemplateError, match="empty"):
            render_path("{{ vars.missing }}", ns)


# ---------------------------------------------------------------------------
# Sandbox security
# ---------------------------------------------------------------------------


class TestSandbox:
    def test_attribute_walk_returns_empty_not_class(self, ns):
        # `__class__` is not a *key* in the user-vars dict, so it resolves
        # to "" — never reaches Python attribute lookup.
        assert render_value("{{ vars.__class__ }}", ns) == ""

    def test_double_dot_disallowed(self, ns):
        # `{{ vars.region.upper }}` doesn't match the substitution grammar
        # (only single-dot supported); the post-render check catches the
        # leftover `{{ ... }}` and raises so the user gets a clear error
        # rather than a literal pass-through that bites at connector load.
        with pytest.raises(TemplateError, match="single-dot"):
            render_value("{{ vars.region.upper }}", ns)

    def test_unknown_filter_rejected(self, ns):
        with pytest.raises(TemplateError, match="unknown filter"):
            render_value("{{ today | eval }}", ns)

    def test_unknown_filter_message_lists_allowed(self, ns):
        with pytest.raises(TemplateError, match="default.*replace.*strftime"):
            render_value("{{ today | exec }}", ns)

    def test_control_byte_stripped_from_render(self, ns):
        # Truly-bad control bytes (NUL, SOH) ARE stripped.
        ns2 = dict(ns)
        ns2["vars"]["evil"] = "good\x00\x01bad"
        assert render_value("{{ vars.evil }}", ns2) == "goodbad"

    def test_newline_and_tab_preserved_in_value(self, ns):
        # Whitespace control bytes (\n \t \r) are preserved in cell-content
        # rendering — they're legitimate in multi-line strings.
        ns2 = dict(ns)
        ns2["vars"]["multiline"] = "line1\nline2\tcol"
        assert render_value("{{ vars.multiline }}", ns2) == "line1\nline2\tcol"

    def test_safe_filter_rejects_traversal(self, ns):
        with pytest.raises(TemplateError, match="path traversal"):
            render_value("{{ vars.evil | safe }}", {**ns, "vars": {**ns["vars"], "evil": "a/../b"}})

    def test_safe_filter_rejects_forbidden_char(self, ns):
        with pytest.raises(TemplateError, match="cross-OS-forbidden"):
            render_value("{{ vars.evil | safe }}", {**ns, "vars": {**ns["vars"], "evil": "a:b"}})


# ---------------------------------------------------------------------------
# Helpers + entry-point sanity
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_has_template_positive(self):
        assert has_template("hello {{ today }}")
        assert has_template("{{ x }}")

    def test_has_template_negative(self):
        assert not has_template("hello world")
        assert not has_template("")
        assert not has_template("{ single brace }")
        assert not has_template(None)
        assert not has_template(42)

    def test_assert_path_safe_passes_clean_paths(self):
        assert assert_path_safe("s3://bucket/key.csv") == "s3://bucket/key.csv"
        assert assert_path_safe("exports/2026/05/data.csv") == "exports/2026/05/data.csv"

    def test_assert_path_safe_rejects_dirty(self):
        with pytest.raises(TemplateError):
            assert_path_safe("../escape")
        with pytest.raises(TemplateError):
            assert_path_safe("a/b/../c")
