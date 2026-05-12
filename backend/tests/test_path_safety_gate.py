"""Regression tests for the executor's path-safety gate.

The conftest autouse fixture sets `DIG_LOCAL_FILE_ALLOW_ABSOLUTE=1` for
the rest of the suite (engine tests pass arbitrary `tmp_path` URIs all
over the place; making them all opt in would be tedious and error-prone).
That makes it easy for a regression to silently re-open the bypass that
1.0-rc1 closed (executor calling `read_csv_auto({path})` with a raw
`file:///etc/passwd` URI).

These tests UN-set the env var, then verify the gate still rejects.
A future change that drops `assert_local_path_safe` from
`_dataset_cte` will fail this test loudly.
"""
from __future__ import annotations

import pytest

from dig.engine.uri_safety import assert_local_path_safe


class TestPathSafetyGate:
    def test_etc_passwd_rejected_when_env_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("DIG_LOCAL_FILE_ALLOW_ABSOLUTE", raising=False)
        with pytest.raises(ValueError, match="outside the allowed roots"):
            assert_local_path_safe("file:///etc/passwd")

    def test_dotssh_rejected_when_env_unset(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("DIG_LOCAL_FILE_ALLOW_ABSOLUTE", raising=False)
        with pytest.raises(ValueError, match="outside the allowed roots"):
            assert_local_path_safe("/Users/anyone/.ssh/id_rsa")

    def test_data_dir_path_accepted(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        # Point data_dir at tmp_path so the test isn't tied to repo layout.
        monkeypatch.delenv("DIG_LOCAL_FILE_ALLOW_ABSOLUTE", raising=False)
        monkeypatch.setenv("DIG_DATA_DIR", str(tmp_path))
        # `data_dir()` reads the env var on each call, so tmp_path becomes
        # an allowed root.
        good = tmp_path / "uploads" / "x.csv"
        good.parent.mkdir(parents=True, exist_ok=True)
        good.touch()
        result = assert_local_path_safe(f"file://{good}")
        assert str(result).endswith("x.csv")

    def test_escape_hatch_re_enables_when_explicitly_set(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv("DIG_LOCAL_FILE_ALLOW_ABSOLUTE", "1")
        # With the env var set, /etc/passwd is permitted (operator opted in).
        # On macOS the resolver follows /etc → /private/etc; assert the
        # tail of the path so the test works on both platforms.
        result = assert_local_path_safe("file:///etc/passwd")
        assert str(result).endswith("/etc/passwd")

    def test_executor_dataset_cte_rejects_unsafe_uri(
        self, monkeypatch: pytest.MonkeyPatch,
    ):
        """End-to-end: the executor's `_dataset_cte` MUST gate the URI
        before handing it to DuckDB. If a refactor removes the
        `assert_local_path_safe` call, this test fails."""
        monkeypatch.delenv("DIG_LOCAL_FILE_ALLOW_ABSOLUTE", raising=False)

        from dig.engine.executor import _dataset_cte
        from dig.engine.pipeline import DatasetSpec, Pipeline

        p = Pipeline(
            id="01TESTPIPELINEULID00000000",
            name="hostile",
            datasets=[
                DatasetSpec(id="ds", connector="csv", uri="file:///etc/passwd"),
            ],
        )
        with pytest.raises(ValueError, match="outside the allowed roots"):
            _dataset_cte(p, "ds")
