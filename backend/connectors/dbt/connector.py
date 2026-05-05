"""dbt model ingestion connector.

Reads from a dbt project's `target/manifest.json` to surface dbt models as
DIG datasets. Two materialization paths:

1. Pre-materialized models (table / incremental) — read directly from the
   warehouse using polars.read_database_uri against the dbt target's
   connection string.
2. View / ephemeral models — read by executing the model's compiled_sql
   against the warehouse (extra cost, no caching).

Auth flows through the dbt project's profiles.yml — DIG never copies the
secrets out, just reads the path the user provides and uses dbt's own
config resolution.
"""

from __future__ import annotations

import json as _json
import os
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.connector import Connector


class DbtConnector(Connector):
    def read(self, uri: str, options: dict[str, Any]) -> pl.LazyFrame:
        if not uri.startswith("dbt://"):
            raise ValueError(
                f"dbt connector: URI must start with dbt:// (got: {uri[:24]}…)"
            )

        project_path = options.get("project_path") or ""
        if not project_path:
            raise ValueError("dbt connector: 'project_path' option is required")
        project_path = os.path.expanduser(str(project_path))
        project = Path(project_path)
        if not project.exists():
            raise ValueError(f"dbt connector: project_path {project_path!r} does not exist")

        manifest_path = project / "target" / "manifest.json"
        if not manifest_path.exists():
            raise RuntimeError(
                f"dbt connector: no manifest.json at {manifest_path}. "
                f"Run `dbt parse` (or `dbt compile`) inside {project} first."
            )

        manifest = _json.loads(manifest_path.read_text())

        model_arg = (options.get("model") or "").strip()
        if not model_arg:
            raise ValueError("dbt connector: 'model' option is required")

        model_node = _find_model(manifest, model_arg)
        if model_node is None:
            raise ValueError(
                f"dbt connector: model {model_arg!r} not found in manifest. "
                f"Available models: {_list_models(manifest)[:5]}"
            )

        # Resolve the warehouse via the dbt profile.
        target = (options.get("target") or "dev").strip()
        try:
            warehouse_uri = _resolve_dbt_target_uri(project, manifest, target)
        except Exception as e:
            raise RuntimeError(
                f"dbt connector: couldn't resolve target {target!r}: {e}"
            ) from e

        # For materialized models read the relation; for views/ephemeral, run the SQL.
        materialization = (model_node.get("config") or {}).get("materialized", "view")
        relation = model_node.get("relation_name") or _qualify_relation(model_node)
        compiled_sql = model_node.get("compiled_code") or model_node.get("compiled_sql")

        if materialization in ("table", "incremental") and relation:
            sql = f"SELECT * FROM {relation}"
        elif compiled_sql:
            sql = compiled_sql
        else:
            raise RuntimeError(
                f"dbt connector: model {model_arg!r} has no relation or compiled_sql — "
                "did you run `dbt compile`?"
            )

        try:
            df = pl.read_database_uri(query=sql, uri=warehouse_uri)
        except ModuleNotFoundError as e:
            raise RuntimeError(
                "dbt connector: missing driver. Install one of "
                "`connectorx`, `adbc-driver-postgresql`, or the appropriate ADBC driver "
                "for your warehouse, then retry."
            ) from e

        return df.lazy()


# ---- Helpers ------------------------------------------------------------


def _find_model(manifest: dict[str, Any], model_arg: str) -> dict[str, Any] | None:
    """Find a model in the dbt manifest by bare name or qualified name."""
    nodes = manifest.get("nodes") or {}
    for node_id, node in nodes.items():
        if not node_id.startswith("model."):
            continue
        name = node.get("name") or ""
        if name == model_arg:
            return node
        # qualified: <package>.<name>
        package = node.get("package_name") or ""
        if model_arg == f"{package}.{name}":
            return node
        # also match on resource_path
        if node_id.endswith(f".{model_arg}"):
            return node
    return None


def _list_models(manifest: dict[str, Any]) -> list[str]:
    nodes = manifest.get("nodes") or {}
    return [n.get("name") for k, n in nodes.items() if k.startswith("model.") and n.get("name")]


def _qualify_relation(node: dict[str, Any]) -> str:
    db = node.get("database") or ""
    schema = node.get("schema") or ""
    name = node.get("alias") or node.get("name") or ""
    parts = [p for p in (db, schema, name) if p]
    return ".".join(f'"{p}"' for p in parts)


def _resolve_dbt_target_uri(
    project: Path, manifest: dict[str, Any], target: str
) -> str:
    """Read profiles.yml and build a connection URI for the named target.

    Supports postgres + redshift + snowflake adapters. For other adapters,
    raises with a clear message — production setups should use a saved DIG
    Connection per the Reverse-ETL Connectors proposal.
    """
    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "dbt connector: PyYAML required to read profiles.yml. "
            "Install with `pip install pyyaml`."
        ) from e

    # Profile name comes from dbt_project.yml.
    project_yml = project / "dbt_project.yml"
    if not project_yml.exists():
        raise RuntimeError(f"dbt connector: no dbt_project.yml at {project_yml}")
    project_cfg = yaml.safe_load(project_yml.read_text()) or {}
    profile_name = project_cfg.get("profile")
    if not profile_name:
        raise RuntimeError("dbt connector: dbt_project.yml has no 'profile' key")

    profiles_paths = [
        project / "profiles.yml",
        Path(os.path.expanduser("~/.dbt/profiles.yml")),
    ]
    profiles: dict[str, Any] | None = None
    for pp in profiles_paths:
        if pp.exists():
            profiles = yaml.safe_load(pp.read_text()) or {}
            break
    if profiles is None:
        raise RuntimeError(
            "dbt connector: profiles.yml not found in project or ~/.dbt/"
        )

    profile = profiles.get(profile_name)
    if not profile:
        raise RuntimeError(
            f"dbt connector: profile {profile_name!r} not in profiles.yml"
        )
    outputs = profile.get("outputs") or {}
    target_cfg = outputs.get(target)
    if not target_cfg:
        raise RuntimeError(
            f"dbt connector: target {target!r} not in profile {profile_name!r}"
        )

    adapter = target_cfg.get("type")
    # `urllib.parse.quote` on user/password — without this, a password
    # containing `@`, `:`, `/`, or `#` produces a URI that parses to the
    # wrong host or schema and either silently routes credentials to the
    # wrong endpoint or fails with a confusing parse error.
    from urllib.parse import quote as _qs

    if adapter in ("postgres", "redshift"):
        host = target_cfg.get("host")
        port = target_cfg.get("port", 5432)
        user = _qs(str(target_cfg.get("user") or ""), safe="")
        password = _qs(str(target_cfg.get("password") or target_cfg.get("pass") or ""), safe="")
        dbname = target_cfg.get("dbname") or target_cfg.get("database")
        return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"
    if adapter == "snowflake":
        account = target_cfg.get("account")
        user = _qs(str(target_cfg.get("user") or ""), safe="")
        password = _qs(str(target_cfg.get("password") or ""), safe="")
        database = target_cfg.get("database")
        schema = target_cfg.get("schema", "PUBLIC")
        warehouse = target_cfg.get("warehouse")
        role = target_cfg.get("role")
        qs = []
        if warehouse:
            qs.append(f"warehouse={warehouse}")
        if role:
            qs.append(f"role={role}")
        q = ("?" + "&".join(qs)) if qs else ""
        return f"snowflake://{user}:{password}@{account}/{database}/{schema}{q}"

    raise RuntimeError(
        f"dbt connector: adapter {adapter!r} not supported for direct read. "
        "Use a saved DIG Connection (Reverse-ETL Connectors proposal) and "
        "wire the model output through the matching connector instead."
    )


_manifest_path = Path(__file__).parent / "manifest.json"
connector = DbtConnector(_json.loads(_manifest_path.read_text()))
