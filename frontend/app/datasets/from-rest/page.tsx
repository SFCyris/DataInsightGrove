"use client";

/**
 * REST API dataset wizard.
 *
 * Walks the user through:
 *   1. Name + URL
 *   2. Auth (none / bearer / api_key_query / api_key_header / basic)
 *   3. Pagination (none / cursor / offset_limit / page_number / link_header)
 *   4. JSONPath to records
 *
 * Then calls POST /datasets/from-uri with connector_id="rest_api".
 *
 * For one-off integrations the wizard saves the user from writing a
 * connector folder; for repeated SaaS pulls they can later promote the
 * working configuration into a purpose-built connector via the AI
 * generate-connector flow.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";

type AuthKind = "none" | "bearer" | "api_key_query" | "api_key_header" | "basic";
type Pagination = "none" | "cursor" | "offset_limit" | "page_number" | "link_header";

const AUTH_HELP: Record<AuthKind, string> = {
  none: "No authentication.",
  bearer: "Sends 'Authorization: Bearer <token>'. Most common for modern APIs.",
  api_key_query: "Appends ?<param-name>=<key> to the URL. Common for older APIs.",
  api_key_header: "Sends '<header-name>: <key>'. Use for X-API-Key etc.",
  basic: "Sends 'Authorization: Basic <base64(user:pass)>'. Auth value is 'username:password'.",
};

const PAGINATION_HELP: Record<Pagination, string> = {
  none: "Single fetch — no pagination.",
  cursor: "Response carries a cursor field; next call sends ?<cursor-param>=<cursor>.",
  offset_limit: "?offset=N&limit=<page-size>. Standard SQL-style pagination.",
  page_number: "?page=N&per_page=<page-size>. WordPress / GitHub style.",
  link_header: "Follows the RFC 5988 'Link: <...>; rel=\"next\"' header.",
};

export default function FromRestPage() {
  const router = useRouter();
  const reduce = useReducedMotion();
  const fadeUp = reduce
    ? { initial: false as const, animate: { opacity: 1, y: 0 } }
    : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 30 } };

  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [authKind, setAuthKind] = useState<AuthKind>("none");
  const [authValue, setAuthValue] = useState("");
  const [authParamName, setAuthParamName] = useState("api_key");
  const [jsonPath, setJsonPath] = useState("$");
  const [pagination, setPagination] = useState<Pagination>("none");
  const [cursorParam, setCursorParam] = useState("cursor");
  const [cursorRespPath, setCursorRespPath] = useState("next_cursor");
  const [pageSize, setPageSize] = useState(100);
  const [maxPages, setMaxPages] = useState(50);
  const [extraHeaders, setExtraHeaders] = useState("{}");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async () => {
    setError(null);
    if (!name.trim()) { setError("Name is required."); return; }
    if (!url.trim()) { setError("URL is required."); return; }

    let parsedHeaders: Record<string, string> = {};
    try {
      parsedHeaders = extraHeaders.trim() ? JSON.parse(extraHeaders) : {};
      if (typeof parsedHeaders !== "object" || Array.isArray(parsedHeaders)) {
        throw new Error("must be a JSON object");
      }
    } catch (e) {
      setError(`Extra headers: ${(e as Error).message}`);
      return;
    }

    setSubmitting(true);
    try {
      const dataset = await api.createDatasetFromUri(name.trim(), "rest_api", url.trim(), {
        auth_kind: authKind,
        auth_value: authValue,
        auth_param_name: authParamName,
        json_path: jsonPath,
        pagination,
        cursor_param_name: cursorParam,
        cursor_response_path: cursorRespPath,
        page_size: pageSize,
        max_pages: maxPages,
        extra_headers: parsedHeaders,
      });
      if (dataset.status === "failed") {
        setError(dataset.error ?? "Ingest failed");
      } else {
        toast.success(`Imported ${dataset.rowCount ?? 0} rows`);
        router.push(`/datasets/${dataset.id}`);
      }
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? typeof e.detail === "object" && e.detail && "detail" in e.detail
            ? String((e.detail as { detail: unknown }).detail)
            : e.message
          : (e as Error).message;
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main id="main" className="flex-1 overflow-y-auto p-6 sm:p-10 max-w-3xl mx-auto w-full">
      <motion.header {...fadeUp} className="mb-6">
        <Link href="/datasets" className="text-xs text-muted-foreground hover:text-foreground">← Datasets</Link>
        <h1 className="text-2xl font-semibold tracking-tight mt-1">
          🌐 Import from a REST API
        </h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          One configurable connector for any JSON-returning HTTP API. No code, no
          connector folder — just paste the URL, set auth + pagination, click Import.
          For repeated SaaS pulls you can later promote this into a purpose-built
          connector via <Link href="/connectors/new" className="underline">✨ Generate connector</Link>.
        </p>
      </motion.header>

      <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4 mb-4">
        <Field label="Dataset name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Stripe charges"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
        </Field>
        <Field label="URL">
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://api.example.com/v1/things"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
          />
        </Field>
      </motion.section>

      <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4 mb-4">
        <h2 className="font-medium">Authentication</h2>
        <Field label="Auth kind">
          <select
            value={authKind}
            onChange={(e) => setAuthKind(e.target.value as AuthKind)}
            className="w-full rounded-md border border-input bg-background px-2 py-2 text-sm"
          >
            <option value="none">None</option>
            <option value="bearer">Bearer token</option>
            <option value="api_key_query">API key in query string</option>
            <option value="api_key_header">API key in header</option>
            <option value="basic">Basic auth (user:pass)</option>
          </select>
          <p className="text-[11px] text-muted-foreground mt-1">{AUTH_HELP[authKind]}</p>
        </Field>
        {authKind !== "none" && (
          <>
            {(authKind === "api_key_query" || authKind === "api_key_header") && (
              <Field label="Parameter / header name">
                <input
                  value={authParamName}
                  onChange={(e) => setAuthParamName(e.target.value)}
                  placeholder="api_key"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
                />
              </Field>
            )}
            <Field label="Auth value (token / key / user:pass)">
              <input
                type="password"
                value={authValue}
                onChange={(e) => setAuthValue(e.target.value)}
                autoComplete="new-password"
                placeholder={authKind === "basic" ? "username:password" : "secret value"}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
              />
            </Field>
          </>
        )}
      </motion.section>

      <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4 mb-4">
        <h2 className="font-medium">Records + pagination</h2>
        <Field
          label="JSONPath to records"
          hint="Where in the response the records live. '$' = root array. '$.data' = response.data."
        >
          <input
            value={jsonPath}
            onChange={(e) => setJsonPath(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
          />
        </Field>
        <Field label="Pagination style">
          <select
            value={pagination}
            onChange={(e) => setPagination(e.target.value as Pagination)}
            className="w-full rounded-md border border-input bg-background px-2 py-2 text-sm"
          >
            <option value="none">None — single fetch</option>
            <option value="cursor">Cursor (response carries next-cursor)</option>
            <option value="offset_limit">Offset / limit</option>
            <option value="page_number">Page number / per_page</option>
            <option value="link_header">RFC 5988 Link header</option>
          </select>
          <p className="text-[11px] text-muted-foreground mt-1">{PAGINATION_HELP[pagination]}</p>
        </Field>
        {pagination === "cursor" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Cursor field in response">
              <input
                value={cursorRespPath}
                onChange={(e) => setCursorRespPath(e.target.value)}
                placeholder="next_cursor"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
              />
            </Field>
            <Field label="Cursor query param name">
              <input
                value={cursorParam}
                onChange={(e) => setCursorParam(e.target.value)}
                placeholder="cursor"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
              />
            </Field>
          </div>
        )}
        {pagination !== "none" && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="Page size" hint="Items per request.">
              <input
                type="number"
                value={pageSize}
                min={1}
                max={10000}
                onChange={(e) => setPageSize(Number(e.target.value))}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
              />
            </Field>
            <Field label="Max pages" hint="Hard cap to prevent runaway pagination.">
              <input
                type="number"
                value={maxPages}
                min={1}
                max={1000}
                onChange={(e) => setMaxPages(Number(e.target.value))}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
              />
            </Field>
          </div>
        )}
      </motion.section>

      <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4 mb-4">
        <h2 className="font-medium">Advanced</h2>
        <Field label="Extra request headers (JSON)">
          <textarea
            value={extraHeaders}
            onChange={(e) => setExtraHeaders(e.target.value)}
            placeholder='{"X-Custom": "value"}'
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono min-h-[80px]"
          />
        </Field>
      </motion.section>

      {error && (
        <p className="text-sm text-rose-600 dark:text-rose-400 mb-3 break-words">{error}</p>
      )}

      <div className="flex justify-end gap-2">
        <Link
          href="/datasets"
          className="text-sm text-muted-foreground hover:text-foreground self-center"
        >
          Cancel
        </Link>
        <Button onClick={onSubmit} disabled={submitting} size="sm">
          {submitting ? "⏳ Importing…" : "📥 Import"}
        </Button>
      </div>
    </main>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] uppercase tracking-widest text-muted-foreground block mb-1">
        {label}
      </label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground mt-1">{hint}</p>}
    </div>
  );
}
