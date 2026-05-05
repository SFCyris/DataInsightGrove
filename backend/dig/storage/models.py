from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from dig.storage.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Pipeline(Base):
    """Phase 2+. Defined here so the schema is forward-compatible."""

    __tablename__ = "pipelines"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    document: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    etag: Mapped[int] = mapped_column(Integer, default=1)
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
    """Phase 2+."""

    __tablename__ = "runs"

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
    # Indexed: list_runs orders by `created_at desc`. Composite with
    # pipeline_id would be ideal but two single-column indexes are
    # cheap enough on this workload.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True,
    )


# ---- Server-side settings (Phase 6) ---------------------------------------
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
    on: Mapped[str] = mapped_column(String(16), default="always")  # always | succeeded | failed
    secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    headers: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
