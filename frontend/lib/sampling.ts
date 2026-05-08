/**
 * Pipeline-level sampling methods.
 *
 * Each method maps to a SQL wrapper produced by `wrapWithSampling`
 * below; the wrapper is applied to the compiled pipeline SQL before it
 * runs in DuckDB-WASM (browser) or DuckDB (backend, via the Python
 * twin in `backend/dig/engine/sampling.py`). Adding a new method means
 * touching BOTH files in lockstep, plus the `SamplingDialog` UI here.
 *
 * Universal / first-tier (always available, no column required):
 *   - head:        first N rows — fastest; biased toward file start
 *   - tail:        last N rows — useful for time-series tail inspection
 *   - random:      uniform reservoir sample — representative; optional seed
 *   - systematic:  every Kth row — preserves ordering trends across data
 *
 * Distribution-aware (require a column or two):
 *   - stratified:  preserve the relative frequencies of a column's values
 *                  across the sample (90-year-old textbook method;
 *                  Neyman 1934). Best for imbalanced data — fraud,
 *                  churn, defects — where uniform random would under-
 *                  represent the rare class.
 *   - per_group:   N rows per distinct value of a column (equal
 *                  representation, NOT proportional). Useful for "5
 *                  examples per category" debugging, ML training, and
 *                  any cluster-cap workflow.
 *   - time_bucket: N rows per time bucket (day/hour/week/month) of a
 *                  temporal column. Crucial for log/event data where
 *                  head/tail/random all skew toward dense periods.
 *   - weighted:    sample with probability proportional to a numeric
 *                  column. Useful for revenue-weighted previews where
 *                  high-value rows should be over-represented.
 *   - bootstrap:   sample WITH replacement (rows can repeat). Standard
 *                  for statistical workflows + confidence-interval
 *                  bootstrapping; not a typical preview method.
 */

export type SamplingMethod =
  | "head"
  | "tail"
  | "random"
  | "systematic"
  | "stratified"
  | "per_group"
  | "time_bucket"
  | "weighted"
  | "bootstrap";

/** Time-bucket granularity for `time_bucket` sampling. Translated to
 *  DuckDB's `DATE_TRUNC` argument in the SQL wrapper. */
export type TimeBucket = "hour" | "day" | "week" | "month" | "quarter" | "year";

export interface SamplingConfig {
  method: SamplingMethod;
  /** Target row count. Universal across most methods (head / tail /
   *  random / stratified / weighted / bootstrap). For per_group and
   *  time_bucket, this is the per-group/per-bucket cap (`size` ≡ N). */
  size: number;
  /** Step for "every Kth row" (systematic). */
  everyN?: number;
  /** Seed for reproducible randomness — applies to random / stratified
   *  / weighted / bootstrap. */
  seed?: number;
  /** For `stratified`: column whose value distribution we preserve.
   *  For `per_group`:  column whose distinct values define the groups.
   *  For `weighted`:   numeric column used as the per-row weight. */
  column?: string;
  /** For `time_bucket`: temporal column to bucket by. */
  timeColumn?: string;
  /** For `time_bucket`: granularity of each bucket. */
  bucket?: TimeBucket;
}

/** Methods that need a column-name parameter. The dialog uses this to
 *  decide whether to show a column picker for the chosen method. */
export const METHODS_NEEDING_COLUMN: ReadonlySet<SamplingMethod> = new Set([
  "stratified",
  "per_group",
  "weighted",
]);

/** Methods that need a time column + bucket granularity. */
export const METHODS_NEEDING_TIME_COLUMN: ReadonlySet<SamplingMethod> = new Set([
  "time_bucket",
]);

export const SAMPLING_METHODS: Array<{
  id: SamplingMethod;
  emoji: string;
  label: string;
  blurb: string;
  /** Tier label shown in the picker — groups methods visually so
   *  newcomers see the universal four first, advanced ones below. */
  tier: "universal" | "distribution" | "statistical";
}> = [
  {
    id: "head",
    emoji: "🔝",
    label: "First N rows",
    blurb: "Fastest; biased toward the start. Default — same as a SQL LIMIT.",
    tier: "universal",
  },
  {
    id: "tail",
    emoji: "🔚",
    label: "Last N rows",
    blurb: "The end of the dataset. Useful for time-series 'most recent'.",
    tier: "universal",
  },
  {
    id: "random",
    emoji: "🎲",
    label: "Random uniform",
    blurb: "Each row equally likely. Best for representative previews of large datasets. Optional seed makes it reproducible.",
    tier: "universal",
  },
  {
    id: "systematic",
    emoji: "📐",
    label: "Every Nth row",
    blurb: "Regular cadence — every Nth row from start to end. Preserves any ordering trend across the dataset.",
    tier: "universal",
  },
  {
    id: "stratified",
    emoji: "⚖",
    label: "Stratified by column",
    blurb: "Preserve the column's value distribution in the sample. Best for imbalanced data — fraud, churn, defects — where uniform random would under-represent rare classes.",
    tier: "distribution",
  },
  {
    id: "per_group",
    emoji: "🗂",
    label: "N rows per group",
    blurb: "Equal representation per category, not proportional. Useful for '5 examples of each' debugging and ML training.",
    tier: "distribution",
  },
  {
    id: "time_bucket",
    emoji: "📅",
    label: "N rows per time bucket",
    blurb: "N rows per day / hour / week of a timestamp column. For log/event data where head/tail/random skew toward dense periods.",
    tier: "distribution",
  },
  {
    id: "weighted",
    emoji: "⚓",
    label: "Weighted by column",
    blurb: "Sample probability proportional to a numeric column — high-value rows over-represented. Niche but useful for revenue-weighted previews.",
    tier: "statistical",
  },
  {
    id: "bootstrap",
    emoji: "🎯",
    label: "Bootstrap (with replacement)",
    blurb: "Same row can appear multiple times. Standard for statistical workflows + confidence-interval bootstrapping. Not a typical preview method.",
    tier: "statistical",
  },
];

const _SQL_BUCKET_FN: Record<TimeBucket, string> = {
  hour: "hour", day: "day", week: "week",
  month: "month", quarter: "quarter", year: "year",
};

/** Quote a column identifier for inclusion in DuckDB SQL. Mirrors
 *  `quote_ident` in backend/dig/engine/step.py — DuckDB uses double
 *  quotes for identifiers and `""` to escape an embedded `"`. */
function quoteIdent(name: string): string {
  return `"${name.replace(/"/g, '""')}"`;
}

/**
 * Wrap a compiled pipeline SQL with the chosen sampling method.
 * Returns DuckDB-flavored SQL — used both by the in-browser preview
 * (DuckDB-WASM) and by the backend's preview endpoint (DuckDB).
 *
 * `inner` is the un-wrapped pipeline SQL (already a complete SELECT).
 *
 * Per-method semantics — kept in lockstep with
 * `backend/dig/engine/sampling.py:wrap_with_sampling`.
 */
export function wrapWithSampling(inner: string, cfg: SamplingConfig | null | undefined): string {
  if (!cfg) return inner;
  const size = Math.max(1, Math.floor(cfg.size || 500));
  const seed = typeof cfg.seed === "number" ? Math.floor(cfg.seed) : null;

  switch (cfg.method) {
    case "head":
      return `SELECT * FROM (${inner}) AS __pipeline LIMIT ${size}`;

    case "tail":
      // DuckDB supports OFFSET after LIMIT but the math needs the total
      // count. ROW_NUMBER lets us pick the trailing N rows in one pass.
      return (
        `WITH __t AS (${inner}), __ranked AS (` +
        `SELECT *, ROW_NUMBER() OVER () AS __rn, COUNT(*) OVER () AS __ct FROM __t` +
        `) SELECT * EXCLUDE (__rn, __ct) FROM __ranked ` +
        `WHERE __rn > __ct - ${size} ORDER BY __rn`
      );

    case "random": {
      // DuckDB's USING SAMPLE with reservoir mode + optional seed.
      return (
        `SELECT * FROM (${inner}) AS __pipeline ` +
        `USING SAMPLE reservoir(${size} ROWS)${seed != null ? ` REPEATABLE (${seed})` : ""}`
      );
    }

    case "systematic": {
      const k = Math.max(2, Math.floor(cfg.everyN ?? 10));
      // Modulus on ROW_NUMBER — keeps the cadence stable across passes.
      return (
        `WITH __t AS (${inner}), __ranked AS (` +
        `SELECT *, ROW_NUMBER() OVER () AS __rn FROM __t` +
        `) SELECT * EXCLUDE (__rn) FROM __ranked WHERE __rn % ${k} = 0`
      );
    }

    case "stratified": {
      // Proportional allocation: per-stratum quota = round(size * stratum_count / total).
      // Each row gets a stable per-stratum row-number ordered by random();
      // we keep the first `quota_per_stratum` rows of each stratum.
      // No live distribution preview / no auto column suggestion —
      // textbook proportional stratification, plain. See
      // SAMPLING.md "Distribution-aware methods" for the algorithm
      // attribution.
      if (!cfg.column) return inner;
      const c = quoteIdent(cfg.column);
      const seedFn = seed != null ? `setseed(${(seed % 2147483647) / 2147483647}), random()` : "random()";
      return (
        `WITH __t AS (${inner}),` +
        ` __ranked AS (SELECT *, ` +
        `ROW_NUMBER() OVER (PARTITION BY ${c} ORDER BY ${seedFn}) AS __rn, ` +
        `COUNT(*)    OVER (PARTITION BY ${c}) AS __stratum_ct, ` +
        `COUNT(*)    OVER () AS __total_ct ` +
        `FROM __t)` +
        ` SELECT * EXCLUDE (__rn, __stratum_ct, __total_ct) FROM __ranked ` +
        `WHERE __rn <= GREATEST(1, CAST(ROUND(${size} * __stratum_ct / __total_ct) AS BIGINT))`
      );
    }

    case "per_group": {
      // N rows per distinct value of `column`. ROW_NUMBER over the
      // partition; cap at `size` per group. `size` semantically means
      // "rows per group" here, not "total rows" — the dialog's helper
      // text makes that explicit so the user isn't surprised.
      if (!cfg.column) return inner;
      const c = quoteIdent(cfg.column);
      const ord = seed != null
        ? `setseed(${(seed % 2147483647) / 2147483647}), random()`
        : "random()";
      return (
        `WITH __t AS (${inner}),` +
        ` __ranked AS (SELECT *, ` +
        `ROW_NUMBER() OVER (PARTITION BY ${c} ORDER BY ${ord}) AS __rn ` +
        `FROM __t)` +
        ` SELECT * EXCLUDE (__rn) FROM __ranked WHERE __rn <= ${size}`
      );
    }

    case "time_bucket": {
      // N rows per bucket of `timeColumn`. DATE_TRUNC partitions the
      // ROW_NUMBER; first `size` rows per bucket survive. Empty buckets
      // contribute zero rows (no padding) so the result is exactly
      // those bucket-rows the dataset actually has.
      if (!cfg.timeColumn) return inner;
      const c = quoteIdent(cfg.timeColumn);
      const bucket = _SQL_BUCKET_FN[cfg.bucket ?? "day"] ?? "day";
      const ord = seed != null
        ? `setseed(${(seed % 2147483647) / 2147483647}), random()`
        : "random()";
      return (
        `WITH __t AS (${inner}),` +
        ` __ranked AS (SELECT *, ` +
        `ROW_NUMBER() OVER (PARTITION BY DATE_TRUNC('${bucket}', ${c}::TIMESTAMP) ORDER BY ${ord}) AS __rn ` +
        `FROM __t)` +
        ` SELECT * EXCLUDE (__rn) FROM __ranked WHERE __rn <= ${size}`
      );
    }

    case "weighted": {
      // Probability-proportional-to-size sampling using the
      // efficient -log(U) / w trick (Efraimidis-Spirakis 2006).
      // U ~ Uniform(0,1), key = -log(U)/weight; smallest `size` keys
      // give a sample weighted by `weight`. Negative or null weights
      // are coerced to 0 (excluded). Standard textbook method.
      //
      // Seed not threaded inline — `random()` here is a function arg
      // to `ln()`, where the `setseed(s), random()` comma trick
      // doesn't apply (commas separate sort keys in ORDER BY only).
      // See backend/dig/engine/sampling.py for the same compromise.
      if (!cfg.column) return inner;
      const c = quoteIdent(cfg.column);
      return (
        `WITH __t AS (${inner}),` +
        ` __keyed AS (SELECT *, ` +
        `CASE WHEN COALESCE(${c}, 0) > 0 ` +
        `THEN -ln(random()) / COALESCE(${c}, 0) ` +
        `ELSE 1e18 END AS __ws_key ` +
        `FROM __t)` +
        ` SELECT * EXCLUDE (__ws_key) FROM __keyed ` +
        `ORDER BY __ws_key ASC LIMIT ${size}`
      );
    }

    case "bootstrap": {
      // Sampling WITH replacement. DuckDB's USING SAMPLE doesn't
      // support replacement directly; we emulate via cross join
      // against generate_series + random row pick. REPEATABLE is a
      // clause on USING SAMPLE only — not applicable here — so the
      // bootstrap is non-reproducible across runs.
      return (
        `WITH __t AS (${inner}),` +
        ` __indexed AS (SELECT *, ROW_NUMBER() OVER () AS __rn, COUNT(*) OVER () AS __ct FROM __t),` +
        ` __picks AS (SELECT 1 + CAST(FLOOR(random() * (SELECT __ct FROM __indexed LIMIT 1)) AS BIGINT) AS __pick ` +
        `FROM generate_series(1, ${size}))` +
        ` SELECT __indexed.* EXCLUDE (__rn, __ct) ` +
        `FROM __picks JOIN __indexed ON __indexed.__rn = __picks.__pick`
      );
    }
  }
}
