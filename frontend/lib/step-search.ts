// ─────────────────────────────────────────────────────────────────
// Intent-ranked search for the step picker.
//
// Substring-matching alphabetically is the typical first cut for a
// command palette and it scales badly: 80 steps in, "filter" matches
// `filter_rows`, `unfilter_x`, `bin_numeric` (because of "filter"
// elsewhere in the description), and the user has to scan. Ranking
// fixes that by giving each match a numeric score and sorting.
//
// Score sources, from strongest to weakest signal:
//
//   1. EXACT id / label / alias                 +1000
//   2. PREFIX of id / label / alias             +600
//   3. PREFIX of any token in label / alias     +400
//   4. SUBSTRING of id / label / alias          +250
//   5. SUBSTRING of description                 +80
//   6. SUBSTRING of tag                         +40
//
// Plus a recency boost (most-recent → +100, decaying), and a small
// penalty for steps whose `requires` aren't satisfied by the upstream
// schema so compatible matches surface above incompatible ones (the
// incompatible matches still appear, just lower).
//
// `rankSteps` returns the input list sorted desc by score. When the
// query is empty, we keep the input order (recency-then-grouped is the
// caller's responsibility, since the visual layout is category-based).
// ─────────────────────────────────────────────────────────────────

import type { StepManifest } from "./api/client";
import type { RequirementResult } from "./step-requirements";

export interface RankInputs {
  steps: StepManifest[];
  query: string;
  /** Most-recent first. ids beyond the first ~6 get diminishing boost. */
  recent?: string[];
  /** Map keyed by step id. When a step's req is not ok, it's penalised. */
  reqsByStep?: Record<string, RequirementResult>;
}

export interface RankedStep {
  step: StepManifest;
  score: number;
}

const W_EXACT     = 1000;
const W_PREFIX    = 600;
const W_TOK_PFX   = 400;
const W_SUB       = 250;
const W_DESC      = 80;
const W_TAG       = 40;
const W_RECENT    = 100;
const W_INCOMPAT  = -300;

/** Tokenise on word boundaries — handles snake_case, kebab-case, spaces. */
function tokens(s: string): string[] {
  return s.toLowerCase().split(/[^a-z0-9]+/g).filter(Boolean);
}

function scoreOne(step: StepManifest, q: string): number {
  // The query may be a multi-word phrase ("missing values"). Score each
  // sub-query, sum the maxes — phrase boost: if the literal phrase
  // appears in a strong field (label/alias) we add a phrase bonus.
  const qTokens = tokens(q);
  const phrase = q.toLowerCase().trim();

  const id = step.id.toLowerCase();
  const label = step.label.toLowerCase();
  const desc = (step.description ?? "").toLowerCase();
  const aliases = (step.aliases ?? []).map((a) => a.toLowerCase());
  const tags = (step.tags ?? []).map((t) => t.toLowerCase());

  let score = 0;

  // Phrase scoring on strong fields. When the user types "data quality"
  // and an alias literally contains it, that's a hard signal.
  if (phrase) {
    if (id === phrase || label === phrase || aliases.includes(phrase)) {
      score += W_EXACT;
    } else if (id.startsWith(phrase) || label.startsWith(phrase) || aliases.some((a) => a.startsWith(phrase))) {
      score += W_PREFIX;
    } else if (id.includes(phrase) || label.includes(phrase) || aliases.some((a) => a.includes(phrase))) {
      score += W_SUB;
    }
  }

  // Per-token scoring picks up the union of meaningful matches across
  // the strong fields. We sum up per-token (not per-step) because a
  // multi-word query with two strong matches should outrank a one-word
  // query that fully matches.
  for (const t of qTokens) {
    if (!t) continue;
    let best = 0;

    if (id === t || label === t || aliases.includes(t)) best = Math.max(best, W_EXACT);
    if (id.startsWith(t) || label.startsWith(t) || aliases.some((a) => a.startsWith(t))) {
      best = Math.max(best, W_PREFIX);
    }
    // Token-prefix on label/alias word boundaries — "summ" matches
    // "summarize" inside an alias even when the alias is multi-word.
    const labelToks = tokens(step.label);
    const aliasTokSets = aliases.map(tokens).flat();
    if (labelToks.some((lt) => lt.startsWith(t)) || aliasTokSets.some((at) => at.startsWith(t))) {
      best = Math.max(best, W_TOK_PFX);
    }
    if (id.includes(t) || label.includes(t) || aliases.some((a) => a.includes(t))) {
      best = Math.max(best, W_SUB);
    }
    if (desc.includes(t)) best = Math.max(best, W_DESC);
    if (tags.some((tg) => tg.includes(t))) best = Math.max(best, W_TAG);

    score += best;
  }

  return score;
}

/**
 * Rank step manifests by intent against `query`. Stable sort: when
 * scores tie, steps keep their input order — the caller is expected
 * to pre-sort by category for the empty-query case.
 */
export function rankSteps({ steps, query, recent = [], reqsByStep }: RankInputs): RankedStep[] {
  const q = query.trim();
  const recentBoost = (id: string): number => {
    const idx = recent.indexOf(id);
    if (idx < 0) return 0;
    // Linear decay across the first 6 — newest worth full boost, the
    // sixth-most-recent worth ~17%. After that, none.
    if (idx >= 6) return 0;
    return Math.round(W_RECENT * (1 - idx / 6));
  };
  const compatPenalty = (id: string): number => {
    const r = reqsByStep?.[id];
    return r && !r.ok ? W_INCOMPAT : 0;
  };

  const ranked: RankedStep[] = [];
  for (let i = 0; i < steps.length; i++) {
    const s = steps[i];
    const base = q ? scoreOne(s, q) : 0;
    // When there's no query, only the recency + compat boosts speak;
    // we still return them so callers can use the sorted list for the
    // "recent" rail without computing it twice.
    const score = base + recentBoost(s.id) + compatPenalty(s.id);
    ranked.push({ step: s, score });
  }

  // Stable sort by descending score. JS's sort is stable since ES2019.
  ranked.sort((a, b) => b.score - a.score);

  if (q) {
    // Drop noise: a query was typed and the step scored zero on every
    // signal — it isn't a match, just keep it out.
    return ranked.filter((r) => r.score > 0);
  }
  return ranked;
}
