# ✨ LLM augment

Use the configured AI provider as a column transformer.

## Steps

| Step | Purpose |
| --- | --- |
| `llm_classify`   | Assign each row to one of N labels (zero-shot or with examples) |
| `llm_extract`    | Pull structured fields out of free text into new columns |
| `llm_summarize`  | One-line / one-paragraph summary of a text column |

## Requirements

No extra Python packages. AI must be enabled in Settings → AI (Ollama,
OpenAI, or Anthropic).

## Cost note

Every row is one LLM call. Use `sample_rows` upstream when prototyping.

## Changelog

### 0.1.0 — 2026-05-05

- Initial release.
