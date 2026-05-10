/**
 * Thin typed fetch wrapper around the DIG backend.
 *
 * Path/response types come from `lib/api/types.ts` which is generated from the
 * backend's OpenAPI schema (`pnpm gen:api` from the repo root).
 */
import type { components, paths } from "./types";

/**
 * API base URL — resolved in priority order:
 *
 *   1. window.__DIG_API__         (runtime override, e.g. set by Mac .app)
 *   2. NEXT_PUBLIC_DIG_API env    (build-time, embedded into the bundle)
 *   3. Same hostname as the page  (when running in a browser) — so visiting
 *      `http://10.0.0.5:3000` from a phone on the LAN talks to the backend
 *      at `http://10.0.0.5:8090`, not the phone's own loopback. This is
 *      what "DIG --global" mode relies on.
 *   4. http://127.0.0.1:8090      (SSR / Node fallback)
 *
 * IMPORTANT: don't render this string into HTML attributes (`<a href={…}/>`,
 * `<form action={…}/>`, `<img src={…}/>`). Server and client resolve to
 * different values (SSR can't see window.location), which causes a React
 * hydration mismatch. For rendered URLs use `useApiBase()` instead — it
 * returns the SSR-safe value on first render and swaps to the client-
 * derived value after hydration completes.
 */
function _resolveApiBase(): string {
  if (typeof window !== "undefined") {
    const w = window as { __DIG_API__?: string };
    if (w.__DIG_API__) return w.__DIG_API__;
  }
  if (process.env.NEXT_PUBLIC_DIG_API) return process.env.NEXT_PUBLIC_DIG_API;
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "https:" : "http:";
    // Default API port is 8090 — overridable via NEXT_PUBLIC_DIG_API.
    return `${proto}//${window.location.hostname}:8090`;
  }
  return "http://127.0.0.1:8090";
}

export const API_BASE = _resolveApiBase();

/**
 * The "stable" form of API_BASE for rendering into HTML — never depends
 * on window, so server and client agree. Use it as a hook seed and
 * upgrade to the real value after mount via `useApiBase()`.
 */
export const SSR_SAFE_API_BASE: string =
  process.env.NEXT_PUBLIC_DIG_API || "http://127.0.0.1:8090";

/**
 * Bearer token for the DIG API.
 *
 * Pulled in priority order from:
 *   1. window.__DIG_TOKEN__   (runtime override — set by an enclosing app or
 *      operator, takes precedence so config can roll forward without a rebuild)
 *   2. NEXT_PUBLIC_DIG_AUTH_TOKEN  (build-time env, embedded in the bundle)
 *
 * When unset, no Authorization header is sent — fine for the default loopback
 * deployment where the backend doesn't enforce auth. When set, every fetch +
 * every WebSocket carries the token; the backend BearerAuthMiddleware checks
 * `Authorization: Bearer <token>` for fetches and `?token=<token>` for WS.
 */
export const API_TOKEN: string =
  ((typeof window !== "undefined" &&
    (window as { __DIG_TOKEN__?: string }).__DIG_TOKEN__) ||
    process.env.NEXT_PUBLIC_DIG_AUTH_TOKEN ||
    "").trim();

export type Dataset = components["schemas"]["DatasetOut"];
export type DatasetProfile = components["schemas"]["DatasetProfile"];
export type ColumnInfo = components["schemas"]["ColumnInfo"];

// Logical-type catalog. Every entry corresponds to a TypeDescriptor in
// backend/dig/engine/meta_types.py:TYPES. Loaded lazily via api.listTypes()
// and used by the column-menu Cast submenu to render the "smart picks first
// then show all" UX.
export interface TypeDescriptor {
  id: string;          // "url", "email", "percentage", …
  label: string;       // "🔗 URL"
  base: string;        // physical type — "string" | "integer" | "double" | …
  description: string; // one-line dropdown tooltip
}

// One detected possibility for a column's type. The profile attaches a
// list of these per column, sorted by score descending — element [0] is
// DIG's pick, the rest are alternates surfaced in the Cast UI.
export interface TypeCandidate {
  type: string;        // matches a TypeDescriptor.id (or a base physical type)
  score: number;       // 0..1
  reason: string;      // one-line human reason ("97% URL-shaped")
  /** Physical SQL type the cast would land in. Range-aware — a
   *  `scientific` candidate with out-of-range values reports VARCHAR
   *  rather than DOUBLE, so the Cast UI can show the trade-off
   *  ("scientific → VARCHAR — preserves precision but loses SUM"). */
  storage?: string;
}
export type RowsPage = components["schemas"]["RowsPage"];
export type Health = components["schemas"]["Health"];
export type PipelineSummary = components["schemas"]["PipelineSummary"];
export type PipelineDoc = components["schemas"]["PipelineDoc"];
export type RunOut = components["schemas"]["RunOut"];

// Phase-A-pro #5 — runs list types (mirrors backend RunListItem +
// RunListPage). Kept inline so the runs UI doesn't need to wait for
// an OpenAPI regeneration.
export interface RunListItem {
  id: string;
  pipelineId: string;
  pipelineName: string | null;
  pipelineTags: string[];
  status: string;
  progress: number;
  error: string | null;
  triggeredBy: string;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
  durationMs: number | null;
  outputCount: number;
  nodeCount: number;
  rowCountTotal: number | null;
}

export interface RunListPage {
  items: RunListItem[];
  next_cursor: string | null;
  total_estimate: number | null;
}

// Hand-typed shapes for the JSON-bag step manifest + pipeline document
// (the schemas come from the JSON Schema files in shared/schemas/, not OpenAPI).
export interface ParamSpec {
  type:
    | "string" | "number" | "integer" | "boolean" | "enum"
    | "column_ref" | "column_refs" | "expression" | "regex" | "object" | "array";
  label: string;
  help?: string;
  required?: boolean;
  default?: unknown;
  enumValues?: (string | number)[];
  columnFrom?: string;
  columnTypes?: string[];
  min?: number;
  max?: number;
  pattern?: string;
  items?: ParamSpec;
  properties?: Record<string, ParamSpec>;
  visibleWhen?: Record<string, string | number | boolean>;
  /** Optional UI widget hint — e.g. "filter_builder" for a no-SQL visual editor on an expression field. */
  widget?: string;
}

export interface StepManifest {
  id: string;
  version: string;
  label: string;
  description?: string;
  category: string;
  engine: { primary: "sql" | "polars" | "python"; browser?: "sql" | "js" | "none"; deterministic?: boolean };
  io: {
    inputs: { min: number; max: number | null; ports?: string[] };
    outputs: { min: number; max: number | null; ports?: string[] };
  };
  params: Record<string, ParamSpec>;
  preview?: { rowImpact?: string; schemaImpact?: string };
  tags?: string[];
  /** Search synonyms — surfaced by the picker's intent ranker, not
   *  rendered. See `lib/step-search.ts` for the ranking algorithm. */
  aliases?: string[];
  /** Upstream-schema preconditions used by the picker to grey out
   *  steps that can't run against the current node. See
   *  lib/step-requirements.ts for the predicate vocabulary. */
  requires?: import("../step-requirements").RequirementClause[];
  /** Where this step came from. `'builtin'` for in-tree steps,
   *  `'pack:<id>'` for pack-installed, `'plugin'` for AI-generated
   *  one-off plugins. Picker renders a provenance chip when this
   *  starts with `pack:` so users can see what their installs added. */
  source?: string;
  /** Soft upper bound on input rows for a usable visualization. The
   *  editor renders a "data is dense — consider aggregating first"
   *  banner above the live chart preview when the upstream node's
   *  row count exceeds this value. Two shapes:
   *    - integer       single-kind charts (funnel / pareto / waterfall)
   *    - { kind: N }   multi-kind charts (export_to_image); frontend
   *                    looks up `params.kind`, falls back to `_default`. */
  recommendedMaxRows?: number | Record<string, number>;
}

export interface ConnectorManifest {
  id: string;
  version: string;
  label: string;
  description?: string;
  kind: "source" | "sink" | "both";
  uriSchemes?: string[];
  fileExtensions?: string[];
  options?: Record<string, ParamSpec>;
  tags?: string[];
}

export interface PipelineRef { ref: string; port?: string }
export interface PipelineDataset {
  id: string;
  connector: string;
  connectorVersion?: string;
  uri: string;
  options?: Record<string, unknown>;
  label?: string;
}
export interface PipelineNode {
  id: string;
  step: string;
  stepVersion: string;
  inputs: Record<string, PipelineRef>;
  outputs: string[];
  params: Record<string, unknown>;
  ui?: { x?: number; y?: number; label?: string; note?: string };
}
export interface PipelineOutput {
  id: string;
  name: string;
  from: PipelineRef;
  sink?: { connector: string; uri: string; options?: Record<string, unknown> };
}
export interface PipelineWebhook {
  url: string;
  on?: "always" | "succeeded" | "failed";
  /** Optional shared secret. When set, DIG signs the body with HMAC-SHA256
   * and sends `X-DIG-Signature: sha256=<hex>` so the receiver can verify. */
  secret?: string;
  /** Extra HTTP headers (auth tokens, custom routing, etc.). */
  headers?: Record<string, string>;
  label?: string;
}
export interface PipelineDocument {
  schemaVersion: 1;
  id: string;
  name: string;
  description?: string;
  datasets: PipelineDataset[];
  nodes: PipelineNode[];
  outputs: PipelineOutput[];
  metadata?: Record<string, unknown>;
  /** Outbound notifications fired on terminal run status. */
  webhooks?: PipelineWebhook[];
}

export interface RunOutputPage {
  runId: string;
  outputPath: string;
  columns: Array<{ name: string; type: string }>;
  rows: Array<Record<string, unknown>>;
  offset: number;
  limit: number;
  totalRows: number;
}

export interface NodeStatus {
  ok: boolean;
  error?: string;
}

// ---- Step Packs ---------------------------------------------------------

export interface PackConflict {
  step_id: string;
  existing_source: string;
}

export interface StagedPack {
  pack_id: string;
  version: string;
  label: string;
  description: string;
  license?: string | null;
  author?: string | null;
  homepage?: string | null;
  readme?: string | null;
  steps: string[];
  connectors: string[];
  python_requirements: string[];
  declared_checksum?: string | null;
  computed_checksum: string;
  conflicts: PackConflict[];
}

export interface InstalledPack {
  id: string;
  version: string;
  label: string;
  description?: string | null;
  license?: string | null;
  author?: string | null;
  homepage?: string | null;
  enabled: boolean;
  steps: string[];
  connectors: string[];
  python_requirements: string[];
  checksum?: string | null;
  installed_at: string;
  updated_at: string;
}

// ---- Templates (public gallery) ----------------------------------------

export interface GalleryTemplate {
  id: string;
  slug: string;
  title: string;
  summary: string | null;
  tags: string[];
  needsSampleDataset: boolean;
  sampleDatasetUrl: string | null;
  authorHandle: string | null;
  authorUrl: string | null;
  isCurated: boolean;
  visibility: "private" | "unlisted" | "public";
  upvotes: number;
  viewCount: number;
  createdAt: string;
}

export interface GalleryTemplateDetail extends GalleryTemplate {
  document: PipelineDocument;
}

// ---- Column lineage ----------------------------------------------------

export interface ColumnLineageNode {
  node_id: string;
  is_dataset: boolean;
  column: string;
  label: string;
  transform: string;
  expression: string | null;
}

export interface ColumnLineageEdge {
  from_node_id: string;
  from_column: string;
  to_node_id: string;
  to_column: string;
  transform: string;
}

export interface ColumnLineageGraph {
  target_node_id: string;
  target_column: string;
  nodes: ColumnLineageNode[];
  edges: ColumnLineageEdge[];
}

// ---- Pipeline history + diff -------------------------------------------

export interface PipelineHistoryEntry {
  id: string;
  pipelineId: string;
  etag: number;
  changeSummary: string | null;
  changeReason: string | null;
  triggeredBy: "manual_save" | "run_start" | "import" | "ai_review_apply" | "restore";
  documentHash: string;
  runId: string | null;
  createdAt: string;
}

export interface ParamDiffEntry {
  key: string;
  a_value: unknown;
  b_value: unknown;
  a_summary: string;
  b_summary: string;
}

export interface StepDiffEntry {
  kind: "added" | "removed" | "moved" | "param_changed" | "type_changed" | "unchanged";
  node_id: string;
  label: string;
  step_type: string;
  a_position: number | null;
  b_position: number | null;
  param_changes: ParamDiffEntry[];
}

export interface DatasetDiffEntry {
  kind: "added" | "removed" | "options_changed" | "unchanged";
  dataset_id: string;
  label: string;
  option_changes: ParamDiffEntry[];
}

export interface OutputDiffEntry {
  kind: "added" | "removed" | "renamed" | "rewired" | "unchanged";
  output_id: string;
  name: string;
  a_from: string | null;
  b_from: string | null;
}

export interface PipelineDiffResult {
  summary: string;
  counts: {
    added: number;
    removed: number;
    moved: number;
    param_changed: number;
    type_changed: number;
  };
  steps: StepDiffEntry[];
  datasets: DatasetDiffEntry[];
  outputs: OutputDiffEntry[];
  metadata_changes: ParamDiffEntry[];
}

export interface ValidateResult {
  ok: boolean;
  errors: string[];
  schemas: Record<string, Record<string, string>>;
  /** Per-node compile status — `nodeStatus[node_id] = {ok, error?}`.
   *  Undefined = older backend that doesn't report it (graceful fallback). */
  nodeStatus?: Record<string, NodeStatus>;
}

class ApiError extends Error {
  constructor(public status: number, message: string, public detail?: unknown) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Build headers: Accept first, then user-supplied (so caller can override),
  // then Authorization last (so caller can't accidentally drop the token by
  // passing their own headers map). The backend BearerAuthMiddleware ignores
  // the header when DIG_AUTH_TOKEN is unset, so always sending it is safe.
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...((init?.headers as Record<string, string>) || {}),
  };
  if (API_TOKEN) headers["Authorization"] = `Bearer ${API_TOKEN}`;

  const res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    // Surface the backend's actual error in `Error.message` rather than just
    // "400 Bad Request". FastAPI puts the message in `detail` (string for
    // raise HTTPException(...), or a list of validation errors). Without
    // this, the editor's preview-error box reads "400 Bad Request" and
    // humanizeSqlError has nothing to pattern-match.
    const msg = _extractErrorMessage(detail) ?? `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, msg, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function _extractErrorMessage(detail: unknown): string | null {
  if (detail == null) return null;
  if (typeof detail === "string") return detail.trim() || null;
  if (typeof detail === "object") {
    // FastAPI HTTPException → { detail: string }
    // FastAPI request validation → { detail: [{loc, msg, type}, ...] }
    const d = (detail as { detail?: unknown }).detail;
    if (typeof d === "string") return d.trim() || null;
    if (Array.isArray(d)) {
      const msgs = d
        .map((e) => {
          if (typeof e === "string") return e;
          if (e && typeof e === "object" && "msg" in e) {
            const loc = Array.isArray((e as { loc?: unknown }).loc)
              ? ((e as { loc: unknown[] }).loc).join(".")
              : null;
            const m = String((e as { msg: unknown }).msg);
            return loc ? `${loc}: ${m}` : m;
          }
          return null;
        })
        .filter(Boolean);
      return msgs.length ? msgs.join("; ") : null;
    }
    // Fall back to a JSON dump of the object — better than nothing if the
    // shape is unexpected, since at least the user can see the structure.
    try {
      return JSON.stringify(detail);
    } catch {
      return null;
    }
  }
  return null;
}

export const api = {
  health: () => request<Health>("/health"),

  listConnectors: () =>
    request<Array<Record<string, unknown>>>("/connectors"),

  listDatasets: () => request<Dataset[]>("/datasets"),
  getDataset: (id: string) => request<Dataset>(`/datasets/${id}`),
  getProfile: (id: string) => request<DatasetProfile>(`/datasets/${id}/profile`),
  getRows: (id: string, offset: number, limit: number) =>
    request<RowsPage>(`/datasets/${id}/rows?offset=${offset}&limit=${limit}`),
  deleteDataset: (id: string) =>
    request<void>(`/datasets/${id}`, { method: "DELETE" }),
  updateAnnotations: (id: string, annotations: Record<string, string>) =>
    request<Dataset>(`/datasets/${id}/annotations`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ annotations }),
    }),

  createDatasetFromUri: (
    name: string,
    connectorId: string,
    uri: string,
    options: Record<string, unknown> = {},
  ) =>
    request<Dataset>("/datasets/from-uri", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, connector_id: connectorId, uri, options }),
    }),

  pickSheet: (datasetId: string, sheet: string) =>
    request<Dataset>(`/datasets/${datasetId}/sheet`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sheet }),
    }),

  pickIsland: (datasetId: string, range: string) =>
    request<Dataset>(`/datasets/${datasetId}/island`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ range }),
    }),

  uploadDataset: async (file: File, name?: string, connectorId = "csv", options: object = {}) => {
    const fd = new FormData();
    fd.append("file", file);
    if (name) fd.append("name", name);
    fd.append("connector_id", connectorId);
    fd.append("options", JSON.stringify(options));
    // Multipart upload bypasses request() (which would set the wrong
     // Content-Type), so we hand-build the auth header here.
    const headers: Record<string, string> = {};
    if (API_TOKEN) headers["Authorization"] = `Bearer ${API_TOKEN}`;
    const res = await fetch(`${API_BASE}/datasets`, {
      method: "POST", body: fd, headers,
    });
    if (!res.ok) {
      let detail: unknown;
      try {
        detail = await res.json();
      } catch {
        detail = await res.text();
      }
      throw new ApiError(res.status, `${res.status} ${res.statusText}`, detail);
    }
    return (await res.json()) as Dataset;
  },

  // ---- Steps ----
  listSteps: () => request<StepManifest[]>("/steps"),
  getStep: (id: string) => request<StepManifest>(`/steps/${id}`),

  // ---- Step Packs ----
  listPacks: () => request<InstalledPack[]>("/packs"),
  uploadPack: async (file: File): Promise<StagedPack> => {
    const fd = new FormData();
    fd.append("file", file);
    const headers: Record<string, string> = {};
    if (API_TOKEN) headers["Authorization"] = `Bearer ${API_TOKEN}`;
    const res = await fetch(`${API_BASE}/packs/upload`, {
      method: "POST", body: fd, headers,
    });
    if (!res.ok) {
      let detail: unknown;
      try { detail = await res.json(); } catch { detail = await res.text(); }
      const msg = (detail && typeof detail === "object" && "detail" in detail)
        ? String((detail as { detail: unknown }).detail)
        : `${res.status} ${res.statusText}`;
      throw new ApiError(res.status, msg, detail);
    }
    return (await res.json()) as StagedPack;
  },
  installPack: (pack_id: string, version: string) =>
    request<{
      ok: boolean;
      pack_id: string;
      version: string;
      installed_at: string;
      dep_install: {
        requirements: string[];
        success: boolean;
        elapsed_sec: number;
        output: string;
        skipped_reason: string | null;
      } | null;
    }>("/packs/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pack_id, version }),
    }),
  discardPendingPack: (pack_id: string, version: string) =>
    request<{ ok: boolean }>(
      `/packs/_pending/${encodeURIComponent(pack_id)}?version=${encodeURIComponent(version)}`,
      { method: "DELETE" },
    ),
  togglePack: (pack_id: string, enabled: boolean) =>
    request<{ ok: boolean; id: string; enabled: boolean }>(
      `/packs/${encodeURIComponent(pack_id)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      },
    ),
  uninstallPack: (pack_id: string) =>
    request<{ ok: boolean; uninstalled: string }>(
      `/packs/${encodeURIComponent(pack_id)}`,
      { method: "DELETE" },
    ),

  // ---- Pipelines ----
  listPipelines: () => request<PipelineSummary[]>("/pipelines"),
  createPipeline: (name: string, document?: PipelineDocument) =>
    request<PipelineDoc>("/pipelines", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, document }),
    }),
  listTemplates: () =>
    request<
      Array<{
        slug: string;
        title: string;
        summary: string;
        tags: string[];
        needsSampleDataset: boolean;
        stepCount: number;
      }>
    >("/pipelines/templates/list"),
  createFromTemplate: (slug: string) =>
    request<PipelineDoc>(`/pipelines/templates/${slug}`, { method: "POST" }),
  /** Generate an "overview" pipeline (parallel chart steps) from a dataset's
   *  column profile. Used by the "🚀 Generate overview" CTA on the dataset
   *  page and the first-run starter card on the home page. */
  createPipelineFromDataset: (datasetId: string) =>
    request<PipelineDoc>(`/pipelines/from-dataset/${datasetId}`, { method: "POST" }),
  exportPipeline: (id: string) =>
    request<{
      $dig: string;
      exportedAt: string;
      etag: number;
      name: string;
      document: PipelineDocument;
    }>(`/pipelines/${id}/export`),
  importPipeline: (envelope: unknown) =>
    request<PipelineDoc>("/pipelines/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(envelope),
    }),
  getPipeline: (id: string) => request<PipelineDoc>(`/pipelines/${id}`),
  updatePipeline: (
    id: string,
    document: PipelineDocument,
    expectedEtag?: number,
    opts?: { triggeredBy?: "manual_save" | "autosave" | "import" | "restore"; changeReason?: string | null },
  ) =>
    request<PipelineDoc>(`/pipelines/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        document,
        expectedEtag,
        triggeredBy: opts?.triggeredBy,
        changeReason: opts?.changeReason,
      }),
    }),
  clonePipeline: (id: string, name: string, fromSnapshotId?: string) =>
    request<PipelineDoc>(`/pipelines/${id}/clone`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, fromSnapshotId }),
    }),
  deletePipeline: (id: string) =>
    request<void>(`/pipelines/${id}`, { method: "DELETE" }),
  // ---- Templates (public gallery) ----
  listGalleryTemplates: (visibility?: "public" | "unlisted", tag?: string) => {
    const q = new URLSearchParams();
    if (visibility) q.set("visibility", visibility);
    if (tag) q.set("tag", tag);
    const qs = q.toString();
    return request<GalleryTemplate[]>(`/templates${qs ? "?" + qs : ""}`);
  },
  getGalleryTemplate: (slug: string) =>
    request<GalleryTemplateDetail>(`/templates/${encodeURIComponent(slug)}`),
  createGalleryTemplate: (body: {
    pipelineId: string;
    title: string;
    summary?: string;
    tags?: string[];
    sampleDatasetUrl?: string;
    needsSampleDataset?: boolean;
    authorHandle?: string;
    visibility?: "private" | "unlisted" | "public";
  }) =>
    request<GalleryTemplate>("/templates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  cloneGalleryTemplate: (slug: string) =>
    request<{ pipelineId: string }>(
      `/templates/${encodeURIComponent(slug)}/clone`,
      { method: "POST" },
    ),
  // ---- Column lineage ----
  getColumnLineage: (pipelineId: string, nodeId: string, column: string) =>
    request<ColumnLineageGraph>(
      `/pipelines/${pipelineId}/lineage/columns/${encodeURIComponent(nodeId)}/${encodeURIComponent(column)}`,
    ),
  // ---- History + diff ----
  listPipelineHistory: (id: string, limit = 50) =>
    request<PipelineHistoryEntry[]>(`/pipelines/${id}/history?limit=${limit}`),
  getPipelineSnapshot: (id: string, snapshotId: string) =>
    request<{
      id: string;
      pipelineId: string;
      etag: number;
      document: PipelineDocument;
      changeSummary: string | null;
      triggeredBy: string;
      createdAt: string;
    }>(`/pipelines/${id}/history/${snapshotId}`),
  diffPipeline: (id: string, fromRef: string, toRef: string) =>
    request<PipelineDiffResult>(`/pipelines/${id}/diff`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fromRef, toRef }),
    }),
  restorePipeline: (id: string, snapshotId: string) =>
    request<PipelineDoc>(`/pipelines/${id}/restore/${snapshotId}`, {
      method: "POST",
    }),
  validatePipeline: (id: string) =>
    request<ValidateResult>(`/pipelines/${id}/validate`, { method: "POST" }),
  fetchCompile: (
    id: string,
    sampleRows?: number,
    terminal?: string,
    signal?: AbortSignal,
    terminalViewMode?: "matched" | "unmatched_left" | "unmatched_right",
  ) => {
    const q = new URLSearchParams({
      sample_rows: String(sampleRows ?? 100000),
      target: "browser",
    });
    if (terminal) q.set("terminal", terminal);
    // The default viewMode 'matched' is the same as omitting the
    // param — keep the URL clean so cache keys aren't perturbed for
    // non-join steps where this is irrelevant.
    if (terminalViewMode && terminalViewMode !== "matched") {
      q.set("terminalViewMode", terminalViewMode);
    }
    return request<{
      sql: string;
      files: Array<{ name: string; url: string; format: string }>;
      terminal: string | null;
      sampleRows: number | null;
    }>(`/pipelines/${id}/compile?${q}`, { method: "POST", signal });
  },
  /** Run a pipeline preview on the backend DuckDB and return rows directly.
   *  Used as a transparent fallback when the WASM build can't run the SQL —
   *  notably when the spatial extension is required (geographic / GEOMETRY). */
  previewOnBackend: (
    id: string,
    opts: { sampleRows?: number; previewLimit?: number; terminal?: string; signal?: AbortSignal } = {},
  ) => {
    const q = new URLSearchParams({
      sample_rows: String(opts.sampleRows ?? 100000),
      preview_limit: String(opts.previewLimit ?? 500),
    });
    if (opts.terminal) q.set("terminal", opts.terminal);
    return request<{
      columns: Array<{ name: string; type: string }>;
      rows: Array<Record<string, unknown>>;
      rowCount: number;
      sampleRows: number;
      elapsedMs: number;
    }>(`/pipelines/${id}/preview?${q}`, { method: "POST", signal: opts.signal });
  },
  /** Run a single Polars-engine step on sampled upstream data and return
   *  the resulting DataFrame as JSON rows. Used by the editor as a
   *  transparent fallback when DuckDB-WASM can't run the focused step
   *  (any step with `engine.browser: "none"` — anomaly_zscore, rolling,
   *  forecast, seasonal_decompose, …). Returns the same shape as
   *  `previewOnBackend` so the grid renders it identically. */
  previewStepRows: (
    id: string,
    opts: { terminal: string; sampleRows?: number; previewLimit?: number; signal?: AbortSignal },
  ) => {
    const q = new URLSearchParams({
      terminal: opts.terminal,
      sample_rows: String(opts.sampleRows ?? 20000),
      preview_limit: String(opts.previewLimit ?? 500),
    });
    return request<{
      columns: Array<{ name: string; type: string }>;
      rows: Array<Record<string, unknown>>;
      rowCount: number;
      sampleRows: number;
      elapsedMs: number;
    }>(`/pipelines/${id}/preview-step-rows?${q}`, { method: "POST", signal: opts.signal });
  },

  // ---- Runs ----
  startRun: (pipelineId: string, sampleRows?: number) =>
    request<RunOut>(`/pipelines/${pipelineId}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sampleRows }),
    }),
  listRuns: (pipelineId: string) =>
    request<RunOut[]>(`/pipelines/${pipelineId}/runs`),
  /** Phase A Layer 2 — fetch per-node + per-group freshness states for
   *  the canvas halo overlay. */
  getFreshness: (pipelineId: string) =>
    request<{
      states: Record<string, "fresh" | "due" | "stale" | "never">;
      group_states: Record<string, "fresh" | "due" | "stale" | "never">;
    }>(
      `/pipelines/${pipelineId}/freshness`,
    ),
  // (Phase A Layer 3 column lineage trace lives at line ~699 above —
  // `getColumnLineage` returning ColumnLineageGraph. Don't duplicate it.)
  getRun: (runId: string) => request<RunOut>(`/runs/${runId}`),
  /** Phase-A-pro #5 — workspace-wide runs list. Compact summary
   *  shape; click into a row to fetch the full RunOut. */
  listAllRuns: (params: {
    pipeline_id?: string;
    status?: string;
    tag?: string;
    started_after?: string;
    started_before?: string;
    cursor?: string;
    limit?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (params.pipeline_id) q.set("pipeline_id", params.pipeline_id);
    if (params.status) q.set("status", params.status);
    if (params.tag) q.set("tag", params.tag);
    if (params.started_after) q.set("started_after", params.started_after);
    if (params.started_before) q.set("started_before", params.started_before);
    if (params.cursor) q.set("cursor", params.cursor);
    if (params.limit) q.set("limit", String(params.limit));
    return request<RunListPage>(`/runs?${q}`);
  },
  getRunOutput: (runId: string, offset = 0, limit = 100, outputId?: string) => {
    const q = new URLSearchParams({ offset: String(offset), limit: String(limit) });
    if (outputId) q.set("output_id", outputId);
    return request<RunOutputPage>(`/runs/${runId}/output?${q}`);
  },
  /** Build a URL the browser can <img>-src directly. The backend's
   *  /runs/{id}/artifact endpoint validates the path is inside the run dir. */
  artifactUrl: (runId: string, path: string) =>
    `${API_BASE}/runs/${runId}/artifact?path=${encodeURIComponent(path)}`,

  /** Walk an output row back to its source dataset rows. Requires the
   *  pipeline to have been run with metadata.trackLineage=true. */
  getRunLineage: (runId: string, rowIndex: number, outputId?: string) => {
    const q = new URLSearchParams({ row_index: String(rowIndex) });
    if (outputId) q.set("output_id", outputId);
    return request<{
      runId: string;
      outputRowIndex: number;
      sources: Array<{
        dataset_id: string;
        dataset_label?: string;
        row_index: number;
        row: Record<string, unknown> | null;
      }>;
    }>(`/runs/${runId}/lineage?${q}`);
  },

  /** Cell-level diff between two runs of the same pipeline. */
  diffRuns: (runId: string, otherRunId: string, outputId?: string) => {
    const q = new URLSearchParams({ other: otherRunId });
    if (outputId) q.set("output_id", outputId);
    return request<{
      joinKey: string | null;
      rowsA: number;
      rowsB: number;
      addedCount: number;
      droppedCount: number;
      changedCount: number;
      added: Array<Record<string, unknown> | unknown[]>;
      dropped: Array<Record<string, unknown> | unknown[]>;
      changed: Array<{
        key?: unknown;
        diffs?: Record<string, { a: unknown; b: unknown }>;
      }>;
    }>(`/runs/${runId}/diff?${q}`);
  },

  /** Render the pipeline as a standalone Polars Python script. */
  exportPipelinePython: (id: string) =>
    request<{
      pipelineId: string;
      name: string;
      code: string;
      language: string;
      unsupportedSteps: string[];
    }>(`/pipelines/${id}/python`),

  /** Render the pipeline as a Jupyter notebook (.ipynb) document. */
  exportPipelineNotebook: (id: string) =>
    request<Record<string, unknown>>(`/pipelines/${id}/notebook`),

  // ---- Connectors ----
  listConnectorsTyped: () => request<ConnectorManifest[]>("/connectors"),

  // ---- Logical types catalog (powers the Cast smart-picks UI) ----
  listTypes: () => request<TypeDescriptor[]>("/types"),

  // ---- Settings (server-side) ----
  listSettings: () => request<SettingDescriptor[]>("/settings"),
  setSetting: (key: string, value: unknown) =>
    request<SettingDescriptor>(`/settings/${key}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ value }),
    }),

  // ---- JDBC drivers ----
  listJdbcDrivers: () => request<JdbcDriverRecord[]>("/jdbc-drivers"),
  createJdbcDriver: (body: JdbcDriverInput) =>
    request<JdbcDriverRecord>("/jdbc-drivers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  updateJdbcDriver: (id: string, body: JdbcDriverInput) =>
    request<JdbcDriverRecord>(`/jdbc-drivers/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteJdbcDriver: (id: string) =>
    request<void>(`/jdbc-drivers/${id}`, { method: "DELETE" }),
  /** Try a quick connect against the supplied params and return the result
   *  — never throws on a failed connection (the response body's `ok` flag
   *  carries that). Only throws on outright API errors (network down, 500). */
  testJdbcDriver: (body: JdbcTestInput) =>
    request<JdbcTestResult>("/jdbc-drivers/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  // ---- Filesystem browser (settings directory picker) ----
  browseDir: (path?: string) =>
    request<FsBrowseResult>(`/fs/browse${path ? `?path=${encodeURIComponent(path)}` : ""}`),

  // ---- Global webhooks ----
  listGlobalWebhooks: () => request<GlobalWebhookRecord[]>("/global-webhooks"),
  createGlobalWebhook: (body: GlobalWebhookInput) =>
    request<GlobalWebhookRecord>("/global-webhooks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  updateGlobalWebhook: (id: string, body: GlobalWebhookInput) =>
    request<GlobalWebhookRecord>(`/global-webhooks/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  deleteGlobalWebhook: (id: string) =>
    request<void>(`/global-webhooks/${id}`, { method: "DELETE" }),
};

// ---- Settings types ------------------------------------------------------

export interface SettingDescriptor {
  key: string;
  value: unknown | null;
  default: unknown | null;
  label: string;
  help: string;
  type: "path" | "integer" | "enum" | "boolean" | "string" | "secret" | "float";
  options?: string[];
}

export interface FsBrowseEntry {
  name: string;
  is_dir: boolean;
}
export interface FsBrowseResult {
  path: string;
  parent: string | null;
  home: string;
  entries: FsBrowseEntry[];
  exists: boolean;
}

export interface JdbcDriverInput {
  name: string;
  driverClass: string;
  jarPath: string;
  urlTemplate?: string | null;
  notes?: string | null;
}
export interface JdbcDriverRecord extends JdbcDriverInput {
  id: string;
}

/** Ad-hoc connection test parameters. URL + creds are not persisted —
 *  one-off use for the "🔌 Test connection" affordance in Settings → JDBC. */
export interface JdbcTestInput {
  driverClass: string;
  jarPath: string;
  url?: string | null;
  username?: string | null;
  password?: string | null;
}

export interface JdbcTestResult {
  ok: boolean;
  /** Human-readable summary — "Connected · 87ms" on success, the JDBC
   *  driver's own error message on failure. */
  message: string;
  latencyMs?: number | null;
  /** Server product + version reported via DatabaseMetaData when the
   *  driver exposes it. */
  serverInfo?: string | null;
}

export interface GlobalWebhookInput {
  label?: string | null;
  url: string;
  /** "triggered" never auto-fires — only invoked by the in-pipeline
   * 🔔 Trigger webhook step. */
  on?: "always" | "succeeded" | "failed" | "triggered";
  secret?: string | null;
  headers?: Record<string, string> | null;
  enabled?: boolean;
}
export interface GlobalWebhookRecord extends GlobalWebhookInput {
  id: string;
}

// ---- AI assistant -------------------------------------------------------

export interface AiConfigOut {
  enabled: boolean;
  provider: "local" | "openai_compat" | "disabled";
  endpoint: string;
  model: string;
  has_api_key: boolean;
  max_tokens: number;
  temperature: number;
}

export interface AiProbeOut {
  ok: boolean;
  error?: string | null;
  model?: string | null;
  reply?: string | null;
}

export interface AiChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface AiChatResponse {
  text: string;
  model: string;
  usage?: Record<string, number> | null;
}

export interface AiExplainOut {
  markdown: string;
  model: string;
}

export type AiReviewSeverity = "info" | "warn" | "high";
export type AiReviewCategory =
  | "performance"
  | "correctness"
  | "quality"
  | "lineage"
  | "ergonomics";

export interface AiReviewFinding {
  severity: AiReviewSeverity;
  category: AiReviewCategory;
  title: string;
  explanation: string;
  affected_nodes: string[];
  confidence: number;
}

export interface AiReviewOut {
  findings: AiReviewFinding[];
  model: string;
  rawText: string | null;
}

export interface AiFixExpressionIn {
  expression: string;
  columns?: Array<{ name: string; type: string }>;
  intent?: string;
  error?: string;
  kind?: "predicate" | "scalar";
}

export interface AiFixExpressionOut {
  fixed: string;
  explanation: string;
  confidence: "high" | "medium" | "low";
  model: string;
}

export interface AiProbeUrlIn {
  url: string;
  auth_header?: string | null;
}

export interface AiProbeUrlOut {
  ok: boolean;
  status: number | null;
  content_type?: string | null;
  final_url?: string | null;
  length?: number;
  error?: string | null;
  body_preview?: string | null;
  json_shape?: { type: string; length?: number; keys?: string[]; first_keys?: string[] | null } | null;
}

export interface AiGenerateConnectorIn {
  url: string;
  intent?: string | null;
  sample_shape?: Record<string, unknown> | null;
  auth_kind?: "none" | "bearer" | "api_key_query" | "basic";
}

export interface AiLintIssue {
  line: number;
  col: number;
  rule: string;
  message: string;
}

export interface AiGeneratedConnector {
  id: string;
  label?: string | null;
  description?: string | null;
  manifest: Record<string, unknown>;
  connector_py: string;
  lint_issues: AiLintIssue[];
  model: string;
  pending_path: string;
  safe_to_install: boolean;
}

export interface AiSuggestion {
  step_id: string;
  params: Record<string, unknown>;
  why: string;
  confidence: "high" | "medium" | "low";
}

export interface AiVizSuggestion {
  step_id: string;
  params: Record<string, unknown>;
  title: string;
  why: string;
  confidence: "high" | "medium" | "low";
}

export interface AiSuggestVisualizationsOut {
  domain: string;
  domain_confidence: "high" | "medium" | "low";
  suggestions: AiVizSuggestion[];
  model?: string | null;
  /** When set, the LLM returned no usable content — surface as
   *  "No suitable domain or visualization identified" in the UI. */
  reason?: string | null;
}

export interface AiColumnMeaning {
  name: string;
  meaning: string;
}

export interface AiExplainDatasetOut {
  narrative: string;
  domain: string;
  confidence: "high" | "medium" | "low";
  columns: AiColumnMeaning[];
  model?: string | null;
  reason?: string | null;
}

export interface AiPipelineStepSuggestion {
  step_id: string;
  params: Record<string, unknown>;
  rationale: string;
  outcome?: string | null;
  /** For `step_id == "join"` only — the ref id (dataset alias or
   *  upstream node id) the validator chose for the right input
   *  port. The frontend wires this when applying the route. */
  right_ref?: string | null;
}

export interface AiPipelineRoute {
  title: string;
  why: string;
  steps: AiPipelineStepSuggestion[];
  confidence: "high" | "medium" | "low";
}

export interface AiSuggestPipelineStepsOut {
  domain: string;
  routes: AiPipelineRoute[];
  model?: string | null;
  reason?: string | null;
}

export interface AiSuggestNextIn {
  pipeline_id: string;
  focused_node_id?: string | null;
  focused_schema?: Record<string, string>;
  goal: string;
}

export interface AiSuggestNextOut {
  suggestions: AiSuggestion[];
  model: string;
}

export interface AiGenerateStepIn {
  description: string;
  schema_hint?: Record<string, string>;
}

export interface AiGeneratedStep {
  id: string;
  label?: string | null;
  description?: string | null;
  manifest: Record<string, unknown>;
  step_py: string;
  lint_issues: AiLintIssue[];
  model: string;
  pending_path: string;
  safe_to_install: boolean;
}

export interface AiModelsOut {
  models: string[];
  endpoint: string;
}

export const aiApi = {
  config: () => request<AiConfigOut>("/ai/config"),
  probe: () => request<AiProbeOut>("/ai/probe", { method: "POST" }),
  listModels: () => request<AiModelsOut>("/ai/models"),
  chat: (
    messages: AiChatMessage[],
    opts?: { responseFormat?: "json_object"; temperature?: number; maxTokens?: number },
  ) =>
    request<AiChatResponse>("/ai/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages,
        response_format: opts?.responseFormat,
        temperature: opts?.temperature,
        max_tokens: opts?.maxTokens,
      }),
    }),
  explainPipeline: (pipelineId: string) =>
    request<AiExplainOut>(`/ai/explain-pipeline/${pipelineId}`, { method: "POST" }),
  reviewPipeline: (pipelineId: string) =>
    request<AiReviewOut>(`/ai/review-pipeline/${pipelineId}`, { method: "POST" }),
  fixExpression: (body: AiFixExpressionIn) =>
    request<AiFixExpressionOut>("/ai/fix-expression", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  probeUrl: (body: AiProbeUrlIn) =>
    request<AiProbeUrlOut>("/ai/probe-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  generateConnector: (body: AiGenerateConnectorIn) =>
    request<AiGeneratedConnector>("/ai/generate-connector", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  installConnector: (connectorId: string) =>
    request<{ ok: boolean; installed_at: string; note: string }>(
      "/ai/install-connector",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ connector_id: connectorId }),
      },
    ),
  discardConnector: (connectorId: string) =>
    request<{ ok: boolean; discarded: string }>(
      `/ai/pending-connector/${connectorId}`,
      { method: "DELETE" },
    ),
  suggestNextStep: (body: AiSuggestNextIn) =>
    request<AiSuggestNextOut>("/ai/suggest-next-step", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  // The three Hints-panel AI endpoints accept either a registered
  // dataset id (legacy) OR a pipeline-doc node id (any focused node —
  // dataset alias OR step output). When `node_id` is set the backend
  // pulls schema + samples from that node's actual output via the
  // pipeline's chosen sampling method; the prompt is also rephrased
  // for derived contexts. `pipeline_id` is required.
  suggestVisualizations: (body: {
    pipeline_id: string;
    node_id?: string | null;
    dataset_id?: string | null;
  }) =>
    request<AiSuggestVisualizationsOut>("/ai/suggest-visualizations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  explainDataset: (body: {
    pipeline_id: string;
    node_id?: string | null;
    dataset_id?: string | null;
  }) =>
    request<AiExplainDatasetOut>("/ai/explain-dataset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  suggestPipelineSteps: (body: {
    pipeline_id: string;
    node_id?: string | null;
    dataset_id?: string | null;
    goal?: string | null;
  }) =>
    request<AiSuggestPipelineStepsOut>("/ai/suggest-pipeline-steps", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  generateStep: (body: AiGenerateStepIn) =>
    request<AiGeneratedStep>("/ai/generate-step", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  installStep: (stepId: string) =>
    request<{ ok: boolean; installed_at: string; note: string }>(
      "/ai/install-step",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ step_id: stepId }),
      },
    ),
  discardStep: (stepId: string) =>
    request<{ ok: boolean; discarded: string }>(
      `/ai/pending-step/${stepId}`,
      { method: "DELETE" },
    ),
};

// ---- Schedules (cron-backed) -------------------------------------------

export interface ScheduleEntry {
  pipeline_id: string;
  cron: string;
  sample_rows?: number | null;
  raw: string;
}

export const schedulesApi = {
  list: () => request<ScheduleEntry[]>("/schedules"),
  add: (pipelineId: string, cron: string, sampleRows?: number) =>
    request<ScheduleEntry>("/schedules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pipeline_id: pipelineId,
        cron,
        sample_rows: sampleRows,
      }),
    }),
  remove: (pipelineId: string) =>
    request<{ ok: boolean }>(`/schedules/${pipelineId}`, { method: "DELETE" }),
};

// ---- Notifications -----------------------------------------------------

export type NotificationKind =
  | "system" | "runtime" | "freshness" | "login" | "resources" | "security";
export type NotificationLevel = "notification" | "warning" | "error";

export interface NotificationOut {
  id: string;
  createdAt: string;
  kind: string;
  level: string;
  title: string;
  message?: string | null;
  userId?: string | null;
  context?: Record<string, unknown> | null;
  dismissedAt?: string | null;
}

export interface NotificationListOut {
  items: NotificationOut[];
  total: number;
  unread: number;
}

// ---- Catalog (cross-pipeline lineage) ----------------------------------

export interface CatalogNodeOut {
  id: string;
  kind: "pipeline" | "consumer";
  name: string;
  description?: string | null;
  last_run_at?: string | null;
  last_run_status?: string | null;
  node_count: number;
  group_count: number;
  inputs: string[];
  outputs: string[];
  /** Phase-A-pro #3 — user tags. Powers the catalog filter chips. */
  tags?: string[];
}

export interface CatalogEdgeOut {
  from_id: string;
  to_id: string;
  via?: string | null;
  /** Phase-A-pro #6 — column names that flow through this edge.
   *  Populated when the URI in `via` matches a registered Dataset's
   *  source/storage URI; empty otherwise. */
  columns?: string[];
}

export const catalogApi = {
  lineage: () =>
    request<{ nodes: CatalogNodeOut[]; edges: CatalogEdgeOut[] }>(
      "/catalog/lineage",
    ),
};

// Phase-A-pro #3 — workspace search.
export interface SearchHit {
  kind: "pipeline" | "dataset" | "column" | "tag";
  id: string;
  label: string;
  subtitle?: string | null;
  href: string;
  tag_match?: string | null;
}
export interface SearchOut {
  query: string;
  hits: SearchHit[];
  total: number;
}

export const searchApi = {
  /** Workspace-wide substring search across pipelines, datasets, and
   *  columns. Empty query returns empty hits (no "show everything"
   *  fallback — the cmdk already lists pipelines+datasets without
   *  hitting this endpoint). */
  query: (q: string, limit = 50) =>
    request<SearchOut>(`/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  /** Distinct tag names across the workspace, sorted alphabetically.
   *  Powers tag autocomplete + the catalog filter dropdown. */
  listTags: () => request<{ tags: string[] }>("/search/tags"),
  /**
   * Update a pipeline's tag list. Pass the current ``etag`` so the backend
   * can reject the call (HTTP 409) if another writer modified the pipeline
   * in the meantime — without this gate, a tag-edit can race against the
   * editor's autosave and silently lose the autosave's changes (round-3
   * QA finding).
   */
  setPipelineTags: (pipelineId: string, tags: string[], etag?: number | null) => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (typeof etag === "number") headers["If-Match"] = String(etag);
    return request<{ tags: string[] }>(`/search/pipelines/${pipelineId}/tags`, {
      method: "PUT",
      headers,
      body: JSON.stringify({ tags }),
    });
  },
};

// ---- Notification rules -----------------------------------------------

export type NotificationChannel = "in_app" | "email" | "slack" | "webhook";

export interface RuleAction {
  level: "auto" | "notification" | "warning" | "error";
  title: string;
  message?: string | null;
  channel: NotificationChannel;
}

export interface NotificationRuleOut {
  id: string;
  name: string;
  description?: string | null;
  enabled: boolean;
  event_kind: string;
  filters?: Record<string, unknown> | null;
  action: RuleAction;
  cooldown_seconds?: number | null;
  last_fired_at?: string | null;
  fire_count: number;
  is_builtin: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationRuleIn {
  name: string;
  description?: string | null;
  enabled: boolean;
  event_kind: string;
  filters?: Record<string, unknown> | null;
  action: RuleAction;
  cooldown_seconds?: number | null;
}

export const notificationRulesApi = {
  list: () => request<NotificationRuleOut[]>("/notification-rules"),
  eventKinds: () =>
    request<{ kinds: string[] }>("/notification-rules/event-kinds"),
  create: (body: NotificationRuleIn) =>
    request<NotificationRuleOut>("/notification-rules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  update: (id: string, body: NotificationRuleIn) =>
    request<NotificationRuleOut>(`/notification-rules/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  toggle: (id: string) =>
    request<NotificationRuleOut>(`/notification-rules/${id}/toggle`, {
      method: "PATCH",
    }),
  remove: (id: string) =>
    request<void>(`/notification-rules/${id}`, { method: "DELETE" }),
};

export const notificationsApi = {
  list: (opts: {
    kind?: string;
    level?: string;
    includeDismissed?: boolean;
    limit?: number;
    offset?: number;
  } = {}) => {
    const q = new URLSearchParams();
    if (opts.kind) q.set("kind", opts.kind);
    if (opts.level) q.set("level", opts.level);
    if (opts.includeDismissed) q.set("include_dismissed", "true");
    if (opts.limit != null) q.set("limit", String(opts.limit));
    if (opts.offset != null) q.set("offset", String(opts.offset));
    const qs = q.toString();
    return request<NotificationListOut>(
      `/notifications${qs ? `?${qs}` : ""}`,
    );
  },
  unreadCount: () => request<{ unread: number }>("/notifications/unread-count"),
  dismiss: (id: string) =>
    request<NotificationOut>(`/notifications/${id}/dismiss`, { method: "PATCH" }),
  dismissAll: () =>
    request<{ dismissed: number }>("/notifications/dismiss-all", { method: "POST" }),
  remove: (id: string) =>
    request<void>(`/notifications/${id}`, { method: "DELETE" }),
};

export { ApiError };
export type { paths };
