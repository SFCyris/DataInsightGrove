# Pipeline format

This is the human reference for the DIG pipeline document. The authoritative spec is `shared/schemas/pipeline.schema.json` (JSON Schema 2020-12). When this document and the schema disagree, the schema wins.

## File extension

`.dig.json`. Plain JSON, no embedded scripts.

## Top-level shape

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

## DAG model

The DAG is **implicit** — there is no `edges` array. Each `node` declares its inputs as a map of port name → reference:

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
  "params": { "on": [ {"left":"id","right":"customer_id"} ], "how": "left" }
}
```

A `Reference` is `{ ref, port? }` where `ref` is a dataset id or upstream node id, and `port` defaults to the first declared output port. This means the reference list IS the edge list.

## Validation pipeline

Server-side, on every save and before every run:

1. JSON-Schema validate the document.
2. Resolve every reference; verify the target exists.
3. Topological sort; reject cycles.
4. Look up each node's manifest; validate `params` against the manifest's params spec.
5. Left-to-right schema inference; surface schema errors before execution.

## See also

- [`docs/STEPS.md`](STEPS.md) — auto-generated reference for every built-in step (params + examples).
- [`docs/AUTHORING_GUIDE.md`](AUTHORING_GUIDE.md) — how to write your own steps and connectors.
- [`shared/schemas/pipeline.schema.json`](../shared/schemas/pipeline.schema.json) — authoritative JSON Schema, the source of truth for both the Python and TypeScript clients.
