"""Extension discovery — entry points + on-disk `data/extensions/`.

Both channels are designed so an OSS upgrade (`./upgrade.sh`) cannot
touch them:

  ┌─ entry points: live in site-packages of separately-installed pip
  │  packages. `pip install -e ./backend` only re-installs the `dig`
  │  package; other packages' site-packages entries are untouched.
  │
  └─ data/extensions/: lives under `data_dir()`, which is gitignored
     and excluded from any git checkout — survives every upgrade.

Discovery is purely informational at this layer. The caller (FastAPI
lifespan, step registry, etc.) decides what to do with discovered
extensions — register routes, add a Step subclass to the registry,
mount static files at `/ext/<name>/*`, etc.

Extension authors implement against `dig.protocols`, not against
`dig.engine.*` directly — see that module's docstring for the contract.
"""
from __future__ import annotations

import importlib.metadata
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dig.storage.files import data_dir

log = logging.getLogger(__name__)


# ── Entry-point groups DIG scans ───────────────────────────────────────
#
# Plugins under `dig.plugins` are generic — anything that wants to tap
# into a startup hook. Specific groups (steps, connectors, routers) get
# routed by the consumer; this module just discovers them.

ENTRY_POINT_GROUPS: tuple[str, ...] = (
    "dig.plugins",      # generic — any callable run at startup
    "dig.steps",        # extra step plugins (in addition to backend/steps/)
    "dig.connectors",   # extra connector plugins
    "dig.routers",      # FastAPI routers to mount on startup
)

# Reserved subdirectory under data_dir() for filesystem-mounted extensions.
EXTENSIONS_SUBDIR = "extensions"


@dataclass(frozen=True)
class DiscoveredExtension:
    """A discovered entry-point-based plugin.

    `loaded_object` is None when the entry point failed to import — the
    instance is still recorded so the caller can report the failure
    in /health and the operator knows why their plugin is silent.
    """
    group: str          # one of ENTRY_POINT_GROUPS
    name: str           # entry-point name
    package: str        # distributing package name (e.g. "dig-enterprise")
    package_version: str
    loaded_object: Any | None = None
    load_error: str | None = None


@dataclass(frozen=True)
class DiscoveredFsExtension:
    """An on-disk extension under `data/extensions/<name>/`."""
    name: str           # directory name
    path: Path          # absolute path to the extension's root
    manifest: dict[str, Any] = field(default_factory=dict)
    has_static: bool = False
    load_error: str | None = None

    @property
    def static_dir(self) -> Path:
        return self.path / "static"

    @property
    def url_prefix(self) -> str:
        """Frontend-visible mount point: /ext/<name>/static/..."""
        return f"/ext/{self.name}"


# ── Public API ─────────────────────────────────────────────────────────


def extensions_dir() -> Path:
    """Where filesystem extensions live. Created lazily on first call."""
    p = data_dir() / EXTENSIONS_SUBDIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def discover_entry_points(
    *, groups: tuple[str, ...] = ENTRY_POINT_GROUPS,
) -> list[DiscoveredExtension]:
    """Scan installed Python distributions for DIG entry points.

    Best-effort: every entry-point load is wrapped so a broken plugin
    can't block DIG startup. Failed loads return a record with
    `load_error` set so the operator can investigate via /health.

    Duplicate (group, name) pairs (e.g. two installed packages both
    declaring `dig.routers.audit`) are de-duped — the FIRST wins, the
    rest are recorded with a `load_error` so the operator can resolve
    the conflict.
    """
    discovered: list[DiscoveredExtension] = []
    seen: set[tuple[str, str]] = set()
    for group in groups:
        try:
            eps = importlib.metadata.entry_points(group=group)
        except Exception:
            log.exception("entry-point lookup failed for group %s", group)
            continue
        for ep in eps:
            # `ep.dist` can be None for editable / vendored / namespace-package
            # installs. Guard explicitly so the loader doesn't AttributeError.
            pkg = ep.dist.name if ep.dist is not None else "<unknown>"
            ver = ep.dist.version if ep.dist is not None else "0.0.0"
            key = (group, ep.name)
            if key in seen:
                discovered.append(DiscoveredExtension(
                    group=group, name=ep.name, package=pkg,
                    package_version=ver, loaded_object=None,
                    load_error=(
                        f"duplicate {group}:{ep.name} from {pkg} {ver}; "
                        "the first-discovered registration was kept. Uninstall "
                        "or rename one of the conflicting packages."
                    ),
                ))
                log.warning("duplicate extension %s:%s from %s — skipped", group, ep.name, pkg)
                continue
            seen.add(key)
            try:
                obj = ep.load()
                discovered.append(DiscoveredExtension(
                    group=group, name=ep.name, package=pkg,
                    package_version=ver, loaded_object=obj,
                ))
                log.info("loaded extension %s:%s from %s %s",
                         group, ep.name, pkg, ver)
            except Exception as exc:  # noqa: BLE001 - we deliberately catch broad
                log.exception("failed to load extension %s:%s from %s",
                              group, ep.name, pkg)
                discovered.append(DiscoveredExtension(
                    group=group, name=ep.name, package=pkg,
                    package_version=ver, loaded_object=None,
                    load_error=f"{type(exc).__name__}: {exc}",
                ))
    return discovered


def discover_fs_extensions() -> list[DiscoveredFsExtension]:
    """Scan `data/extensions/<name>/` directories.

    Each directory is a separate extension. A `manifest.json` describes
    the extension; a `static/` subdirectory (if present) is mounted at
    `/ext/<name>/static/*` by the FastAPI lifespan hook.

    Best-effort: a malformed manifest doesn't block other extensions.
    """
    root = extensions_dir()
    out: list[DiscoveredFsExtension] = []
    if not root.exists():
        return out
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        # Reject names that would break the URL path or filesystem.
        if not _is_safe_name(child.name):
            log.warning("skipping fs extension with unsafe name: %s", child.name)
            continue
        manifest: dict[str, Any] = {}
        load_error: str | None = None
        manifest_path = child / "manifest.json"
        if manifest_path.exists():
            try:
                # Cap manifest at 1 MiB — anything larger is definitely a
                # malformed manifest or a hostile dropped file (e.g.
                # symlink to /dev/zero) and we don't want to OOM the boot.
                size = manifest_path.stat().st_size
                if size > 1 * 1024 * 1024:
                    raise ValueError(
                        f"manifest.json too large ({size} bytes; max 1 MiB)",
                    )
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                log.exception("malformed manifest.json in %s", child)
                load_error = f"manifest.json: {type(exc).__name__}: {exc}"
        has_static = (child / "static").is_dir()
        out.append(DiscoveredFsExtension(
            name=child.name, path=child, manifest=manifest,
            has_static=has_static, load_error=load_error,
        ))
        if not load_error:
            log.info("discovered fs extension %s (static=%s)", child.name, has_static)
    return out


def discover_all() -> dict[str, Any]:
    """Convenience wrapper: returns both channels in a JSON-friendly shape.

    Used by the FastAPI lifespan hook + surfaced in /health.extensions.
    """
    eps = discover_entry_points()
    fs = discover_fs_extensions()
    return {
        "entry_points": [
            {
                "group": e.group,
                "name": e.name,
                "package": e.package,
                "package_version": e.package_version,
                "loaded": e.loaded_object is not None,
                "load_error": e.load_error,
            }
            for e in eps
        ],
        "fs": [
            {
                "name": f.name,
                "path": str(f.path),
                "manifest": f.manifest,
                "has_static": f.has_static,
                "url_prefix": f.url_prefix,
                "load_error": f.load_error,
            }
            for f in fs
        ],
        "loaded_objects": eps,  # for in-process consumers (router mounting, etc.)
    }


# ── Helpers ────────────────────────────────────────────────────────────


# Reserved top-level paths the extension namespace must not collide with.
# Names matching these are silently skipped — pen-tester pattern: an
# extension named `health` mounting `/ext/health/static` doesn't collide
# with `/health` today, but the deny-list is defence-in-depth in case a
# future change adds wildcard / non-prefixed mounts that could shadow
# the unauthenticated `/health` route or any other reserved API path.
_RESERVED_NAMES = frozenset({
    "health", "metrics", "openapi.json", "docs", "redoc",
    "connectors", "types", "datasets", "pipelines", "runs",
    "search", "catalog", "settings", "ai", "schedules",
    "templates", "packs", "notifications", "notification_rules",
    "ws", "ext", "docs-files",
})


def _is_safe_name(name: str) -> bool:
    """Names become URL path segments + filesystem dirs.

    Conservative: lowercase + alphanumerics + hyphens + underscores
    only. Rejects path traversal, URL reserved chars, control bytes,
    and DIG's reserved top-level route names.
    """
    if not name or len(name) > 64:
        return False
    if name in {".", ".."}:
        return False
    if name.lower() in _RESERVED_NAMES:
        return False
    return all(c.isalnum() or c in "-_" for c in name)
