# Proposal: AI assistant (tabled — design notes only)

> **Status:** TABLED, not scheduled. This is a design record from a working session in May 2026, kept here so future contributors (and future-me) can pick up where it left off. **Nothing in this document is implemented yet.**

## The idea in one sentence

Add an optional AI layer to DIG that helps users (a) build pipelines from natural language, (b) generate custom transform steps and connectors on demand, and (c) explain / fix existing pipelines — with a **pluggable provider** model that defaults to a **local LLM** so the OSS / self-hosted ethos is preserved.

## Why this matters for DIG specifically

The visual data-preparation field (Trifacta, Alteryx, KNIME, OpenRefine, dbt, Airbyte) is being leapfrogged by AI-assisted competitors (dbt-ai, Hex Magic, Snowflake Cortex, Coalesce AI Builder). Most existing tools were architected before LLM-assisted code generation was a thing, and their plugin systems are too heavy (Java/OSGi for KNIME, .NET SDKs for Alteryx) to be AI-writable.

**DIG's plugin architecture is unusually well-suited to AI generation:**

- Each plugin is self-contained (one folder, ~50 lines of Python + a JSON manifest) — perfect token budget for LLM generation.
- The contract is explicit (`Step` base class, JSON Schema for the manifest) — model can be prompted with the exact shape of valid output.
- 46 existing steps + 8 connectors are training examples that can be passed as few-shot context.
- The result is reviewable before activation — the AI writes to `plugins/_pending/`, the user sees the diff with syntax highlighting, clicks "install" or "discard".

This is the Cursor / Copilot pattern applied to a visual data-preparation tool. None of the OSS competitors do it.

## Architecture: pluggable provider

Settings → AI section, three radio buttons:

```
○ Local (recommended)
  endpoint: http://localhost:11434/v1     ← Ollama, llama.cpp, vLLM all speak this
  model:    gemma4:e4b                    ← user-pickable from `ollama list`

○ OpenAI-compatible (bring your own key)
  endpoint: https://api.anthropic.com/v1  ← or OpenAI, Groq, OpenRouter, Together, …
  model:    claude-haiku-4-5
  api_key:  ●●●●●●●●

○ Disabled
  (no AI features in the UI)
```

One client speaks the OpenAI API spec; everything else is an endpoint URL. Same client code talks to Anthropic (via their compat endpoint), OpenAI, Groq, OpenRouter, Together, vLLM, llama.cpp, LiteLLM, Ollama. Implementation: ~50 lines of HTTP + JSON.

## Recommended default model: Gemma 4 E4B

Released ~April 2026 (https://ollama.com/library/gemma4). Verified specs from the Ollama page:

| Metric | Value | Why it fits DIG |
|---|---|---|
| **Parameters** | 4.5B effective (8B with embeddings) | Sweet spot — more capable than 3-4B class, smaller than 12-14B |
| **File size** | 7.2 GB | Fits 16 GB Macs with massive headroom for OS + DIG + DuckDB |
| **Context window** | 128K tokens | Big enough to fit pipeline doc + step library + sample rows in one prompt |
| **Branding** | Google "Edge Models" line | Tuned for laptop/mobile inference — Apple Silicon Metal acceleration should be excellent |

### Tier list of alternates

| Pick | Model | When to use |
|---|---|---|
| **Default** | **Gemma 4 E4B** | First-install experience; works on any 16 GB+ Mac |
| **Smaller fallback** | **Gemma 4 E2B** (~7.2 GB on Ollama, may be smaller in higher quant) | Older / less-RAM machines, or as a "fast mode" |
| **Coder specialist** | **Qwen 2.5 Coder 14B** (~8.5 GB, Apache 2.0) | Plugin/connector generation specifically — coding models still beat generalists for code |
| **Power user** | **Gemma 4 31B Dense** (20 GB) | 32 GB Macs and up; best local quality |
| **Cloud BYOK** | OpenAI-compat to Anthropic / OpenAI / Groq / etc. | Best quality, when user has an API key |

### Open questions to resolve before defaulting

1. **License verification.** Gemma 3 used the "Gemma Terms of Use" — permissive but custom (commercial OK, attribution required, no using outputs to train competing models). Gemma 4 almost certainly follows the same template. **For DIG's purpose this is fine** (we'd be using it to assist users, not training a competitor model), but the install flow should show users a "Accept Gemma terms" gate the first time they pull the model. Verify the actual license text before shipping.

2. **Structured-output reliability.** Suggest-next-step and generate-plugin-code both need the model to emit clean JSON / valid Python. Run a 20-prompt eval on E4B before committing — count parse failures, manifest-validation failures, lint failures.

## Use cases

| Capability | Prompt shape | Output | Complexity |
|---|---|---|---|
| **Suggest next step** | Pipeline doc + sample rows + user intent | JSON list of `{step_id, params}` to drop into the canvas | Low |
| **Explain this pipeline** | Pipeline doc | Markdown narrative ("This pipeline filters customers active in the last 30 days, then…") | Low |
| **Fix this expression** | Broken predicate + DuckDB error message | Suggested correction | Low |
| **Auto-cast suggestion** | Column profile + sample values | Recommended `cast_type` step with target type + reason | Low |
| **Generate transform step** | Natural language description + schema | New `plugins/<id>/manifest.json` + `step.py` | High |
| **Generate connector** | URL + auth spec + sample response | New `connectors/<id>/manifest.json` + `connector.py` | High |

## Safety wrinkle

DIG already has [`assert_safe_expr`](../../backend/dig/engine/step.py:194) that blocks `attach`, `copy`, `read_csv_auto('s3://…')`, etc. in user-authored expressions. **AI-generated step code needs equivalent protection** — actually stronger, since now it's generating Python, not just SQL fragments. Two layers of defense:

1. **Static lint pre-install.** Parse the generated `.py`, reject anything that imports `os.system`, `subprocess`, `socket`, or hits the DuckDB IO function denylist.
2. **User-confirms-install gate.** The AI never auto-registers a plugin. It writes to `plugins/_pending/`, the UI shows the diff with syntax highlighting, the user clicks "install" or "discard". No silent activation.

Generated-connector is more sensitive than generated-step because it touches the network. Default to a sandboxed test fetch ("preview the first 10 rows from your URL") before allowing the connector into pipelines.

## Suggested rollout order

When this is un-tabled, the natural sequence is:

1. **Pluggable AI provider settings + OpenAI-compat client** (1 week) — the foundation; nothing user-facing yet.
2. **"Suggest next step" feature** (3 days) — cheapest demo of value; shows up as a button in the step strip.
3. **"Explain this pipeline"** (1 day) — generates a Markdown description that lives next to the pipeline; useful for docs + handoff.
4. **"Fix this expression"** when an expression is invalid (2 days) — high-conversion feature; shows up exactly when users are stuck.
5. **Generate transform step** from natural language (1 week) — the wow feature; needs the safety lint + diff-review UI.
6. **Generate connector** from a URL spec (1 week) — opens the addressable-source aperture massively.

A "spike" before committing fully: install Ollama + Gemma 4 E4B, write the OpenAI-compat client (~50 lines), and prove the suggest-next-step prompt works end-to-end. Could be done in an afternoon, then we know whether to commit to E4B as the default before building out the full feature set.

## Why now (competitive landscape, May 2026)

Recent moves in the field:
- **dbt-ai** — natural language to dbt models
- **Hex Magic** — embedded LLM in Hex notebooks
- **Snowflake Cortex** — LLM functions as SQL primitives
- **Coalesce AI Builder** — visual pipeline assistant
- **Quadratic** — LLM-aware spreadsheet

OSS visual data-preparation tools (KNIME, OpenRefine) have **not** moved on this. DIG is uniquely positioned because of its plugin architecture (see "Why this matters" above) and its modern stack (Anthropic SDK / OpenAI SDK is a few lines in TypeScript).

The window for "first OSS visual data-preparation tool with a proper LLM assistant" is open and hasn't been claimed yet.
