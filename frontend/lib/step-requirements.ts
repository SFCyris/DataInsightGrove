// ─────────────────────────────────────────────────────────────────
// Step requirement predicates.
//
// A step manifest can declare `requires: RequirementClause[]` to
// describe the minimum upstream-schema shape it needs. The picker
// uses this to grey out steps that can't run against the current
// upstream node, with a tooltip explaining what's missing.
//
// Backend execution is unaffected — this is purely a UX hint.
// Steps without `requires` (or with an empty array) pass for any
// schema.
// ─────────────────────────────────────────────────────────────────

/** A coarse type bucket. Multiple physical/meta-types map to one bucket. */
export type RequirementBucket =
  | "numeric"
  | "temporal"
  | "string"
  | "vector"
  | "array"
  | "json"
  | "spatial"
  | "boolean"
  | "any";

/** One clause of a step's requirement. AND-combined with siblings. */
export interface RequirementClause {
  /** Bucket name, or a list of bucket names (any-of). */
  kind: RequirementBucket | RequirementBucket[];
  /** Minimum matching columns (default 1). */
  min?: number;
}

// ─────────────────────────────────────────────────────────────────
// Bucket membership
//
// Source of truth for the type ids: backend/dig/engine/meta_types.py
// (the TYPES list) plus the physical types DuckDB emits during
// profiling. Keep in sync when meta-types are added — but a missing
// type_id just falls into "any", which fails closed (the requirement
// won't be satisfied). That's the right default.
// ─────────────────────────────────────────────────────────────────

const BUCKET_MEMBERS: Record<Exclude<RequirementBucket, "any">, ReadonlySet<string>> = {
  numeric: new Set([
    // physical
    "integer", "double", "num", "int", "float",
    // numeric meta-types
    "percentage", "currency", "scientific", "bignum", "hex", "index", "decimal_string",
  ]),
  temporal: new Set(["date", "datetime", "timestamp", "time"]),
  string: new Set([
    "string", "varchar", "str",
    // string meta-types
    "email", "url", "ip", "phone", "country", "color", "timezone", "uuid",
  ]),
  vector: new Set(["vector"]),
  array: new Set(["array", "list"]),
  json: new Set(["json"]),
  spatial: new Set(["cartesian2d", "cartesian3d", "polar2d", "polar3d", "geographic"]),
  boolean: new Set(["boolean", "bool"]),
};

/** True iff `typeId` is a member of `bucket`. "any" matches anything non-empty. */
export function typeMatchesBucket(typeId: string, bucket: RequirementBucket): boolean {
  if (bucket === "any") return typeId.length > 0;
  const members = BUCKET_MEMBERS[bucket];
  return members?.has(typeId.toLowerCase()) ?? false;
}

/** Count columns whose type satisfies any of the given buckets. */
function countMatching(schema: Record<string, string>, buckets: RequirementBucket[]): number {
  let n = 0;
  for (const t of Object.values(schema)) {
    if (buckets.some((b) => typeMatchesBucket(t, b))) n += 1;
  }
  return n;
}

export interface UnmetClause {
  clause: RequirementClause;
  /** How many columns matched (always < clause.min when reported as unmet). */
  matched: number;
  /** Friendly description: "≥2 numeric columns". */
  label: string;
}

export interface RequirementResult {
  ok: boolean;
  unmet: UnmetClause[];
}

/** Pretty-print one bucket name for tooltips. */
function bucketLabel(b: RequirementBucket): string {
  switch (b) {
    case "numeric":  return "numeric";
    case "temporal": return "date/datetime";
    case "string":   return "text";
    case "vector":   return "vector";
    case "array":    return "array/list";
    case "json":     return "JSON";
    case "spatial":  return "spatial";
    case "boolean":  return "boolean";
    case "any":      return "any";
  }
}

function clauseLabel(c: RequirementClause): string {
  const kinds = Array.isArray(c.kind) ? c.kind : [c.kind];
  const min = c.min ?? 1;
  const kindLabel = kinds.map(bucketLabel).join(" or ");
  const noun = min === 1 ? "column" : "columns";
  return `≥${min} ${kindLabel} ${noun}`;
}

/**
 * Evaluate a step's `requires` against an upstream schema.
 *
 * `schema` maps column-name → type-id (the same shape as the runtime
 * `schemas[nodeId]` in the pipeline editor). When `requires` is empty
 * or missing, returns `{ ok: true }` — the step has no constraints.
 * When the schema itself is empty (no upstream selected yet), every
 * step passes for the same reason: there's nothing to disqualify.
 */
export function evaluateRequirements(
  requires: RequirementClause[] | undefined | null,
  schema: Record<string, string> | undefined | null,
): RequirementResult {
  if (!requires || requires.length === 0) return { ok: true, unmet: [] };
  if (!schema || Object.keys(schema).length === 0) return { ok: true, unmet: [] };
  const unmet: UnmetClause[] = [];
  for (const clause of requires) {
    const buckets = Array.isArray(clause.kind) ? clause.kind : [clause.kind];
    const min = clause.min ?? 1;
    const matched = countMatching(schema, buckets);
    if (matched < min) {
      unmet.push({ clause, matched, label: clauseLabel(clause) });
    }
  }
  return { ok: unmet.length === 0, unmet };
}

/** Compose a one-line tooltip describing why a step is greyed. */
export function unmetTooltip(unmet: UnmetClause[]): string {
  if (unmet.length === 0) return "";
  const parts = unmet.map((u) => u.label);
  return `Needs ${parts.join(" + ")} in upstream`;
}
