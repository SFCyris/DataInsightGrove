# Glossary

A short tour of the words DIG uses for its building blocks. If you've used a spreadsheet, a SQL editor, or any visual ETL tool, most of this will land quickly — the names are deliberately plain.

## Quick reference

| Term         | One-liner                                                                       |
|--------------|---------------------------------------------------------------------------------|
| **Dataset**  | An imported file or external source — the rows-and-columns input to your work.  |
| **Connector**| The plugin that knows how to read or write a particular format or system.       |
| **Pipeline** | A graph of steps that takes one or more datasets and produces an output.        |
| **Step**     | One transformation inside a pipeline — filter, cast, group, join, derive, etc.  |
| **Profile**  | The per-column statistics DIG computes on ingest (types, nulls, distincts, …).  |
| **Sample**   | The subset of rows used for in-browser live preview while you edit.             |
| **Hint**     | A rule-based suggestion shown in the editor's side panel.                       |
| **Run**      | One backend execution of a pipeline. Runs write results to disk.                |
| **Output**   | What a pipeline writes when run — Parquet by default, plus any sinks you add.   |
| **Schedule** | A cron expression that runs a pipeline automatically on a cadence.              |
| **Lineage**  | Optional per-row source tracing — click 🔍 to see which input row(s) made it.    |
| **Module**   | A reusable, packaged sub-pipeline you can drop into a larger pipeline.          |
| **Sub-pipeline** | A pipeline published as a reusable step (`metadata.publishedAsStep`). Appears in every other pipeline's picker as `pipeline:<id>`. See [SUB_PIPELINES.md](SUB_PIPELINES.md). |
| **Checkpoint** | A labelled save (`💾 Save`) that survives autosave history pruning. The version you intend to come back to. See [SAVE_AND_VERSIONS.md](SAVE_AND_VERSIONS.md). |
| **Sampling** | Per-pipeline setting (head / tail / random / systematic) controlling how the editor preview draws rows from the pipeline output. See [SAMPLING.md](SAMPLING.md). |
| **Pinned etag** | The specific source-pipeline version a sub-pipeline consumer is locked to. Bumped via the **⬆ Upgrade to vN** button on the wrapper node. |
| **Exposed param** | A node parameter declared (via the 🪆 expose pill) as customisable from outside when the pipeline is published as a reusable step. |

## In a bit more detail

### Dataset
Your imported data. CSV, TSV, Excel, JSON, Parquet, Feather, generic delimited text (`.dat`, `.data`, `.tab`, `.psv`), and a handful of scientific binary formats (NumPy, HDF5, MATLAB, NetCDF, FITS) are recognised out of the box. Drop a file onto the Datasets page and DIG profiles every column so you know what you're working with before writing a single transform. Datasets live in your local `~/.local/share/dig/` folder — DIG never uploads them anywhere.

### Connector
Each file format and external system (REST API, JDBC, Postgres, MySQL, SQLite, …) is implemented as a small **connector** plugin. A connector is a folder under `backend/connectors/` containing one Python file and one JSON manifest — that's the whole contract. Drop in your own and DIG picks it up on next start. See the [authoring guide](AUTHORING_GUIDE.md) for how to write one.

### Pipeline
A directed graph of steps that consumes one or more datasets and produces output. Pipelines are *portable* — they're stored as a small JSON document (`.dig.json`) you can commit to git, share, or replay against a different dataset of the same shape. See the [pipeline format](PIPELINE_FORMAT.md) for the schema.

A pipeline always describes *what* to do, never *where* to run it. The same pipeline runs in your browser (DuckDB-WASM, instant preview) or on the backend (DuckDB or Polars, full data) — you choose at run time.

### Step
A single transformation in a pipeline: keep some rows, change a column's type, group and aggregate, join two inputs, derive a new column from an expression, write to a file, train a model, render a chart. DIG ships ~50 steps (see the [step library](STEPS.md)) and you can drop in your own — same plugin shape as connectors, one folder, two files.

### Profile
On ingest, DIG runs every column through a quick stats pass: physical type, null fraction, distinct count, min/max for numbers, top values, distribution. The profile feeds the column header tooltip, the cast-type smart picks, and the **Hints** panel. It also drives the auto-detection of *meta-types* — columns that look like emails, URLs, currencies, vectors, geographic coordinates, etc., even when they're stored as plain strings or numbers.

### Sample
The pipeline editor recomputes a live preview on every change. To stay snappy, that preview runs on a **sample** of your data (default 100,000 rows) inside DuckDB-WASM in your browser. The full dataset only gets touched when you click **Run on backend**. The status strip below the live grid always shows which sample size is in use, so you know what you're looking at.

### Hint
The right-side **Hints** panel shows deterministic, rule-based observations from the column profile — *"this column is 30% null — drop nulls?"*, *"these two columns look like (lat, lon) — pack and cast to geographic"*. Hints are not predictions and not ranked AI suggestions; they're a calm "by the way…" surface that proposes one specific step you can apply with one click.

### Run
A **run** is one execution of the whole pipeline on the backend over the full dataset. Runs happen as background jobs (you can navigate away and come back), produce Parquet outputs by default, and surface progress + logs in the side panel. Past runs are listed under the **Run history** menu — click any one to view its output, artifacts, and lineage.

### Output
What a pipeline writes when run. By default DIG writes Parquet to your local data directory; you can also configure other **sinks** (write to a file in another format, push to a database, post a webhook, render a chart, save a plot). Outputs are first-class citizens of the pipeline document — they're versioned with the rest of the steps.

### Schedule
A pipeline can be scheduled to run automatically using a standard cron expression (`0 6 * * *` etc.). Open **Schedules** to add, list, pause, or trigger a scheduled pipeline manually. Schedule history shows every triggered run with its outcome.

### Lineage
Optional per-row source tracing. When you turn on **🔍 lineage** in the pipeline editor, the run records which input row(s) each output row came from. After the run, the **Lineage** tab on the right shows a 🔍 button on each output row — click it to jump back to the source row in the original dataset. Adds ~10–30 % to run time and a bit of storage; off by default.

### Module
A pipeline you've packaged for reuse. Drop a module into another pipeline as a single node and DIG runs it inline like any other step. Modules let you build up a small library of reusable patterns ("clean an address column", "compute revenue per tier") without copy-pasting steps between pipelines.

---

For the file-format and architecture vocabulary (parquet caches, the `.dig.json` schema, the WASM/backend split, etc.), see [`ARCHITECTURE.md`](ARCHITECTURE.md). For the step catalogue, see [`STEPS.md`](STEPS.md).
