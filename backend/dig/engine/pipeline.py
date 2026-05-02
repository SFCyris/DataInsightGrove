"""Pipeline document — Pydantic models mirroring shared/schemas/pipeline.schema.json.

These models drive validation on save and run-time DAG analysis. The JSON schema
remains authoritative for cross-language consumers (the frontend's typed
client); these models add Python ergonomics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class NodeUI(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float | None = None
    y: float | None = None
    label: str | None = None


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    step: str
    stepVersion: str
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
    on: Literal["always", "succeeded", "failed", "triggered"] = "always"
    secret: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    label: str | None = None


class Pipeline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1] = 1
    id: str
    name: str
    description: str | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    datasets: list[DatasetSpec] = Field(default_factory=list)
    nodes: list[Node] = Field(default_factory=list)
    outputs: list[OutputSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhooks: list[Webhook] = Field(default_factory=list)
