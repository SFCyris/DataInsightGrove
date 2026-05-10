"""Structural pipeline diff.

Pure functions over the pipeline JSON document. Used by:
- The /pipelines/{id}/diff endpoint (visual pipeline diff feature).
- The AI Pipeline Reviewer (renders mutation suggestions through this).
- The pipeline editor's "Compare" toolbar action.

Match strategy:
- Nodes are matched by `node.id` first (stable across edits — React Flow IDs
  are persisted). Same-id nodes with different `step` types are still treated
  as one node (a "type_changed" diff).
- Unmatched nodes that share the same `step` type and most-similar params
  are heuristically matched as "moved" — handles the case where a copy/paste
  produced a new ID for the same logical step.
- True additions / removals are what's left.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal, TypedDict


def canonical_json(doc: Any) -> str:
    """Stable JSON for hashing (sorted keys, no whitespace)."""
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))


def document_hash(doc: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON, ignoring fields that don't affect
    semantics (`ui.*` coordinates, `etag`, timestamps).
    """
    stripped = _strip_non_semantic(doc)
    return hashlib.sha256(canonical_json(stripped).encode("utf-8")).hexdigest()


def _strip_non_semantic(doc: dict[str, Any]) -> dict[str, Any]:
    """Remove fields that don't affect pipeline behavior (UI coords, etag)."""
    out = {k: v for k, v in doc.items() if k not in {"etag", "updated_at", "created_at"}}
    if "nodes" in out:
        out["nodes"] = [
            {k: v for k, v in n.items() if k != "ui"} for n in out["nodes"]
        ]
    return out


# ---- Diff result types ---------------------------------------------------


class ParamDiff(TypedDict):
    key: str
    a_value: Any
    b_value: Any
    a_summary: str
    b_summary: str


class StepDiff(TypedDict):
    kind: Literal[
        "added", "removed", "moved", "param_changed", "type_changed", "unchanged"
    ]
    node_id: str
    label: str
    step_type: str
    a_position: int | None
    b_position: int | None
    param_changes: list[ParamDiff]


class DatasetDiff(TypedDict):
    kind: Literal["added", "removed", "options_changed", "unchanged"]
    dataset_id: str
    label: str
    option_changes: list[ParamDiff]


class OutputDiff(TypedDict):
    kind: Literal["added", "removed", "renamed", "rewired", "unchanged"]
    output_id: str
    name: str
    a_from: str | None
    b_from: str | None


class PipelineDiff(TypedDict):
    summary: str
    counts: dict[str, int]  # added / removed / moved / param_changed / type_changed
    steps: list[StepDiff]
    datasets: list[DatasetDiff]
    outputs: list[OutputDiff]
    metadata_changes: list[ParamDiff]


# ---- Public diff API ------------------------------------------------------


def diff_pipelines(a: dict[str, Any], b: dict[str, Any]) -> PipelineDiff:
    """Diff two pipeline documents. Both must conform to pipeline.schema.json.

    Either side may be missing entirely (e.g. comparing against an empty
    starting pipeline) — represented as `{"nodes": [], "datasets": [], ...}`.
    """
    a = a or {}
    b = b or {}

    steps = _diff_nodes(a.get("nodes", []), b.get("nodes", []))
    datasets = _diff_datasets(a.get("datasets", []), b.get("datasets", []))
    outputs = _diff_outputs(a.get("outputs", []), b.get("outputs", []))
    metadata_changes = _diff_dict(a.get("metadata", {}) or {}, b.get("metadata", {}) or {})

    counts: dict[str, int] = {
        "added": 0,
        "removed": 0,
        "moved": 0,
        "param_changed": 0,
        "type_changed": 0,
    }
    for s in steps:
        if s["kind"] in counts:
            counts[s["kind"]] += 1

    summary = (
        f"+{counts['added']} / -{counts['removed']} / "
        f"~{counts['param_changed'] + counts['type_changed']}"
        + (f" / →{counts['moved']}" if counts["moved"] else "")
    )

    return {
        "summary": summary,
        "counts": counts,
        "steps": steps,
        "datasets": datasets,
        "outputs": outputs,
        "metadata_changes": metadata_changes,
    }


# ---- Node diff -----------------------------------------------------------


def _diff_nodes(a_nodes: list[dict[str, Any]], b_nodes: list[dict[str, Any]]) -> list[StepDiff]:
    # Skip nodes without an `id` instead of KeyError-ing — a malformed import
    # or partial in-memory edit shouldn't crash the diff endpoint.
    a_by_id = {n["id"]: (i, n) for i, n in enumerate(a_nodes) if n.get("id")}
    b_by_id = {n["id"]: (i, n) for i, n in enumerate(b_nodes) if n.get("id")}

    out: list[StepDiff] = []
    seen: set[str] = set()

    # Pass 1: nodes present in both, matched by id.
    for nid, (a_pos, a_node) in a_by_id.items():
        if nid not in b_by_id:
            continue
        seen.add(nid)
        b_pos, b_node = b_by_id[nid]
        if a_node.get("step") != b_node.get("step"):
            out.append(_step_diff_type_changed(nid, a_node, b_node, a_pos, b_pos))
            continue
        param_changes = _diff_dict(a_node.get("params", {}) or {}, b_node.get("params", {}) or {})
        moved = _node_moved(a_node, b_node, a_pos, b_pos)
        if param_changes:
            out.append({
                "kind": "param_changed",
                "node_id": nid,
                "label": _node_label(b_node),
                "step_type": b_node.get("step", ""),
                "a_position": a_pos,
                "b_position": b_pos,
                "param_changes": param_changes,
            })
        elif moved:
            out.append({
                "kind": "moved",
                "node_id": nid,
                "label": _node_label(b_node),
                "step_type": b_node.get("step", ""),
                "a_position": a_pos,
                "b_position": b_pos,
                "param_changes": [],
            })
        else:
            out.append({
                "kind": "unchanged",
                "node_id": nid,
                "label": _node_label(b_node),
                "step_type": b_node.get("step", ""),
                "a_position": a_pos,
                "b_position": b_pos,
                "param_changes": [],
            })

    # Pass 2: nodes only in a → removed.
    for nid, (a_pos, a_node) in a_by_id.items():
        if nid in seen:
            continue
        out.append({
            "kind": "removed",
            "node_id": nid,
            "label": _node_label(a_node),
            "step_type": a_node.get("step", ""),
            "a_position": a_pos,
            "b_position": None,
            "param_changes": [],
        })

    # Pass 3: nodes only in b → added.
    for nid, (b_pos, b_node) in b_by_id.items():
        if nid in seen:
            continue
        if nid in a_by_id:
            continue
        out.append({
            "kind": "added",
            "node_id": nid,
            "label": _node_label(b_node),
            "step_type": b_node.get("step", ""),
            "a_position": None,
            "b_position": b_pos,
            "param_changes": [],
        })

    return out


def _step_diff_type_changed(
    nid: str,
    a_node: dict[str, Any],
    b_node: dict[str, Any],
    a_pos: int,
    b_pos: int,
) -> StepDiff:
    return {
        "kind": "type_changed",
        "node_id": nid,
        "label": f"{_node_label(a_node)} → {_node_label(b_node)}",
        "step_type": f"{a_node.get('step', '')} → {b_node.get('step', '')}",
        "a_position": a_pos,
        "b_position": b_pos,
        "param_changes": _diff_dict(a_node.get("params", {}) or {}, b_node.get("params", {}) or {}),
    }


def _node_label(node: dict[str, Any]) -> str:
    ui = node.get("ui") or {}
    return ui.get("label") or node.get("step", "<unknown>")


def _node_moved(
    a_node: dict[str, Any],
    b_node: dict[str, Any],
    a_pos: int,
    b_pos: int,
) -> bool:
    """Treat as moved if either DAG inputs changed or position changed."""
    if a_pos != b_pos:
        return True
    return canonical_json(a_node.get("inputs") or {}) != canonical_json(b_node.get("inputs") or {})


# ---- Dataset diff --------------------------------------------------------


def _diff_datasets(
    a_datasets: list[dict[str, Any]],
    b_datasets: list[dict[str, Any]],
) -> list[DatasetDiff]:
    a_by_id = {d["id"]: d for d in a_datasets if d.get("id")}
    b_by_id = {d["id"]: d for d in b_datasets if d.get("id")}
    out: list[DatasetDiff] = []
    for did, d in a_by_id.items():
        if did not in b_by_id:
            out.append({
                "kind": "removed",
                "dataset_id": did,
                "label": d.get("label") or did,
                "option_changes": [],
            })
            continue
        b_d = b_by_id[did]
        opt_changes = _diff_dict(d.get("options", {}) or {}, b_d.get("options", {}) or {})
        if opt_changes or d.get("uri") != b_d.get("uri") or d.get("connector") != b_d.get("connector"):
            out.append({
                "kind": "options_changed",
                "dataset_id": did,
                "label": b_d.get("label") or did,
                "option_changes": opt_changes,
            })
    for did, d in b_by_id.items():
        if did not in a_by_id:
            out.append({
                "kind": "added",
                "dataset_id": did,
                "label": d.get("label") or did,
                "option_changes": [],
            })
    return out


# ---- Output diff ---------------------------------------------------------


def _diff_outputs(
    a_outputs: list[dict[str, Any]],
    b_outputs: list[dict[str, Any]],
) -> list[OutputDiff]:
    a_by_id = {o["id"]: o for o in a_outputs if o.get("id")}
    b_by_id = {o["id"]: o for o in b_outputs if o.get("id")}
    out: list[OutputDiff] = []
    for oid, a_o in a_by_id.items():
        if oid not in b_by_id:
            out.append({
                "kind": "removed",
                "output_id": oid,
                "name": a_o.get("name", ""),
                "a_from": _output_from(a_o),
                "b_from": None,
            })
            continue
        b_o = b_by_id[oid]
        a_from = _output_from(a_o)
        b_from = _output_from(b_o)
        if a_o.get("name") != b_o.get("name"):
            out.append({
                "kind": "renamed",
                "output_id": oid,
                "name": f"{a_o.get('name')} → {b_o.get('name')}",
                "a_from": a_from,
                "b_from": b_from,
            })
        elif a_from != b_from:
            out.append({
                "kind": "rewired",
                "output_id": oid,
                "name": b_o.get("name", ""),
                "a_from": a_from,
                "b_from": b_from,
            })
    for oid, b_o in b_by_id.items():
        if oid not in a_by_id:
            out.append({
                "kind": "added",
                "output_id": oid,
                "name": b_o.get("name", ""),
                "a_from": None,
                "b_from": _output_from(b_o),
            })
    return out


def _output_from(o: dict[str, Any]) -> str | None:
    f = o.get("from")
    if not f:
        return None
    if isinstance(f, dict):
        ref = f.get("ref")
        port = f.get("port")
        return f"{ref}:{port}" if port else ref
    return str(f)


# ---- Generic dict diff ---------------------------------------------------


def _diff_dict(a: dict[str, Any], b: dict[str, Any]) -> list[ParamDiff]:
    """Per-key recursive structural diff for params/options/metadata."""
    out: list[ParamDiff] = []
    keys = sorted(set(a.keys()) | set(b.keys()))
    for k in keys:
        av = a.get(k)
        bv = b.get(k)
        if canonical_json(av) == canonical_json(bv):
            continue
        out.append({
            "key": k,
            "a_value": av,
            "b_value": bv,
            "a_summary": _summarize_value(av),
            "b_summary": _summarize_value(bv),
        })
    return out


def _summarize_value(v: Any) -> str:
    """One-line human summary suitable for showing in the diff card."""
    if v is None:
        return "—"
    if isinstance(v, (str, int, float, bool)):
        s = str(v)
        return s if len(s) <= 64 else s[:61] + "…"
    if isinstance(v, list):
        return f"[{len(v)} item{'s' if len(v) != 1 else ''}]"
    if isinstance(v, dict):
        keys = list(v.keys())
        if not keys:
            return "{}"
        if len(keys) <= 3:
            return "{" + ", ".join(keys) + "}"
        return "{" + ", ".join(keys[:3]) + f", +{len(keys) - 3}}}"
    return str(v)[:64]
