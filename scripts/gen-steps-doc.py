#!/usr/bin/env python3
"""Generate docs/STEPS.md by walking every step manifest in the repo.

This is the source of truth for "what steps does DIG ship?". Run it whenever
you add or update a step. The output is committed alongside the steps
themselves so the docs stay in sync.

Hand-written use-case + example sections live in `docs/_steps/<step_id>.md`.
If a step has no companion file we still emit a stub with the manifest
metadata; you can fill in the example later.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STEPS_DIR = REPO / "backend" / "steps"
PLUGINS_STEPS_DIR = REPO / "plugins" / "steps"
HAND_NOTES = REPO / "docs" / "_steps"
OUT = REPO / "docs" / "STEPS.md"

CATEGORY_LABELS = {
    "ingest":    "📥 Ingest",
    "shape":     "✂️ Shape",
    "clean":     "🧼 Clean",
    "derive":    "🪄 Derive",
    "combine":   "🤝 Combine",
    "aggregate": "📊 Aggregate",
    "output":    "📤 Output",
    "custom":    "🧩 Custom",
}

CATEGORY_ORDER = ["ingest", "shape", "clean", "derive", "combine", "aggregate", "output", "custom"]


def collect_manifests() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for base in (STEPS_DIR, PLUGINS_STEPS_DIR):
        if not base.exists():
            continue
        for sub in sorted(base.iterdir()):
            if not sub.is_dir():
                continue
            mf = sub / "manifest.json"
            if not mf.exists():
                continue
            try:
                items.append(json.loads(mf.read_text()))
            except json.JSONDecodeError as e:
                print(f"⚠️  skipping {sub.name}: {e}", file=sys.stderr)
    return items


def hand_note(step_id: str) -> str | None:
    p = HAND_NOTES / f"{step_id}.md"
    if not p.exists():
        return None
    return p.read_text().rstrip()


def render_param_table(params: dict[str, Any]) -> str:
    if not params:
        return "_(no parameters)_"
    rows = [
        "| Name | Type | Required | Default | Description |",
        "|---|---|---|---|---|",
    ]
    for name, spec in params.items():
        ptype = spec.get("type", "—")
        req = "✓" if spec.get("required") else ""
        default = spec.get("default")
        default_md = "—" if default is None else f"`{default}`"
        desc = spec.get("help") or spec.get("label") or ""
        # Escape pipes in description for markdown table.
        desc = desc.replace("|", "\\|")
        rows.append(f"| `{name}` | {ptype} | {req} | {default_md} | {desc} |")
    return "\n".join(rows)


def render_step(manifest: dict[str, Any]) -> str:
    sid = manifest["id"]
    label = manifest.get("label", sid)
    desc = manifest.get("description", "")
    engine = manifest.get("engine", {})
    io = manifest.get("io", {})
    preview = manifest.get("preview", {})
    tags = manifest.get("tags", [])

    inputs = io.get("inputs", {})
    outputs = io.get("outputs", {})
    in_min = inputs.get("min", 1)
    in_max = inputs.get("max", 1)
    out_min = outputs.get("min", 1)
    out_max = outputs.get("max", 1)
    in_str = f"{in_min}" if in_min == in_max else f"{in_min}–{in_max if in_max is not None else '∞'}"
    out_str = f"{out_min}" if out_min == out_max else f"{out_min}–{out_max if out_max is not None else '∞'}"

    lines: list[str] = []
    lines.append(f"### {label}")
    lines.append("")
    lines.append(f"**ID:** `{sid}` · **Version:** `{manifest.get('version', '?')}`")
    lines.append("")
    if desc:
        lines.append(desc)
        lines.append("")
    badges = []
    badges.append(f"🛠 engine: `{engine.get('primary', 'sql')}`")
    if engine.get("browser") and engine["browser"] != "none":
        badges.append(f"🌐 browser: `{engine['browser']}`")
    if engine.get("deterministic") is False:
        badges.append("⚠️ non-deterministic")
    badges.append(f"⬅️ inputs: {in_str}")
    badges.append(f"➡️ outputs: {out_str}")
    if preview.get("rowImpact"):
        badges.append(f"rows: {preview['rowImpact']}")
    if preview.get("schemaImpact"):
        badges.append(f"schema: {preview['schemaImpact']}")
    lines.append(" · ".join(badges))
    lines.append("")
    if tags:
        lines.append("Tags: " + " ".join(f"`{t}`" for t in tags))
        lines.append("")

    lines.append("**Parameters**")
    lines.append("")
    lines.append(render_param_table(manifest.get("params", {})))
    lines.append("")

    note = hand_note(sid)
    if note:
        lines.append("**Use case + example**")
        lines.append("")
        lines.append(note)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_doc(manifests: list[dict[str, Any]]) -> str:
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for m in manifests:
        by_cat.setdefault(m.get("category", "custom"), []).append(m)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda m: m["id"])

    out: list[str] = []
    out.append("# 📚 DataInsightGrove — Step library")
    out.append("")
    out.append(
        "This page documents every step DIG ships with. It is **auto-generated**"
        " from each step's `manifest.json` plus optional hand-written notes under"
        " `docs/_steps/<step_id>.md` — re-run `python scripts/gen-steps-doc.py`"
        " whenever you add or change a step."
    )
    out.append("")
    total = len(manifests)
    out.append(
        f"**{total} steps** across "
        + ", ".join(
            f"{CATEGORY_LABELS.get(c, c)} ({len(by_cat[c])})"
            for c in CATEGORY_ORDER if c in by_cat
        )
        + "."
    )
    out.append("")
    out.append("## Index")
    out.append("")
    for cat in CATEGORY_ORDER:
        if cat not in by_cat:
            continue
        out.append(f"### {CATEGORY_LABELS.get(cat, cat)}")
        out.append("")
        for m in by_cat[cat]:
            out.append(f"- [{m.get('label', m['id'])}](#{_anchor(m.get('label', m['id']))}) — {m.get('description', '').split('.')[0]}.")
        out.append("")

    for cat in CATEGORY_ORDER:
        if cat not in by_cat:
            continue
        out.append("---")
        out.append("")
        out.append(f"## {CATEGORY_LABELS.get(cat, cat)}")
        out.append("")
        for m in by_cat[cat]:
            out.append(render_step(m))
            out.append("")

    return "\n".join(out).rstrip() + "\n"


def _anchor(label: str) -> str:
    """GitHub-flavored markdown header → anchor."""
    out = []
    for c in label.lower():
        if c.isalnum() or c == "-":
            out.append(c)
        elif c == " ":
            out.append("-")
        # other characters (emoji, punctuation) are dropped
    return "".join(out).strip("-")


def main() -> None:
    manifests = collect_manifests()
    if not manifests:
        print("no manifests found", file=sys.stderr)
        sys.exit(1)
    OUT.write_text(render_doc(manifests))
    print(f"wrote {OUT.relative_to(REPO)} ({len(manifests)} steps)")


if __name__ == "__main__":
    main()
