"use client";

/**
 * AI-assisted transform step wizard.
 *
 * Mirrors /connectors/new but produces a step plugin (manifest + step.py)
 * staged to plugins/_pending/steps/, then promoted to plugins/steps/ on
 * Install. The same dig/ai/safety.py lint applies: install button is
 * disabled until the AST walker passes.
 */

import Link from "next/link";
import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { toast } from "sonner";
import { aiApi, ApiError, type AiGeneratedStep } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { ThinkingLabel } from "@/components/positive-loader";

export default function NewStepPage() {
  const reduce = useReducedMotion();
  const fadeUp = reduce
    ? { initial: false as const, animate: { opacity: 1, y: 0 } }
    : { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 30 } };

  const [description, setDescription] = useState("");
  const [schemaText, setSchemaText] = useState("");

  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState<AiGeneratedStep | null>(null);
  const [installError, setInstallError] = useState<string | null>(null);

  const onGenerate = async () => {
    if (!description.trim()) return;
    setGenerating(true);
    setGenerated(null);
    setInstallError(null);

    // Parse the optional column hint — one "name: type" per line.
    const schema_hint: Record<string, string> = {};
    for (const line of schemaText.split("\n")) {
      const m = line.match(/^\s*([^:\s]+)\s*:\s*(.+?)\s*$/);
      if (m) schema_hint[m[1]] = m[2];
    }

    try {
      const result = await aiApi.generateStep({
        description: description.trim(),
        schema_hint: Object.keys(schema_hint).length ? schema_hint : undefined,
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
      await aiApi.installStep(generated.id);
      toast.success(`Installed step "${generated.id}" — restart backend to register`);
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
      await aiApi.discardStep(generated.id);
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
          ✨ Generate a transform step
        </h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          Describe what the step should do. AI generates the manifest + Python.
          Static safety lint runs (same allowlist as connectors). Install only
          activates after you've reviewed the diff.
          Requires <Link href="/settings#ai" className="underline">AI Settings</Link> to be enabled.
        </p>
      </motion.header>

      <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4 mb-4">
        <div>
          <label className="text-[11px] uppercase tracking-widest text-muted-foreground block mb-1">
            What should this step do?
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="e.g. round numeric columns to N decimal places · or · convert phone numbers from (xxx) xxx-xxxx to E.164 · or · compute the geometric mean of two columns"
            className="w-full text-sm rounded-md border border-input bg-background px-3 py-2 min-h-[120px]"
          />
        </div>
        <div>
          <label className="text-[11px] uppercase tracking-widest text-muted-foreground block mb-1">
            Optional: column hints (one per line, format: <code>name: type</code>)
          </label>
          <textarea
            value={schemaText}
            onChange={(e) => setSchemaText(e.target.value)}
            placeholder={"price: double\nphone: string\ncountry: country"}
            className="w-full text-sm rounded-md border border-input bg-background px-3 py-2 font-mono min-h-[80px]"
          />
          <p className="text-[10px] text-muted-foreground mt-1">
            Helps the AI pick correct column names + types. Leave blank if you'd rather generate a generic step.
          </p>
        </div>

        <Button onClick={onGenerate} disabled={generating || !description.trim()} size="sm">
          {generating ? <ThinkingLabel text="Generating (30–60s for cold local model)…" /> : "✨ Generate step"}
        </Button>
      </motion.section>

      {generated && (
        <motion.section {...fadeUp} className="rounded-lg border border-border bg-card p-5 space-y-4">
          <header className="flex items-center gap-3">
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
            </div>
          ) : (
            <div className="rounded-md border border-emerald-300/60 bg-emerald-50/40 dark:bg-emerald-900/20 p-3 text-sm text-emerald-800 dark:text-emerald-200">
              ✓ Safety lint passed
            </div>
          )}

          <div>
            <p className="text-[11px] uppercase tracking-widest text-muted-foreground mb-1">manifest.json</p>
            <pre className="text-xs font-mono p-3 rounded bg-muted/40 overflow-auto max-h-[200px]">
              {JSON.stringify(generated.manifest, null, 2)}
            </pre>
          </div>

          <div>
            <p className="text-[11px] uppercase tracking-widest text-muted-foreground mb-1">step.py</p>
            <pre className="text-xs font-mono p-3 rounded bg-muted/40 overflow-auto max-h-[400px] whitespace-pre">
              {generated.step_py}
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
              title={generated.safe_to_install ? "Move to plugins/steps/ — restart backend to register" : "Lint blocked"}
            >
              ✓ Install
            </Button>
          </div>
        </motion.section>
      )}
    </main>
  );
}
