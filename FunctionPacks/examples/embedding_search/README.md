# 🧭 `embedding_search` · cluster + nearest-neighbour

**Scenario:** 15 short documents on three obvious topics (pets / cars
/ food) with toy 3-D embeddings already baked in. The pack should
recover the three clusters perfectly and surface each doc's nearest
siblings.

**Data** (`data.csv`, 15 rows): `doc_id, topic_truth, text, embedding`.
The `embedding` column is JSON-array text — `semantic_cluster` and
`nearest_neighbors` both auto-parse that form.

## What the flow shows

```
ds ─┬─→ semantic_cluster(k=3)        → cluster column 0/1/2 should match topic_truth
    └─→ nearest_neighbors(k=2)       → long-form (source, neighbour, distance, rank)
```

After the flow:
- `cluster` column on each row matches its `topic_truth` (modulo cluster IDs)
- `nearest_neighbors` output: 30 rows (15 × 2 neighbours), with each
  doc's neighbours from the same topic at distances near 0.

## In production

Replace the pre-baked `embedding` column with output from the built-in
`embed_text` step (which calls a sentence-transformer or OpenAI embed
endpoint). The pack steps work the same way — they just see real
high-dimensional vectors.

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py embedding_search
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".
