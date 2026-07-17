"""Pipeline document — Pydantic models mirroring shared/schemas/pipeline.schema.json.

These models drive validation on save and run-time DAG analysis. The JSON schema
remains authoritative for cross-language consumers (the frontend's typed
client); these models add Python ergonomics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    port: str | None = None


class DatasetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    connector: str
    connectorVersion: str | None = None
    uri: str
    options: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None


def effective_connector(spec: "DatasetSpec") -> str:
    """Return the connector to actually use when reading this dataset.

    Pipeline docs persist `connector` as a string (csv / parquet / …), but
    the bytes on disk are the source of truth. When a dataset got
    re-cached as parquet after originally being CSV (or vice versa), the
    persisted spec can lag and DuckDB then reads parquet bytes through
    `read_csv_auto`, producing a confusing "Error when sniffing file"
    error from a CTE the user didn't write.

    This helper trusts the URI extension over the persisted connector:
      - `.parquet` → "parquet"
      - `.csv`     → "csv"
      - anything else → fall back to `spec.connector` (JDBC, custom
        connectors, etc. all have non-file URIs and are unaffected).

    Used by both `compile.compile_for_browser` and `executor._dataset_cte`
    so browser and backend executions stay in lockstep — Layer 4 of the
    AI-features defense ("Backend covers all paths" / dispatcher routes
    transparently) applies to dataset I/O too.
    """
    uri = (spec.uri or "").lower()
    # Strip query strings and fragments for extension detection (e.g.
    # `?download=1`). urlparse-grade isn't needed — these are local paths
    # 99% of the time.
    bare = uri.split("?", 1)[0].split("#", 1)[0]
    if bare.endswith(".parquet"):
        return "parquet"
    if bare.endswith(".csv"):
        return "csv"
    if bare.endswith((".json", ".jsonl", ".ndjson")):
        return "json"
    return spec.connector


class ExposedParam(BaseModel):
    """One row of node.ui.exposedParams — declares a node-level param
    as customisable from outside when the pipeline is published as a
    reusable step."""
    model_config = ConfigDict(extra="forbid")
    alias: str
    help: str | None = None


class FreshnessPolicy(BaseModel):
    """Optional declarative freshness SLA on a node's output.

    Declaration only; the canvas renders halos based on `last_run_at +
    sla` vs `now()`. The scheduler that *acts on* this is not implemented
    here.

    Durations are short strings: "30m", "2h", "1d", "7d". Anything pydantic
    rejects gets a clean error message at pipeline-save time.
    """
    model_config = ConfigDict(extra="forbid")
    sla: str
    warn_at: str | None = None  # halo flips amber within this window of stale


class NodeUI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float | None = None
    y: float | None = None
    label: str | None = None
    note: str | None = None
    # Map of param-key → exposure metadata. When the pipeline is
    # published as a step (metadata.publishedAsStep), each entry here
    # surfaces as a customisable param on the synthesised manifest.
    exposedParams: dict[str, ExposedParam] | None = None
    # Freshness policy — optional. When present, the canvas renders a
    # colored halo around the node based on last-run age vs sla.
    freshness: FreshnessPolicy | None = None


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    step: str
    # ``stepVersion`` is optional on the wire: API callers who don't know
    # (or care) which version to pin can omit it, and the Pipeline-level
    # ``_fill_step_versions`` validator backfills the live version from
    # the registry. Docs persisted to disk always have it set because the
    # validator runs on every parse. Older docs that already carry an
    # explicit version are passed through unchanged so a pipeline pinned
    # to 1.0.0 of a step keeps using that contract even if the registry
    # now ships 1.2.0.
    stepVersion: str | None = None
    inputs: dict[str, Reference] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=lambda: ["out"])
    params: dict[str, Any] = Field(default_factory=dict)
    ui: NodeUI | None = None


class Sink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connector: str
    connectorVersion: str | None = None
    uri: str
    options: dict[str, Any] = Field(default_factory=dict)


class OutputSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    id: str
    name: str
    from_: Reference = Field(alias="from")
    sink: Sink | None = None


class Webhook(BaseModel):
    """Outbound notification fired when a run reaches a terminal status,
    or fired explicitly from inside a pipeline by the `webhook_trigger` step.

    DIG POSTs a JSON body describing the run (or, for triggered fires, a
    payload assembled by the step); the receiver can chain external
    workflows (Slack, n8n, GitHub Actions, etc.) off of either signal.
    When `secret` is set, DIG also sends an `X-DIG-Signature: sha256=...`
    HMAC header so the receiver can authenticate the call.

    The `on` selector controls auto-dispatch:
      - always:    fires on both succeeded and failed terminal status
      - succeeded: fires only on success
      - failed:    fires only on failure
      - triggered: never auto-fires; only fires when an in-pipeline
                   `webhook_trigger` step explicitly invokes it. Use this
                   for "pipeline-as-trigger" workflows where the act of
                   reaching a particular step is itself the signal.
    """
    model_config = ConfigDict(extra="forbid")
    url: str
    # Free-form string (not enum) so vendors / enterprise builds can introduce
    # new triggers (e.g. "partial_success", "data_quality_failed") without a
    # schemaVersion bump. Known values: always, succeeded, failed, triggered.
    # Unknown values are treated as "never" by the OSS reader.
    on: str = "always"
    secret: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    label: str | None = None


class GroupUI(BaseModel):
    """Visual treatment for a node group on the canvas."""
    model_config = ConfigDict(extra="forbid")
    color: str | None = None      # tailwind color name or hex; default chosen by frontend
    collapsed: bool = False       # whether the group renders as a super-node
    # Optional group-level freshness SLA — applied to the group as a
    # logical "data product". Independent from per-node freshness; the
    # group can have its own SLA whether or not its members do. The
    # /freshness endpoint computes both and the frontend renders both
    # halos.
    freshness: FreshnessPolicy | None = None


class NodeGroup(BaseModel):
    """A labeled grouping of pipeline nodes for visual organization +
    aggregate run-state on the canvas.

    Pure UI metadata; does not affect execution semantics. Groups can
    nest via `parent_group_id` — the
    outer group's bbox auto-expands to include child group bboxes, so a
    user can group sub-clusters inside a larger logical region (e.g.
    "Revenue Models" containing "Forecast" and "Anomaly" as sub-groups).
    """
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    node_ids: list[str] = Field(default_factory=list)
    # Optional parent group for nesting. None = top-level group. Cycles
    # are not validated server-side; the frontend assumes acyclic
    # construction (which it enforces in its create-group flow).
    parent_group_id: str | None = None
    ui: GroupUI = Field(default_factory=GroupUI)


class Pipeline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1] = 1
    # Round-4 QA finding: ``id`` was a bare ``str`` with no regex, no
    # length cap, no character set restriction. The rc1 relaxation
    # widened the ID alphabet to allow ``-`` and ``:`` but never
    # re-imposed shape constraints, so a doc with ``id="abc\ndef"``
    # or ``id="…26+ chars…"`` landed in JSON history and could
    # corrupt downstream string-concatenation surfaces (crontab line,
    # log paths, /schedules marker). Constrain shape here; existing
    # ULID-shaped IDs continue to validate.
    # Round-9 fix: drop ``:`` from the allowed character class — `:` is
    # used as a namespace separator in multiple places (``pipeline:<id>``
    # step prefix, ``run:<id>`` / ``pipeline:<id>`` WS topics, freshness
    # LRU keys), so a pipeline id like ``abc:def`` would collide with
    # them. Existing colon-free ULID-shaped IDs continue to validate.
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str
    description: str | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    datasets: list[DatasetSpec] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    # Namespaced extension fields — vendors / enterprise builds attach
    # their own data under top-level namespace keys (e.g. extensions.acme
    # .customField) so future first-party fields never collide. The OSS
    # core treats every namespace except its own as opaque pass-through.
    extensions: dict[str, Any] = Field(default_factory=dict)
    webhooks: list[Webhook] = Field(default_factory=list)
    # Optional visual node groupings for canvas organization. See
    # NodeGroup. Empty list = no groups (canvas renders flat).
    groups: list[NodeGroup] = Field(default_factory=list)
    # Workspace tags. Lowercase-normalised + dedup'd
    # alphanumeric / dash / underscore strings. Used by /search and
    # the catalog tag-filter chips. Set via /search/pipelines/{id}/tags.
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _fill_step_versions(self) -> "Pipeline":
        """Backfill ``stepVersion`` on every node that omitted it.

        API clients (and humans writing pipelines by hand) shouldn't need
        to look up the current registry version for each step before
        constructing a doc — the registry already knows. We resolve once
        per parse and stamp the live version into any node whose
        ``stepVersion`` was left ``None``.

        Pipelines that DO pin a version (older docs, intentional
        version-locks) pass through untouched. Unknown step IDs fall
        through to ``"1.0.0"`` because version validation surfaces a
        clearer error elsewhere ("unknown step '<id>'") that points at
        the real problem.

        Lazy import keeps ``pipeline.py`` free of a hard dependency on
        the registry module's side effects (avoids circular-import
        complaints when the registry imports models from here for
        manifest validation).
        """
        # Cheap exit: nothing to backfill.
        if all(n.stepVersion for n in self.nodes):
            return self

        try:
            from dig.engine.registry import steps as _steps  # noqa: PLC0415
            reg = _steps()
        except Exception:  # noqa: BLE001 — registry may not be primed in unit tests
            reg = None

        for n in self.nodes:
            if n.stepVersion:
                continue
            ver: str | None = None
            if reg is not None:
                try:
                    m = reg.get(n.step)
                    ver = getattr(m, "version", None)
                except Exception:  # noqa: BLE001
                    ver = None
            n.stepVersion = ver or "1.0.0"
        return self
