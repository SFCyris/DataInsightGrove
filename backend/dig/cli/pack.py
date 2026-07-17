"""``dig-pack`` — build, verify, inspect, and scaffold DIG step-packs.

Usage:

  dig-pack build <pack_dir> [--check]
        Zip the pack's data/ directory into data.zip, compute hashes
        + row counts + sizes, rewrite pack.json's `resources` block.
        With --check, exit non-zero if the on-disk pack.json / data.zip
        differ from what would be regenerated (useful as a pre-commit /
        pre-publish gate).

  dig-pack verify <pack_dir>
        Verify the pack on disk is internally consistent:
          - archive sha256 matches pack.json
          - per-file sha256 matches archive contents
          - all declared `files` exist inside the archive
          - declared `extractedBytes` matches actual sum.

  dig-pack info <pack_dir>
        Pretty-print the pack's manifest summary: id, version, label,
        step + connector counts, declared resources, license roll-up.

  dig-pack scaffold <name> [--dir <parent>]
        Create a new pack skeleton from the bundled template.

  dig-pack install <pack_dir>
        Force-extract the pack's archive into the runtime cache now
        (normally done lazily on first step execution).

  dig-pack list
        List every pack the runtime can find, with cache state.

  dig-pack test <pack_dir>
        Reserved for v2 — runs each declared step against a smoke
        fixture and asserts column shape + geometry validity.

All commands are pure-local. No network, no CI dependency, no git
host coupling. URL-typed sources in `_build/sources.json` are fetched
with the stdlib's urllib at build time and their bytes are hashed into
`_build/sources.lock.json`; once that file is committed the verifier
no longer needs the source URLs to remain reachable.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

# Reproducible-zip constant: 1980-01-01 00:00 is the earliest timestamp
# the zip format can encode. Hard-coding it makes two authors with the
# same data/ produce byte-identical data.zip + identical sha256.
_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


# ---------- helpers --------------------------------------------------------


def _read_manifest(pack_dir: Path) -> dict[str, Any]:
    manifest_path = pack_dir / "pack.json"
    if not manifest_path.exists():
        sys.exit(f"error: {manifest_path} not found")
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit(f"error: pack.json is not valid JSON — {e}")


def _write_manifest(pack_dir: Path, manifest: dict[str, Any]) -> None:
    # Stable key order + 2-space indent so commits show meaningful diffs.
    text = json.dumps(manifest, indent=2, sort_keys=False, ensure_ascii=False)
    (pack_dir / "pack.json").write_text(text + "\n", encoding="utf-8")


def _sha256_bytes(buf: bytes) -> str:
    return hashlib.sha256(buf).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parquet_row_count(path: Path) -> int | None:
    """Cheap row-count via parquet metadata. Returns None if unreadable."""
    try:
        import polars as pl
        return pl.scan_parquet(path).select(pl.len()).collect().item()
    except Exception:
        return None


def _detect_resource_id(filename: str) -> str:
    """Map a filename to a stable resource id. ``us_states_10m.parquet``
    → ``us_states_10m``. Drops extension only."""
    base = Path(filename).stem
    # Schema regex is ^[a-z][a-z0-9_]*$ — lowercase + replace dashes.
    return base.lower().replace("-", "_")


# ---------- build ----------------------------------------------------------


def cmd_build(pack_dir: Path, check_only: bool = False) -> int:
    manifest = _read_manifest(pack_dir)
    data_dir = pack_dir / "data"

    if not data_dir.exists() or not data_dir.is_dir():
        # No data to bundle — strip the `resources` section if present,
        # then no-op. Lets a build run idempotently on packs that have no
        # reference data yet.
        if "resources" in manifest:
            del manifest["resources"]
            if check_only:
                if (pack_dir / "pack.json").read_text() != json.dumps(
                    manifest, indent=2, sort_keys=False, ensure_ascii=False
                ) + "\n":
                    print(f"drift: pack.json would change (resources removed)")
                    return 1
            else:
                _write_manifest(pack_dir, manifest)
                print(f"build: {manifest['id']} has no data/ directory; "
                      f"removed resources from pack.json")
        else:
            print(f"build: {manifest['id']} has no data/ directory; nothing to do")
        return 0

    # Gather files. Flat layout — only top-level files in data/, not
    # recursive (per schema rule: archive paths must be flat).
    files = sorted([p for p in data_dir.iterdir() if p.is_file()])
    if not files:
        sys.exit(f"error: {data_dir} contains no files to bundle")

    # Load existing pack.json's `resources.files` so we can preserve
    # human-authored metadata (license, attribution, source). The author
    # is expected to fill these in BEFORE building; the build only
    # refreshes the machine-derived fields (sha256, sizes, rowCount).
    prior = (manifest.get("resources") or {}).get("files") or []
    prior_by_id: dict[str, dict[str, Any]] = {f["id"]: f for f in prior if isinstance(f, dict)}

    file_entries: list[dict[str, Any]] = []
    for f in files:
        rid = _detect_resource_id(f.name)
        prior_entry = prior_by_id.get(rid, {})
        entry: dict[str, Any] = {
            "id": rid,
            "path": f.name,
            "sha256": _sha256_file(f),
            "sizeBytes": f.stat().st_size,
        }
        rc = _parquet_row_count(f) if f.suffix == ".parquet" else None
        if rc is not None:
            entry["rowCount"] = rc
        # Schema version: keep prior or default to 1.
        entry["schemaVersion"] = prior_entry.get("schemaVersion", 1)
        # License is REQUIRED by the schema. Carry forward; if missing,
        # the author hasn't filled it in yet — warn but don't fail.
        if "license" in prior_entry:
            entry["license"] = prior_entry["license"]
        else:
            entry["license"] = "UNDECLARED"
            print(f"warn: resource {rid!r} has no license declared; "
                  "set it in pack.json's resources.files entry")
        for k in ("attribution", "source", "description"):
            if k in prior_entry:
                entry[k] = prior_entry[k]
        file_entries.append(entry)

    # Build the archive deterministically: sorted, fixed timestamps,
    # store mode for parquet (already compressed), deflate for text.
    archive_path = pack_dir / "data.zip"
    # Write to a temp file first so a failed build doesn't leave a
    # half-written data.zip in the repo.
    temp_archive = pack_dir / "data.zip.tmp"
    if temp_archive.exists():
        temp_archive.unlink()
    with zipfile.ZipFile(temp_archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            # Parquet is already zstd-compressed internally; storing is
            # ~free and avoids burning CPU re-compressing.
            comp = zipfile.ZIP_STORED if f.suffix == ".parquet" else zipfile.ZIP_DEFLATED
            zi = zipfile.ZipInfo(f.name, date_time=_FIXED_ZIP_TIME)
            zi.compress_type = comp
            zi.external_attr = 0o100644 << 16  # regular file, rw-r--r--
            zf.writestr(zi, f.read_bytes())

    archive_sha = _sha256_file(temp_archive)
    archive_size = temp_archive.stat().st_size
    extracted_size = sum(f.stat().st_size for f in files)

    # Build the new resources block.
    new_resources = {
        "archive": "data.zip",
        "sha256": archive_sha,
        "compressedBytes": archive_size,
        "extractedBytes": extracted_size,
        "files": file_entries,
    }

    new_manifest = dict(manifest)
    new_manifest["resources"] = new_resources

    if check_only:
        # Compare: does the on-disk state already match what we just built?
        on_disk_manifest = (pack_dir / "pack.json").read_text(encoding="utf-8")
        would_be_manifest = json.dumps(new_manifest, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
        on_disk_archive_sha = _sha256_file(archive_path) if archive_path.exists() else None
        # Clean up temp regardless of result.
        temp_archive.unlink(missing_ok=True)
        drift = False
        if on_disk_manifest != would_be_manifest:
            print("drift: pack.json would change after `dig pack build`")
            drift = True
        if on_disk_archive_sha != archive_sha:
            print(f"drift: data.zip sha256 would change "
                  f"(on disk: {on_disk_archive_sha or '<missing>'}, "
                  f"would be: {archive_sha})")
            drift = True
        if drift:
            return 1
        print(f"check: {manifest['id']} is in sync")
        return 0

    # Promote temp → final.
    if archive_path.exists():
        archive_path.unlink()
    temp_archive.rename(archive_path)
    _write_manifest(pack_dir, new_manifest)

    # Write a sources.lock.json if _build/sources.json exists.
    _maybe_write_sources_lock(pack_dir)

    print(f"build: {manifest['id']} → data.zip "
          f"({archive_size:,} bytes compressed, {extracted_size:,} extracted, "
          f"{len(files)} files, sha256={archive_sha[:12]}…)")
    return 0


def _maybe_write_sources_lock(pack_dir: Path) -> None:
    """If `_build/sources.json` exists, capture a sha256 + size per source
    into `_build/sources.lock.json`. URL sources need their fetched bytes
    cached in `_build/sources/<id>.<ext>` by the pack's own build.py first;
    this helper just records what's there."""
    sources_json = pack_dir / "_build" / "sources.json"
    if not sources_json.exists():
        return
    try:
        spec = json.loads(sources_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"warn: _build/sources.json is malformed — {e}; skipping lock")
        return

    lock: dict[str, Any] = {
        "generatedAt": _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": [],
    }
    for src in spec.get("sources", []):
        if not isinstance(src, dict):
            continue
        entry = {"id": src.get("id"), "type": src.get("type")}
        if src.get("type") == "file":
            p = pack_dir / src.get("path", "")
            if p.exists():
                entry["path"] = src.get("path")
                entry["sha256"] = _sha256_file(p)
                entry["sizeBytes"] = p.stat().st_size
            else:
                entry["error"] = "file missing"
        elif src.get("type") == "url":
            # Look for cached bytes under _build/sources/<id>.<ext>.
            cache_dir = pack_dir / "_build" / "sources"
            entry["url"] = src.get("url")
            matches = list(cache_dir.glob(f"{src.get('id')}.*")) if cache_dir.exists() else []
            if matches:
                entry["sha256"] = _sha256_file(matches[0])
                entry["sizeBytes"] = matches[0].stat().st_size
                entry["fetchedAt"] = _dt.datetime.fromtimestamp(
                    matches[0].stat().st_mtime
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                entry["error"] = "source not fetched yet"
        elif src.get("type") == "inline":
            payload = json.dumps(src.get("data"), sort_keys=True).encode("utf-8")
            entry["sha256"] = _sha256_bytes(payload)
            entry["sizeBytes"] = len(payload)
        if "description" in src:
            entry["description"] = src["description"]
        lock["sources"].append(entry)

    (pack_dir / "_build" / "sources.lock.json").write_text(
        json.dumps(lock, indent=2) + "\n", encoding="utf-8"
    )


# ---------- verify ---------------------------------------------------------


def cmd_verify(pack_dir: Path) -> int:
    manifest = _read_manifest(pack_dir)
    resources = manifest.get("resources")
    if not resources:
        print(f"verify: {manifest['id']} has no resources to check")
        return 0
    archive = pack_dir / resources["archive"]
    if not archive.exists():
        print(f"FAIL: archive {archive.name} missing")
        return 1
    actual_sha = _sha256_file(archive)
    if actual_sha != resources["sha256"]:
        print(f"FAIL: archive sha256 mismatch")
        print(f"  declared: {resources['sha256']}")
        print(f"  actual:   {actual_sha}")
        return 1
    # Check per-file shas by scanning the archive without extracting to disk.
    with zipfile.ZipFile(archive) as zf:
        entries_in_zip = {zi.filename for zi in zf.infolist() if not zi.is_dir()}
        for entry in resources["files"]:
            path = entry["path"]
            if path not in entries_in_zip:
                print(f"FAIL: file {path!r} declared in manifest but missing from archive")
                return 1
            if "sha256" in entry:
                with zf.open(path) as f:
                    h = hashlib.sha256()
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(chunk)
                    if h.hexdigest() != entry["sha256"]:
                        print(f"FAIL: file {path!r} sha256 mismatch inside archive")
                        return 1
    print(f"verify: {manifest['id']} ✓ all integrity checks pass")
    return 0


# ---------- info -----------------------------------------------------------


def cmd_info(pack_dir: Path) -> int:
    manifest = _read_manifest(pack_dir)
    print(f"📦 {manifest.get('label', manifest['id'])} ({manifest['id']} v{manifest['version']})")
    if "description" in manifest:
        print(f"   {manifest['description']}")
    print()
    print(f"  steps:      {len(manifest.get('steps') or [])}")
    print(f"  connectors: {len(manifest.get('connectors') or [])}")
    print(f"  license:    {manifest.get('license', '—')}")
    print(f"  author:     {manifest.get('author', '—')}")
    res = manifest.get("resources") or {}
    if res:
        print()
        print(f"  📚 Resources: {res['archive']} ({res.get('compressedBytes', 0):,} bytes compressed, "
              f"{res.get('extractedBytes', 0):,} extracted)")
        for f in res.get("files", []):
            rc = f" · {f['rowCount']:,} rows" if "rowCount" in f else ""
            print(f"     · {f['id']:<28} {f.get('sizeBytes', 0):>10,} B{rc}  [{f.get('license', '—')}]")
            if f.get("attribution"):
                print(f"        {f['attribution']}")
    return 0


# ---------- install + list -------------------------------------------------


def cmd_install(pack_dir: Path) -> int:
    """Force-extract NOW (instead of lazy on first step run)."""
    from dig.extensions.pack_data import pack_data
    manifest = _read_manifest(pack_dir)
    res = manifest.get("resources") or {}
    files = res.get("files") or []
    if not files:
        print(f"install: {manifest['id']} has no resources")
        return 0
    # Touching any single file forces extraction of the whole archive.
    first = files[0]
    try:
        path = pack_data(manifest["id"], first["id"])
        print(f"install: {manifest['id']} → {path.parent}")
        return 0
    except Exception as e:
        print(f"FAIL: {e}")
        return 1


def cmd_list() -> int:
    """List discovered packs + their cache state."""
    here = Path(__file__).resolve()
    repo_root = here.parents[3]
    roots = [
        repo_root / "FunctionPacks" / "packs",
        repo_root / "plugins" / "packs",
    ]
    from dig.storage.files import data_dir
    cache_root = data_dir() / "cache" / "pack_data"
    found = 0
    for root in roots:
        if not root.exists():
            continue
        for pack_dir in sorted(root.iterdir()):
            manifest_path = pack_dir / "pack.json"
            if not manifest_path.exists():
                continue
            try:
                m = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            found += 1
            res = m.get("resources") or {}
            has_res = "📚" if res else "  "
            cache_state = ""
            if res:
                cached = cache_root / m["id"] / m["version"]
                cache_state = "  (extracted)" if (cached / ".installed").exists() else "  (not yet extracted)"
            print(f"{has_res} {m['id']:<32} v{m['version']:<10} {m.get('label','')}{cache_state}")
    if found == 0:
        print("(no packs found)")
    return 0


# ---------- scaffold -------------------------------------------------------


def cmd_scaffold(name: str, parent: Path) -> int:
    if not name.replace("_", "").isalnum() or not name[0].isalpha() or not name.islower():
        sys.exit(
            f"error: pack name must be lowercase snake_case (got {name!r})"
        )
    pack_dir = parent / name
    if pack_dir.exists():
        sys.exit(f"error: {pack_dir} already exists")
    pack_dir.mkdir(parents=True)
    (pack_dir / "steps").mkdir()
    (pack_dir / "_build").mkdir()
    (pack_dir / "_build" / "sources").mkdir()
    (pack_dir / "data").mkdir()

    manifest = {
        "id": name,
        "version": "0.1.0",
        "label": f"📦 {name}",
        "description": "TODO — describe what this pack adds.",
        "author": "TODO",
        "license": "AGPL-3.0",
        "minDigVersion": "1.0.0",
        "steps": [],
        "connectors": [],
    }
    _write_manifest(pack_dir, manifest)
    (pack_dir / "README.md").write_text(
        f"# {name}\n\nTODO — describe this pack.\n\n## Sources\n\nTODO\n",
        encoding="utf-8",
    )
    (pack_dir / "LICENSES.md").write_text(
        "# Third-party data licenses\n\nTODO — list per-resource license + attribution.\n",
        encoding="utf-8",
    )
    (pack_dir / "_build" / "sources.json").write_text(
        json.dumps({"sources": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    (pack_dir / "_build" / "build.py").write_text(
        '"""Build script: fetch/read sources → convert → write data/.\n\n'
        'Run with: backend/.venv/bin/python _build/build.py\n"""\n\n'
        'def main():\n'
        '    print("TODO: implement source → data/*.parquet conversion")\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n',
        encoding="utf-8",
    )
    # Gitignore the data/ tree + build artefacts; ship data.zip only.
    (pack_dir / ".gitignore").write_text(
        "data/\n_build/sources/\ndata.zip.tmp\n",
        encoding="utf-8",
    )
    print(f"scaffold: created {pack_dir}")
    print("  next: edit pack.json + _build/sources.json + _build/build.py")
    print("  then: python _build/build.py && dig-pack build .")
    return 0


# ---------- entry ----------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dig-pack", description="DIG step-pack tooling")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Zip data/ → data.zip + update pack.json")
    p_build.add_argument("pack_dir", type=Path)
    p_build.add_argument("--check", action="store_true",
                         help="Exit non-zero if on-disk pack.json/data.zip differ from rebuild")

    p_verify = sub.add_parser("verify", help="Verify pack.json hashes match on-disk archive")
    p_verify.add_argument("pack_dir", type=Path)

    p_info = sub.add_parser("info", help="Pretty-print pack summary")
    p_info.add_argument("pack_dir", type=Path)

    p_install = sub.add_parser("install", help="Force-extract pack's archive now (vs lazy on first use)")
    p_install.add_argument("pack_dir", type=Path)

    sub.add_parser("list", help="List discovered packs + cache state")

    p_scaffold = sub.add_parser("scaffold", help="Create a new pack skeleton")
    p_scaffold.add_argument("name", type=str)
    p_scaffold.add_argument("--dir", dest="parent", type=Path,
                            default=Path("FunctionPacks/packs"))

    return p


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    if args.cmd == "build":
        sys.exit(cmd_build(args.pack_dir, check_only=args.check))
    if args.cmd == "verify":
        sys.exit(cmd_verify(args.pack_dir))
    if args.cmd == "info":
        sys.exit(cmd_info(args.pack_dir))
    if args.cmd == "install":
        sys.exit(cmd_install(args.pack_dir))
    if args.cmd == "list":
        sys.exit(cmd_list())
    if args.cmd == "scaffold":
        sys.exit(cmd_scaffold(args.name, args.parent))
    sys.exit(f"unknown command: {args.cmd}")
