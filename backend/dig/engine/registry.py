from __future__ import annotations

import importlib.util
import json
import logging
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
    spec.loader.exec_module(module)
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


def connectors() -> ConnectorRegistry:
    global _connectors
    if _connectors is None:
        repo = Path(__file__).resolve().parents[3]
        _connectors = ConnectorRegistry(repo / "backend" / "connectors")
        _connectors.scan()
        # Also scan user plugins/connectors/ if present.
        user_dir = repo / "plugins" / "connectors"
        if user_dir.exists():
            _connectors._base_dir = user_dir  # noqa: SLF001
            _connectors.scan()
            _connectors._base_dir = repo / "backend" / "connectors"  # restore
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


def steps() -> StepRegistry:
    global _steps
    if _steps is None:
        repo = Path(__file__).resolve().parents[3]
        _steps = StepRegistry(repo / "backend" / "steps")
        _steps.scan()
        # Also scan user plugins/steps/ if present.
        user_dir = repo / "plugins" / "steps"
        if user_dir.exists():
            _steps._base_dir = user_dir  # noqa: SLF001
            _steps.scan()
            _steps._base_dir = repo / "backend" / "steps"  # restore
    return _steps
