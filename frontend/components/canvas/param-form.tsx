"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";
import type { ParamSpec, StepManifest } from "@/lib/api/client";
import { FilterBuilder } from "@/components/canvas/filter-builder";
import { FixExpressionButton } from "@/components/canvas/fix-expression";

interface Props {
  manifest: StepManifest;
  values: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  /** Map of port name -> available column names from the upstream node. */
  upstreamColumns: Record<string, string[]>;
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

export function ParamForm({ manifest, values, onChange, upstreamColumns }: Props) {
  const set = (name: string, value: unknown) => onChange({ ...values, [name]: value });
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
        return (
          <Field key={name} name={name} spec={spec} value={values[name]} onSet={set} upstreamColumns={upstreamColumns} />
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
}

function Field({ name, spec, value, onSet, upstreamColumns }: FieldProps) {
  const label = (
    <label className="block text-xs font-medium text-foreground mb-1">
      {spec.label}
      {spec.required && <span className="text-destructive ml-0.5">*</span>}
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
