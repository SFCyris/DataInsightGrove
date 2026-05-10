# ✨ AI features in DIG

DIG ships an optional AI assistant that runs against any
OpenAI-compatible endpoint — local Ollama by default, or
bring-your-own-key for Anthropic, OpenAI, Groq, OpenRouter, etc. All
AI features degrade gracefully when AI is disabled (Settings → AI),
so the editor stays useful even on a fully offline setup.

This doc covers the **five AI surfaces** in the editor. Configuration
lives in [Settings → AI](#configuration); see also the
**[Settings reference](#settings-reference)** at the bottom.

| Feature | Where it appears | Trigger | Cost |
|---|---|---|---|
| ✨ Explain pipeline | toolbar | click | one chat call |
| 🔍 Review pipeline | toolbar | click | one structured chat call |
| 📖 Explain dataset / step output | Hints panel (focus any node) | click | one chat call |
| 🛤 Suggest steps | Hints panel (focus any node) | click | one chat call |
| ✨ Suggest visualizations | Hints panel (focus any node) | click | one chat call |
| 🔧 Suggest fix (expression errors) | inline on broken nodes | click | one chat call |
| ✨ Generate connector / step | wizard pages | click | one chat call + safety lint |

All five "Hints panel" cards use the **same lineage signals** so
they reach the same conclusion about the focused node's domain:

1. **Sample values** — for a registered dataset these come from the
   cached profile (top-3 per column); for any derived step the
   backend runs the focused node's output through the pipeline's
   chosen sampling method (`metadata.sampling`, head / random / etc.)
   and harvests top-N from the actual rows. Sample harvesting lives
   in `backend/dig/ai/node_context.py`.
2. **Source URI** — filename + scheme often gives the game away
   (`exoplanet-survey.csv`, `claims_2024_q3.parquet`). Walked back
   from the focused node to its root dataset.
3. **Connector** — JDBC clinical trials vs. CSV marketing OKRs.
4. **Dataset name + project name** — operator-supplied labels.
5. **Schema** — column names + types as a baseline. For derived
   nodes this is the schema *at the focused node's output*, not the
   raw dataset's.

**Applied-steps chain.** When the focus is a derived step, an
additional block is sent to the LLM listing the step labels + key
params from the upstream dataset to the focused node. The
`📖 Explain` prompt is rephrased for derived contexts to ask "given
the original dataset and these applied steps, what does the current
output represent?" — so an aggregated grouping doesn't get described
as if it were the raw rows.

### Apply mid-chain → branch automatically

Applying a 🛤 route or ✨ viz suggestion while focused on a step
that *already has downstream successors* would silently re-wire those
successors through the new node — almost never what the user
wanted. Instead, the editor uses `branchStepAfter` for the first
inserted step (no successor re-wiring), and continues linearly off
the new branch for the rest of the route. The toast wording reflects
which path was chosen (`Branched 3 steps off "<focused label>"` vs.
`Added 3 steps`). When the focused node has no successors, the
linear-insert path is used as before — both behaviors live in
`frontend/app/pipelines/[id]/page.tsx` (`insertStepAfter`,
`branchStepAfter`, `hasSuccessors`).

## 📖 Explain dataset

Click the card on a focused dataset:

```
┌─ AI DATASET EXPLANATION ───── looks like: Industrial IoT ─┐
│                                                            │
│  [ 📖 Explain this dataset (domain + columns)     ~3s  ]  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

The LLM returns a domain-aware narrative + per-column meanings.
Example output for the Factory telemetry dataset:

```
Industrial IoT / Manufacturing Telemetry                [high]

This dataset captures detailed telemetry readings from a factory's
manufacturing process over time. Each record represents a snapshot
of operational conditions, including machine performance metrics,
environmental readings, and production output. It is used to
monitor efficiency, detect potential defects, and analyze the
correlation between operational parameters and quality control.

KEY COLUMNS
  ts                    — Timestamp indicating when the recorded
                          measurements were taken.
  line_id               — The specific production line where the
                          measurements were recorded.
  machine_id            — The unique identifier for the machine
                          generating the data.
  cycle_time_s          — The time taken (in seconds) to complete
                          one production cycle.
  units_produced        — The number of units successfully produced
                          during the measurement interval.
  defect_count_running  — The cumulative count of defects observed
                          up to this point.
  is_defect_event       — A boolean flag indicating if a defect was
                          detected during this cycle.
  defect_type           — The category of the defect found (e.g.,
                          surface, assembly).
  power_kwh             — The electrical power consumed by the
                          machine (in kilowatt-hours).
                                                via gemma4:latest
```

The **confidence pill** ("high" | "medium" | "low") tells you how
strongly the model thinks it nailed the domain. Low confidence is a
useful signal — generic column names like `id, name, value` won't
yield much, and the model should say so rather than hallucinate.

When the LLM returns no usable content, the card shows:

> 🤔 No suitable domain or visualization identified.
>
> The model couldn't infer a confident topic from these column names
> + sample values. Try renaming columns to more descriptive terms,
> or click ↻ to re-ask.

## 🛤 Suggest steps

Click the card on a focused dataset:

```
┌─ AI STEP SUGGESTIONS ──── for: Industrial Machine Telemetry ─┐
│                                                                 │
│  [ 🛤 Suggest transform routes for this dataset       ~3s  ]   │
│                                                                 │
│  ▸ Optional: tell the AI what you want to discover…             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

Returns 1-3 **routes** — each a small ordered chain of 1-4
transformation steps that together yield a meaningful derived
dataset. Each route has a confidence rating, a rationale, and an
**Apply route** button that inserts ALL the steps in order. Example:

```
┌─────────────────────────────────────────────── high ─┐
│ Analyze operational efficiency and identify          │
│ potential failure modes.                             │
│                                                       │
│ By calculating rolling averages and identifying      │
│ correlations between physical metrics and defect     │
│ rates, we can build predictive models for machine    │
│ failure.                                             │
│                                                       │
│ 1. ⏱ Rolling window  →  Rolling averages of key      │
│    Calculate a 3-period rolling average for power,   │
│    temperature, and vibration to smooth noise.       │
│                                                       │
│ 2. 🔣 Math equation   →  Single composite stress     │
│    Create a composite stress index by weighting and  │
│    combining the smoothed physical metrics.          │
│                                                       │
│ 3. 🔬 Correlation matrix → Correlation matrix +     │
│    Determine the statistical relationship between   │
│    the calculated stress index and the observed     │
│    defects or cycle time variations.                │
│                                                       │
│           [ ✓ Apply route (3 steps) ]                │
└──────────────────────────────────────────────────────┘
```

The route gets inserted into the pipeline as a chain — step N's
output feeds step N+1. Useful for "I have data X, what's
analytically interesting to do with it" exploration.

The optional goal box lets you steer the model: "find groups of
similar records", "detect anomalies", "build a forecast", etc.

## ✨ Suggest visualizations

Click the card on a focused dataset:

```
┌─ ✨ AI VIZ SUGGESTIONS ──────── looks like: factory telemetry ─┐
│                                                                  │
│  [ ✨ Suggest visualizations for this dataset        ~2s  ]    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

Returns 1-3 chart suggestions, each pre-populated with the right
column choices for that domain. Example for retail data:

```
┌────────────────────────────────────────────── high ─┐
│ Sales trend with seasonality                        │
│ Line chart of weekly_sales over week — surfaces    │
│ the holiday spikes and trend at a glance.          │
│                                                     │
│ kind=line · x=week · y=units_sold                  │
│           [ ✓ Apply ]                              │
└─────────────────────────────────────────────────────┘
```

Each suggestion's **Apply** button inserts the corresponding
visualization step (`export_to_image`, `pareto_chart`, `funnel_chart`,
…) with the suggested params already filled in.

When the LLM returns no usable content (factory-telemetry-style
specific column names sometimes confuse smaller models), the card
falls back to:

> 🤔 No suitable domain or visualization identified.

## ✨ Explain pipeline

Top-bar button. Generates a 2-4 paragraph plain-English description of
the pipeline as a whole, useful for documentation handoff or for
reviewing what an inherited pipeline actually does.

## 🔍 Review pipeline

Top-bar button. Returns severity-ranked findings (info / warn / high)
across these categories: performance, correctness, quality, lineage,
ergonomics. Each finding names the affected node ids and includes a
short explanation.

## 🔧 Suggest fix (expression-level)

When a node like `derive_column` or `filter_rows` has a broken
expression — typically a column-name typo or wrong type cast — the
error UI in the live preview gets a `🔧 Suggest fix` button. The LLM
sees the expression, the available columns, and the DuckDB error
message, and proposes a corrected expression with a confidence rating.
You preview the change inline before applying.

The button is **gated to expression-class errors only**. Errors that
originate upstream of the focused node — broken dataset registration
(`Error when sniffing file …parquet`), missing input wiring (`Table
"X" does not exist`), Polars-only step compiled for the browser
engine, etc. — set `humanized.originatesUpstream: true` in the SQL
error humanizer and the editor suppresses Suggest-fix on those. The
focused step's params can't repair an upstream problem; offering an
LLM "fix" there produces misleading results (the AI would mutate
unrelated params trying to satisfy an impossible request). The
recogniser lives in `frontend/lib/humanize-sql-error.ts`. New error
shapes that should disable Suggest-fix flip the same flag — no
gating logic change required at the page layer.

## ✨ Generate connector / step

Two wizard pages (`/connectors/new`, `/steps/new`) that ask the LLM to
generate a complete plugin folder (manifest + Python). The output goes
through a **safety lint** before it can be installed:

- Allowed Python imports only (no `os`, `subprocess`, network calls
  outside `httpx`).
- No file-system writes outside the plugin folder.
- No `eval`, `exec`, `compile` of arbitrary strings.

Generated code is staged in `plugins/_pending/` and never auto-installed
— you review the code in-browser, then click **Install** which
re-lints server-side before promoting. See
[PLUGIN_AUTHORING.md](PLUGIN_AUTHORING.md) for the full safety model.

## 🛡 Four-layer AI defense

Every AI feature in DIG (the seven listed in the table above) routes
through the same four-layer pipeline before its output reaches you.
This is a **global rule set** — adding a new AI feature means wiring
it into all four layers, not bypassing any.

### Layer 1 — Better prompt

System prompts include the shared
**[`PRINCIPLES_BLOCK`](../backend/dig/ai/prompts.py)** so the model
gets the same upfront rules everywhere it emits a step suggestion:

- Fill **every** required param (no blanks, no empty arrays).
- Use **meaningful, data-aware names** for output columns
  (`cl_to_cd_ratio`, not `derived_0`).
- Use **meaningful titles + rationales** that reference the actual
  columns, not generic boilerplate ("Linear regression.").
- **Match types** — numeric ops on numeric columns, temporal on
  dates; skip the suggestion if the schema doesn't fit.

Tightening the upstream prompt means the validate+repair layer has
less to fix.

### Layer 2 — Validate + repair

Every step suggestion runs through
**[`validate_and_repair_step`](../backend/dig/ai/repair.py)** before
reaching the UI. Per-step rules:

| Step | Repair |
|---|---|
| `group_aggregate` | Empty `aggregates` → row-count using first `groupBy` column |
| `derive_column`   | Auto-name from referenced columns; drop if no expression |
| `rolling`         | Fill default window/fn; auto-name `as` field |
| `linear_regression` | Auto-name `predicted_column` + `residual_column` |
| `forecast` / `seasonal_decompose` | Default `horizon=12` / `period=12` if missing |
| `cast_type`, `select_columns`, `sort_rows`, `rename_columns`, … | Drop on missing required field |

The contract is **conservative repairs only**: we never invent
free-text fields the user has to author (filter predicates, derive
expressions). Returning `None` means "drop this step" — and for
multi-step routes (`suggest_pipeline_steps`), one `None` drops the
**whole route** rather than serving a half-broken "Apply (3 steps)"
button.

### Layer 3 — Robust parsing

JSON parsing is centralised in
**[`parse_json_lenient`](../backend/dig/ai/parsing.py)** and handles:

- prose-around-JSON ("Sure! Here's the suggestion: { … }")
- Markdown code fences (` ```json … ``` `)
- Trailing prose after the closing brace
- Trailing commas

Token budgets live in **[`TOKEN_BUDGETS`](../backend/dig/ai/prompts.py)**
sized for each feature's expected output. Lower budgets cause
truncated JSON which the lenient parser can't always rescue, so the
table is the source of truth — change the budget there, not inline.

Every JSON-emitting feature also runs a **two-phase chat**: first
attempt with `response_format=json_object`, on empty-message fall
back without the constraint. Some local models (older Ollama
quantizations) return empty content when the structured-output
enforcement is on — the second attempt usually recovers them. Both
empty → the feature surfaces a graceful "no suggestion" result
rather than a stack trace.

### Layer 4 — Backend covers all paths

The dispatcher's runtime executes a "valid" suggestion regardless of
which engine each step uses (DuckDB-WASM in the browser, DuckDB on
the backend, Polars). Mixed-engine pipelines (a SQL terminal with
Polars ancestors, or vice versa) are materialised transparently via
`materialize_polars_ancestors` + `compile_to_sql(overrides=…)`.

This means a suggestion that *passes* layers 1–3 always *renders* —
the user never sees a "this step doesn't have a live preview" dead
end because the AI picked a step that runs server-side.

### Adding a new AI feature

Wire each layer:

1. Import `PRINCIPLES_BLOCK` from `dig.ai.prompts` and inject it
   into your system prompt (only if the feature emits step
   suggestions or column-level metadata).
2. After parsing, route every emitted step through
   `validate_and_repair_step`. Drop suggestions that return `None`.
   For multi-step output, drop the whole route on a single `None`.
3. Use `parse_json_lenient` instead of `json.loads`. Add an entry
   to `TOKEN_BUDGETS` sized for your expected output. Wrap the
   `chat()` call in the two-phase empty-message fallback.
4. If your feature emits step suggestions, ensure they go through
   the dispatcher's normal execution path — don't shortcut around
   the engine-selection logic.

## Configuration

Settings → AI Assistant. Six fields:

| Field | What it does |
|---|---|
| **Enable AI assistant** | Master switch. Off = no AI surfaces in the UI. |
| **AI provider** | `local` (Ollama-style) or `openai_compat` (BYOK Anthropic / OpenAI / etc.) |
| **Endpoint URL** | OpenAI-compat `/v1` base. Default `http://localhost:11434/v1` (Ollama). |
| **Model** | **Real `<select>` dropdown** populated from the endpoint's `/models` endpoint. Includes a "✏️ Custom…" option that flips to a text input for models you haven't pulled yet. |
| **API key** | Bearer token. Local Ollama doesn't need one. Stored masked in the settings DB. |
| **Max output tokens** | Default 4096. Higher = more verbose explanations. |
| **Temperature** | Default 0.0 (deterministic). 0.7 = creative. |
| **Ping interval (seconds)** | When > 0, the UI sends a tiny ping to the LLM every N seconds to keep it loaded in memory. **5 seconds** is a safe default for local Ollama which unloads idle models. **0** = off (the default). |

### About the model dropdown

The model field used to be a free-text input that browsers sometimes
treated as a password field (Firefox's heuristic, neighbouring an
actual password input). It's now a real `<select>` populated from the
configured endpoint's `/models` listing — no more autofill, no more
inline suggestion strip, real keyboard semantics.

If your endpoint doesn't expose `/models` (rare; only some self-hosted
proxies skip it) the field falls back to a plain text input.

If you want a model that isn't in the dropdown (e.g. you haven't run
`ollama pull` yet for a new release), pick **✏️ Custom…** at the
bottom of the dropdown — it switches to a text input so you can type
the exact model id.

### About the keep-alive pump

The frontend includes a tiny background component (`<AiKeepalive />`)
that sends `POST /ai/probe` every `ai_ping_interval_s` seconds when
the setting is non-zero. The probe is a 1-token chat call so it's
essentially free, but it keeps Ollama from unloading the model after
its idle timeout (default 5 min). Without it, the first AI request
after a coffee break stalls for 30-60 seconds while the model reloads.

The pump pauses automatically when the tab is hidden (Page Visibility
API) so background tabs don't burn CPU.

## Test connection

Settings → AI → **🔌 Test connection** sends a `ping → pong` round-trip
and reports the latency + the model that replied. Use this after
changing the endpoint, the model, or pulling a new local model:

> ✓ gemma4:latest replied: pong  (412ms)

If you see:

> ✗ AI provider unreachable at http://localhost:11434/v1: …

Check that Ollama is running (`ollama serve` or open the menubar app)
and the model is pulled (`ollama list`). The error message points at
the URL it tried.

## Settings reference

Stored in DIG's local SQLite settings table; nothing leaves your
machine unless you point the endpoint at a cloud API.

```
ai_enabled            : bool, default false
ai_provider           : "local" | "openai_compat" | "disabled"
ai_endpoint           : URL, default "http://localhost:11434/v1"
ai_model              : model id, default "gemma4:e4b"
ai_api_key            : secret, default ""
ai_max_tokens         : int, 64..131072, default 4096
ai_temperature        : float, 0.0..2.0, default 0.0
ai_ping_interval_s    : int, 0..600, default 0
```

## Quick start: local Ollama

1. Install Ollama: `brew install ollama` (macOS) or
   [ollama.com/download](https://ollama.com/download).
2. Start the server: `ollama serve` (or just open the menubar app).
3. Pull a model: `ollama pull gemma4:e4b` (~7 GB, 128K context).
4. In DIG: Settings → AI Assistant → set provider = **local**,
   endpoint stays at the default, model = **gemma4:e4b**, enable.
5. Click **🔌 Test connection** — should reply "pong" in under a second.
6. Open a pipeline, focus any node (dataset OR step), expand the
   Hints panel — the three AI cards (📖 / 🛤 / ✨) are now active.
   On a derived step the cards retitle to "this step's output" and
   the AI sees the actual sampled output rather than the raw dataset.

## Empty-message recovery

Local LLMs (especially older quantizations) sometimes return an empty
message when the `response_format=json_object` constraint is on. **All
JSON-emitting AI features** (the seven in the table above, except
the prose-only "Explain pipeline") **retry once without the
constraint** before surfacing an error — see
[Layer 3](#layer-3--robust-parsing) above for the detail. Both empty
→ the card shows the friendly "no suitable domain identified"
surface instead of a stack trace.

If you hit this consistently with one model but not another, it's
usually fixable by switching to a slightly larger quantization
(`gemma4:e4b` → `gemma4:q4_K_M`).
