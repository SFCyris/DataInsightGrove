"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { aiApi, type AiConfigOut } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { ThinkingLabel } from "@/components/positive-loader";

/**
 * SuggestFix — "✨ Suggest fix" button shown next to a step's preview error.
 *
 * Wraps the existing /ai/chat proxy (no new backend endpoint needed) with a
 * structured JSON prompt: given the step's manifest, current params, the
 * error, and the columns visible at this step's input, ask the model to
 * return a proposed parameter set + 1–2 sentence explanation + a confidence
 * label.
 *
 * UX:
 *   1. Button is hidden when AI is disabled in Settings → AI (config check
 *      is cached via useQuery so it costs at most one /ai/config call per
 *      session).
 *   2. Clicking dispatches the chat request and shows a small proposal card
 *      below the button with the explanation, the diff (what params change
 *      from current → proposed), and Apply / Dismiss controls.
 *   3. Apply calls back into the editor via the `onApply` prop; Dismiss
 *      collapses the card.
 *
 * The model is asked for a *full* params object (not a diff) so applying
 * is a single replace — no merge logic in the client. We diff client-side
 * just for display purposes.
 */

interface ParamSpec {
  type?: string;
  required?: boolean;
  min?: number;
  max?: number;
  enumValues?: unknown[];
  default?: unknown;
  help?: string;
  label?: string;
}

interface StepManifestLite {
  id: string;
  label?: string;
  description?: string;
  params?: Record<string, ParamSpec>;
}

interface ProposedFix {
  params: Record<string, unknown>;
  explanation: string;
  confidence: "low" | "medium" | "high";
}

interface SuggestFixProps {
  /** The step the user is editing. Manifest comes from the registry. */
  manifest: StepManifestLite;
  /** Current param values on the focused node. */
  currentParams: Record<string, unknown>;
  /** Columns visible at the input port (used to ground the suggestion in
   *  what the user can actually pick). */
  availableColumns: string[];
  /** The raw error message from the preview (the humanizer's text or the
   *  backend error — whichever is most informative). */
  errorMessage: string;
  /** The humanized title (kept short — used as the user's stated intent). */
  humanizedTitle: string;
  /** Callback to apply the proposed params to the node. The parent runs
   *  setNodeParams(...) + updateDoc(...). Returns nothing. */
  onApply: (params: Record<string, unknown>) => void;
}

export function SuggestFix(props: SuggestFixProps) {
  const [proposal, setProposal] = useState<ProposedFix | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  // Cached AI config — re-fetches on focus (default RQ behaviour). One call
  // per page load is fine; the result is small and infrequently changes.
  const aiConfig = useQuery<AiConfigOut, Error>({
    queryKey: ["ai", "config"],
    queryFn: () => aiApi.config(),
    staleTime: 60_000,
    retry: false,
  });

  const ask = useMutation({
    mutationFn: async () => {
      const prompt = buildPrompt(props);
      const res = await aiApi.chat(
        [
          {
            role: "system",
            content:
              "You are a precise data-engineering assistant. You only output valid JSON. " +
              "When asked to fix a pipeline step, return ONE complete params object that resolves the error, " +
              "preferring minimal changes. Use only column names from the provided list. Never invent columns.",
          },
          { role: "user", content: prompt },
        ],
        { responseFormat: "json_object", temperature: 0.1, maxTokens: 800 },
      );
      return parseProposal(res.text);
    },
    onSuccess: (out) => setProposal(out),
    onError: (e: Error) => toast.error(`Suggest fix failed: ${e.message}`),
  });

  const diff = useMemo(
    () => (proposal ? diffParams(props.currentParams, proposal.params) : []),
    [proposal, props.currentParams],
  );

  // Hide entirely when AI is disabled or not loaded yet — no flicker.
  if (!aiConfig.data?.enabled) return null;

  return (
    <div className="mt-3 flex flex-col items-center gap-2">
      {!proposal && (
        <Button
          size="sm"
          variant="outline"
          disabled={ask.isPending}
          onClick={() => ask.mutate()}
        >
          {ask.isPending ? <ThinkingLabel text="Thinking…" /> : "✨ Suggest fix"}
        </Button>
      )}

      {proposal && (
        <div className="w-full max-w-md rounded-lg border border-border bg-card p-3 text-left shadow-sm">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="text-[11px] uppercase tracking-widest text-muted-foreground">
              ✨ AI suggestion
            </span>
            <span
              className={[
                "text-[10px] px-1.5 py-0.5 rounded-full border",
                proposal.confidence === "high"
                  ? "border-emerald-300 text-emerald-700 bg-emerald-50 dark:border-emerald-700 dark:text-emerald-200 dark:bg-emerald-950"
                  : proposal.confidence === "medium"
                    ? "border-amber-300 text-amber-700 bg-amber-50 dark:border-amber-700 dark:text-amber-200 dark:bg-amber-950"
                    : "border-zinc-300 text-zinc-600 bg-zinc-50 dark:border-zinc-700 dark:text-zinc-300 dark:bg-zinc-900",
              ].join(" ")}
            >
              {proposal.confidence}
            </span>
          </div>
          <p className="text-xs text-foreground leading-relaxed mb-2">
            {proposal.explanation}
          </p>
          {diff.length > 0 ? (
            <ul className="text-[11px] font-mono space-y-0.5 mb-2 max-h-32 overflow-y-auto">
              {diff.map((d) => (
                <li key={d.key} className="flex gap-1.5">
                  <span className="text-muted-foreground shrink-0">{d.key}:</span>
                  <span className="text-rose-600 dark:text-rose-300 line-through">
                    {fmtVal(d.before)}
                  </span>
                  <span className="text-muted-foreground">→</span>
                  <span className="text-emerald-700 dark:text-emerald-300">
                    {fmtVal(d.after)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[11px] text-muted-foreground italic mb-2">
              Suggestion matches the current params — try adjusting the error
              or providing a clearer goal.
            </p>
          )}
          <div className="flex items-center gap-2 justify-end">
            <Button
              size="xs"
              variant="ghost"
              onClick={() => setShowRaw((s) => !s)}
            >
              {showRaw ? "Hide" : "Show"} raw
            </Button>
            <Button
              size="xs"
              variant="ghost"
              onClick={() => setProposal(null)}
            >
              Dismiss
            </Button>
            <Button
              size="xs"
              disabled={diff.length === 0}
              onClick={() => {
                props.onApply(proposal.params);
                setProposal(null);
                toast.success("✨ Applied suggested fix");
              }}
            >
              Apply
            </Button>
          </div>
          {showRaw && (
            <pre className="mt-2 text-[10px] font-mono whitespace-pre-wrap break-all bg-muted/40 p-2 rounded">
              {JSON.stringify(proposal.params, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ── Prompt construction ──────────────────────────────────────────────────

function buildPrompt(p: SuggestFixProps): string {
  // Trim manifest to the bits the model actually needs to reason about a
  // fix — type, enumValues, min/max, required. Stripping everything else
  // keeps the prompt cheap and focuses the model on actionable constraints.
  const manifestSlim: Record<string, ParamSpec> = {};
  for (const [k, v] of Object.entries(p.manifest.params ?? {})) {
    manifestSlim[k] = {
      type: v.type,
      required: v.required,
      ...(v.min != null ? { min: v.min } : {}),
      ...(v.max != null ? { max: v.max } : {}),
      ...(v.enumValues ? { enumValues: v.enumValues } : {}),
      ...(v.default != null ? { default: v.default } : {}),
    };
  }

  return [
    `Fix this pipeline step's parameters so the error goes away.`,
    ``,
    `Step: ${p.manifest.label ?? p.manifest.id} (id="${p.manifest.id}")`,
    p.manifest.description ? `Description: ${p.manifest.description}` : "",
    ``,
    `Current params:`,
    "```json",
    JSON.stringify(p.currentParams, null, 2),
    "```",
    ``,
    `Manifest constraints (only the fields that constrain the values):`,
    "```json",
    JSON.stringify(manifestSlim, null, 2),
    "```",
    ``,
    `Columns visible at this step's input (use ONLY these names for column_ref params):`,
    p.availableColumns.length > 0 ? p.availableColumns.join(", ") : "(no columns)",
    ``,
    `Error:`,
    p.errorMessage,
    p.humanizedTitle && p.humanizedTitle !== p.errorMessage
      ? `Summary: ${p.humanizedTitle}`
      : "",
    ``,
    `Return a JSON object with exactly these keys:`,
    `  "params": full parameter object that should replace the current one (preserve correct values, only change what needs fixing)`,
    `  "explanation": 1-2 sentences plainly explaining what you changed and why (refer to columns by name)`,
    `  "confidence": one of "low" | "medium" | "high"`,
    ``,
    `If you can't fix it (e.g. the error needs a structural change like adding a different upstream step), still return params unchanged and set confidence to "low" with an explanation of what the user should do instead.`,
  ]
    .filter(Boolean)
    .join("\n");
}

// ── Response parsing ─────────────────────────────────────────────────────

function parseProposal(text: string): ProposedFix {
  // The model sometimes wraps JSON in ```json ... ``` despite the response
  // format hint — strip that first. Also tolerate a leading explanation
  // before the JSON, which happens with smaller local models.
  let cleaned = text.trim();
  const fenceMatch = cleaned.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenceMatch) cleaned = fenceMatch[1].trim();
  const objStart = cleaned.indexOf("{");
  const objEnd = cleaned.lastIndexOf("}");
  if (objStart >= 0 && objEnd > objStart) {
    cleaned = cleaned.slice(objStart, objEnd + 1);
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(cleaned);
  } catch (e) {
    throw new Error(
      `Couldn't parse AI response as JSON: ${(e as Error).message}`,
    );
  }
  if (!parsed || typeof parsed !== "object") {
    throw new Error("AI response was not a JSON object");
  }
  const o = parsed as Record<string, unknown>;
  if (!o.params || typeof o.params !== "object") {
    throw new Error("AI response missing 'params' object");
  }
  const conf = String(o.confidence ?? "low").toLowerCase();
  return {
    params: o.params as Record<string, unknown>,
    explanation:
      typeof o.explanation === "string"
        ? o.explanation
        : "(no explanation provided)",
    confidence:
      conf === "high" || conf === "medium" || conf === "low" ? conf : "low",
  };
}

// ── Param diff for display ───────────────────────────────────────────────

interface ParamChange {
  key: string;
  before: unknown;
  after: unknown;
}

function diffParams(
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): ParamChange[] {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  const changes: ParamChange[] = [];
  for (const k of keys) {
    const a = before[k];
    const b = after[k];
    if (!sameVal(a, b)) changes.push({ key: k, before: a, after: b });
  }
  return changes;
}

function sameVal(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a == null && b == null) return true;
  if (a == null || b == null) return false;
  // Cheap structural equality for arrays/objects — JSON.stringify is fine
  // for the params shapes we deal with (no functions, no Dates).
  try {
    return JSON.stringify(a) === JSON.stringify(b);
  } catch {
    return false;
  }
}

function fmtVal(v: unknown): string {
  if (v == null || v === "") return "—";
  if (typeof v === "string") return `"${v}"`;
  if (Array.isArray(v) || typeof v === "object") {
    const s = JSON.stringify(v);
    return s.length > 40 ? s.slice(0, 37) + "…" : s;
  }
  return String(v);
}
