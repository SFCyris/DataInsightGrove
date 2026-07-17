"""DAG analysis: validation, topological sort, schema inference.

Operates on a Pipeline document (dig.engine.pipeline.Pipeline). Pure functions —
no I/O, no DuckDB. The executor calls these and then compiles + runs SQL.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from dig.engine.pipeline import Node, Pipeline, Reference, effective_connector
from dig.engine.profile import _logical_type
from dig.engine.registry import connectors, steps


class DagError(ValueError):
    """Raised when the DAG document is structurally invalid."""


def _resolve_target(p: Pipeline, ref: Reference) -> tuple[str, str]:
    """Return (kind, id) where kind in {dataset, node}. Raises DagError."""
    for d in p.datasets:
        if d.id == ref.ref:
            return ("dataset", d.id)
    for n in p.nodes:
        if n.id == ref.ref:
            if ref.port is not None and ref.port not in n.outputs:
                raise DagError(
                    f"node '{n.id}' has no output port '{ref.port}' (declares {n.outputs})"
                )
            return ("node", n.id)
    raise DagError(f"unresolved reference: {ref.ref}")


def validate(p: Pipeline) -> None:
    """Structural validation: unique ids, references resolve, ports declared."""
    seen_ds: set[str] = set()
    for d in p.datasets:
        if d.id in seen_ds:
            raise DagError(f"duplicate dataset id: {d.id}")
        seen_ds.add(d.id)
    seen_nodes: set[str] = set()
    for n in p.nodes:
        if n.id in seen_nodes:
            raise DagError(f"duplicate node id: {n.id}")
        if n.id in seen_ds:
            raise DagError(f"node id conflicts with dataset id: {n.id}")
        seen_nodes.add(n.id)
        for port, ref in n.inputs.items():
            try:
                _resolve_target(p, ref)
            except DagError as e:
                raise DagError(f"node '{n.id}' input '{port}': {e}") from e
    seen_outputs: set[str] = set()
    for o in p.outputs:
        if o.id in seen_outputs:
            raise DagError(f"duplicate output id: {o.id}")
        seen_outputs.add(o.id)
        try:
            _resolve_target(p, o.from_)
        except DagError as e:
            raise DagError(f"output '{o.id}': {e}") from e


def topo_sort(p: Pipeline) -> list[Node]:
    """Return nodes in topological order, raising DagError on cycles or missing refs.

    Datasets are not included — only steps. They form the leaves of the DAG.
    """
    nodes_by_id = {n.id: n for n in p.nodes}
    in_deg: dict[str, int] = {n.id: 0 for n in p.nodes}
    deps: dict[str, set[str]] = {n.id: set() for n in p.nodes}

    for n in p.nodes:
        for ref in n.inputs.values():
            kind, target_id = _resolve_target(p, ref)
            if kind == "node" and target_id not in deps[n.id]:
                deps[n.id].add(target_id)
                in_deg[n.id] += 1

    queue = [nid for nid, d in in_deg.items() if d == 0]
    out: list[Node] = []
    while queue:
        # stable order: alphabetical to make output reproducible
        queue.sort()
        nid = queue.pop(0)
        out.append(nodes_by_id[nid])
        for downstream in p.nodes:
            if nid in deps[downstream.id]:
                in_deg[downstream.id] -= 1
                if in_deg[downstream.id] == 0:
                    queue.append(downstream.id)
    if len(out) != len(p.nodes):
        unresolved = [n.id for n in p.nodes if n not in out]
        raise DagError(f"cycle detected involving nodes: {unresolved}")
    return out


def _dataset_schema(p: Pipeline, dataset_id: str) -> dict[str, str]:
    """Probe a dataset's schema by reading 0 rows via its connector."""
    spec = next(d for d in p.datasets if d.id == dataset_id)
    # Trust the URI extension over the persisted connector — schema
    # inference must agree with the actual reader compile.py picks, or
    # column-validation steps falsely flag missing columns.
    connector = connectors().get(effective_connector(spec))
    lf = connector.read(spec.uri, spec.options)
    schema = lf.collect_schema()
    return {name: _logical_type(dtype) for name, dtype in schema.items()}


def infer_schemas(p: Pipeline) -> dict[str, dict[str, str]]:
    """Compute output schema (column name -> logical type) for every node and dataset.

    Returns: { ref_id : { col : type } } with one entry per dataset and per node.
    Multi-port nodes are not supported (single 'out' port).
    """
    out: dict[str, dict[str, str]] = {}
    for d in p.datasets:
        out[d.id] = _dataset_schema(p, d.id)
    for n in topo_sort(p):
        step = steps().get(n.step)
        input_schemas: dict[str, dict[str, str]] = {}
        for port, ref in n.inputs.items():
            input_schemas[port] = out.get(ref.ref, {})
        out[n.id] = step.infer_schema(input_schemas, n.params)
    return out


def validate_params_against_manifests(p: Pipeline) -> list[str]:
    """Return a list of human-readable validation errors for node params.

    Per-param checks (in order):
      1. Step exists in the registry.
      2. Required param present + non-empty.
      3. Value matches `type` from the manifest's paramSpec.
      4. Numeric bounds (min/max) honored.
      5. Enum values in `enumValues`.
      6. Pattern (regex) matches for type='string'.
      7. Array `items` validated recursively (only for typed scalar items).
      8. **column_ref / column_refs reference columns that exist in the
         upstream's output schema** — catches AI routes that reference
         columns dropped by an earlier transform (e.g. `linear_regression
         (y=temperature_c)` after a `correlation_matrix` that emits only
         `(col_a, col_b, r)`).

    Catches UI-shape mismatches at save time instead of crash time.
    """
    errs: list[str] = []
    # Build per-node input-port schemas once so column_ref checks below
    # can validate against the actual upstream output. If schema inference
    # itself fails (a partially-configured sibling branch, say), we
    # degrade to no-schemas — same behaviour as the pre-existing path.
    try:
        all_schemas = infer_schemas(p)
    except Exception:
        all_schemas = {}
    for n in p.nodes:
        try:
            step = steps().get(n.step)
        except KeyError:
            errs.append(f"node '{n.id}': unknown step '{n.step}'")
            continue
        params_spec = step.manifest.get("params", {})
        # Build the per-port input schema map for this node; pass to the
        # checker so column_ref params can verify their references resolve.
        node_input_schemas: dict[str, dict[str, str]] = {
            port: all_schemas.get(ref.ref, {}) for port, ref in n.inputs.items()
        }
        for pname, pspec in params_spec.items():
            value = n.params.get(pname)
            if pspec.get("required") and value in (None, "", []):
                errs.append(f"node '{n.id}': required param '{pname}' missing")
                continue
            if value is None:
                continue
            for e in _check_param_value(
                value, pspec, f"node '{n.id}'.{pname}",
                input_schemas=node_input_schemas,
            ):
                errs.append(e)
    return errs


_PYTYPE_MAP = {
    "string": (str,),
    "number": (int, float),
    "integer": (int, bool),  # bool is technically int — caller may intend integer
    "boolean": (bool,),
    "enum": (str, int, float),
    "column_ref": (str,),
    "column_refs": (list,),
    "expression": (str,),
    "regex": (str,),
    "object": (dict,),
    "array": (list,),
}


def _check_param_value(
    value: Any,
    spec: dict[str, Any],
    where: str,
    *,
    input_schemas: dict[str, dict[str, str]] | None = None,
) -> list[str]:
    errs: list[str] = []
    ptype = spec.get("type", "string")
    expected = _PYTYPE_MAP.get(ptype, (object,))

    # bool is subclass of int — disallow when type=="integer" (likely UI bug).
    if ptype == "integer" and isinstance(value, bool):
        errs.append(f"{where}: expected integer, got boolean")
        return errs
    if not isinstance(value, expected):
        errs.append(
            f"{where}: expected {ptype}, got {type(value).__name__}"
        )
        return errs

    # column_refs: every item must be a string.
    if ptype == "column_refs" and not all(isinstance(c, str) for c in value):
        errs.append(f"{where}: column_refs must be a list of strings")

    # column_ref / column_refs: when we have the upstream schema, verify
    # the referenced column actually exists. Catches AI-suggested
    # multi-step routes whose later steps reference columns dropped by
    # an earlier transform (correlation_matrix → linear_regression
    # was the smoking-gun case).
    if input_schemas:
        # Pick the port the manifest names if any (e.g. "left"/"right"
        # for join keys); otherwise use the union of all input ports.
        port = spec.get("columnFrom")
        if port and port in input_schemas:
            available = set(input_schemas[port].keys())
        else:
            available: set[str] = set()
            for s in input_schemas.values():
                available.update(s.keys())
        if available:
            if ptype == "column_ref" and isinstance(value, str) and value not in available:
                errs.append(
                    f"{where}: column {value!r} not found in upstream output "
                    f"(available: {', '.join(sorted(available)[:8])}"
                    f"{'…' if len(available) > 8 else ''})"
                )
            if ptype == "column_refs" and isinstance(value, list):
                missing = [c for c in value if isinstance(c, str) and c not in available]
                if missing:
                    errs.append(
                        f"{where}: columns {missing!r} not found in upstream output "
                        f"(available: {', '.join(sorted(available)[:8])}"
                        f"{'…' if len(available) > 8 else ''})"
                    )

    # Numeric bounds.
    if ptype in ("number", "integer") and isinstance(value, (int, float)) and not isinstance(value, bool):
        if "min" in spec and value < spec["min"]:
            errs.append(f"{where}: {value} < min {spec['min']}")
        if "max" in spec and value > spec["max"]:
            errs.append(f"{where}: {value} > max {spec['max']}")

    # Enum.
    if ptype == "enum" and "enumValues" in spec and value not in spec["enumValues"]:
        errs.append(
            f"{where}: {value!r} not in allowed values {spec['enumValues']}"
        )

    # String pattern.
    if ptype == "string" and "pattern" in spec and isinstance(value, str):
        import re as _re
        try:
            if not _re.search(spec["pattern"], value):
                errs.append(f"{where}: doesn't match pattern {spec['pattern']!r}")
        except _re.error:
            pass  # malformed pattern in manifest — not the user's fault

    # Array items: recurse if items spec is a typed scalar shape.
    if ptype == "array" and isinstance(spec.get("items"), dict) and isinstance(value, list):
        items_spec = spec["items"]
        # Only recurse for scalar item types — object items have unbounded
        # nesting and the manifest authors haven't asked for that depth.
        if items_spec.get("type") in ("string", "number", "integer", "boolean", "enum"):
            for i, v in enumerate(value):
                errs.extend(_check_param_value(v, items_spec, f"{where}[{i}]"))

    return errs
