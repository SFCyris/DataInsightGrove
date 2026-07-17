from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from dig.storage.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    # Indexed: upload registration scans for name conflicts on every upload.
    name: Mapped[str] = mapped_column(String(255), index=True)
    connector: Mapped[str] = mapped_column(String(64))
    source_uri: Mapped[str] = mapped_column(Text)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    columns: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="registering")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Per-column free-text notes from the user. Shape: { "<col_name>": "this is in cents, not dollars" }
    annotations: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    # Identity columns — always NULL in single-user deployments.
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Free-form metadata + namespaced extensions slot.
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    extensions: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Indexed: list_datasets orders by `created_at desc`. Without an index
    # the planner does a full sort over every row.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Pipeline(Base):
    """Defined here so the schema is forward-compatible."""

    __tablename__ = "pipelines"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    document: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    etag: Mapped[int] = mapped_column(Integer, default=1)
    # Identity + audit columns — always NULL in single-user deployments.
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    extensions: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # Indexed: list_pipelines orders by `updated_at desc`. Without an index
    # the planner does a full sort over every row.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, index=True,
    )


class PipelineHistory(Base):
    """Snapshot of a pipeline document at a particular point in time.

    Written on every save (deduped by document hash), on run start (so a run's
    pipeline is locked-in even if the editor is mutated mid-run), and on
    import. Powers the visual pipeline-diff feature.

    Retention: keep DIG_PIPELINE_HISTORY_MAX (default 50) most-recent rows per
    pipeline; older ones expire on next save.
    """

    __tablename__ = "pipeline_history"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(String(26), index=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSON)
    etag: Mapped[int] = mapped_column(Integer)
    # Auto-generated 1-line ("added 2 steps, removed 1, changed 3 params").
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-text reason from the user, optional.
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "manual_save" | "run_start" | "import" | "ai_review_apply" | "restore"
    triggered_by: Mapped[str] = mapped_column(String(32), default="manual_save")
    # SHA-256 of the canonical-JSON document. Lets us dedupe consecutive saves
    # that don't actually change anything (e.g. opening a pipeline and saving
    # without edits).
    document_hash: Mapped[str] = mapped_column(String(64), index=True)
    # When this snapshot was taken at run-start, the corresponding Run.id —
    # so the diff endpoint can resolve `run:<run_id>` refs without searching
    # for a needle that was never threaded into the document.
    run_id: Mapped[str | None] = mapped_column(String(26), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class Run(Base):
    """A single backend execution of a pipeline over the full dataset."""

    __tablename__ = "runs"

    # Composite index for the latest-run-per-pipeline window
    # (row_number() OVER (PARTITION BY pipeline_id ORDER BY created_at DESC))
    # used by catalog.get_catalog_lineage and pipelines.list_pipelines. The
    # two single-column indexes below can't serve this ordering, forcing a
    # per-partition sort; (pipeline_id, created_at DESC) matches it directly.
    __table_args__ = (
        Index("ix_runs_pipeline_created", "pipeline_id", text("created_at DESC")),
    )

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    # Indexed: list_runs filters by pipeline_id; without it every page-load
    # scans the full runs table.
    pipeline_id: Mapped[str] = mapped_column(String(26), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[float] = mapped_column(default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_paths: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # Free-form per-output artifacts (file/db/image/sink dicts) — populated by
    # the executor when Polars-engine terminal steps produce side effects.
    artifacts: Mapped[dict[str, list[dict[str, Any]]] | None] = mapped_column(JSON, nullable=True)
    # Per-node execution metrics — populated by the executor when each node
    # runs. Shape: { node_id: { rows_in?: int, rows_out?: int, elapsed_ms?: int,
    # status?: "success"|"failed"|"skipped" } }. Drives the canvas run-state
    # overlay. Optional fields because not every engine path
    # gives us cheap row counts.
    node_metrics: Mapped[dict[str, dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # Per-node NaN-origin sidecars — populated by the executor's post-step
    # scanner (Polars steps) and by the cast_type SQL hook. Shape:
    # { node_id: [ {column, row_indices, cause, source_column?, count, truncated}, … ] }.
    # Surfaces in the grid as the orange-⚠ NULL variant on cells that became
    # NULL via a conversion / computation failure on THIS step. Lives on the
    # producing step only — the next step sees plain NULL.
    nan_origins: Mapped[dict[str, list[dict[str, Any]]] | None] = mapped_column(JSON, nullable=True)
    # Identity + cost columns — always NULL in single-user deployments.
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    org_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bytes_scanned: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compute_seconds: Mapped[float | None] = mapped_column(nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    extra_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    extensions: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Indexed: list_runs orders by `created_at desc`. The composite
    # ix_runs_pipeline_created (pipeline_id, created_at DESC) above serves
    # the latest-run-per-pipeline window; this single-column index serves
    # the cross-pipeline ORDER BY created_at DESC list query.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )


# ---- Notifications --------------------------------------------------------
#
# Persistent log of system + runtime events: pipeline failures, freshness
# breaches, login attempts (when auth is wired), resource warnings (disk
# space, OOM), etc. Surfaced in the /settings page's Notifications panel
# and queried by future delivery channels (email, syslog, webhooks).
#
# Design notes:
#   - Append-only from the producer side; the user dismisses individual
#     rows or the whole panel. We don't auto-prune; periodic VACUUM is
#     a future cron job.
#   - `kind` is a free-form string but constrained at the API surface to
#     a known vocabulary so the UI's filter dropdown stays meaningful.
#   - `level` mirrors syslog severity in spirit but smaller: notification,
#     warning, error. (No "critical" — anything that critical should
#     have already paged via webhook.)
#   - `context` holds whatever the producer wants to attach: pipeline_id,
#     run_id, node_id, error fingerprint, stack trace location, etc.
#     Lets us evolve display without changing the schema.


class NotificationRule(Base):
    """User-configured rule that converts events into notifications.

    Events are always emitted by producers (see dig/api/events.py).
    Rules are the OPT-IN layer that filters events, applies a template,
    and produces a notification (or, in the future, dispatches to email
    / Slack / webhook).

    Separates "what happened" from "who cares about it".
    """

    __tablename__ = "notification_rules"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Event-kind matcher. Exact ("run.failed") or wildcard ("run.*", "*").
    # Indexed because the rule engine looks up rules by event_kind
    # prefix on every emit.
    event_kind: Mapped[str] = mapped_column(String(64), index=True)

    # Optional context filters — JSON dict. Keys: pipeline_id, group_id,
    # node_id, error_type, level, etc. The matcher does an exact-match
    # on each present key. Empty dict = no extra filtering (rule fires
    # on every matching event).
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Action — what to do when the rule fires. JSON because we expect
    # this to evolve with channels (email/slack):
    #   { level: "error" | "warning" | "notification" | "auto",
    #     title: "{pipeline_name} run failed",     # template
    #     message: "{error_type}: {error}",        # template
    #     channel: "in_app" }
    action: Mapped[dict[str, Any]] = mapped_column(JSON)

    # Cooldown: don't fire the same rule on the same target more than
    # once per N seconds. None = no cooldown. The matcher keys cooldowns
    # on (rule_id, primary target — pipeline_id or node_id or group_id).
    cooldown_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    # Counter for the rules-list UI so the user can tell "this rule has
    # actually fired N times" vs "this rule never matches".
    fire_count: Mapped[int] = mapped_column(Integer, default=0)

    # Built-in rules ship with the install and aren't user-deletable.
    # They CAN be disabled or have their templates customised.
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )


class Notification(Base):
    """One notification / alert event in the system."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    # Indexed for the default ORDER BY created_at DESC list query.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )
    # "system" | "runtime" | "login" | "resources" | "freshness" | …
    kind: Mapped[str] = mapped_column(String(32), index=True)
    # "notification" | "warning" | "error"
    level: Mapped[str] = mapped_column(String(16), index=True, default="notification")
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Reserved for when auth lands. Indexed because per-user filtering is
    # the obvious future query shape.
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Free-form attachment dict — pipeline_id, run_id, node_id, etc.
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Soft-dismiss flag: the row stays for audit but the user has cleared
    # it from their default view. Hard-delete is a separate endpoint.
    dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


# ---- Server-side settings ---------------------------------------
#
# Three new tables back the /settings UI. Kept narrow on purpose — these are
# the things a user genuinely wants to change at runtime without restarting
# the API server. Anything tied to startup (ports, bind host, auth token) is
# still env-var driven and surfaced read-only in the UI.


class Setting(Base):
    """Free-form key/value store for server-side preferences.

    Used for things like preview/sample defaults, run concurrency hints,
    input/output dir overrides, etc. The schema stays tiny because the
    set of meaningful settings drifts faster than DB migrations should.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class JdbcDriver(Base):
    """User-managed inventory of JDBC drivers.

    Lets the user set up "Oracle 19c", "Snowflake", "Sybase ASE" once and
    then reference them by name from any pipeline that uses the `jdbc`
    connector or `export_to_jdbc` step — instead of pasting the driver
    class + JAR path every time.
    """

    __tablename__ = "jdbc_drivers"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    driver_class: Mapped[str] = mapped_column(String(255))
    jar_path: Mapped[str] = mapped_column(Text)
    # Optional: a URL template the UI can pre-fill — e.g.
    # "jdbc:oracle:thin:@//<host>:1521/<service>".
    url_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Template(Base):
    """User-owned shareable pipeline templates.

    Distinct from the bundled `samples/templates/*.json` repo files (those
    ship with DIG and never change at runtime). Templates here are pipelines
    a user marked as shareable + a sample dataset URL, with a stable slug
    that powers the public template-gallery feature.

    Visibility semantics:
      - "private"   — visible only to the user; not surfaced in /gallery.
      - "unlisted"  — anyone with the link can open; not in /gallery search.
      - "public"    — surfaced in /gallery search results.

    `is_curated` is reserved for the official curated set (highlighted on
    the gallery landing page); user-published templates start curated=false.
    """

    __tablename__ = "templates"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    document: Mapped[dict[str, Any]] = mapped_column(JSON)
    sample_dataset_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_sample_dataset: Mapped[bool] = mapped_column(Boolean, default=False)
    author_handle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    author_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_curated: Mapped[bool] = mapped_column(Boolean, default=False)
    visibility: Mapped[str] = mapped_column(String(16), default="unlisted")
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class StepPack(Base):
    """Installed step-pack registry.

    Tracks which packs are present on disk under `<repo>/plugins/packs/<id>/`,
    their installed version, integrity checksum, and the cached pack.json
    manifest. Disk state is the source of truth for *content*; this table
    is the source of truth for *enabled-ness* and the install metadata.

    The `enabled` flag lets the operator soft-disable a pack without
    physically removing it — useful when troubleshooting "is this pack
    causing my preview error?". A disabled pack's directory remains on
    disk but its steps are not registered with the StepRegistry.
    """

    __tablename__ = "step_packs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[str] = mapped_column(String(32))
    checksum: Mapped[str | None] = mapped_column(String(80), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cached at install time so the Settings list renders without a disk
    # read per row. Refreshed when the pack is updated.
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow,
    )


class GlobalWebhook(Base):
    """Webhooks that fire for *every* run (not just one pipeline's runs).

    Per-pipeline webhooks already live on `Pipeline.webhooks`. These global
    ones are useful for catch-all integrations: a single Slack channel that
    pings on any pipeline failure, an audit log endpoint, etc.
    """

    __tablename__ = "global_webhooks"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    # Free-form string so vendors / enterprise builds can introduce new
    # triggers without a schemaVersion bump (matches Pipeline.Webhook.on).
    # Built-in values: always | succeeded | failed | triggered.
    on: Mapped[str] = mapped_column(String(16), default="always")
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    headers: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
