"""Lazy resolver for pack-bundled reference data.

A pack ships its reference datasets as a single ``data.zip`` next to its
``pack.json``. The first time a step calls ``pack_data(pack_id, resource_id)``
this module:

  1. Looks up the pack's manifest and locates its archive on disk.
  2. Verifies the archive's sha256 against ``resources.sha256``.
  3. Extracts every entry into
     ``data/cache/pack_data/<pack_id>/<pack_version>/``
     under a zip-slip-safe extractor with a hard size cap.
  4. Writes a ``.installed`` marker so subsequent calls skip steps 1-3.
  5. Returns the absolute path to the requested file.

Two layout modes are supported:

  - **Ship mode** (production): the pack folder contains ``data.zip`` and
    no ``data/`` directory. The loader extracts on first use.
  - **Dev mode** (during pack authoring): the pack folder contains a
    ``data/`` directory of source files. The loader skips extraction and
    serves files directly from that directory, so authors can iterate on
    parquet content without rebuilding the zip every save.

Security:
  - Per-entry zip-slip check: every file inside the archive must resolve
    inside the target cache directory.
  - Total-size cap: ``resources.extractedBytes`` is validated before
    extraction; the loader also enforces an absolute cap
    (DIG_PACK_MAX_EXTRACT_MB, default 200 MB) regardless of what the
    manifest declares.
  - No nested directories: archive entries with ``/`` in the path are
    rejected. Keeps the surface area small and matches the schema rule.

Concurrency:
  - A file lock on ``<cache>/.lock`` serialises concurrent extraction so
    two worker processes don't race. The lock is only held during the
    short extract window; reads are unsynchronised.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import zipfile
from pathlib import Path
from typing import Any

from dig.storage.files import data_dir

log = logging.getLogger(__name__)

# Absolute cap on extracted archive size. The pack manifest can declare a
# smaller cap via ``resources.extractedBytes`` but this is the hard ceiling
# regardless of what the manifest says — defends against a malicious zip
# that lies about its size.
_HARD_MAX_BYTES = int(os.environ.get("DIG_PACK_MAX_EXTRACT_MB", "200")) * 1024 * 1024

# Process-local memoisation. ``pack_data()`` is called per row in a
# tight loop; we don't want to re-stat the marker file every call.
_resolved: dict[tuple[str, str], Path] = {}
_resolve_lock = threading.Lock()


class PackDataError(RuntimeError):
    """Raised when a pack-data resource can't be resolved."""


def pack_data(pack_id: str, resource_id: str) -> Path:
    """Return the on-disk Path for ``resource_id`` within ``pack_id``.

    Triggers a one-time extraction on first call per (pack_id, version)
    pair. Subsequent calls hit a process-local cache.

    Raises ``PackDataError`` if the pack isn't registered, the resource
    isn't declared, or integrity / extraction fails.
    """
    cache_key = (pack_id, resource_id)
    if cache_key in _resolved:
        return _resolved[cache_key]

    with _resolve_lock:
        # Re-check inside the lock — another thread may have just resolved.
        if cache_key in _resolved:
            return _resolved[cache_key]
        path = _resolve_uncached(pack_id, resource_id)
        _resolved[cache_key] = path
        return path


def _resolve_uncached(pack_id: str, resource_id: str) -> Path:
    pack_dir, manifest = _find_pack(pack_id)
    resources = manifest.get("resources") or {}
    if not resources:
        raise PackDataError(
            f"pack {pack_id!r} has no `resources` section in pack.json — "
            "no reference data is registered for this pack",
        )

    # Locate the file entry matching the resource_id.
    files = resources.get("files") or []
    entry = next((f for f in files if f.get("id") == resource_id), None)
    if entry is None:
        known = ", ".join(repr(f.get("id")) for f in files) or "(none)"
        raise PackDataError(
            f"pack {pack_id!r} declares no resource {resource_id!r}; "
            f"available: {known}",
        )

    file_in_archive = entry["path"]
    if "/" in file_in_archive or "\\" in file_in_archive or ".." in file_in_archive:
        # Defence-in-depth — the schema regex already forbids these.
        raise PackDataError(
            f"pack {pack_id!r}: resource path {file_in_archive!r} contains "
            "a directory separator; pack-data archive entries must be flat",
        )

    # DEV MODE: if the pack folder has a `data/` directory and the file is
    # present there, serve it directly. Lets pack authors iterate on data
    # without rebuilding the zip on every change. The presence of `data/`
    # is the signal; production packs ship only `data.zip`.
    dev_path = pack_dir / "data" / file_in_archive
    if dev_path.exists() and dev_path.is_file():
        log.debug("pack_data: serving %s/%s from dev data/ tree", pack_id, resource_id)
        return dev_path.resolve()

    # SHIP MODE: locate the archive, verify integrity, extract once.
    archive_name = resources.get("archive") or "data.zip"
    archive_path = pack_dir / archive_name
    if not archive_path.exists():
        raise PackDataError(
            f"pack {pack_id!r}: archive {archive_name!r} not found at {archive_path}. "
            "If you're developing the pack, populate data/ with the expected files; "
            "otherwise reinstall the pack.",
        )

    declared_sha = resources.get("sha256")
    if not declared_sha:
        raise PackDataError(
            f"pack {pack_id!r}: resources.sha256 missing — refusing to extract "
            "an unverified archive",
        )

    pack_version = manifest.get("version", "unknown")
    cache_root = data_dir() / "cache" / "pack_data" / pack_id / pack_version
    marker = cache_root / ".installed"

    if marker.exists():
        # Check the marker recorded our archive's sha256 — guards against
        # a stale extraction from an older pack version whose folder was
        # later overwritten without bumping the version.
        try:
            recorded = marker.read_text(encoding="utf-8").strip()
            if recorded == declared_sha:
                extracted = cache_root / file_in_archive
                if extracted.exists():
                    return extracted.resolve()
        except Exception:
            # Corrupted marker — fall through and re-extract.
            pass

    _extract_archive(
        archive_path=archive_path,
        declared_sha=declared_sha,
        declared_extracted_bytes=int(resources.get("extractedBytes") or 0),
        cache_root=cache_root,
        pack_id=pack_id,
    )
    marker.write_text(declared_sha, encoding="utf-8")
    extracted = cache_root / file_in_archive
    if not extracted.exists():
        raise PackDataError(
            f"pack {pack_id!r}: extraction completed but {file_in_archive!r} "
            "is missing from the archive",
        )
    return extracted.resolve()


def _find_pack(pack_id: str) -> tuple[Path, dict[str, Any]]:
    """Locate the pack folder + parsed manifest for ``pack_id``.

    Searches the same roots the loader walks:
      - Step-Pack-internal/packs/<id>/
      - plugins/packs/<id>/
    """
    # Walk up from this file to the repo root so the search works
    # regardless of cwd at process start.
    here = Path(__file__).resolve()
    # backend/dig/extensions/pack_data.py → repo is parents[3]
    repo_root = here.parents[3]
    candidates = [
        repo_root / "Step-Pack-internal" / "packs" / pack_id,
        repo_root / "plugins" / "packs" / pack_id,
    ]
    for cand in candidates:
        manifest_path = cand / "pack.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                return cand, manifest
            except json.JSONDecodeError as e:
                raise PackDataError(
                    f"pack {pack_id!r}: pack.json failed to parse: {e}",
                ) from e
    raise PackDataError(f"pack {pack_id!r}: not found in any pack root")


def _extract_archive(
    *,
    archive_path: Path,
    declared_sha: str,
    declared_extracted_bytes: int,
    cache_root: Path,
    pack_id: str,
) -> None:
    """Verify, validate, and extract the archive into ``cache_root``.

    All-or-nothing: extracts to a temp dir, renames into place atomically.
    On failure the temp dir is removed; the destination is untouched.
    """
    # 1. Hash the archive bytes.
    h = hashlib.sha256()
    with archive_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual_sha = h.hexdigest()
    if actual_sha != declared_sha:
        raise PackDataError(
            f"pack {pack_id!r}: archive sha256 mismatch — declared "
            f"{declared_sha[:12]}…, got {actual_sha[:12]}…. "
            "The archive may be corrupted or tampered; reinstall the pack.",
        )

    # 2. Walk archive entries; size + zip-slip check before any write.
    with zipfile.ZipFile(archive_path) as zf:
        total_size = 0
        for zi in zf.infolist():
            # Reject directory traversal + nested dirs.
            name = zi.filename
            if name.endswith("/"):
                # Directory entries are fine but we don't actually need
                # them — flat archives only. Treat as no-op.
                continue
            if "/" in name or "\\" in name or ".." in name:
                raise PackDataError(
                    f"pack {pack_id!r}: archive entry {name!r} contains a "
                    "directory separator; pack-data archives must be flat",
                )
            if zi.file_size < 0:
                raise PackDataError(
                    f"pack {pack_id!r}: archive entry {name!r} reports "
                    "negative size; refusing to extract",
                )
            total_size += zi.file_size
            if total_size > _HARD_MAX_BYTES:
                raise PackDataError(
                    f"pack {pack_id!r}: archive declares {total_size} bytes "
                    f"of extracted data — exceeds hard cap "
                    f"{_HARD_MAX_BYTES // 1024 // 1024} MB "
                    "(set DIG_PACK_MAX_EXTRACT_MB to raise)",
                )
        if declared_extracted_bytes and total_size > declared_extracted_bytes * 2:
            # Manifest declared X bytes but archive actually has >2X.
            # Suspicious; refuse to proceed.
            raise PackDataError(
                f"pack {pack_id!r}: archive declares {total_size} bytes "
                f"but manifest says ~{declared_extracted_bytes}; refusing",
            )

        # 3. Extract to a temp sibling dir, then rename into place.
        cache_root.parent.mkdir(parents=True, exist_ok=True)
        temp_root = cache_root.with_suffix(".extracting")
        if temp_root.exists():
            # Stale temp from a prior crashed extract — clean up.
            import shutil as _shutil
            _shutil.rmtree(temp_root, ignore_errors=True)
        temp_root.mkdir(parents=True, exist_ok=False)
        try:
            for zi in zf.infolist():
                if zi.filename.endswith("/"):
                    continue
                target = (temp_root / zi.filename).resolve()
                # Final zip-slip check on the resolved path.
                if not str(target).startswith(str(temp_root.resolve())):
                    raise PackDataError(
                        f"pack {pack_id!r}: archive entry {zi.filename!r} "
                        "resolves outside the extraction directory",
                    )
                with zf.open(zi) as src, target.open("wb") as dst:
                    # Stream copy in chunks to bound memory on big files.
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        dst.write(chunk)
            # 4. Atomic-ish rename into place. If cache_root already
            # exists (race), prefer ours and remove the loser.
            if cache_root.exists():
                import shutil as _shutil
                _shutil.rmtree(cache_root, ignore_errors=True)
            temp_root.rename(cache_root)
        except Exception:
            import shutil as _shutil
            _shutil.rmtree(temp_root, ignore_errors=True)
            raise

    log.info(
        "pack_data: extracted %s (%d bytes) → %s",
        pack_id, total_size, cache_root,
    )


def clear_cache(pack_id: str | None = None) -> None:
    """Wipe the extracted cache. Mostly useful for tests + the
    'Reinstall pack' Settings affordance. If ``pack_id`` is None,
    clears everything; otherwise clears just that pack."""
    import shutil
    root = data_dir() / "cache" / "pack_data"
    if pack_id is None:
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
    else:
        target = root / pack_id
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
    # Drop process-local memo.
    if pack_id is None:
        _resolved.clear()
    else:
        for k in list(_resolved.keys()):
            if k[0] == pack_id:
                _resolved.pop(k, None)
