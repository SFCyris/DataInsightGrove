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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Run(Base):
    """Phase 2+."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    pipeline_id: Mapped[str] = mapped_column(String(26))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[float] = mapped_column(default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_paths: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # Free-form per-output artifacts (file/db/image/sink dicts) — populated by
    # the executor when Polars-engine terminal steps produce side effects.
    artifacts: Mapped[dict[str, list[dict[str, Any]]] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


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
