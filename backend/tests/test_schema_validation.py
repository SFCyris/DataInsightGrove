"""Tests for the pre-1.0 schema lockdown.

Covers the forward-compatibility surfaces that protect users from
breaking changes when the Enterprise tier ships:

  - Opened enums (`engine.primary`, `webhook.on`, `step.category`) accept
    both the original closed set + arbitrary new values.
  - Relaxed ID regex (`^[a-z0-9][a-z0-9_:-]*$`) accepts hyphens + colons
    for enterprise namespacing while remaining backwards-compatible
    with the original `^[a-z][a-z0-9_]*$` IDs.
  - `metadata` + `extensions` slots round-trip on pipeline / step /
    pack / connector manifests without rejection.
  - Pydantic Pipeline model still rejects truly bad input
    (`additionalProperties: false` at top level, schemaVersion mismatch).
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from ulid import ULID

from dig.engine.pipeline import (
    DatasetSpec,
    Node,
    OutputSpec,
    Pipeline,
    Reference,
    Webhook,
)

REPO_ROOT = Path(__file__).parent.parent.parent
SCHEMAS = REPO_ROOT / "shared" / "schemas"


@pytest.fixture(scope="module")
def pipeline_schema() -> dict:
    return json.loads((SCHEMAS / "pipeline.schema.json").read_text())


@pytest.fixture(scope="module")
def step_manifest_schema() -> dict:
    return json.loads((SCHEMAS / "step-manifest.schema.json").read_text())


@pytest.fixture(scope="module")
def pack_manifest_schema() -> dict:
    return json.loads((SCHEMAS / "pack-manifest.schema.json").read_text())


@pytest.fixture(scope="module")
def connector_manifest_schema() -> dict:
    return json.loads((SCHEMAS / "connector-manifest.schema.json").read_text())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_pipeline_doc(**overrides) -> dict:
    base = {
        "schemaVersion": 1,
        "id": "01TESTPIPELINEULID00000000",
        "name": "test",
        "datasets": [],
        "nodes": [],
        "outputs": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Opened enums — engine.primary, webhook.on, step.category
# ---------------------------------------------------------------------------


class TestOpenedEnums:
    def test_engine_primary_accepts_known_values(self, step_manifest_schema):
        for engine in ("sql", "polars", "python"):
            doc = {
                "id": "x", "version": "1.0.0", "label": "x", "category": "derive",
                "engine": {"primary": engine},
                "io": {"inputs": {"min": 1, "max": 1}, "outputs": {"min": 1, "max": 1}},
                "params": {},
            }
            jsonschema.validate(doc, step_manifest_schema)

    def test_engine_primary_accepts_new_backend(self, step_manifest_schema):
        # Future enterprise backends should validate without a schema bump.
        for engine in ("spark", "dask", "snowflake_pushdown", "bigquery_pushdown"):
            doc = {
                "id": "x", "version": "1.0.0", "label": "x", "category": "derive",
                "engine": {"primary": engine},
                "io": {"inputs": {"min": 1, "max": 1}, "outputs": {"min": 1, "max": 1}},
                "params": {},
            }
            jsonschema.validate(doc, step_manifest_schema)

    def test_engine_primary_rejects_uppercase(self, step_manifest_schema):
        # Pattern still enforces lowercase snake_case to prevent typos /
        # accidental drift.
        doc = {
            "id": "x", "version": "1.0.0", "label": "x", "category": "derive",
            "engine": {"primary": "SQL"},
            "io": {"inputs": {"min": 1, "max": 1}, "outputs": {"min": 1, "max": 1}},
            "params": {},
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(doc, step_manifest_schema)

    def test_webhook_on_accepts_known_values(self, pipeline_schema):
        for trigger in ("always", "succeeded", "failed", "triggered"):
            doc = _minimal_pipeline_doc(
                webhooks=[{"url": "https://x.example.com", "on": trigger}]
            )
            jsonschema.validate(doc, pipeline_schema)

    def test_webhook_on_accepts_new_trigger(self, pipeline_schema):
        for trigger in ("partial_success", "data_quality_failed", "rate_limited"):
            doc = _minimal_pipeline_doc(
                webhooks=[{"url": "https://x.example.com", "on": trigger}]
            )
            jsonschema.validate(doc, pipeline_schema)

    def test_pydantic_webhook_accepts_new_trigger(self):
        # The Pydantic Webhook model mirrors the schema — used to be a
        # closed Literal, must now accept arbitrary strings.
        w = Webhook(url="https://x.example.com", on="partial_success")
        assert w.on == "partial_success"

    def test_step_category_accepts_known_values(self, step_manifest_schema):
        known = ["ingest", "shape", "clean", "derive", "combine", "aggregate",
                 "analyze", "model", "validate", "visualize", "output", "custom"]
        for cat in known:
            doc = {
                "id": "x", "version": "1.0.0", "label": "x", "category": cat,
                "engine": {"primary": "sql"},
                "io": {"inputs": {"min": 1, "max": 1}, "outputs": {"min": 1, "max": 1}},
                "params": {},
            }
            jsonschema.validate(doc, step_manifest_schema)

    def test_step_category_accepts_new_category(self, step_manifest_schema):
        for cat in ("observability", "cost_optimization", "data_governance"):
            doc = {
                "id": "x", "version": "1.0.0", "label": "x", "category": cat,
                "engine": {"primary": "sql"},
                "io": {"inputs": {"min": 1, "max": 1}, "outputs": {"min": 1, "max": 1}},
                "params": {},
            }
            jsonschema.validate(doc, step_manifest_schema)


# ---------------------------------------------------------------------------
# Relaxed ID regex — dataset + node IDs
# ---------------------------------------------------------------------------


class TestRelaxedIds:
    def test_original_id_shape_still_valid(self, pipeline_schema):
        # The classic `^[a-z][a-z0-9_]*$` shape must continue to work.
        doc = _minimal_pipeline_doc(
            datasets=[{"id": "customers", "connector": "csv", "uri": "file:///x.csv"}]
        )
        jsonschema.validate(doc, pipeline_schema)

    def test_hyphenated_id_valid(self, pipeline_schema):
        doc = _minimal_pipeline_doc(
            datasets=[{"id": "customer-orders", "connector": "csv", "uri": "file:///x.csv"}]
        )
        jsonschema.validate(doc, pipeline_schema)

    def test_colon_namespaced_id_valid(self, pipeline_schema):
        # The enterprise namespacing use case.
        doc = _minimal_pipeline_doc(
            datasets=[{"id": "org_42:customers", "connector": "csv", "uri": "file:///x.csv"}]
        )
        jsonschema.validate(doc, pipeline_schema)

    def test_leading_digit_id_valid(self, pipeline_schema):
        # The new regex starts `^[a-z0-9]` (was `^[a-z]`), so an ID
        # starting with a digit is now accepted.
        doc = _minimal_pipeline_doc(
            datasets=[{"id": "2026_orders", "connector": "csv", "uri": "file:///x.csv"}]
        )
        jsonschema.validate(doc, pipeline_schema)

    def test_uppercase_id_rejected(self, pipeline_schema):
        # Lowercase-only stays enforced.
        doc = _minimal_pipeline_doc(
            datasets=[{"id": "Customers", "connector": "csv", "uri": "file:///x.csv"}]
        )
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(doc, pipeline_schema)

    def test_pydantic_accepts_namespaced_id(self):
        # Pydantic Pipeline model also accepts the new shape.
        p = Pipeline(
            id=str(ULID()),
            name="t",
            datasets=[DatasetSpec(id="org_42:customers", connector="csv", uri="file:///x.csv")],
        )
        assert p.datasets[0].id == "org_42:customers"


# ---------------------------------------------------------------------------
# Extensions + metadata slots
# ---------------------------------------------------------------------------


class TestExtensionsSlot:
    def test_pipeline_extensions_roundtrip(self, pipeline_schema):
        doc = _minimal_pipeline_doc(
            extensions={
                "acme": {"costCenter": "data-platform", "approved": True},
                "openlineage": {"facets": {"x": "y"}},
            },
        )
        jsonschema.validate(doc, pipeline_schema)

    def test_pipeline_metadata_roundtrip(self, pipeline_schema):
        doc = _minimal_pipeline_doc(
            metadata={"engineHints": {"prefer": "polars"}, "variables": {"region": "us-east-1"}},
        )
        jsonschema.validate(doc, pipeline_schema)

    def test_step_manifest_extensions_roundtrip(self, step_manifest_schema):
        doc = {
            "id": "x", "version": "1.0.0", "label": "x", "category": "derive",
            "engine": {"primary": "sql"},
            "io": {"inputs": {"min": 1, "max": 1}, "outputs": {"min": 1, "max": 1}},
            "params": {},
            "metadata": {"author_email": "team@example.com"},
            "extensions": {"acme": {"premium": True}},
        }
        jsonschema.validate(doc, step_manifest_schema)

    def test_pack_manifest_extensions_roundtrip(self, pack_manifest_schema):
        doc = {
            "id": "xy", "version": "1.0.0", "label": "x", "description": "x",
            "extensions": {"acme": {"premiumTier": "gold"}},
        }
        jsonschema.validate(doc, pack_manifest_schema)

    def test_connector_manifest_extensions_roundtrip(self, connector_manifest_schema):
        doc = {
            "id": "x", "version": "1.0.0", "label": "x",
            "kind": "source", "options": {},
            "extensions": {"acme": {"sla_seconds": 300}},
        }
        jsonschema.validate(doc, connector_manifest_schema)

    def test_pydantic_pipeline_extensions_default_empty(self):
        p = Pipeline(id=str(ULID()), name="t")
        assert p.extensions == {}

    def test_pydantic_pipeline_extensions_populated(self):
        p = Pipeline(
            id=str(ULID()),
            name="t",
            extensions={"acme": {"foo": "bar"}},
        )
        assert p.extensions == {"acme": {"foo": "bar"}}


# ---------------------------------------------------------------------------
# Schema integrity — what should still be rejected
# ---------------------------------------------------------------------------


class TestSchemaIntegrity:
    def test_top_level_unknown_field_rejected(self, pipeline_schema):
        # additionalProperties:false at the top level — protects against
        # silent field-name typos until we explicitly add a new top-level slot.
        doc = _minimal_pipeline_doc(unknown_field="oops")
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(doc, pipeline_schema)

    def test_wrong_schema_version_rejected(self, pipeline_schema):
        doc = _minimal_pipeline_doc(schemaVersion=2)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(doc, pipeline_schema)

    def test_missing_required_fields_rejected(self, pipeline_schema):
        bad = {"schemaVersion": 1, "id": "x"}  # missing name + arrays
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, pipeline_schema)

    def test_step_manifest_id_still_strict(self, step_manifest_schema):
        # Step IDs use the original `^[a-z][a-z0-9_]*$` (not the relaxed
        # dataset/node ID regex) — step IDs are global names referenced
        # by every pipeline that uses them, so the constraint stays tight.
        doc = {
            "id": "STEP_NAME", "version": "1.0.0", "label": "x", "category": "derive",
            "engine": {"primary": "sql"},
            "io": {"inputs": {"min": 1, "max": 1}, "outputs": {"min": 1, "max": 1}},
            "params": {},
        }
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(doc, step_manifest_schema)
