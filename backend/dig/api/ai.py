"""AI assistant API.

Three endpoints today:

  GET  /ai/config     read the current resolved AI config (api_key masked)
  POST /ai/probe      send a tiny "ping" to verify the configured provider
                      is reachable + the model exists. Powers the
                      "Test connection" button in Settings → AI.
  POST /ai/chat       generic OpenAI-compat chat-completion proxy. Used
                      by the explain / fix / generate features so the
                      frontend never holds the API key.

Future endpoints layered on top of /ai/chat live in the feature files
(dig/ai/features/*.py) and are wired into pipelines + the column menu.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dig.ai.client import AiError, chat as client_chat, list_models as client_list_models, probe as client_probe
from dig.ai.config import load_config
from dig.ai.features.explain import explain_pipeline
from dig.ai.features.review import review_pipeline
from dig.ai.features.fix_expression import fix_expression
from dig.ai.features.generate_connector import (
    _pending_dir as _pending_connector_dir,
    discard_pending as discard_pending_connector,
    generate_connector,
    install_pending as install_pending_connector,
    probe_url,
    stage_pending as stage_pending_connector,
)
from dig.ai.features.generate_step import (
    _pending_step_dir,
    discard_pending_step,
    generate_step,
    install_pending_step,
    stage_pending_step,
)
from dig.ai.safety import lint_plugin_python
from dig.ai.features.suggest_next import suggest_next_step
from pathlib import Path as _Path
from dig.engine.registry import steps as steps_registry
from dig.storage.db import get_session
from dig.storage.models import Pipeline as PipelineRow
from sqlalchemy import select as sa_select

log = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


# ---- Schemas --------------------------------------------------------------


class AiConfigOut(BaseModel):
    """Resolved AI config for display. api_key is masked."""
    enabled: bool
    provider: str
    endpoint: str
    model: str
    has_api_key: bool
    max_tokens: int
    temperature: float


class ProbeOut(BaseModel):
    ok: bool
    error: str | None = None
    model: str | None = None
    reply: str | None = None


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    response_format: str | None = Field(
        default=None,
        description="Pass 'json_object' to request structured JSON output.",
    )
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=131072)


class ChatResponse(BaseModel):
    text: str
    model: str
    usage: dict[str, int] | None = None


class ExplainOut(BaseModel):
    markdown: str
    model: str


class ReviewFinding(BaseModel):
    severity: str  # "info" | "warn" | "high"
    category: str  # "performance" | "correctness" | "quality" | "lineage" | "ergonomics"
    title: str
    explanation: str
    affected_nodes: list[str]
    confidence: float


class ReviewOut(BaseModel):
    findings: list[ReviewFinding]
    model: str
    rawText: str | None = None


class FixExpressionIn(BaseModel):
    expression: str
    columns: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of {name, type} for the expression's available columns.",
    )
    intent: str | None = Field(
        default=None,
        description="Optional plain-English description of what the user wants the expression to do.",
    )
    error: str | None = Field(
        default=None,
        description="Optional DuckDB error message from a failed validation.",
    )
    kind: str = Field(
        default="predicate",
        description="'predicate' (filter_rows) or 'scalar' (derive_column) — affects expected result type.",
    )


class FixExpressionOut(BaseModel):
    fixed: str
    explanation: str
    confidence: str
    model: str


class ProbeUrlIn(BaseModel):
    url: str
    auth_header: str | None = None


class GenerateConnectorIn(BaseModel):
    url: str
    intent: str | None = None
    sample_shape: dict[str, Any] | None = None
    auth_kind: str = Field(default="none", pattern="^(none|bearer|api_key_query|basic)$")


class GeneratedConnectorOut(BaseModel):
    id: str
    label: str | None = None
    description: str | None = None
    manifest: dict[str, Any]
    connector_py: str
    lint_issues: list[dict[str, Any]]
    model: str
    pending_path: str
    safe_to_install: bool


class InstallConnectorIn(BaseModel):
    connector_id: str


class SuggestNextIn(BaseModel):
    pipeline_id: str
    focused_node_id: str | None = Field(
        default=None,
        description="Node id whose schema is used as the 'currently visible' state. None = no focus, suggestions are about adding a first transform after the dataset.",
    )
    focused_schema: dict[str, str] = Field(
        default_factory=dict,
        description="Map of column-name → logical-type at the focused node.",
    )
    goal: str = Field(min_length=1, max_length=500)


class SuggestNextOut(BaseModel):
    suggestions: list[dict[str, Any]]
    model: str


class GenerateStepIn(BaseModel):
    description: str = Field(min_length=1, max_length=2000)
    schema_hint: dict[str, str] = Field(default_factory=dict)


class GeneratedStepOut(BaseModel):
    id: str
    label: str | None = None
    description: str | None = None
    manifest: dict[str, Any]
    step_py: str
    lint_issues: list[dict[str, Any]]
    model: str
    pending_path: str
    safe_to_install: bool


class InstallStepIn(BaseModel):
    step_id: str


# Repository root — same convention used elsewhere in the backend.
_REPO_ROOT = _Path(__file__).resolve().parents[3]


# ---- Endpoints ------------------------------------------------------------


@router.get("/config", response_model=AiConfigOut)
async def get_config(session: AsyncSession = Depends(get_session)) -> AiConfigOut:
    """Read the resolved AI config — api_key is masked."""
    cfg = await load_config(session)
    return AiConfigOut(
        enabled=cfg.enabled,
        provider=cfg.provider,
        endpoint=cfg.endpoint,
        model=cfg.model,
        has_api_key=bool(cfg.api_key),
        max_tokens=cfg.max_tokens,
        temperature=cfg.temperature,
    )


class ModelsOut(BaseModel):
    models: list[str]
    endpoint: str


@router.get("/models", response_model=ModelsOut)
async def list_models_endpoint(session: AsyncSession = Depends(get_session)) -> ModelsOut:
    """List the models available at the configured endpoint.

    Calls GET {endpoint}/models on the configured provider. Always returns
    200 with possibly-empty `models` — the frontend uses an empty list as
    "couldn't fetch, fall back to free-text input". Never raises so the
    settings page can poll silently.
    """
    cfg = await load_config(session)
    models = await client_list_models(cfg)
    return ModelsOut(models=models, endpoint=cfg.endpoint)


@router.post("/probe", response_model=ProbeOut)
async def probe_provider(session: AsyncSession = Depends(get_session)) -> ProbeOut:
    """Ping the configured AI provider. Powers the "Test connection" button.

    Always returns 200 — failures land in the response body so the UI
    can show a friendly error without parsing HTTP statuses.
    """
    cfg = await load_config(session)
    result = await client_probe(cfg)
    return ProbeOut(**result)


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    """Generic chat-completions proxy. The frontend never holds the API
    key — every LLM call routes through this endpoint."""
    cfg = await load_config(session)
    if not cfg.enabled:
        raise HTTPException(400, "AI is disabled — enable it in Settings → AI")

    try:
        resp = await client_chat(
            cfg,
            messages=[m.model_dump() for m in body.messages],
            response_format=body.response_format,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
    except AiError as e:
        # 502 because we proxied successfully but the upstream provider
        # failed. The UI surfaces the error message verbatim.
        raise HTTPException(502, str(e)) from e

    return ChatResponse(text=resp.text, model=resp.model, usage=resp.usage)


@router.post("/explain-pipeline/{pipeline_id}", response_model=ExplainOut)
async def explain(
    pipeline_id: str,
    session: AsyncSession = Depends(get_session),
) -> ExplainOut:
    """Generate a Markdown explanation of a saved pipeline. Reads the
    pipeline doc + the live step manifest catalog, asks the LLM."""
    cfg = await load_config(session)
    if not cfg.enabled:
        raise HTTPException(400, "AI is disabled — enable it in Settings → AI")

    row = (await session.execute(
        sa_select(PipelineRow).where(PipelineRow.id == pipeline_id),
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"pipeline {pipeline_id!r} not found")

    doc = row.document or {}
    catalog = [s.manifest for s in steps_registry().all()]

    try:
        markdown = await explain_pipeline(cfg, doc, catalog)
    except AiError as e:
        raise HTTPException(502, str(e)) from e
    return ExplainOut(markdown=markdown, model=cfg.model)


@router.post("/review-pipeline/{pipeline_id}", response_model=ReviewOut)
async def review(
    pipeline_id: str,
    session: AsyncSession = Depends(get_session),
) -> ReviewOut:
    """Severity-ranked findings for a saved pipeline.

    Reviews ordering, type mismatches, missing expectations, lineage
    opportunities, and ergonomics. Returns typed JSON; the frontend
    renders each finding as an actionable card.
    """
    cfg = await load_config(session)
    if not cfg.enabled:
        raise HTTPException(400, "AI is disabled — enable it in Settings → AI")

    row = (await session.execute(
        sa_select(PipelineRow).where(PipelineRow.id == pipeline_id),
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"pipeline {pipeline_id!r} not found")

    doc = row.document or {}
    catalog = [s.manifest for s in steps_registry().all()]

    # Gather column profiles for each dataset referenced by the pipeline.
    # Single IN-clause query — the previous form did one round-trip per
    # dataset which was an obvious N+1 (a 12-dataset pipeline → 13 SQLite
    # round-trips for one review request).
    from dig.storage.models import Dataset as DatasetRow

    ds_ids = [
        ds.get("id")
        for ds in (doc.get("datasets") or [])
        if ds.get("id")
    ]
    profiles: dict[str, Any] = {}
    if ds_ids:
        rows = (
            await session.execute(
                sa_select(DatasetRow).where(DatasetRow.id.in_(ds_ids))
            )
        ).scalars().all()
        for ds_row in rows:
            if ds_row.profile:
                profiles[ds_row.id] = ds_row.profile

    try:
        result = await review_pipeline(cfg, doc, catalog, profiles or None)
    except AiError as e:
        raise HTTPException(502, str(e)) from e

    return ReviewOut(
        findings=[ReviewFinding(**f) for f in result["findings"]],
        model=result["model"],
        rawText=result.get("rawText"),
    )


@router.post("/fix-expression", response_model=FixExpressionOut)
async def fix_expression_endpoint(
    body: FixExpressionIn,
    session: AsyncSession = Depends(get_session),
) -> FixExpressionOut:
    """Suggest a corrected SQL expression."""
    cfg = await load_config(session)
    if not cfg.enabled:
        raise HTTPException(400, "AI is disabled — enable it in Settings → AI")

    try:
        result = await fix_expression(
            cfg,
            expression=body.expression,
            columns=body.columns,
            intent=body.intent,
            error=body.error,
            kind=body.kind,
        )
    except AiError as e:
        raise HTTPException(502, str(e)) from e

    return FixExpressionOut(
        fixed=result["fixed"],
        explanation=result["explanation"],
        confidence=result["confidence"],
        model=cfg.model,
    )


@router.post("/probe-url")
async def probe_endpoint(body: ProbeUrlIn) -> dict[str, Any]:
    """Fetch a URL once and return its shape — status, content-type, JSON
    structure preview. Used by the Generate Connector wizard so the user
    can verify their URL works before committing AI tokens to generating
    a connector around it."""
    return await probe_url(body.url, auth_header=body.auth_header)


@router.post("/generate-connector", response_model=GeneratedConnectorOut)
async def generate_connector_endpoint(
    body: GenerateConnectorIn,
    session: AsyncSession = Depends(get_session),
) -> GeneratedConnectorOut:
    """Ask the LLM to generate a connector folder, run the safety lint,
    stage the result in plugins/_pending/. Returns the generated content
    + lint findings; the user reviews and explicitly installs."""
    cfg = await load_config(session)
    if not cfg.enabled:
        raise HTTPException(400, "AI is disabled — enable it in Settings → AI")

    try:
        gen = await generate_connector(
            cfg,
            url=body.url,
            intent=body.intent,
            sample_shape=body.sample_shape,
            auth_kind=body.auth_kind,
        )
    except AiError as e:
        raise HTTPException(502, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    safe = len(gen["lint_issues"]) == 0
    try:
        pending_path = stage_pending_connector(_REPO_ROOT, gen)
    except ValueError as e:
        raise HTTPException(400, f"Generated connector rejected: {e}") from e

    return GeneratedConnectorOut(
        id=gen["id"],
        label=gen.get("label"),
        description=gen.get("description"),
        manifest=gen["manifest"],
        connector_py=gen["connector_py"],
        lint_issues=gen["lint_issues"],
        model=gen["model"],
        pending_path=str(pending_path),
        safe_to_install=safe,
    )


@router.post("/install-connector")
async def install_connector_endpoint(body: InstallConnectorIn) -> dict[str, Any]:
    """Move a staged connector from plugins/_pending/connectors/<id>/ to
    the live plugins/connectors/ directory. The connector becomes
    available on the next registry refresh (next API restart, OR if
    the registry exposes a hot-reload, immediately).

    Server-side re-lints the staged code before promoting; the frontend
    `safe_to_install` flag is advisory and a direct API call would
    otherwise bypass the gate, leading to RCE on next registry scan.
    """
    try:
        pending_dir = _pending_connector_dir(_REPO_ROOT, body.connector_id)
        py_path = pending_dir / "connector.py"
        if not py_path.exists():
            raise HTTPException(404, f"pending connector {body.connector_id!r} not found")
        issues = lint_plugin_python(py_path.read_text())
        if issues:
            raise HTTPException(
                400,
                {
                    "error": "lint_failed",
                    "message": "Refusing to install — staged code has lint issues.",
                    "issues": [
                        {"line": i.line, "col": i.col, "rule": i.rule, "message": i.message}
                        for i in issues
                    ],
                },
            )
        path = install_pending_connector(_REPO_ROOT, body.connector_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except FileExistsError as e:
        raise HTTPException(409, str(e)) from e
    return {
        "ok": True,
        "installed_at": str(path),
        "note": "Restart the backend (or hot-reload registry) to pick up the new connector.",
    }


@router.delete("/pending-connector/{connector_id}")
async def discard_connector_endpoint(connector_id: str) -> dict[str, Any]:
    """Delete a staged connector without installing it."""
    try:
        discard_pending_connector(_REPO_ROOT, connector_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "discarded": connector_id}


@router.post("/suggest-next-step", response_model=SuggestNextOut)
async def suggest_next_endpoint(
    body: SuggestNextIn,
    session: AsyncSession = Depends(get_session),
) -> SuggestNextOut:
    """Suggest the next step(s) to add to a pipeline given a goal."""
    cfg = await load_config(session)
    if not cfg.enabled:
        raise HTTPException(400, "AI is disabled — enable it in Settings → AI")

    row = (await session.execute(
        sa_select(PipelineRow).where(PipelineRow.id == body.pipeline_id),
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"pipeline {body.pipeline_id!r} not found")

    catalog = [s.manifest for s in steps_registry().all()]

    try:
        result = await suggest_next_step(
            cfg,
            pipeline_doc=row.document or {},
            focused_schema=body.focused_schema,
            goal=body.goal,
            step_catalog=catalog,
        )
    except AiError as e:
        raise HTTPException(502, str(e)) from e

    return SuggestNextOut(suggestions=result["suggestions"], model=result["model"])


@router.post("/generate-step", response_model=GeneratedStepOut)
async def generate_step_endpoint(
    body: GenerateStepIn,
    session: AsyncSession = Depends(get_session),
) -> GeneratedStepOut:
    """Ask the LLM to generate a step plugin folder, lint it, stage it
    in plugins/_pending/steps/. The user reviews + explicitly installs."""
    cfg = await load_config(session)
    if not cfg.enabled:
        raise HTTPException(400, "AI is disabled — enable it in Settings → AI")

    try:
        gen = await generate_step(
            cfg,
            description=body.description,
            schema_hint=body.schema_hint or None,
        )
    except AiError as e:
        raise HTTPException(502, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    safe = len(gen["lint_issues"]) == 0
    try:
        pending_path = stage_pending_step(_REPO_ROOT, gen)
    except ValueError as e:
        raise HTTPException(400, f"Generated step rejected: {e}") from e

    return GeneratedStepOut(
        id=gen["id"],
        label=gen.get("label"),
        description=gen.get("description"),
        manifest=gen["manifest"],
        step_py=gen["step_py"],
        lint_issues=gen["lint_issues"],
        model=gen["model"],
        pending_path=str(pending_path),
        safe_to_install=safe,
    )


@router.post("/install-step")
async def install_step_endpoint(body: InstallStepIn) -> dict[str, Any]:
    """Move plugins/_pending/steps/<id>/ → plugins/steps/<id>/.

    Server-side re-lints the staged code before promoting (same reason
    as install-connector — the frontend `safe_to_install` flag can be
    bypassed by a direct API call).
    """
    try:
        pending_dir = _pending_step_dir(_REPO_ROOT, body.step_id)
        py_path = pending_dir / "step.py"
        if not py_path.exists():
            raise HTTPException(404, f"pending step {body.step_id!r} not found")
        issues = lint_plugin_python(py_path.read_text())
        if issues:
            raise HTTPException(
                400,
                {
                    "error": "lint_failed",
                    "message": "Refusing to install — staged code has lint issues.",
                    "issues": [
                        {"line": i.line, "col": i.col, "rule": i.rule, "message": i.message}
                        for i in issues
                    ],
                },
            )
        path = install_pending_step(_REPO_ROOT, body.step_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except FileExistsError as e:
        raise HTTPException(409, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {
        "ok": True,
        "installed_at": str(path),
        "note": "Restart the backend to register the new step in the registry.",
    }


@router.delete("/pending-step/{step_id}")
async def discard_step_endpoint(step_id: str) -> dict[str, Any]:
    """Delete a staged step without installing."""
    try:
        discard_pending_step(_REPO_ROOT, step_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "discarded": step_id}
