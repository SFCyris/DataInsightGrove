/**
 * Thin typed fetch wrapper around the DIG backend.
 *
 * Path/response types come from `lib/api/types.ts` which is generated from the
 * backend's OpenAPI schema (`pnpm gen:api` from the repo root).
 */
import type { components, paths } from "./types";

export const API_BASE =
  (typeof window !== "undefined" && (window as { __DIG_API__?: string }).__DIG_API__) ||
  process.env.NEXT_PUBLIC_DIG_API ||
  "http://127.0.0.1:8090";

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
}
export type RowsPage = components["schemas"]["RowsPage"];
export type Health = components["schemas"]["Health"];
export type PipelineSummary = components["schemas"]["PipelineSummary"];
export type PipelineDoc = components["schemas"]["PipelineDoc"];
export type RunOut = components["schemas"]["RunOut"];

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
  ui?: { x?: number; y?: number; label?: string };
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

export interface ValidateResult {
  ok: boolean;
  errors: string[];
  schemas: Record<string, Record<string, string>>;
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
    throw new ApiError(res.status, `${res.status} ${res.statusText}`, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
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
  updatePipeline: (id: string, document: PipelineDocument, expectedEtag?: number) =>
    request<PipelineDoc>(`/pipelines/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document, expectedEtag }),
    }),
  deletePipeline: (id: string) =>
    request<void>(`/pipelines/${id}`, { method: "DELETE" }),
  validatePipeline: (id: string) =>
    request<ValidateResult>(`/pipelines/${id}/validate`, { method: "POST" }),
  fetchCompile: (id: string, sampleRows?: number, terminal?: string, signal?: AbortSignal) => {
    const q = new URLSearchParams({
      sample_rows: String(sampleRows ?? 100000),
      target: "browser",
    });
    if (terminal) q.set("terminal", terminal);
    return request<{
      sql: string;
      files: Array<{ name: string; url: string; format: string }>;
      terminal: string | null;
      sampleRows: number | null;
    }>(`/pipelines/${id}/compile?${q}`, { method: "POST", signal });
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
  getRun: (runId: string) => request<RunOut>(`/runs/${runId}`),
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
  type: "path" | "integer" | "enum" | "boolean";
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

export { ApiError };
export type { paths };
