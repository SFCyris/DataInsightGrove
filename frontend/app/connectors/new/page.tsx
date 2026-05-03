"use client";

/**
 * AI-assisted connector wizard.
 *
 * Three-step flow:
 *   1. Enter URL + auth → Probe (one-shot fetch via backend) to verify
 *      it works and discover the JSON shape
 *   2. Optionally describe intent → Generate (LLM produces manifest +
 *      connector.py, backend stages to plugins/_pending/, runs safety
 *      lint)
 *   3. Review the generated diff + lint findings → Install (move to
 *      plugins/connectors/) or Discard
 *
 * Safety: AI-generated Python is statically linted on the backend
 * (see dig/ai/safety.py). The user only sees an "Install" button when
 * the lint passes. Lint findings are shown verbatim with the line/col
 * so the user can see exactly what tripped it.
 */

import Link from "next/link";
import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import {
  aiApi,
  ApiError,
  type AiGeneratedConnector,
  type AiProbeUrlOut,
} from "@/lib/api/client";
import { Button, buttonVariants } from "@/components/ui/button";

type AuthKind = "none" | "bearer" | "api_key_query" | "basic";

const AUTH_PLACEHOLDER: Record<AuthKind, string> = {
  none: "",
  bearer: "Bearer sk-…",
  api_key_query: "?api_key=…",
  basic: "Basic dXNlcjpwYXNz",
};

export default function NewConnectorPage() {
  const reduce = useReducedMotion();
  const fadeUp = reduce
    ? { initial: false as const, animate: { opacity: 1, y: 0 } }
    : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 30 } };

  const [url, setUrl] = useState("");
  const [authKind, setAuthKind] = useState<AuthKind>("none");
  const [authValue, setAuthValue] = useState("");
  const [intent, setIntent] = useState("");

  const [probing, setProbing] = useState(false);
  const [probe, setProbe] = useState<AiProbeUrlOut | null>(null);

  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState<AiGeneratedConnector | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);

  const onProbe = async () => {
    if (!url.trim()) return;
    setProbing(true);
    setProbe(null);
    setGenerated(null);
    try {
      const result = await aiApi.probeUrl({
        url: url.trim(),
        auth_header: authKind === "bearer" || authKind === "basic" ? authValue.trim() || undefined : undefined,
      });
      setProbe(result);
    } catch (e) {
      setProbe({ ok: false, status: null, error: (e as Error).message });
    } finally {
      setProbing(false);
    }
  };

  const onGenerate = async () => {
    if (!url.trim() || !probe?.ok) return;
    setGenerating(true);
    setGenerated(null);
    setInstallError(null);
    try {
      const result = await aiApi.generateConnector({
        url: url.trim(),
        intent: intent.trim() || undefined,
        sample_shape: probe ? { ...probe } : undefined,
        auth_kind: authKind,
      });
      setGenerated(result);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? typeof e.detail === "object" && e.detail && "detail" in e.detail
            ? String((e.detail as { detail: unknown }).detail)
            : e.message
          : (e as Error).message;
      toast.error(msg);
    } finally {
      setGenerating(false);
    }
  };

  const onInstall = async () => {
    if (!generated) return;
    setInstallError(null);
    try {
      await aiApi.installConnector(generated.id);
      toast.success(`Installed connector "${generated.id}"`);
      setGenerated(null);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? typeof e.detail === "object" && e.detail && "detail" in e.detail
            ? String((e.detail as { detail: unknown }).detail)
            : e.message
          : (e as Error).message;
      setInstallError(msg);
    }
  };

  const onDiscard = async () => {
    if (!generated) return;
    try {
      await aiApi.discardConnector(generated.id);
      setGenerated(null);
      toast.success("Discarded");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <main id="main" className="flex-1 overflow-y-auto p-6 sm:p-10 max-w-4xl mx-auto w-full">
      <motion.header {...fadeUp} className="mb-6">
        <Link href="/" className="text-xs text-muted-foreground hover:text-foreground">← Home</Link>
        <h1 className="text-2xl font-semibold tracking-tight mt-1">
          ✨ Generate a connector
        </h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          Paste a URL, DIG probes it, asks the configured AI to generate a connector folder
          (manifest + Python). Static safety lint runs before you can install.
          Requires <Link href="/settings#ai" className="underline">AI Settings</Link> to be enabled.
        </p>
      </motion.header>

      {/* Step 1 — URL + auth */}
      <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4 mb-4">
        <header className="flex items-center gap-2">
          <span className="text-base font-medium">1.</span>
          <span className="font-medium">URL + authentication</span>
        </header>

        <div>
          <label className="text-[11px] uppercase tracking-widest text-muted-foreground block mb-1">URL</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://api.example.com/v1/things"
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono"
          />
        </div>

        <div className="grid grid-cols-[160px_1fr] gap-3">
          <div>
            <label className="text-[11px] uppercase tracking-widest text-muted-foreground block mb-1">Auth</label>
            <select
              value={authKind}
              onChange={(e) => setAuthKind(e.target.value as AuthKind)}
              className="w-full rounded-md border border-input bg-background px-2 py-2 text-sm"
            >
              <option value="none">None</option>
              <option value="bearer">Bearer token</option>
              <option value="api_key_query">API key in query string</option>
              <option value="basic">Basic auth</option>
            </select>
          </div>
          {authKind !== "none" && (
            <div>
              <label className="text-[11px] uppercase tracking-widest text-muted-foreground block mb-1">
                {authKind === "bearer" ? "Authorization header value (probe only — never stored)" :
                 authKind === "basic" ? "Authorization header value (probe only — never stored)" :
                 "Note: API key in query string — set via the connector's options at runtime"}
              </label>
              <input
                type="password"
                value={authValue}
                onChange={(e) => setAuthValue(e.target.value)}
                placeholder={AUTH_PLACEHOLDER[authKind]}
                disabled={authKind === "api_key_query"}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono disabled:opacity-50"
                autoComplete="new-password"
              />
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          <Button onClick={onProbe} disabled={probing || !url.trim()} variant="outline" size="sm">
            {probing ? "⏳ Probing…" : "🔍 Probe URL"}
          </Button>
          {probe && (
            probe.ok ? (
              <span className="text-xs text-emerald-600 dark:text-emerald-400">
                ✓ HTTP {probe.status} · {probe.content_type ?? "?"}
                {probe.json_shape && ` · ${probe.json_shape.type}`}
                {probe.json_shape?.length !== undefined && ` (${probe.json_shape.length} items)`}
              </span>
            ) : (
              <span className="text-xs text-rose-600 dark:text-rose-400">✗ {probe.error ?? "Unknown error"}</span>
            )
          )}
        </div>

        {probe?.ok && (probe.json_shape?.keys || probe.json_shape?.first_keys) && (
          <div className="text-[11px] text-muted-foreground">
            Detected fields:{" "}
            <span className="font-mono text-foreground/80">
              {(probe.json_shape.keys ?? probe.json_shape.first_keys ?? []).join(", ") || "(none)"}
            </span>
          </div>
        )}
      </motion.section>

      {/* Step 2 — Intent + Generate */}
      {probe?.ok && (
        <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4 mb-4">
          <header className="flex items-center gap-2">
            <span className="text-base font-medium">2.</span>
            <span className="font-medium">Describe intent (optional) + generate</span>
          </header>

          <div>
            <label className="text-[11px] uppercase tracking-widest text-muted-foreground block mb-1">Intent</label>
            <textarea
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              placeholder="e.g. fetch all charges, paginate via the next_page cursor, flatten the customer object into top-level columns"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm min-h-[80px]"
            />
            <p className="text-[10px] text-muted-foreground mt-1">
              Optional but helps. The AI sees the URL + the probe response shape.
            </p>
          </div>

          <Button onClick={onGenerate} disabled={generating} size="sm">
            {generating ? "⏳ Generating (30–60s for cold local model)…" : "✨ Generate connector"}
          </Button>
        </motion.section>
      )}

      {/* Step 3 — Review + install */}
      {generated && (
        <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4">
          <header className="flex items-center gap-3">
            <span className="text-base font-medium">3.</span>
            <span className="font-medium">Review</span>
            <span className="text-xs text-muted-foreground">
              id: <span className="font-mono">{generated.id}</span> · model: {generated.model}
            </span>
          </header>

          {generated.lint_issues.length > 0 ? (
            <div className="rounded-md border border-rose-300/60 bg-rose-50/40 dark:bg-rose-900/20 p-3 space-y-2">
              <p className="text-sm font-medium text-rose-800 dark:text-rose-200">
                ⛔ Safety lint failed — install blocked
              </p>
              <ul className="text-xs space-y-1 list-disc pl-5">
                {generated.lint_issues.map((i, n) => (
                  <li key={n}>
                    <span className="font-mono">L{i.line}:{i.col}</span> · {i.rule} — {i.message}
                  </li>
                ))}
              </ul>
              <p className="text-xs opacity-80">
                Try regenerating with a more specific intent, or pick a different model.
              </p>
            </div>
          ) : (
            <div className="rounded-md border border-emerald-300/60 bg-emerald-50/40 dark:bg-emerald-900/20 p-3 text-sm text-emerald-800 dark:text-emerald-200">
              ✓ Safety lint passed — no banned imports, calls, or attributes detected.
            </div>
          )}

          <div>
            <p className="text-[11px] uppercase tracking-widest text-muted-foreground mb-1">manifest.json</p>
            <pre className="text-xs font-mono p-3 rounded bg-muted/40 overflow-auto max-h-[200px]">
              {JSON.stringify(generated.manifest, null, 2)}
            </pre>
          </div>

          <div>
            <p className="text-[11px] uppercase tracking-widest text-muted-foreground mb-1">connector.py</p>
            <pre className="text-xs font-mono p-3 rounded bg-muted/40 overflow-auto max-h-[400px] whitespace-pre">
              {generated.connector_py}
            </pre>
          </div>

          {installError && (
            <p className="text-xs text-rose-600 dark:text-rose-400">{installError}</p>
          )}

          <div className="flex items-center gap-2 justify-end pt-2 border-t border-border">
            <Button variant="ghost" size="sm" onClick={onDiscard}>Discard</Button>
            <Button
              size="sm"
              disabled={!generated.safe_to_install}
              onClick={onInstall}
              title={generated.safe_to_install ? "Move to plugins/connectors/ — restart backend to activate" : "Lint blocked"}
            >
              ✓ Install
            </Button>
          </div>
        </motion.section>
      )}
    </main>
  );
}
