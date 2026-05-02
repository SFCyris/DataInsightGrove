# Pipeline format — what's inside a `.dig.json` file

Every pipeline you build in DIG can be saved as a single small JSON file and re-opened anywhere — on another machine, in a code review, in a Git diff, in another DIG installation. **This page is the friendly tour of what's actually in that file.**

You don't need to read it to *use* DIG; the editor builds and reads these files for you. But if you've ever wanted to:

- Tweak a pipeline by hand (rename twenty columns at once with sed, say)
- Generate pipelines programmatically from a template
- Diff two pipelines in code review
- Understand why DIG rejected an import

…this is the page that makes the inside of the file legible.

> **For the rule-perfect specification** that DIG's validator actually runs against — types, regex patterns, exact field names, default values — see [`shared/schemas/pipeline.schema.json`](../shared/schemas/pipeline.schema.json). It's a JSON Schema (2020-12) file. This page explains the *intent* of each piece in plain English; the schema is what your editor and the backend will both check against. If you ever spot the two disagreeing, please [open an issue](https://github.com/SFCyris/DataInsightGrove/issues) — they should match.

---

## File extension and shape

A pipeline is a plain JSON file with the extension `.dig.json`. No embedded scripts, no macros — just data. You can open one in any text editor, in `jq`, or paste it into ChatGPT.

The top level looks like this:

```json
{
  "schemaVersion": 1,
  "id": "01J…ULID",
  "name": "Customer cleanup",
  "createdAt": "2026-05-01T10:00:00Z",
  "updatedAt": "2026-05-01T10:30:00Z",
  "datasets": [ … ],
  "nodes":    [ … ],
  "outputs":  [ … ],
  "metadata": { … }
}
```

In one sentence: **a pipeline is a list of datasets you brought in, a list of steps you applied to them, and a list of outputs you want back out.**

---

## How nodes connect — the DAG, made implicit

In most "boxes-and-arrows" tools you have two lists in the file: a list of nodes and a separate list of arrows between them. DIG skips the arrow list. Each node names the upstream nodes it reads from, and *that* list of names is the arrow list.

Here's a join step that pulls from a filter step (called `n_filter_active`) on its left input port and from a raw dataset (`ds_orders`) on its right:

```json
{
  "id": "n_join_orders",
  "step": "join",
  "stepVersion": "1.0.0",
  "inputs": {
    "left":  { "ref": "n_filter_active", "port": "out" },
    "right": { "ref": "ds_orders" }
  },
  "outputs": ["out"],
  "params": { "on": [ { "left": "id", "right": "customer_id" } ], "how": "left" }
}
```

A `Reference` is just `{ ref, port? }`:
- `ref` — the id of an upstream node or a dataset (datasets have ids too, like `ds_orders` here)
- `port` — which named output of that upstream you want. Most steps only have one output (`out`) and you can leave `port` off.

**Why no separate `edges` array?** Two lists that have to stay in sync are an entire bug class. With one list (the references inside each node) the wiring is the references — they can't diverge.

---

## What happens when you save or run

Whenever the editor saves a pipeline, and again every time you click ▶ Run, the backend walks through five checks. They run fast and any failure surfaces in the UI before anything actually executes:

1. **Shape check.** Does the JSON match the schema? (Field names, types, required fields, value ranges.)
2. **Reference check.** Every `ref` points at something real — no dangling references.
3. **Cycle check.** The graph is a tree-of-steps, not a knot of mutually-referencing ones. (Topological sort; if it can't sort, you have a cycle.)
4. **Parameter check.** Each step's `params` block matches what *that step* expects (a filter has a `predicate`, a join has an `on`, etc.).
5. **Schema inference.** DIG walks left-to-right computing what columns each step produces. If your downstream step asks for a column that vanished upstream, you find out here, before any data moves.

If any check fails, the editor highlights what went wrong with a clear message. Nothing executes until the pipeline is structurally sound.

---

## See also

- [`docs/STEPS.md`](STEPS.md) — every step DIG ships with, plus what params it takes (auto-generated from the same schema, so it stays in sync).
- [`docs/AUTHORING_GUIDE.md`](AUTHORING_GUIDE.md) — how to add your own step or connector. The piece you'd plug into the `step` field above to introduce a new node type.
- [`shared/schemas/pipeline.schema.json`](../shared/schemas/pipeline.schema.json) — the JSON Schema this page describes in English. Use it for IDE autocomplete (`# yaml-language-server: $schema=…` works for JSON-with-comments too) or to validate generated pipelines in CI.
