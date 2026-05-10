**When to use:** factor a reusable transform out of one pipeline into its own pipeline, then call it from many. Encourages the same testability + ownership boundaries you'd get from a function in code.

**Example:** a "clean customer events" pipeline (filter test users, dedupe by event_id, attach country from IP) is referenced from a "weekly retention dashboard" pipeline and a "monthly cohort" pipeline.

```json
{
  "step": "subpipeline",
  "params": {
    "pipeline_id": "01J5VWPFKZTB6X2K3D8X4MN7CY",
    "output_id": "o_clean"
  }
}
```

To get the inner pipeline's id, open it in the editor — the URL is `/pipelines/<id>`.

**Cycle detection:** DIG tracks the call chain through `PolarsContext.pipeline_chain`. A pipeline that recursively references itself (directly or via a chain) raises immediately rather than spinning forever.

**Tip:** combine with the `expectations` step to enforce a contract on every consumer — the inner pipeline emits a known schema; the outer one fails-fast if that contract is violated.
