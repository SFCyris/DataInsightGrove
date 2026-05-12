"""Tests for the out-of-tree extension loader.

Two channels — both must be:
  - Discoverable when present
  - Quiet when absent
  - Isolated: a broken plugin never blocks DIG startup
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DIG_DATA_DIR", str(tmp_path))
    return tmp_path


# ── extensions_dir + filesystem channel ────────────────────────────────


class TestFsExtensions:
    def test_extensions_dir_created_on_first_call(self, tmp_data_dir):
        from dig.extensions import extensions_dir
        d = extensions_dir()
        assert d.exists()
        assert d.is_dir()
        assert d.parent == tmp_data_dir

    def test_empty_directory_returns_empty_list(self, tmp_data_dir):
        from dig.extensions import discover_fs_extensions
        assert discover_fs_extensions() == []

    def test_extension_with_manifest_discovered(self, tmp_data_dir):
        from dig.extensions import discover_fs_extensions, extensions_dir

        ext = extensions_dir() / "my_plugin"
        ext.mkdir()
        (ext / "manifest.json").write_text(json.dumps({
            "name": "my_plugin",
            "version": "1.2.3",
            "label": "Test Plugin",
        }))
        result = discover_fs_extensions()
        assert len(result) == 1
        assert result[0].name == "my_plugin"
        assert result[0].manifest["version"] == "1.2.3"
        assert result[0].load_error is None
        assert result[0].url_prefix == "/ext/my_plugin"

    def test_extension_with_static_dir_flagged(self, tmp_data_dir):
        from dig.extensions import discover_fs_extensions, extensions_dir
        ext = extensions_dir() / "static_only"
        (ext / "static").mkdir(parents=True)
        result = discover_fs_extensions()
        assert len(result) == 1
        assert result[0].has_static is True

    def test_malformed_manifest_recorded_not_raised(self, tmp_data_dir):
        from dig.extensions import discover_fs_extensions, extensions_dir
        ext = extensions_dir() / "bad_manifest"
        ext.mkdir()
        (ext / "manifest.json").write_text("{this is not json")
        result = discover_fs_extensions()
        # The extension is still listed — the operator can see the failure
        # in /health.extensions[*].load_error.
        assert len(result) == 1
        assert result[0].name == "bad_manifest"
        assert result[0].load_error is not None
        assert "manifest.json" in result[0].load_error

    def test_unsafe_name_skipped(self, tmp_data_dir):
        from dig.extensions import discover_fs_extensions, extensions_dir
        # Names that would break URL routing or escape the static dir
        # are filtered out — never surface in /health, never get mounted.
        for bad in ["../escape", "with space", "name/with/slash"]:
            try:
                (extensions_dir() / bad).mkdir(parents=True, exist_ok=True)
            except OSError:
                # Some OS / FS combos refuse the name outright; skip.
                continue
        # Add one safe one to confirm the loop doesn't bail on the bad ones.
        (extensions_dir() / "safe_one").mkdir()
        result = discover_fs_extensions()
        names = {r.name for r in result}
        assert "safe_one" in names
        assert "../escape" not in names
        assert "with space" not in names

    def test_dotfile_directories_skipped(self, tmp_data_dir):
        # `.git`, `.DS_Store/`, etc. — never picked up.
        from dig.extensions import discover_fs_extensions, extensions_dir
        (extensions_dir() / ".git").mkdir()
        (extensions_dir() / "real").mkdir()
        names = {r.name for r in discover_fs_extensions()}
        assert names == {"real"}


# ── Entry-point channel ────────────────────────────────────────────────


class TestEntryPointDiscovery:
    def test_no_entry_points_returns_empty_list(self, tmp_data_dir):
        # A clean install of DIG (no enterprise pip-installed) sees zero.
        # NB: this is a regression check — it depends on no test-time
        # plugin being registered against `dig.steps` etc. by an
        # accidental pip install of a sibling package.
        from dig.extensions import discover_entry_points
        result = discover_entry_points(groups=("dig.nonexistent_group_xyz",))
        assert result == []

    def test_failed_entry_point_records_error_not_raises(
        self, tmp_data_dir, monkeypatch: pytest.MonkeyPatch,
    ):
        """The contract: a single broken plugin never blocks DIG startup.

        We simulate this by patching importlib.metadata.entry_points to
        return a synthetic entry point whose `.load()` raises.
        """
        import importlib.metadata as md

        class _FakeDist:
            name = "broken-plugin"
            version = "0.0.1"

        class _FakeEntryPoint:
            name = "broken_thing"
            dist = _FakeDist()

            def load(self):  # noqa: D401
                raise RuntimeError("simulated broken plugin")

        def _fake_entry_points(*, group: str):
            if group == "dig.steps":
                return [_FakeEntryPoint()]
            return []

        monkeypatch.setattr(md, "entry_points", _fake_entry_points)
        # The loader uses importlib.metadata.entry_points; patch the
        # binding the loader sees.
        from dig.extensions import loader
        monkeypatch.setattr(loader.importlib.metadata, "entry_points", _fake_entry_points)

        result = loader.discover_entry_points(groups=("dig.steps",))
        assert len(result) == 1
        assert result[0].name == "broken_thing"
        assert result[0].package == "broken-plugin"
        assert result[0].loaded_object is None
        assert result[0].load_error is not None
        assert "simulated broken plugin" in result[0].load_error


# ── discover_all combines both channels ────────────────────────────────


class TestDiscoverAll:
    def test_returns_canonical_shape(self, tmp_data_dir):
        from dig.extensions import discover_all
        result = discover_all()
        assert set(result.keys()) == {"entry_points", "fs", "loaded_objects"}
        assert isinstance(result["entry_points"], list)
        assert isinstance(result["fs"], list)

    def test_serialises_to_json(self, tmp_data_dir):
        # The shape /health uses must be JSON-serialisable. Drop the
        # in-process `loaded_objects` (which contains live Python objects)
        # since /health doesn't expose those.
        from dig.extensions import discover_all
        result = discover_all()
        result.pop("loaded_objects")
        json.dumps(result)  # must not raise


# ── Integration: /health surfaces extensions ───────────────────────────


class TestHealthEndpoint:
    def test_health_exposes_protocol_version(self, tmp_data_dir):
        from fastapi.testclient import TestClient

        from dig.api.main import create_app

        app = create_app()
        with TestClient(app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "ok"
            assert "extensions" in body
            assert isinstance(body["extensions"], list)
            assert "protocol_version" in body
            # tuple → list across the wire
            assert body["protocol_version"] == [1, 0]

    def test_health_extensions_empty_on_clean_install(self, tmp_data_dir):
        from fastapi.testclient import TestClient

        from dig.api.main import create_app

        app = create_app()
        with TestClient(app) as client:
            body = client.get("/health").json()
            # No enterprise pip package installed in CI; no fs extensions
            # in the test's tmp data dir → list is empty.
            assert body["extensions"] == []
