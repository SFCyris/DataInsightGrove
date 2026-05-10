**When to use:** persist the result of your pipeline as a file on disk — CSV for humans, Parquet for downstream tools, Excel for stakeholders, NDJSON for streaming consumers.

**Example — CSV:**

```json
{
  "step": "export_to_file",
  "params": {
    "format": "csv",
    "path": "active-customers.csv"
  }
}
```

**Example — Parquet:**

```json
{
  "step": "export_to_file",
  "params": {
    "format": "parquet",
    "path": "daily-revenue.parquet"
  }
}
```

**Format trade-offs:**

| Format | Pros | Cons | Pick when |
|---|---|---|---|
| `csv` | universal, human-readable, opens in any tool | no types, big files, no nesting | sharing with humans / spreadsheets |
| `parquet` | columnar, typed, compressed (zstd default), fast | needs a parquet reader | feeding another data tool |
| `excel` | non-technical stakeholders | row limit (~1M), slow on large data | exec / finance handoffs |
| `json` | preserves nested structure | bulky | API mocks, document stores |
| `ndjson` | line-streamable, append-friendly | bulky | logs, queue feeds, kafka producers |

**Tip:** the path is resolved relative to the run output dir (`data/outputs/<run_id>/`). Use absolute paths only when you intentionally want to write outside that — e.g. into a share you've mounted.
