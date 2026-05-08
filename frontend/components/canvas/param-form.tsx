"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { ParamSpec, StepManifest } from "@/lib/api/client";
import { FilterBuilder } from "@/components/canvas/filter-builder";
import { FixExpressionButton } from "@/components/canvas/fix-expression";
import { JoinPanel } from "@/components/canvas/join-widgets";

interface Props {
  manifest: StepManifest;
  values: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  /** Map of port name -> available column names from the upstream node. */
  upstreamColumns: Record<string, string[]>;
  /** Optional — when provided, each param row gets an "expose" toggle
   *  that flips entries on `node.ui.exposedParams`. Used to surface
   *  customisable params on a published reusable step. */
  exposedParams?: Record<string, { alias: string; help?: string }>;
  onExposeParam?: (
    paramKey: string,
    next: { alias: string; help?: string } | null,
  ) => void;
  /** Context required for the bespoke join panel. Optional so steps
   *  that don't use it (everything except `join`) keep working
   *  unchanged; pass for `join` and the param form short-circuits to
   *  `<JoinPanel>` instead of the generic per-param rendering. */
  pipelineId?: string;
  etag?: number;
  /** Map of port name → upstream node id. The join panel looks up
   *  `left` and `right` to fetch sample rows from each input. */
  inputRefs?: Record<string, string | null | undefined>;
  /** Eligible upstream sources for the join's input dropdowns
   *  (datasets + non-descendant nodes). */
  eligibleSources?: Array<{ id: string; kind: "dataset" | "node"; label: string }>;
  /** Callback to rewire one of the join's input ports. Owner of this
   *  callback decides terminal-mutate vs. mid-chain-branch. */
  onSetInputRef?: (port: string, newRef: string) => void;
  /** Callback to flip left ↔ right (with key swap, kind flip, etc.). */
  onSwapJoinSides?: () => void;
}

function isVisible(spec: ParamSpec, values: Record<string, unknown>): boolean {
  if (!spec.visibleWhen) return true;
  for (const [k, v] of Object.entries(spec.visibleWhen)) {
    if (values[k] !== v) return false;
  }
  return true;
}

const inputCls =
  "w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40";

export function ParamForm({
  manifest, values, onChange, upstreamColumns, exposedParams, onExposeParam,
  pipelineId, etag, inputRefs, eligibleSources, onSetInputRef, onSwapJoinSides,
}: Props) {
  const set = (name: string, value: unknown) => onChange({ ...values, [name]: value });

  // Bespoke join panel — replaces the generic per-param rendering with
  // the cardinality strip + icon-ladder + suggestion-first keys
  // builder + collisions panel. Only fires when the page wired through
  // the context props; falls back to standard rendering otherwise (so
  // this still works in surfaces that don't have pipelineId/etag, e.g.
  // a future "preview manifest in the picker" affordance).
  if (
    manifest.id === "join"
    && pipelineId != null
    && etag != null
    && inputRefs != null
  ) {
    return (
      <JoinPanel
        pipelineId={pipelineId}
        etag={etag}
        params={values}
        onChange={onChange}
        leftRef={inputRefs.left}
        rightRef={inputRefs.right}
        eligibleSources={eligibleSources ?? []}
        onSetInputRef={onSetInputRef}
        onSwapSides={onSwapJoinSides}
      />
    );
  }

  const entries = Object.entries(manifest.params);
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic">
        This step has no parameters.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {entries.map(([name, spec]) => {
        if (!isVisible(spec, values)) return null;
        const exposure = exposedParams?.[name];
        return (
          <Field
            key={name}
            name={name}
            spec={spec}
            value={values[name]}
            onSet={set}
            upstreamColumns={upstreamColumns}
            exposed={exposure}
            onToggleExpose={
              onExposeParam
                ? (next) => onExposeParam(name, next)
                : undefined
            }
          />
        );
      })}
    </div>
  );
}

interface FieldProps {
  name: string;
  spec: ParamSpec;
  value: unknown;
  onSet: (name: string, value: unknown) => void;
  upstreamColumns: Record<string, string[]>;
  /** Current exposure state for this param. Falsy = not exposed. */
  exposed?: { alias: string; help?: string };
  /** When provided, the field shows an "Expose" toggle that calls
   *  this with `null` to remove the exposure or `{ alias, help }` to
   *  set/update it. When undefined, the toggle is hidden entirely
   *  (e.g. when the consumer is editing a non-published pipeline). */
  onToggleExpose?: (next: { alias: string; help?: string } | null) => void;
}

function Field({ name, spec, value, onSet, upstreamColumns, exposed, onToggleExpose }: FieldProps) {
  const label = (
    <label className="flex items-center justify-between gap-2 mb-1">
      <span className="block text-xs font-medium text-foreground">
        {spec.label}
        {spec.required && <span className="text-destructive ml-0.5">*</span>}
      </span>
      {onToggleExpose && (
        // Expose-this-param toggle. When on, the param surfaces on
        // the synthesised manifest of the published step (after
        // metadata.publishedAsStep is set on the pipeline). Click =
        // toggle; default alias is the param key.
        <button
          type="button"
          onClick={() =>
            onToggleExpose(exposed ? null : { alias: name, help: spec.help })
          }
          title={
            exposed
              ? `Param is exposed as "${exposed.alias}". Click to hide.`
              : "Expose this param so consumers of this published step can override it."
          }
          className={[
            "shrink-0 text-[10px] px-1.5 py-0.5 rounded-full border transition-colors",
            exposed
              ? "border-violet-400/60 bg-violet-50 text-violet-700 dark:bg-violet-900/20 dark:text-violet-300 dark:border-violet-700/60"
              : "border-border text-muted-foreground hover:border-foreground/40 hover:text-foreground",
          ].join(" ")}
        >
          {exposed ? `🪆 ${exposed.alias}` : "🪆 expose"}
        </button>
      )}
    </label>
  );
  const help = spec.help ? (
    <p className="text-[11px] text-muted-foreground mt-1">{spec.help}</p>
  ) : null;

  switch (spec.type) {
    case "string":
    case "regex":
      // Custom widgets layered on top of string. Currently:
      //   - webhook_picker: dropdown populated from /global-webhooks
      //   - json_textarea:  multi-line monospace input for JSON blobs
      // Other widget hints fall through to the plain input.
      if (spec.widget === "webhook_picker") {
        return (
          <div>
            {label}
            <WebhookPicker
              value={(value as string) ?? ""}
              onChange={(v) => onSet(name, v)}
            />
            {help}
          </div>
        );
      }
      if (spec.widget === "json_textarea") {
        return (
          <div>
            {label}
            <textarea
              className={inputCls + " font-mono min-h-[80px]"}
              value={(value as string) ?? (spec.default as string) ?? ""}
              placeholder='{ "key": "value" }'
              onChange={(e) => onSet(name, e.target.value)}
            />
            {help}
          </div>
        );
      }
      return (
        <div>
          {label}
          <input
            type="text"
            className={inputCls}
            value={(value as string) ?? (spec.default as string) ?? ""}
            pattern={spec.pattern}
            onChange={(e) => onSet(name, e.target.value)}
          />
          {help}
        </div>
      );
    case "expression":
      if (spec.widget === "filter_builder") {
        const portCols = upstreamColumns[spec.columnFrom ?? "in"] ?? [];
        // We don't have detailed types here yet; pass an empty map and the builder
        // will default to string-style operators per column. (Future: thread types
        // from the validate response down through ParamForm props.)
        return (
          <div>
            {label}
            <FilterBuilder
              columns={portCols}
              value={(value as string) ?? ""}
              onChange={(sql) => onSet(name, sql)}
            />
            {help}
          </div>
        );
      }
      return (
        <div>
          {label}
          <textarea
            className={inputCls + " font-mono min-h-[60px]"}
            value={(value as string) ?? (spec.default as string) ?? ""}
            onChange={(e) => onSet(name, e.target.value)}
            spellCheck={false}
          />
          <div className="flex items-center justify-end mt-1">
            <FixExpressionButton
              expression={(value as string) ?? ""}
              // The expression sees the upstream `in` port (or the
              // configured columnFrom) — same set the FilterBuilder uses.
              columns={(upstreamColumns[spec.columnFrom ?? "in"] ?? []).map((c) => ({
                name: c,
                type: "string", // detailed types aren't threaded here yet — future enhancement
              }))}
              kind={name === "predicate" ? "predicate" : "scalar"}
              onApply={(next) => onSet(name, next)}
            />
          </div>
          {help}
        </div>
      );
    case "number":
    case "integer":
      return (
        <div>
          {label}
          <input
            type="number"
            className={inputCls + " tabular-nums"}
            min={spec.min}
            max={spec.max}
            step={spec.type === "integer" ? 1 : "any"}
            value={(value as number | string | undefined)?.toString() ?? ""}
            onChange={(e) =>
              onSet(name, e.target.value === "" ? null : spec.type === "integer" ? parseInt(e.target.value) : Number(e.target.value))
            }
          />
          {help}
        </div>
      );
    case "boolean":
      return (
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={Boolean(value ?? spec.default)}
            onChange={(e) => onSet(name, e.target.checked)}
          />
          <span>{spec.label}</span>
        </label>
      );
    case "enum":
      return (
        <div>
          {label}
          <select
            className={inputCls}
            value={(value as string) ?? (spec.default as string) ?? ""}
            onChange={(e) => onSet(name, e.target.value)}
          >
            <option value="">— choose —</option>
            {spec.enumValues?.map((v) => (
              <option key={String(v)} value={v as string | number}>
                {String(v)}
              </option>
            ))}
          </select>
          {help}
        </div>
      );
    case "column_ref": {
      const portCols = upstreamColumns[spec.columnFrom ?? "in"] ?? [];
      return (
        <div>
          {label}
          <select
            className={inputCls}
            value={(value as string) ?? ""}
            onChange={(e) => onSet(name, e.target.value)}
          >
            <option value="">— column —</option>
            {portCols.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
          {help}
        </div>
      );
    }
    case "column_refs": {
      const portCols = upstreamColumns[spec.columnFrom ?? "in"] ?? [];
      const selected = (value as string[]) ?? [];
      return (
        <div>
          {label}
          <div className="flex flex-wrap gap-1.5 p-2 rounded-md border border-input bg-background min-h-[40px]">
            {portCols.length === 0 && (
              <span className="text-xs text-muted-foreground italic">
                Connect this step to see columns.
              </span>
            )}
            {portCols.map((c) => {
              const isOn = selected.includes(c);
              return (
                <button
                  key={c}
                  type="button"
                  onClick={() =>
                    onSet(
                      name,
                      isOn ? selected.filter((x) => x !== c) : [...selected, c],
                    )
                  }
                  className={[
                    "px-2 py-0.5 rounded-md text-xs border transition-colors",
                    isOn
                      ? "bg-foreground text-background border-foreground"
                      : "bg-muted/40 hover:bg-muted text-foreground border-border",
                  ].join(" ")}
                >
                  {c}
                </button>
              );
            })}
          </div>
          {help}
        </div>
      );
    }
    case "array": {
      const items = (value as Array<Record<string, unknown>>) ?? [];
      const itemSpec = spec.items;
      if (!itemSpec) return null;
      return (
        <div>
          {label}
          <div className="space-y-2">
            {items.map((item, idx) => (
              <div key={idx} className="flex gap-2 items-start">
                <div className="flex-1 grid grid-cols-2 gap-2">
                  {itemSpec.type === "object" && itemSpec.properties &&
                    Object.entries(itemSpec.properties).map(([pn, ps]) => (
                      <Field
                        key={pn}
                        name={pn}
                        spec={ps}
                        value={item[pn]}
                        upstreamColumns={upstreamColumns}
                        onSet={(_n, v) => {
                          const next = [...items];
                          next[idx] = { ...next[idx], [pn]: v };
                          onSet(name, next);
                        }}
                      />
                    ))}
                </div>
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-destructive mt-1"
                  onClick={() => onSet(name, items.filter((_, i) => i !== idx))}
                  aria-label="Remove"
                >
                  ✕
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => onSet(name, [...items, {}])}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              ➕ Add
            </button>
          </div>
          {help}
        </div>
      );
    }
    case "object":
      return (
        <div>
          {label}
          <textarea
            className={inputCls + " font-mono min-h-[80px] text-xs"}
            value={JSON.stringify(value ?? {}, null, 2)}
            onChange={(e) => {
              try {
                onSet(name, JSON.parse(e.target.value));
              } catch {
                /* leave invalid editor state until user fixes it */
              }
            }}
          />
          {help}
        </div>
      );
    default:
      return (
        <div>
          {label}
          <input
            className={inputCls}
            value={(value as string) ?? ""}
            onChange={(e) => onSet(name, e.target.value)}
          />
        </div>
      );
  }
}

/** Dropdown of global webhooks (by label). Used by webhook_trigger.
 *
 * Three observable states: loading, empty (no webhooks defined yet), and
 * populated. The empty state offers a deep link to Settings → Global
 * webhooks so the user can fix it without losing their place. */
function WebhookPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const q = useQuery({
    queryKey: ["global-webhooks"],
    queryFn: api.listGlobalWebhooks,
    // Webhooks rarely change while the user is editing a step — stale-fresh
    // for 30 s is plenty and avoids a refetch on every focus.
    staleTime: 30_000,
  });

  if (q.isLoading) {
    return <div className={inputCls + " text-muted-foreground italic"}>Loading webhooks…</div>;
  }
  if (q.isError) {
    return (
      <div className={inputCls + " text-destructive text-xs"}>
        Couldn't load webhooks ({(q.error as Error).message}).
      </div>
    );
  }

  const hooks = q.data ?? [];
  // Surface the labelled, enabled ones first; skip unlabelled (they can't
  // be selected by label anyway). Disabled hooks are shown but greyed out
  // with an explicit marker so the user understands why their step might
  // not fire.
  const labelled = hooks.filter((h) => h.label && h.label.trim());

  if (labelled.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-border/80 bg-muted/30 px-3 py-3 text-xs space-y-2">
        <p className="text-muted-foreground">
          No global webhooks defined yet.{" "}
          <Link
            href="/settings#webhooks"
            className="underline underline-offset-2 hover:text-foreground"
            target="_blank"
            rel="noreferrer"
          >
            Add one in Settings →
          </Link>
        </p>
        <p className="text-[11px] text-muted-foreground/80">
          You can save this step empty as a placeholder and pick a webhook later.
          Tip: set the webhook&apos;s <em>on</em> selector to <code className="font-mono text-[10px] bg-muted px-1 rounded">triggered</code> so it only fires from this step.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <select
        className={inputCls}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">— None (placeholder) —</option>
        {labelled.map((h) => (
          <option key={h.id} value={h.label!} disabled={h.enabled === false}>
            {h.label}
            {h.on && h.on !== "always" ? ` · on=${h.on}` : ""}
            {h.enabled === false ? " (paused)" : ""}
          </option>
        ))}
      </select>
      <p className="text-[11px] text-muted-foreground">
        <Link
          href="/settings#webhooks"
          className="underline underline-offset-2 hover:text-foreground"
          target="_blank"
          rel="noreferrer"
        >
          Manage webhooks ↗
        </Link>
      </p>
    </div>
  );
}
