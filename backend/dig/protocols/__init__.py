"""Frozen public protocol surface — the contract `dig-enterprise` (and any
third-party out-of-tree plugin) consumes.

Why this module exists separately from `dig.engine.*`
=====================================================

An extension that imports `from dig.engine.executor import ExecutionResult`
is taking a load-bearing dependency on a path that's free to refactor —
move the class to a new module, rename the attribute, drop the field, etc.
The rest of `dig.engine.*` is internal-volatility code; we evolve it
freely.

This module re-exports a *named subset* with a stricter promise:

  ┌───────────────────────────────────────────────────────────────────┐
  │ The names in `dig.protocols.__all__` do not change shape between  │
  │ MINOR versions. New names may appear; existing names keep their   │
  │ signatures and field shapes. Removals only happen at MAJOR.       │
  └───────────────────────────────────────────────────────────────────┘

Plugins / enterprise builds should import from `dig.protocols` only.
The OSS internals continue to import from `dig.engine.*` directly.

What's in the surface
=====================

Step plugin contract:
    Step                — abstract step base class
    PolarsResult        — return shape of execute_polars()
    PolarsContext       — runtime context passed to a Polars step
    NanOrigin           — sidecar entry produced by the post-step scanner
    ColumnLineage,
      ColumnRef         — column-dependency declaration

Pipeline document contract:
    Pipeline, Node,
    DatasetSpec,
    OutputSpec, Sink,
    Reference,
    Webhook             — Pydantic models matching the JSON schema

Execution contract:
    ExecutionResult     — what execute() returns
    execute             — top-level executor entry point

Templating contract:
    TemplateError
    build_namespace
    render_value
    render_path
    has_template

Future-tier protocols (not yet implemented in OSS — declared so
out-of-tree enterprise impls have a stable shape to satisfy):
    StorageBackend      — file/object-store backend Protocol
    AuthProvider        — identity + RBAC Protocol
    ComputeBackend      — pluggable compute (Spark, Dask, pushdown) Protocol
"""
from __future__ import annotations

from typing import IO, TYPE_CHECKING, Any, Protocol, runtime_checkable

# ── Step plugin contract ────────────────────────────────────────────────
from dig.engine.step import (
    ColumnLineage,
    ColumnRef,
    NanOrigin,
    PolarsContext,
    PolarsResult,
    Step,
)

# ── Pipeline document contract ──────────────────────────────────────────
from dig.engine.pipeline import (
    DatasetSpec,
    Node,
    OutputSpec,
    Pipeline,
    Reference,
    Sink,
    Webhook,
)

# ── Execution contract ──────────────────────────────────────────────────
from dig.engine.executor import ExecutionResult, execute

# ── Templating contract ─────────────────────────────────────────────────
from dig.engine.templates import (
    TemplateError,
    build_namespace,
    has_template,
    render_path,
    render_value,
)


if TYPE_CHECKING:
    import polars as pl


# ── Protocol interfaces (Protocol ABCs for type-checking) ───────────────
#
# These are interface declarations, not implementations. The shipped
# impls are LocalFSBackend, single-user auth, and in-process Polars
# compute.


@runtime_checkable
class StorageBackend(Protocol):
    """File / object-store backend.

    OSS impl: dig.storage.backends.LocalFSBackend (writes to data_dir()).
    Enterprise impls: S3, GCS, Azure Blob, MinIO.
    """

    def write_parquet(self, df: "pl.DataFrame", path: str) -> str:
        """Write a frame and return the canonical URI of the written object."""
        ...

    def read_parquet_schema(self, uri: str) -> dict[str, str]:
        """Cheap header-only read; return {column: dtype-name}."""
        ...

    def open_for_read(self, uri: str) -> IO[bytes]:
        """Open the object for streaming bytes."""
        ...

    def delete(self, uri: str) -> None:
        """Best-effort delete; idempotent."""
        ...


@runtime_checkable
class AuthProvider(Protocol):
    """Identity + RBAC.

    OSS impl: returns a synthetic single-user session ("local").
    Enterprise impls: OIDC / SAML / SSO + per-resource ACL.
    """

    def current_user(self) -> dict[str, Any]:
        """Returns {id, email?, org_id?, tenant_id?} for the current request."""
        ...

    def can(self, action: str, resource: dict[str, Any]) -> bool:
        """Authorisation check. action is e.g. 'read'/'write'/'delete'.

        Resource shape: {kind, id, owner_id?, org_id?}.
        OSS impl: always True (single-user).
        """
        ...


@runtime_checkable
class ComputeBackend(Protocol):
    """Pluggable execution backend.

    OSS impl: in-process Polars + DuckDB (the executor we already have).
    Enterprise impls: Spark cluster, Dask cluster, Snowflake / BigQuery
    SQL pushdown.
    """

    name: str

    def can_execute(self, pipeline: Pipeline) -> bool:
        """Whether this backend is appropriate for the given pipeline.

        Lets the dispatcher pick (e.g. SparkExecutor.can_execute returns
        True only when the pipeline declares engineHints.preferSpark or
        the workload exceeds a size threshold).
        """
        ...

    def execute(
        self,
        pipeline: Pipeline,
        *,
        run_id: str,
        sample_rows: int | None = None,
    ) -> ExecutionResult:
        """Run the pipeline and return the result. Same signature as the
        in-process executor so the API surface stays uniform."""
        ...


# ── Public surface — versioned by docstring contract above ──────────────

# Round-4 QA finding: ``__all__`` was a mutable list, so external code
# (an extension, a misbehaving test) could ``dig.protocols.__all__.pop()``
# / ``.append()`` and poison every subsequent ``from dig.protocols import *``
# in the same process. The module docstring promises a FROZEN public
# surface — back that with a tuple so the type forbids mutation.
__all__ = (
    # Step plugin contract
    "Step",
    "PolarsResult",
    "PolarsContext",
    "NanOrigin",
    "ColumnLineage",
    "ColumnRef",
    # Pipeline document contract
    "Pipeline",
    "Node",
    "DatasetSpec",
    "OutputSpec",
    "Sink",
    "Reference",
    "Webhook",
    # Execution contract
    "ExecutionResult",
    "execute",
    # Templating contract
    "TemplateError",
    "build_namespace",
    "render_value",
    "render_path",
    "has_template",
    # Future-tier protocols
    "StorageBackend",
    "AuthProvider",
    "ComputeBackend",
)


# ── Surface-version stamp for compatibility checks ──────────────────────
#
# Bumped whenever a new MINOR adds names to __all__. Enterprise builds can
# cross-check at install time:
#
#   from dig.protocols import PROTOCOL_VERSION
#   assert PROTOCOL_VERSION >= (1, 0)
#
# Major-bump (e.g. 1.x → 2.0) means a removed / changed signature in the
# surface above; enterprise pin must move to a new range.

PROTOCOL_VERSION: tuple[int, int] = (1, 0)
