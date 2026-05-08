/**
 * Pipeline doctor — structural validator + fixer for pipeline documents.
 *
 * Runs on every editor load + on import (drag-drop, paste). Returns a
 * list of `Diagnosis` entries. Fixable issues offer a `apply()` that
 * returns a corrected document; the editor surfaces these in a friendly
 * "tune-up" dialog and only applies them after the user confirms.
 *
 * Design principles:
 *
 *   1. **Diagnoses are observations, not errors.** The pipeline still
 *      works (via runtime fallbacks like the URI-keyed dataset lookup)
 *      even when un-fixed. The doctor's job is to nudge the doc toward
 *      canonical shape, not to gate functionality.
 *   2. **Each rule is independent.** Adding a new rule = appending one
 *      function. Rules don't talk to each other.
 *   3. **Fixes are deterministic + side-effect-free.** Each `apply()`
 *      returns a new document; the caller decides when to commit it.
 *   4. **Severity is `info` or `warn` — never `error`.** Errors would
 *      imply the pipeline is broken; we reserve those for runtime
 *      compile failures the user has to fix manually.
 */
import type { PipelineDocument, Dataset, StepManifest } from "@/lib/api/client";

export type DiagnosisSeverity = "info" | "warn";

export interface Diagnosis {
  /** Stable id — used for per-pipeline localStorage dismissal keys. */
  id: string;
  severity: DiagnosisSeverity;
  /** One short sentence the user reads first. No jargon. */
  title: string;
  /** 1-3 short sentences explaining why this matters + what the fix does. */
  detail: string;
  /** True if `apply` is set and produces a corrected document. */
  fixable: boolean;
  /** Human-readable preview of the change ("ds_main → ds_01ABC…"). */
  preview?: string;
  /** Returns a new document with this issue resolved. Undefined when not fixable. */
  apply?: (doc: PipelineDocument) => PipelineDocument;
}

// ── Rule 1: dataset id doesn't match `ds_<ulid_lowercase>` ─────────────
//
// Pipelines built before the canonical-id convention (and templates
// using doc-internal aliases like `ds_main`) miss a few preview-time
// integrations: the focused-dataset profile, the rule-based hints
// panel, and any tooling that maps doc.datasets[].id back to a Dataset
// row. The runtime URI-fallback handles it, but renaming the alias
// makes everything resolve consistently — and shorter pipelines
// stay easier to skim when ids look the same as everywhere else.
function ruleNonCanonicalDatasetId(
  doc: PipelineDocument,
  datasets: Dataset[],
): Diagnosis | null {
  const ULID_RE = /^[0-9A-Z]{26}$/i;
  const targets: { fromId: string; toId: string; label: string }[] = [];
  for (const ds of doc.datasets) {
    // Already canonical → skip.
    if (/^ds_[0-9a-z]{26}$/.test(ds.id)) continue;
    // Find the matching Dataset row by URI (`.../<ULID>.parquet`).
    const m = ds.uri?.match(/([0-9A-Z]{26})\.parquet/i);
    if (!m) continue;
    const ulid = m[1].toUpperCase();
    const real = datasets.find((d) => d.id.toUpperCase() === ulid);
    if (!real) continue;
    targets.push({ fromId: ds.id, toId: `ds_${ulid.toLowerCase()}`, label: real.name });
  }
  if (targets.length === 0) return null;
  const preview = targets
    .map((t) => `${t.fromId} → ${t.toId}`)
    .join("\n");
  return {
    id: "non-canonical-dataset-id",
    severity: "info",
    title:
      targets.length === 1
        ? `Dataset id “${targets[0].fromId}” is non-canonical`
        : `${targets.length} dataset ids are non-canonical`,
    detail:
      "Some preview surfaces (the focused-dataset grid, the rule-based hints panel, lineage tracing) match Dataset rows via the canonical `ds_<ULID>` form. Renaming the doc-internal alias to the canonical id makes every surface resolve consistently. References inside the pipeline get rewritten automatically.",
    fixable: true,
    preview,
    apply: (doc) => {
      let out = doc;
      for (const t of targets) {
        out = {
          ...out,
          datasets: out.datasets.map((d) =>
            d.id === t.fromId ? { ...d, id: t.toId } : d,
          ),
          nodes: out.nodes.map((n) => ({
            ...n,
            inputs: Object.fromEntries(
              Object.entries(n.inputs).map(([port, ref]) => [
                port,
                ref.ref === t.fromId ? { ...ref, ref: t.toId } : ref,
              ]),
            ),
          })),
          outputs: out.outputs.map((o) =>
            o.from?.ref === t.fromId
              ? { ...o, from: { ...o.from, ref: t.toId } }
              : o,
          ),
        };
      }
      return out;
    },
  };
}

// ── Rule 2: filter_rows uses legacy `expression` param key ─────────────
//
// Older docs used `expression` for the filter SQL; the canonical key
// is `predicate`. Same value, just renamed; the validator surfaces a
// "Required param 'predicate' is missing" error otherwise.
function ruleFilterRowsLegacyParam(doc: PipelineDocument): Diagnosis | null {
  const offenders = doc.nodes.filter(
    (n) =>
      n.step === "filter_rows" &&
      typeof (n.params as Record<string, unknown>)?.expression === "string" &&
      typeof (n.params as Record<string, unknown>)?.predicate !== "string",
  );
  if (offenders.length === 0) return null;
  return {
    id: "filter-rows-legacy-expression",
    severity: "warn",
    title:
      offenders.length === 1
        ? `“${offenders[0].id}” uses legacy filter param`
        : `${offenders.length} filter steps use legacy param key`,
    detail:
      "filter_rows now expects `predicate` instead of `expression`. The fix renames the key — same SQL, no behaviour change. Without it the param validator flags 'predicate is missing'.",
    fixable: true,
    preview: offenders
      .map((n) => `${n.id}: expression → predicate`)
      .join("\n"),
    apply: (doc) => ({
      ...doc,
      nodes: doc.nodes.map((n) => {
        if (n.step !== "filter_rows") return n;
        const params = { ...(n.params || {}) } as Record<string, unknown>;
        if (typeof params.expression === "string" && typeof params.predicate !== "string") {
          params.predicate = params.expression;
          delete params.expression;
        }
        return { ...n, params };
      }),
    }),
  };
}

// ── Rule 2b: join uses legacy `how` / `on` param keys ─────────────────
//
// Older docs (pre-1.1) used `how` + `on` for the join's kind + keys.
// The compile path still accepts them via runtime aliasing, but the
// JSON-schema param validator reports `'kind' missing` / `'keys' missing`
// because it sees only the canonical names. Renaming the keys is a
// mechanical, behaviour-preserving fix — same semantics, validator-clean.
function ruleJoinLegacyParams(doc: PipelineDocument): Diagnosis | null {
  const offenders = doc.nodes.filter((n) => {
    if (n.step !== "join") return false;
    const p = (n.params || {}) as Record<string, unknown>;
    const hasLegacy =
      (typeof p.how === "string" && typeof p.kind !== "string")
      || (Array.isArray(p.on) && !Array.isArray(p.keys));
    return hasLegacy;
  });
  if (offenders.length === 0) return null;
  return {
    id: "join-legacy-params",
    severity: "warn",
    title:
      offenders.length === 1
        ? `“${offenders[0].id}” uses legacy join params`
        : `${offenders.length} join steps use legacy params`,
    detail:
      "join now expects `kind` (was `how`) and `keys` (was `on`). The fix renames both keys, preserving the values exactly. Without it, the param validator flags both as missing — the join can't compile.",
    fixable: true,
    preview: offenders.map((n) => `${n.id}: how→kind, on→keys`).join("\n"),
    apply: (doc) => ({
      ...doc,
      nodes: doc.nodes.map((n) => {
        if (n.step !== "join") return n;
        const params = { ...(n.params || {}) } as Record<string, unknown>;
        if (typeof params.how === "string" && typeof params.kind !== "string") {
          params.kind = params.how;
          delete params.how;
        }
        if (Array.isArray(params.on) && !Array.isArray(params.keys)) {
          params.keys = params.on;
          delete params.on;
        }
        return { ...n, params };
      }),
    }),
  };
}

// ── Rule 3: stepVersion behind the registry's current version ──────────
//
// Cosmetic-only — DIG accepts any stepVersion at runtime. But up-to-date
// docs validate cleaner against the JSON schema and show fewer surprise
// diffs in run history. Auto-bump is safe.
function ruleStepVersionDrift(
  doc: PipelineDocument,
  steps: StepManifest[],
): Diagnosis | null {
  const byId = new Map(steps.map((s) => [s.id, s]));
  const drifts: { nodeId: string; from: string; to: string; stepId: string }[] = [];
  for (const n of doc.nodes) {
    const m = byId.get(n.step);
    if (!m) continue;
    if (n.stepVersion === m.version) continue;
    drifts.push({ nodeId: n.id, from: n.stepVersion, to: m.version, stepId: n.step });
  }
  if (drifts.length === 0) return null;
  return {
    id: "step-version-drift",
    severity: "info",
    title:
      drifts.length === 1
        ? `1 node's stepVersion is behind the registry`
        : `${drifts.length} nodes' stepVersions are behind the registry`,
    detail:
      "DIG accepts any stepVersion at runtime, but matching the registry version makes diffs cleaner in run history and avoids spurious migration prompts on re-import. Auto-bump is purely a label change — no params or behaviour are affected.",
    fixable: true,
    preview: drifts
      .map((d) => `${d.nodeId} (${d.stepId}): v${d.from} → v${d.to}`)
      .join("\n"),
    apply: (doc) => ({
      ...doc,
      nodes: doc.nodes.map((n) => {
        const d = drifts.find((x) => x.nodeId === n.id);
        return d ? { ...n, stepVersion: d.to } : n;
      }),
    }),
  };
}

// ── Rule 4: dangling input refs (informational; not auto-fixable) ──────
function ruleDanglingRefs(doc: PipelineDocument): Diagnosis | null {
  const known = new Set<string>([
    ...doc.datasets.map((d) => d.id),
    ...doc.nodes.map((n) => n.id),
  ]);
  const broken: { nodeId: string; port: string; ref: string }[] = [];
  for (const n of doc.nodes) {
    for (const [port, ref] of Object.entries(n.inputs || {})) {
      if (!known.has(ref.ref)) {
        broken.push({ nodeId: n.id, port, ref: ref.ref });
      }
    }
  }
  if (broken.length === 0) return null;
  return {
    id: "dangling-input-refs",
    severity: "warn",
    title:
      broken.length === 1
        ? `“${broken[0].nodeId}” references something that no longer exists`
        : `${broken.length} input refs point at missing nodes/datasets`,
    detail:
      "These refs survive in the doc but resolve to nothing — likely an upstream node was deleted without rewiring downstream. Removing the broken nodes or re-pointing the refs is a manual decision; the doctor doesn't guess which.",
    fixable: false,
    preview: broken
      .map((b) => `${b.nodeId}.${b.port} → ${b.ref}`)
      .join("\n"),
  };
}

// ── Driver ─────────────────────────────────────────────────────────────

export function diagnose(
  doc: PipelineDocument,
  datasets: Dataset[],
  steps: StepManifest[],
): Diagnosis[] {
  const out: Diagnosis[] = [];
  const r1 = ruleNonCanonicalDatasetId(doc, datasets);
  if (r1) out.push(r1);
  const r2 = ruleFilterRowsLegacyParam(doc);
  if (r2) out.push(r2);
  const r2b = ruleJoinLegacyParams(doc);
  if (r2b) out.push(r2b);
  const r3 = ruleStepVersionDrift(doc, steps);
  if (r3) out.push(r3);
  const r4 = ruleDanglingRefs(doc);
  if (r4) out.push(r4);
  return out;
}

/** Apply a list of diagnoses' fixes to the doc. Skips ones without an
 *  `apply()`. Returns the post-fix document — caller decides when to
 *  commit (typically by running it through the labelled-save path). */
export function applyFixes(doc: PipelineDocument, diagnoses: Diagnosis[]): PipelineDocument {
  let out = doc;
  for (const d of diagnoses) {
    if (d.apply) out = d.apply(out);
  }
  return out;
}
