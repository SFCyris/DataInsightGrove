from __future__ import annotations

import importlib.util
import json
import logging
import sys
import threading
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from dig.engine.connector import Connector
from dig.engine.step import Step

log = logging.getLogger(__name__)


def _schemas_dir() -> Path:
    # backend/dig/engine/registry.py -> repo root is parents[3]
    return Path(__file__).resolve().parents[3] / "shared" / "schemas"


def _build_registry() -> Registry:
    """Pre-load all schemas in shared/schemas/ so cross-schema $refs resolve offline."""
    reg: Registry = Registry()
    for path in _schemas_dir().glob("*.schema.json"):
        schema = json.loads(path.read_text())
        if "$id" in schema:
            reg = reg.with_resource(
                uri=schema["$id"],
                resource=Resource(contents=schema, specification=DRAFT202012),
            )
    return reg


_registry: Registry | None = None


def _shared_registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return _registry


def _load_validator(name: str) -> Draft202012Validator:
    p = _schemas_dir() / name
    schema = json.loads(p.read_text())
    return Draft202012Validator(schema, registry=_shared_registry())


def _load_module(folder: Path, file: str, mod_name: str) -> Any:
    file_path = folder / file
    if not file_path.exists():
        raise FileNotFoundError(f"plugin {folder.name} missing {file}")
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load module spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    # `module_from_spec` doesn't insert into `sys.modules`, but exec_module
    # may rely on the module being importable by name (e.g., dataclasses).
    # Insert it now and pop on failure so a half-loaded module doesn't
    # poison subsequent reload attempts after the user fixes their code.
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(mod_name, None)
        raise
    return module


class ConnectorRegistry:
    """Auto-discovery of connector plugins.

    Each connector lives at `<base_dir>/<id>/` containing:
      - manifest.json validated against connector-manifest.schema.json
      - connector.py exporting `connector` (an instance of dig.engine.connector.Connector)
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._validator = _load_validator("connector-manifest.schema.json")
        # Also need step manifest validator because connector schema $refs it.
        self._step_validator = _load_validator("step-manifest.schema.json")
        self._by_id: dict[str, Connector] = {}

    def scan(self) -> None:
        if not self._base_dir.exists():
            log.warning("connector dir not found: %s", self._base_dir)
            return
        for folder in sorted(self._base_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_") or folder.name.startswith("."):
                continue
            try:
                self._load_one(folder)
            except Exception as e:
                log.exception("failed to load connector %s: %s", folder.name, e)

    def _load_one(self, folder: Path) -> None:
        manifest_path = folder / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text())
        errors = sorted(self._validator.iter_errors(manifest), key=lambda e: e.path)
        if errors:
            raise ValueError(
                f"{folder.name}/manifest.json invalid: " + "; ".join(e.message for e in errors)
            )
        module = _load_module(folder, "connector.py", f"dig_connector_{folder.name}")
        connector = getattr(module, "connector", None)
        if not isinstance(connector, Connector):
            raise TypeError(
                f"{folder.name}/connector.py must export `connector` of type Connector"
            )
        if connector.id != manifest["id"]:
            raise ValueError(
                f"{folder.name}: manifest id '{manifest['id']}' != connector.id '{connector.id}'"
            )
        self._by_id[connector.id] = connector
        log.info("loaded connector %s v%s", connector.id, connector.version)

    def get(self, connector_id: str) -> Connector:
        if connector_id not in self._by_id:
            raise KeyError(f"connector '{connector_id}' not registered")
        return self._by_id[connector_id]

    def all(self) -> list[Connector]:
        return list(self._by_id.values())


_connectors: ConnectorRegistry | None = None
_connectors_lock = threading.Lock()


def connectors() -> ConnectorRegistry:
    global _connectors
    # Double-checked locking — avoid taking the lock on the hot path once the
    # registry is initialized. Without the lock, two threads racing here
    # both saw `_connectors is None`, both built a registry, and the
    # _base_dir mutation hack made the second thread's scan() use whatever
    # base_dir was current mid-mutation in the first.
    if _connectors is None:
        with _connectors_lock:
            if _connectors is None:
                repo = Path(__file__).resolve().parents[3]
                reg = ConnectorRegistry(repo / "backend" / "connectors")
                reg.scan()
                # Also scan user plugins/connectors/ if present. Use a
                # separate registry instance scoped to that dir, then merge —
                # the previous form mutated `_base_dir` in place which races
                # under any concurrent reader.
                user_dir = repo / "plugins" / "connectors"
                if user_dir.exists():
                    user_reg = ConnectorRegistry(user_dir)
                    user_reg.scan()
                    for c in user_reg.all():
                        reg._by_id[c.id] = c  # noqa: SLF001
                _connectors = reg
    return _connectors


class StepRegistry:
    """Auto-discovery of step plugins.

    Each step lives at `<base_dir>/<id>/` containing:
      - manifest.json validated against step-manifest.schema.json
      - step.py exporting `step` (an instance of dig.engine.step.Step)
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._validator = _load_validator("step-manifest.schema.json")
        self._by_id: dict[str, Step] = {}

    def scan(self) -> None:
        if not self._base_dir.exists():
            log.warning("step dir not found: %s", self._base_dir)
            return
        for folder in sorted(self._base_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_") or folder.name.startswith("."):
                continue
            try:
                self._load_one(folder)
            except Exception as e:
                log.exception("failed to load step %s: %s", folder.name, e)

    def _load_one(self, folder: Path) -> None:
        manifest_path = folder / "manifest.json"
        if not manifest_path.exists():
            return
        manifest = json.loads(manifest_path.read_text())
        errors = sorted(self._validator.iter_errors(manifest), key=lambda e: e.path)
        if errors:
            raise ValueError(
                f"{folder.name}/manifest.json invalid: " + "; ".join(e.message for e in errors)
            )
        module = _load_module(folder, "step.py", f"dig_step_{folder.name}")
        step = getattr(module, "step", None)
        if not isinstance(step, Step):
            raise TypeError(
                f"{folder.name}/step.py must export `step` of type Step"
            )
        if step.id != manifest["id"]:
            raise ValueError(
                f"{folder.name}: manifest id '{manifest['id']}' != step.id '{step.id}'"
            )
        self._by_id[step.id] = step
        log.info("loaded step %s v%s (%s)", step.id, step.version, step.category)

    def get(self, step_id: str) -> Step:
        if step_id not in self._by_id:
            raise KeyError(f"step '{step_id}' not registered")
        return self._by_id[step_id]

    def all(self) -> list[Step]:
        return list(self._by_id.values())


_steps: StepRegistry | None = None
_steps_lock = threading.Lock()


def _load_pack_steps(reg: StepRegistry, repo: Path) -> None:
    """Layer steps from every enabled installed pack into `reg`.

    Disk layout: `<repo>/plugins/packs/<pack_id>/steps/<step_id>/…`. We
    skip pack directories prefixed with `_` or `.` and any pack the
    StepPack table has marked as disabled.
    """
    packs_root = repo / "plugins" / "packs"
    if not packs_root.exists():
        return

    # Read which packs are disabled via a synchronous lightweight check.
    # We avoid importing the async ORM here to keep registry init free of
    # async machinery; instead we read the row directly with a sync
    # connection. If the table doesn't exist yet (first boot before
    # init_db has run), treat every pack as enabled — the registry is
    # robust without the table.
    disabled_pack_ids: set[str] = set()
    try:
        from dig.storage.files import data_dir as _data_dir
        import sqlite3 as _sqlite
        db_path = _data_dir() / "dig.sqlite"
        if db_path.exists():
            conn = _sqlite.connect(str(db_path))
            try:
                cur = conn.execute(
                    "SELECT id FROM step_packs WHERE enabled = 0",
                )
                disabled_pack_ids = {row[0] for row in cur.fetchall()}
            except _sqlite.OperationalError:
                pass  # table doesn't exist yet
            finally:
                conn.close()
    except Exception:
        pass  # disabled-pack visibility is best-effort

    for pack_dir in sorted(packs_root.iterdir()):
        if not pack_dir.is_dir() or pack_dir.name.startswith(("_", ".")):
            continue
        if pack_dir.name in disabled_pack_ids:
            log.info("skipping disabled pack: %s", pack_dir.name)
            continue
        steps_dir = pack_dir / "steps"
        if not steps_dir.exists():
            continue
        sub = StepRegistry(steps_dir)
        sub.scan()
        for s in sub.all():
            # Tag the step with its source pack so the UI can show a
            # provenance badge. The Step base class doesn't have a
            # `source` attr by default; setattr is the cheap way to add
            # it without changing every Step subclass.
            try:
                setattr(s, "source", f"pack:{pack_dir.name}")
            except Exception:
                pass
            reg._by_id[s.id] = s  # noqa: SLF001


def steps() -> StepRegistry:
    global _steps
    if _steps is None:
        with _steps_lock:
            if _steps is None:
                repo = Path(__file__).resolve().parents[3]
                reg = StepRegistry(repo / "backend" / "steps")
                reg.scan()
                # Built-ins win when there's a name clash. Pack steps
                # layered next, then per-step user plugins last.
                _load_pack_steps(reg, repo)
                user_dir = repo / "plugins" / "steps"
                if user_dir.exists():
                    user_reg = StepRegistry(user_dir)
                    user_reg.scan()
                    for s in user_reg.all():
                        reg._by_id[s.id] = s  # noqa: SLF001
                _steps = reg
    return _steps


def reset_steps_registry() -> None:
    """Drop the cached registry so the next `steps()` call rescans.

    Used after pack install / uninstall so the new content shows up
    without an API restart. This is the canonical hot-reload path.
    """
    global _steps
    with _steps_lock:
        _steps = None
