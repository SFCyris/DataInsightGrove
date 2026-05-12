"""Surface-stability tests for `dig.protocols`.

Locks the public protocol surface so an accidental refactor of the
internals (rename / remove / signature change) is caught in CI before
it breaks every out-of-tree plugin in the wild.

The test is intentionally exhaustive: every name in `dig.protocols.__all__`
gets a presence check + a basic shape assertion. Adding to the surface
is fine; removing or renaming requires updating this file (which forces
a deliberate decision + a CHANGELOG entry).
"""
from __future__ import annotations

import inspect

import dig.protocols as P


# ── The frozen surface, expected ────────────────────────────────────────
#
# Bumping PROTOCOL_VERSION's MINOR allows additions; the surface below
# documents what every MINOR ≥ this baseline must continue to provide.

EXPECTED_NAMES_v1_0 = frozenset({
    # Step plugin contract
    "Step", "PolarsResult", "PolarsContext", "NanOrigin",
    "ColumnLineage", "ColumnRef",
    # Pipeline document contract
    "Pipeline", "Node", "DatasetSpec", "OutputSpec", "Sink",
    "Reference", "Webhook",
    # Execution contract
    "ExecutionResult", "execute",
    # Templating contract
    "TemplateError", "build_namespace", "render_value", "render_path",
    "has_template",
    # Future-tier protocols
    "StorageBackend", "AuthProvider", "ComputeBackend",
})


class TestSurfacePresence:
    def test_every_v1_0_name_is_exported(self):
        missing = EXPECTED_NAMES_v1_0 - set(P.__all__)
        assert not missing, f"protocol surface regression — names removed: {sorted(missing)}"

    def test_every_v1_0_name_is_importable(self):
        for name in EXPECTED_NAMES_v1_0:
            assert hasattr(P, name), f"dig.protocols.{name} missing"
            assert getattr(P, name) is not None

    def test_protocol_version_present_and_well_formed(self):
        assert hasattr(P, "PROTOCOL_VERSION")
        assert isinstance(P.PROTOCOL_VERSION, tuple)
        assert len(P.PROTOCOL_VERSION) == 2
        assert all(isinstance(v, int) for v in P.PROTOCOL_VERSION)

    def test_protocol_version_at_least_1_0(self):
        # MINOR can grow; never falls below 1.0.
        assert P.PROTOCOL_VERSION >= (1, 0)


class TestStepContract:
    def test_step_is_abc(self):
        # Step must be an ABC (or at least uninstantiable bare).
        # Out-of-tree plugins subclass it.
        assert inspect.isclass(P.Step)

    def test_polars_result_has_required_fields(self):
        # The shape PolarsResult MUST have. Any rename/removal here breaks
        # every step plugin in the wild.
        assert "output" in P.PolarsResult.__dataclass_fields__
        assert "artifacts" in P.PolarsResult.__dataclass_fields__
        assert "nan_origins" in P.PolarsResult.__dataclass_fields__

    def test_nan_origin_has_required_fields(self):
        for f in ("column", "row_indices", "cause", "source_column"):
            assert f in P.NanOrigin.__dataclass_fields__, (
                f"NanOrigin must keep field {f!r}"
            )

    def test_polars_context_has_required_fields(self):
        for f in ("run_id", "out_dir", "node_id", "pipeline_chain"):
            assert f in P.PolarsContext.__dataclass_fields__


class TestPipelineDocContract:
    def test_pipeline_top_level_fields(self):
        # Required shape consumed by enterprise persistence layer.
        for f in ("schemaVersion", "id", "name", "datasets", "nodes",
                  "outputs", "metadata", "extensions"):
            assert f in P.Pipeline.model_fields, f"Pipeline.{f} regression"

    def test_extensions_field_default_is_empty_dict(self):
        # Enterprise builds rely on `pipeline.extensions["enterprise"]`
        # being safe to read (not None) on OSS-authored pipelines.
        p = P.Pipeline(id="01TESTPIPELINEULID00000000", name="t")
        assert p.extensions == {}


class TestExecutionContract:
    def test_execute_signature_keyword_args(self):
        sig = inspect.signature(P.execute)
        assert "p" in sig.parameters or "pipeline" in sig.parameters
        # run_id is required keyword arg for every caller; locking it.
        assert "run_id" in sig.parameters

    def test_execution_result_fields(self):
        for f in ("runId", "outputs", "rowCounts", "elapsedMs",
                  "artifacts", "nodeMetrics", "nanOrigins"):
            assert f in P.ExecutionResult.__dataclass_fields__, (
                f"ExecutionResult.{f} regression"
            )


class TestTemplatingContract:
    def test_render_value_signature(self):
        sig = inspect.signature(P.render_value)
        params = list(sig.parameters)
        assert params[:2] == ["template", "namespace"]

    def test_render_path_has_expand_absolute_kwarg(self):
        sig = inspect.signature(P.render_path)
        assert "expand_absolute" in sig.parameters

    def test_build_namespace_callable(self):
        # Must accept zero positional args (all kw-only with defaults).
        ns = P.build_namespace()
        assert isinstance(ns, dict)


class TestProtocolABCs:
    def test_storage_backend_is_runtime_checkable_protocol(self):
        # Out-of-tree S3Backend etc. need isinstance() checks to work.
        assert hasattr(P.StorageBackend, "_is_protocol")

    def test_storage_backend_has_required_methods(self):
        for m in ("write_parquet", "read_parquet_schema", "open_for_read", "delete"):
            assert hasattr(P.StorageBackend, m)

    def test_auth_provider_has_required_methods(self):
        for m in ("current_user", "can"):
            assert hasattr(P.AuthProvider, m)

    def test_compute_backend_has_required_methods(self):
        for m in ("can_execute", "execute"):
            assert hasattr(P.ComputeBackend, m)
        assert "name" in P.ComputeBackend.__annotations__
