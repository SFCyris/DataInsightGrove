# ✨ `llm_augment` · ticket triage

**Scenario:** customer-support inbox dump. Each ticket is free text; we
want an at-a-glance triage view.

**Data** (`data.csv`, 10 rows): `ticket_id, subject, body`.

## What the flow shows

```
ds → llm_classify(6-way category)
   → llm_extract(sentiment, urgency, blocker_yes_no, mentioned_competitor)
   → llm_summarize(<= 15 words)
```

Each row gains:
- `category` + `category_confidence` — bug / billing / feature_request /
  general_question / churn_risk / praise
- `sentiment`, `urgency`, `blocker_yes_no`, `mentioned_competitor`
- `summary` — one-line description suitable for a Slack alert or a
  standup-board card

## Cost note

Three LLM calls per row × 10 rows = 30 calls. With a local Ollama setup
this is free; with a cloud provider it's a few cents. Use `sample_rows`
upstream when prototyping on larger datasets.

## How to load

The fastest path — uploads the CSV, substitutes the placeholders in
`flow.dig.json`, and creates the pipeline:

```bash
python3 FunctionPacks/scripts/import_example.py llm_augment
```

It prints a `http://localhost:3100/pipelines/<id>` URL — open it.

If you'd rather build the flow by hand, see the index in
`examples/README.md` → "Manual recreation".
