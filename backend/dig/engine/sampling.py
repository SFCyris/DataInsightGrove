"""Pipeline-level sampling — Python twin of `frontend/lib/sampling.ts`.

Single source of truth on the backend for wrapping a compiled pipeline
SQL with the user-selected sampling method. Both `preview-step-rows`
and the AI-features sample harvester route through this helper, so any
new method (or a tweak to an existing one) lands in one place.

**Forward-compatibility contract.** When a new sampling method is added
to the TS side (`SamplingMethod` literal in `frontend/lib/sampling.ts`),
add it here in the same shape — same id, same SQL semantics. Anything
that reads `metadata.sampling` is expected to call this helper, never
to inline its own LIMIT/OFFSET/etc.

Methods currently supported (mirroring the TS version verbatim):

  Universal (no column required):
  - head        first N rows (default; biased but instant)
  - tail        last N rows (time-series tail inspection)
  - random      uniform random sample (DuckDB reservoir, optional seed)
  - systematic  every Kth row (cadence-preserving)

  Distribution-aware (require a column):
  - stratified  proportional allocation across `column` distinct values
                (Neyman 1934, textbook).
  - per_group   N rows per distinct value of `column` (cluster cap).
  - time_bucket N rows per DATE_TRUNC(`bucket`, `time_column`).
  - weighted    probability-proportional-to-`column` (Efraimidis-Spirakis).
  - bootstrap   sample WITH replacement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


SamplingMethod = Literal[
    "head", "tail", "random", "systematic",
    "stratified", "per_group", "time_bucket", "weighted", "bootstrap",
]
TimeBucket = Literal["hour", "day", "week", "month", "quarter", "year"]


_SQL_BUCKET_FN: dict[str, str] = {
    "hour": "hour", "day": "day", "week": "week",
    "month": "month", "quarter": "quarter", "year": "year",
}


def _quote_ident(name: str) -> str:
    """Mirror frontend `quoteIdent` — DuckDB double-quote identifiers."""
    return '"' + name.replace('"', '""') + '"'


@dataclass(frozen=True)
class SamplingConfig:
    method: SamplingMethod
    size: int = 500
    every_n: int | None = None
    seed: int | None = None
    # Column the method needs to compute its partition / weight key.
    # `stratified` + `per_group` + `weighted` all use this slot.
    column: str | None = None
    # Time-bucket sampling: temporal column + bucket granularity.
    time_column: str | None = None
    bucket: TimeBucket | None = None

    @classmethod
    def from_metadata(cls, raw: Any) -> "SamplingConfig | None":
        """Build a config from the pipeline document's
        ``metadata.sampling`` blob. Tolerates missing / partial keys
        and snake_case-vs-camelCase mismatches (the doc may have been
        written by either the TS frontend or a Python migration script).
        """
        if not isinstance(raw, dict):
            return None
        method = raw.get("method")
        valid_methods: tuple[str, ...] = (
            "head", "tail", "random", "systematic",
            "stratified", "per_group", "time_bucket", "weighted", "bootstrap",
        )
        if method not in valid_methods:
            return None
        size = raw.get("size") or 500
        every_n = raw.get("everyN") or raw.get("every_n")
        seed = raw.get("seed")
        column = raw.get("column")
        time_column = raw.get("timeColumn") or raw.get("time_column")
        bucket = raw.get("bucket")
        try:
            size_i = max(1, int(size))
        except (TypeError, ValueError):
            size_i = 500
        try:
            every_n_i = int(every_n) if every_n is not None else None
        except (TypeError, ValueError):
            every_n_i = None
        try:
            seed_i = int(seed) if seed is not None else None
        except (TypeError, ValueError):
            seed_i = None
        if bucket not in (None, "hour", "day", "week", "month", "quarter", "year"):
            bucket = None
        return cls(
            method=method,
            size=size_i,
            every_n=every_n_i,
            seed=seed_i,
            column=column if isinstance(column, str) else None,
            time_column=time_column if isinstance(time_column, str) else None,
            bucket=bucket,
        )


def _seed_random_expr(seed: int | None) -> str:
    """Build a `random()` expression that's deterministic when ``seed``
    is set. DuckDB's setseed() returns NULL but seeds the RNG; we
    chain it with random() inside an ORDER BY to get a deterministic
    per-row key. Map int seed → [-1, 1] float as DuckDB requires."""
    if seed is None:
        return "random()"
    s = (seed % 2_147_483_647) / 2_147_483_647
    return f"setseed({s}), random()"


def wrap_with_sampling(inner_sql: str, cfg: SamplingConfig | None) -> str:
    """Wrap a pipeline-shaped SELECT with the chosen sampling method.

    ``inner_sql`` MUST be a complete SELECT statement (no trailing
    semicolon). Returns a SELECT that yields the sampled rows. Pass
    ``cfg=None`` to leave the SQL untouched.

    Mirrors `wrapWithSampling` in `frontend/lib/sampling.ts` — keep the
    two in lockstep when adding methods.
    """
    if cfg is None:
        return inner_sql
    size = max(1, cfg.size)
    seed = cfg.seed

    if cfg.method == "head":
        return f"SELECT * FROM ({inner_sql}) AS __pipeline LIMIT {size}"
    if cfg.method == "tail":
        return (
            f"WITH __t AS ({inner_sql}), __ranked AS ("
            "SELECT *, ROW_NUMBER() OVER () AS __rn, COUNT(*) OVER () AS __ct FROM __t"
            ") SELECT * EXCLUDE (__rn, __ct) FROM __ranked "
            f"WHERE __rn > __ct - {size} ORDER BY __rn"
        )
    if cfg.method == "random":
        seed_clause = (
            f" REPEATABLE ({int(seed)})" if isinstance(seed, int) else ""
        )
        return (
            f"SELECT * FROM ({inner_sql}) AS __pipeline "
            f"USING SAMPLE reservoir({size} ROWS){seed_clause}"
        )
    if cfg.method == "systematic":
        k = max(2, cfg.every_n or 10)
        return (
            f"WITH __t AS ({inner_sql}), __ranked AS ("
            "SELECT *, ROW_NUMBER() OVER () AS __rn FROM __t"
            f") SELECT * EXCLUDE (__rn) FROM __ranked WHERE __rn % {k} = 0"
        )

    if cfg.method == "stratified":
        # Proportional allocation per stratum. Per-stratum quota =
        # round(size * stratum_count / total). Floor at 1 so tiny
        # strata aren't dropped entirely — keeps rare-class
        # representation visible. Plain Neyman 1934.
        if not cfg.column:
            return inner_sql
        c = _quote_ident(cfg.column)
        ord_ = _seed_random_expr(seed)
        return (
            f"WITH __t AS ({inner_sql}),"
            " __ranked AS (SELECT *, "
            f"ROW_NUMBER() OVER (PARTITION BY {c} ORDER BY {ord_}) AS __rn, "
            f"COUNT(*)    OVER (PARTITION BY {c}) AS __stratum_ct, "
            "COUNT(*)    OVER () AS __total_ct "
            "FROM __t)"
            " SELECT * EXCLUDE (__rn, __stratum_ct, __total_ct) FROM __ranked "
            f"WHERE __rn <= GREATEST(1, CAST(ROUND({size} * __stratum_ct / __total_ct) AS BIGINT))"
        )

    if cfg.method == "per_group":
        if not cfg.column:
            return inner_sql
        c = _quote_ident(cfg.column)
        ord_ = _seed_random_expr(seed)
        return (
            f"WITH __t AS ({inner_sql}),"
            " __ranked AS (SELECT *, "
            f"ROW_NUMBER() OVER (PARTITION BY {c} ORDER BY {ord_}) AS __rn "
            "FROM __t)"
            f" SELECT * EXCLUDE (__rn) FROM __ranked WHERE __rn <= {size}"
        )

    if cfg.method == "time_bucket":
        if not cfg.time_column:
            return inner_sql
        c = _quote_ident(cfg.time_column)
        bucket = _SQL_BUCKET_FN.get(cfg.bucket or "day", "day")
        ord_ = _seed_random_expr(seed)
        return (
            f"WITH __t AS ({inner_sql}),"
            " __ranked AS (SELECT *, "
            f"ROW_NUMBER() OVER (PARTITION BY DATE_TRUNC('{bucket}', {c}::TIMESTAMP) ORDER BY {ord_}) AS __rn "
            "FROM __t)"
            f" SELECT * EXCLUDE (__rn) FROM __ranked WHERE __rn <= {size}"
        )

    if cfg.method == "weighted":
        # Efraimidis-Spirakis 2006: key = -ln(U) / w; smallest `size`
        # keys give a sample weighted by `w`. Null/non-positive weights
        # excluded (sentinel key 1e18 sorts to the bottom).
        #
        # Note: seed is intentionally not threaded through here because
        # `random()` appears as an argument to `ln()` — the inline
        # `setseed(s), random()` comma trick only works inside ORDER BY
        # (where commas separate sort keys), not inside a single
        # function argument. Reproducible weighted sampling is rare
        # enough to defer; users who need it can call setseed() at the
        # session level via a custom step or rely on DuckDB's default
        # PRNG state across runs of the same pipeline.
        if not cfg.column:
            return inner_sql
        c = _quote_ident(cfg.column)
        return (
            f"WITH __t AS ({inner_sql}),"
            " __keyed AS (SELECT *, "
            f"CASE WHEN COALESCE({c}, 0) > 0 "
            f"THEN -ln(random()) / COALESCE({c}, 0) "
            "ELSE 1e18 END AS __ws_key "
            "FROM __t)"
            " SELECT * EXCLUDE (__ws_key) FROM __keyed "
            f"ORDER BY __ws_key ASC LIMIT {size}"
        )

    if cfg.method == "bootstrap":
        # Sampling WITH replacement. DuckDB's USING SAMPLE doesn't
        # support replacement directly; emulate via index pick from
        # generate_series. Seed handling: REPEATABLE is a clause on
        # USING SAMPLE only — for the picks side we rely on plain
        # random(), so bootstraps aren't reproducible across runs
        # without setseed() at the session level. Same compromise as
        # weighted; statistical workflows that need reproducibility
        # tend to do their bootstrap in code anyway.
        return (
            f"WITH __t AS ({inner_sql}),"
            " __indexed AS (SELECT *, ROW_NUMBER() OVER () AS __rn, COUNT(*) OVER () AS __ct FROM __t),"
            " __picks AS (SELECT 1 + CAST(FLOOR(random() * (SELECT __ct FROM __indexed LIMIT 1)) AS BIGINT) AS __pick "
            f"FROM generate_series(1, {size}))"
            " SELECT __indexed.* EXCLUDE (__rn, __ct) "
            "FROM __picks JOIN __indexed ON __indexed.__rn = __picks.__pick"
        )

    # Unknown method — defensively return the unwrapped SQL rather than
    # crashing. New methods on the TS side that haven't been ported yet
    # land here; they degrade to "no sampling" instead of an exception.
    return inner_sql


def adapt_to_schema(
    cfg: SamplingConfig | None,
    schema: dict[str, str] | None,
) -> SamplingConfig | None:
    """Return a sampling config that's safe to wrap around a SELECT
    whose output has the given ``schema`` (column → type map).

    Pipeline-level sampling is configured for the **final output** of
    the pipeline. When previewing an intermediate node — especially an
    upstream input that doesn't yet have the configured column — the
    column-needing methods (`stratified` / `per_group` / `weighted` /
    `time_bucket`) would generate SQL that references a column DuckDB
    can't bind, producing a confusing 'Referenced column "X" not found
    in FROM clause' error instead of the live preview.

    This adapter degrades to ``head`` (with the configured size) when
    the required column is missing from the focused terminal's output.
    Same size-cap, same shape, no surprise binder errors.

    When ``schema`` is None (caller doesn't have it handy), returns
    ``cfg`` unchanged — caller takes responsibility for SQL-bind
    errors.
    """
    if cfg is None or schema is None:
        return cfg
    needed = None
    if cfg.method in ("stratified", "per_group", "weighted"):
        needed = cfg.column
    elif cfg.method == "time_bucket":
        needed = cfg.time_column
    if needed is None or needed in schema:
        return cfg
    # Column missing from this terminal — fall back to head with the
    # same size budget. Other fields (every_n, seed, time bucket) are
    # method-specific and don't apply to head.
    return SamplingConfig(method="head", size=cfg.size)
