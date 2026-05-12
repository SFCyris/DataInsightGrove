"""Tests for the boot-time version transition detection.

Covers:
  - Marker file read/write/round-trip
  - Fresh-install path (no prior marker)
  - Same-version path (no-op)
  - Upgrade path (transition detected; marker rewritten)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point dig.storage.files.data_dir at a tmp path so tests can't see / write
    the user's real ~/.local/share/dig."""
    monkeypatch.setenv("DIG_DATA_DIR", str(tmp_path))
    # Reset the module-level cache (data_dir() is a plain function that reads
    # the env var on each call in this codebase — but importing the module
    # might have cached on first call elsewhere).
    return tmp_path


# ---------------------------------------------------------------------------
# Marker-file primitives
# ---------------------------------------------------------------------------


class TestMarkerFile:
    def test_read_returns_none_when_missing(self, tmp_data_dir):
        from dig.storage.version_state import read_last_installed_version
        assert read_last_installed_version() is None

    def test_write_then_read_roundtrip(self, tmp_data_dir):
        from dig.storage.version_state import (
            read_last_installed_version,
            write_installed_version,
        )
        write_installed_version("0.10.0")
        assert read_last_installed_version() == "0.10.0"

    def test_write_overwrites(self, tmp_data_dir):
        from dig.storage.version_state import (
            read_last_installed_version,
            write_installed_version,
        )
        write_installed_version("0.10.0")
        write_installed_version("0.11.0")
        assert read_last_installed_version() == "0.11.0"

    def test_empty_file_reads_as_none(self, tmp_data_dir):
        from dig.storage.version_state import read_last_installed_version
        (tmp_data_dir / ".installed_version").write_text("", encoding="utf-8")
        assert read_last_installed_version() is None

    def test_whitespace_trimmed(self, tmp_data_dir):
        from dig.storage.version_state import read_last_installed_version
        (tmp_data_dir / ".installed_version").write_text("  0.10.0\n\n", encoding="utf-8")
        assert read_last_installed_version() == "0.10.0"


# ---------------------------------------------------------------------------
# Transition detection
# ---------------------------------------------------------------------------


class TestTransitionDetection:
    async def test_fresh_install_no_prior(self, tmp_data_dir):
        from dig import __version__
        from dig.storage.version_state import detect_and_record_version_transition

        prior, current = await detect_and_record_version_transition()
        assert prior is None
        assert current == __version__

    async def test_marker_is_written_on_fresh_install(self, tmp_data_dir):
        from dig import __version__
        from dig.storage.version_state import (
            detect_and_record_version_transition,
            read_last_installed_version,
        )

        await detect_and_record_version_transition()
        assert read_last_installed_version() == __version__

    async def test_same_version_is_noop(self, tmp_data_dir):
        from dig import __version__
        from dig.storage.version_state import (
            detect_and_record_version_transition,
            write_installed_version,
        )

        write_installed_version(__version__)
        prior, current = await detect_and_record_version_transition()
        assert prior == __version__
        assert current == __version__

    async def test_upgrade_transition_detected(self, tmp_data_dir):
        from dig import __version__
        from dig.storage.version_state import (
            detect_and_record_version_transition,
            read_last_installed_version,
            write_installed_version,
        )

        write_installed_version("0.9.0")
        prior, current = await detect_and_record_version_transition()
        assert prior == "0.9.0"
        assert current == __version__
        # Marker is rewritten so the next boot sees no transition.
        assert read_last_installed_version() == __version__

    async def test_emit_event_never_breaks_detection(
        self, tmp_data_dir, monkeypatch: pytest.MonkeyPatch
    ):
        """The transition detector wraps emit_event in try/except so a broken
        event bus never blocks startup. Simulate that here by patching
        emit_event to raise."""
        from dig.storage.version_state import (
            detect_and_record_version_transition,
            write_installed_version,
        )

        async def boom(*_args, **_kwargs):  # noqa: ANN001, ANN002
            raise RuntimeError("event bus is offline")

        import dig.api.events as events_mod
        monkeypatch.setattr(events_mod, "emit_event", boom)

        write_installed_version("0.1.0")
        # Should NOT raise even though emit_event blows up.
        prior, _current = await detect_and_record_version_transition()
        assert prior == "0.1.0"
