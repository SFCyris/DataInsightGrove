"""Column-level lineage trace.

Walks backward from a (node_id, column_name) target through the pipeline DAG,
accumulating every (node, column, transform) tuple that contributed.

Pure structural — uses each step's `column_dependencies()` declaration plus
the inferred upstream schemas. Zero runtime cost; works without executing the
pipeline.
"""

from __future__ import annotations

from typing import Any, TypedDict

from dig.engine.dag import infer_schemas
from dig.engine.pipeline import Pipeline
from dig.engine.registry import steps


class LineageNode(TypedDict):
    node_id: str            # pipeline node id (or dataset id for roots)
    is_dataset: bool
    column: str
    label: str              # human label (step label or dataset label)
    transform: str          # what this node does to produce `column`
    expression: str | None


class LineageEdge(TypedDict):
    from_node_id: str
    from_column: str
    to_node_id: str
    to_column: str
    transform: str


class LineageGraph(TypedDict):
    target_node_id: str
    target_column: str
    nodes: list[LineageNode]
    edges: list[LineageEdge]


def trace_column(
    pipeline: Pipeline | dict[str, Any],
    target_node_id: str,
    target_column: str,
) -> LineageGraph:
    """Trace `target_column` produced by `target_node_id` back to its dataset roots.

    Returns a DAG of (step, column) pairs. The terminal nodes (`is_dataset=True`)
    are dataset columns — actual files / databases the pipeline reads.
    """
    p = pipeline if isinstance(pipeline, Pipeline) else Pipeline.model_validate(pipeline)
    schemas = infer_schemas(p)
    registry = steps()

    nodes_by_id = {n.id: n for n in p.nodes}
    datasets_by_id = {d.id: d for d in p.datasets}

    visited: set[tuple[str, str]] = set()
    graph_nodes: list[LineageNode] = []
    graph_edges: list[LineageEdge] = []

    def upstream_for_input(node_id: str, port_name: str) -> tuple[str | None, bool]:
        """Resolve which upstream (node or dataset) is wired to `node.inputs[port_name]`.
        Returns (upstream_id, is_dataset)."""
        node = nodes_by_id.get(node_id)
        if node is None:
            return None, False
        ref_obj = (node.inputs or {}).get(port_name)
        if ref_obj is None:
            return None, False
        # PipelineRef pydantic model exposes `.ref`
        ref = getattr(ref_obj, "ref", None)
        if ref is None and isinstance(ref_obj, dict):
            ref = ref_obj.get("ref")
        if ref is None:
            return None, False
        if ref in datasets_by_id:
            return ref, True
        return ref, False

    def walk(node_id: str, column: str) -> None:
        key = (node_id, column)
        if key in visited:
            return
        visited.add(key)

        # Dataset root.
        if node_id in datasets_by_id:
            ds = datasets_by_id[node_id]
            graph_nodes.append({
                "node_id": node_id,
                "is_dataset": True,
                "column": column,
                "label": ds.label or ds.connector or node_id,
                "transform": "source",
                "expression": None,
            })
            return

        node = nodes_by_id.get(node_id)
        if node is None:
            return  # unresolved ref

        step = registry.get(node.step)
        if step is None:
            graph_nodes.append({
                "node_id": node_id,
                "is_dataset": False,
                "column": column,
                "label": node.step,
                "transform": "unknown",
                "expression": None,
            })
            return

        # Build input_schemas the step expects: { port_name: { col: type } }
        input_schemas: dict[str, dict[str, str]] = {}
        for port, ref_obj in (node.inputs or {}).items():
            ref = getattr(ref_obj, "ref", None)
            if ref is None and isinstance(ref_obj, dict):
                ref = ref_obj.get("ref")
            if ref is None:
                continue
            input_schemas[port] = schemas.get(ref, {})

        try:
            deps = step.column_dependencies(input_schemas, node.params or {})
        except Exception:
            deps = {}

        col_lineage = deps.get(column)
        if col_lineage is None:
            graph_nodes.append({
                "node_id": node_id,
                "is_dataset": False,
                "column": column,
                "label": _node_label(node),
                "transform": "unknown",
                "expression": None,
            })
            return

        graph_nodes.append({
            "node_id": node_id,
            "is_dataset": False,
            "column": column,
            "label": _node_label(node),
            "transform": col_lineage.transform,
            "expression": col_lineage.expression,
        })

        for src in col_lineage.sources:
            up_id, _is_ds = upstream_for_input(node_id, src.port)
            if up_id is None:
                continue
            graph_edges.append({
                "from_node_id": up_id,
                "from_column": src.column,
                "to_node_id": node_id,
                "to_column": column,
                "transform": col_lineage.transform,
            })
            walk(up_id, src.column)

    walk(target_node_id, target_column)

    return {
        "target_node_id": target_node_id,
        "target_column": target_column,
        "nodes": graph_nodes,
        "edges": graph_edges,
    }


def _node_label(node: Any) -> str:
    ui = getattr(node, "ui", None)
    if ui is not None:
        label = getattr(ui, "label", None)
        if label:
            return label
    return getattr(node, "step", "<unknown>")
