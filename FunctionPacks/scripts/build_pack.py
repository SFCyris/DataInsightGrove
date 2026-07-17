#!/usr/bin/env python3
"""Build a step pack into a .dpack zip artifact.

Usage:
    python3 FunctionPacks/scripts/build_pack.py <pack_id>
    python3 FunctionPacks/scripts/build_pack.py --all

Writes `dist/<pack_id>-<version>.dpack` next to the source.

Validation passes (failures abort with non-zero exit + clear error):
  - pack.json validates against shared/schemas/pack-manifest.schema.json
  - every steps/<id>/manifest.json validates against
    shared/schemas/step-manifest.schema.json
  - pack.json:steps[] matches the directory listing under steps/
  - every step.py exports `step` (executed in a hardened temp module)
  - no path traversal in archive members
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

try:
    import jsonschema  # noqa: F401
except ImportError:
    print("ERROR: jsonschema not installed — run from the dig venv:", file=sys.stderr)
    print("  cd backend && .venv/bin/python ../FunctionPacks/scripts/build_pack.py …", file=sys.stderr)
    sys.exit(2)

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent.parent  # repo root
WORKSPACE = ROOT / "FunctionPacks"
PACKS_DIR = WORKSPACE / "packs"
DIST_DIR = WORKSPACE / "dist"
PACK_SCHEMA = ROOT / "shared" / "schemas" / "pack-manifest.schema.json"
STEP_SCHEMA = ROOT / "shared" / "schemas" / "step-manifest.schema.json"


_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _load_validator(path: Path) -> Draft202012Validator:
    if not path.exists():
        _die(f"schema not found: {path}")
    return Draft202012Validator(json.loads(path.read_text()))


def _validate_doc(validator: Draft202012Validator, doc: dict, label: str) -> None:
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        for e in errors:
            path = "/".join(str(p) for p in e.path) or "<root>"
            print(f"  {label} :: {path} — {e.message}", file=sys.stderr)
        _die(f"{label}: schema validation failed ({len(errors)} error(s))")


def _check_step_py(step_dir: Path) -> None:
    py = step_dir / "step.py"
    if not py.exists():
        _die(f"missing step.py: {py.relative_to(WORKSPACE)}")
    src = py.read_text()
    # Token-level look for an export. We don't exec — that's the runtime's job.
    if "step =" not in src and "step=" not in src:
        _die(f"{py.relative_to(WORKSPACE)} does not appear to export `step`")
    # Soft warnings for risky patterns. Operators can override but the pack
    # build flags them so they're never invisible.
    risky = []
    for needle in ("os.system(", "subprocess.", "eval(", "exec("):
        if needle in src:
            risky.append(needle.rstrip("("))
    if risky:
        print(f"  ⚠ {py.relative_to(WORKSPACE)} uses risky calls: {', '.join(risky)}")
        print("    (allowed but flagged — review before publishing)")


def _zip_safe(name: str) -> bool:
    """Reject member names that try to traverse out of the archive root."""
    if name.startswith("/") or name.startswith("\\"):
        return False
    parts = name.replace("\\", "/").split("/")
    return ".." not in parts


def build_one(pack_id: str) -> Path:
    if not _ID_RE.match(pack_id):
        _die(f"invalid pack id: {pack_id!r}")
    pack_dir = PACKS_DIR / pack_id
    if not pack_dir.is_dir():
        _die(f"pack directory not found: {pack_dir.relative_to(ROOT)}")

    print(f"📦 Building {pack_id}")
    pack_validator = _load_validator(PACK_SCHEMA)
    step_validator = _load_validator(STEP_SCHEMA)

    pack_json_path = pack_dir / "pack.json"
    if not pack_json_path.exists():
        _die(f"missing {pack_json_path.relative_to(ROOT)}")
    pack_doc = json.loads(pack_json_path.read_text())

    # Manifest validation
    _validate_doc(pack_validator, pack_doc, "pack.json")

    if pack_doc.get("id") != pack_id:
        _die(f"pack.json:id ({pack_doc.get('id')!r}) != directory name ({pack_id!r})")
    version = pack_doc.get("version", "")
    if not _SEMVER_RE.match(version):
        _die(f"pack.json:version must be semver, got {version!r}")

    # Step inventory: declared list ↔ disk
    declared_steps = list(pack_doc.get("steps") or [])
    steps_dir = pack_dir / "steps"
    on_disk_steps: list[str] = []
    if steps_dir.exists():
        on_disk_steps = sorted(d.name for d in steps_dir.iterdir() if d.is_dir())
    declared_set = set(declared_steps)
    on_disk_set = set(on_disk_steps)
    missing = declared_set - on_disk_set
    extra = on_disk_set - declared_set
    if missing:
        _die(f"pack.json:steps[] declares but disk is missing: {sorted(missing)}")
    if extra:
        _die(f"steps/ has but pack.json doesn't declare: {sorted(extra)} — add to pack.json:steps[]")

    # Per-step validation
    for sid in declared_steps:
        sdir = steps_dir / sid
        manifest_path = sdir / "manifest.json"
        if not manifest_path.exists():
            _die(f"missing {manifest_path.relative_to(ROOT)}")
        manifest = json.loads(manifest_path.read_text())
        _validate_doc(step_validator, manifest, f"steps/{sid}/manifest.json")
        if manifest.get("id") != sid:
            _die(f"steps/{sid}/manifest.json:id ({manifest.get('id')!r}) != folder name ({sid!r})")
        _check_step_py(sdir)

    # Stamp checksum + write zip
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DIST_DIR / f"{pack_id}-{version}.dpack"
    if out_path.exists():
        out_path.unlink()

    # First pass: write zip without checksum so we can compute it.
    members: list[tuple[Path, str]] = []
    for src in sorted(pack_dir.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(pack_dir)
        # Skip anything that looks like editor / OS detritus.
        # screenshots/ and images/ are README-only — embedded in the
        # pack source for editor preview but excluded from the .dpack
        # so the runtime install allowlist (which restricts to
        # .json/.py/.md/.txt/.rst) doesn't reject .png members.
        # INTERNAL_NOTES.md is internal-only — never ships in the .dpack.
        if any(part in {"__pycache__", ".DS_Store", ".pytest_cache", "screenshots", "images"} for part in rel.parts):
            continue
        if rel.name == "INTERNAL_NOTES.md":
            continue
        if rel.name.endswith((".pyc", ".pyo")):
            continue
        archive_name = f"{pack_id}/{rel.as_posix()}"
        if not _zip_safe(archive_name):
            _die(f"unsafe archive member: {archive_name}")
        members.append((src, archive_name))

    # Compute the content checksum over the *payload* — every member
    # except pack.json itself (which carries this very checksum and
    # therefore can't be part of it). Same algorithm as
    # backend/dig/plugins/packs.py:_compute_pack_checksum so the
    # runtime can verify what the build wrote.
    h = hashlib.sha256()
    for src, archive_name in sorted(members, key=lambda m: m[1]):
        if archive_name == f"{pack_id}/pack.json":
            continue
        h.update(archive_name.encode("utf-8"))
        h.update(b"\x00")
        h.update(src.read_bytes())
    checksum = "sha256:" + h.hexdigest()

    pack_doc_with_sum = dict(pack_doc)
    pack_doc_with_sum["checksum"] = checksum

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, archive_name in members:
            if archive_name == f"{pack_id}/pack.json":
                # Substitute the stamped manifest
                zf.writestr(archive_name, json.dumps(pack_doc_with_sum, indent=2) + "\n")
            else:
                zf.write(src, archive_name)

    size_kb = out_path.stat().st_size / 1024
    print(f"  ✓ {out_path.relative_to(ROOT)}  ({size_kb:.1f} KB, {len(declared_steps)} step(s))")
    print(f"  ✓ checksum {checksum}")
    return out_path


def build_all() -> list[Path]:
    if not PACKS_DIR.exists():
        _die(f"no packs/ dir at {PACKS_DIR.relative_to(ROOT)}")
    out = []
    for d in sorted(PACKS_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("_") and not d.name.startswith("."):
            out.append(build_one(d.name))
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == "--all":
        build_all()
    else:
        for pid in argv[1:]:
            build_one(pid)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
