"use client";

/**
 * Settings → Notification rules.
 *
 * The user-configurable layer between events (always emitted) and
 * notifications (emitted only when a rule matches). Mirrors the way
 * Redis Enterprise alerts / Alteryx Cloud notifications / PagerDuty
 * services configure trigger conditions.
 */

import React, { useEffect, useMemo, useState } from "react";
import { confirmAction } from "@/lib/confirm-toast";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "motion/react";
import { toast } from "sonner";

import {
  notificationRulesApi,
  type NotificationRuleOut,
  type NotificationRuleIn,
  type RuleAction,
} from "@/lib/api/client";

const LEVEL_OPTIONS: { id: RuleAction["level"]; emoji: string; label: string }[] = [
  { id: "auto",         emoji: "✨", label: "Auto (use event default)" },
  { id: "notification", emoji: "🟢", label: "Notification" },
  { id: "warning",      emoji: "🟡", label: "Warning" },
  { id: "error",        emoji: "🔴", label: "Error" },
];

const CHANNEL_OPTIONS: { id: RuleAction["channel"]; emoji: string; label: string; coming?: boolean }[] = [
  { id: "in_app",  emoji: "📥", label: "In-app" },
  { id: "email",   emoji: "📧", label: "Email", coming: true },
  { id: "slack",   emoji: "💬", label: "Slack", coming: true },
  { id: "webhook", emoji: "🔌", label: "Webhook", coming: true },
];

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "never";
  const hasTz = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso);
  const ms = Date.now() - new Date(hasTz ? iso : `${iso}Z`).getTime();
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

export function NotificationRulesSection() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<NotificationRuleOut | null>(null);
  const [creating, setCreating] = useState(false);

  const rulesQ = useQuery({
    queryKey: ["notification-rules"],
    queryFn: notificationRulesApi.list,
  });
  const kindsQ = useQuery({
    queryKey: ["notification-rules", "event-kinds"],
    queryFn: notificationRulesApi.eventKinds,
  });

  const toggleM = useMutation({
    mutationFn: (id: string) => notificationRulesApi.toggle(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notification-rules"] }),
    onError: (e: Error) => toast.error(`Toggle failed: ${e.message}`),
  });
  const deleteM = useMutation({
    mutationFn: (id: string) => notificationRulesApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notification-rules"] });
      toast.success("Rule deleted");
    },
    onError: (e: Error) => toast.error(`Delete failed: ${e.message}`),
  });

  const rules = rulesQ.data ?? [];
  const builtIns = rules.filter((r) => r.is_builtin);
  const customs = rules.filter((r) => !r.is_builtin);

  return (
    <section className="space-y-5">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
            <span aria-hidden>📐</span>
            Notification rules
          </h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Events are always emitted by DIG (run lifecycle, freshness
            transitions, system errors, …). Rules decide which events
            become notifications. The same rules will drive email / Slack
            / webhook delivery when those channels land.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="px-3 py-1.5 rounded-md text-sm font-medium bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-colors"
        >
          + New rule
        </button>
      </header>

      {builtIns.length > 0 && (
        <RulesGroup
          title="Built-in rules"
          subtitle="Ship with DIG. Disable or customise; cannot be deleted."
          rules={builtIns}
          onEdit={setEditing}
          onToggle={(id) => toggleM.mutate(id)}
          onDelete={() => toast.info("Built-in rules can be disabled but not deleted.")}
        />
      )}
      <RulesGroup
        title="Custom rules"
        subtitle={
          customs.length === 0
            ? "None yet. Click + New rule to add one."
            : "Your rules. Edit, toggle, or delete."
        }
        rules={customs}
        onEdit={setEditing}
        onToggle={(id) => toggleM.mutate(id)}
        onDelete={async (id) => {
          const ok = await confirmAction({
            title: "Delete this notification rule?",
            description: "This cannot be undone.",
            confirmLabel: "Delete",
          });
          if (ok) deleteM.mutate(id);
        }}
      />

      <AnimatePresence>
        {(creating || editing) && (
          <RuleEditModal
            rule={editing}
            eventKinds={kindsQ.data?.kinds ?? []}
            onClose={() => {
              setCreating(false);
              setEditing(null);
            }}
            onSaved={() => {
              qc.invalidateQueries({ queryKey: ["notification-rules"] });
              setCreating(false);
              setEditing(null);
            }}
          />
        )}
      </AnimatePresence>
    </section>
  );
}

// ---- Rules list group --------------------------------------------------

function RulesGroup({
  title,
  subtitle,
  rules,
  onEdit,
  onToggle,
  onDelete,
}: {
  title: string;
  subtitle: string;
  rules: NotificationRuleOut[];
  onEdit: (r: NotificationRuleOut) => void;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="text-xs text-muted-foreground">{subtitle}</span>
      </div>
      <div className="rounded-xl border border-border bg-card/40 overflow-hidden">
        {rules.length === 0 ? (
          <div className="px-4 py-6 text-xs text-muted-foreground italic">
            (none)
          </div>
        ) : (
          rules.map((r) => (
            <RuleRow
              key={r.id}
              rule={r}
              onEdit={() => onEdit(r)}
              onToggle={() => onToggle(r.id)}
              onDelete={() => onDelete(r.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}

function RuleRow({
  rule,
  onEdit,
  onToggle,
  onDelete,
}: {
  rule: NotificationRuleOut;
  onEdit: () => void;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const action = rule.action;
  const hasFilters = rule.filters && Object.keys(rule.filters).length > 0;
  return (
    <div
      className={[
        "px-4 py-3 border-b border-border/60 last:border-b-0",
        rule.enabled ? "" : "bg-muted/20 opacity-70",
      ].join(" ")}
    >
      <div className="flex items-start gap-3">
        <button
          type="button"
          onClick={onToggle}
          // p-0 explicitly because Tailwind v4's preflight doesn't always
          // zero out button padding the way v3 did. box-border ensures the
          // 36×20 dimensions are honored.
          className={[
            "mt-0.5 w-9 h-5 p-0 rounded-full relative transition-colors shrink-0 box-border",
            "border-0",
            rule.enabled ? "bg-emerald-500" : "bg-zinc-300 dark:bg-zinc-700",
          ].join(" ")}
          title={rule.enabled ? "Disable" : "Enable"}
          aria-label={rule.enabled ? "Disable rule" : "Enable rule"}
        >
          {/* Knob — anchored top-0.5 + left-0.5 so it actually sits
              inside the track. translate-x-0 vs translate-x-4 toggles
              the on/off position. Without explicit `left`, the knob
              renders at `left: auto` which can drift outside the track
              depending on browser quirks. */}
          <span
            className={[
              "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform",
              rule.enabled ? "translate-x-4" : "translate-x-0",
            ].join(" ")}
          />
        </button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-sm font-medium truncate" title={rule.name}>
              {rule.name}
            </p>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
              {rule.event_kind}
            </span>
            {hasFilters && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-950/40 text-violet-700 dark:text-violet-300 font-mono"
                title={JSON.stringify(rule.filters)}
              >
                filters: {Object.keys(rule.filters!).length}
              </span>
            )}
            {rule.cooldown_seconds && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 font-mono">
                cooldown: {rule.cooldown_seconds}s
              </span>
            )}
          </div>
          {rule.description && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
              {rule.description}
            </p>
          )}
          <div className="text-[11px] text-muted-foreground mt-1.5 flex flex-wrap items-center gap-x-3">
            <span>
              <span className="font-mono">→</span> {action.level}
            </span>
            <span>
              <span className="font-mono">via</span> {action.channel}
            </span>
            <span>
              fired <span className="tabular-nums">{rule.fire_count}</span>×
              {rule.last_fired_at && ` (${formatRelative(rule.last_fired_at)})`}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={onEdit}
            className="text-xs px-2 py-1 rounded hover:bg-muted text-foreground/80 transition-colors"
          >
            Edit
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={rule.is_builtin}
            className="text-xs px-2 py-1 rounded hover:bg-rose-50 dark:hover:bg-rose-950/40 text-muted-foreground hover:text-rose-600 dark:hover:text-rose-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            title={rule.is_builtin ? "Built-in rule — disable instead" : "Delete"}
          >
            🗑
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Edit / create modal ----------------------------------------------

function RuleEditModal({
  rule,
  eventKinds,
  onClose,
  onSaved,
}: {
  rule: NotificationRuleOut | null;
  eventKinds: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const isNew = rule == null;
  const [name, setName] = useState(rule?.name ?? "");
  const [description, setDescription] = useState(rule?.description ?? "");
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  // Round-8 fix: previously defaulted to the literal "run.failed" even
  // when the backend's eventKinds list didn't include it; the select
  // then rendered with no matching option and silently saved a broken
  // rule. Fall back to the first available kind so the value is always
  // valid.
  const [eventKind, setEventKind] = useState(
    rule?.event_kind ?? eventKinds[0] ?? "run.failed",
  );

  // Round-8 a11y: ESC closes the modal so keyboard users aren't stuck.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const [filtersText, setFiltersText] = useState(
    rule?.filters ? JSON.stringify(rule.filters, null, 2) : "",
  );
  const [level, setLevel] = useState<RuleAction["level"]>(rule?.action.level ?? "auto");
  const [title, setTitle] = useState(rule?.action.title ?? "");
  const [message, setMessage] = useState(rule?.action.message ?? "");
  const [channel, setChannel] = useState<RuleAction["channel"]>(
    rule?.action.channel ?? "in_app",
  );
  const [cooldown, setCooldown] = useState(
    rule?.cooldown_seconds != null ? String(rule.cooldown_seconds) : "",
  );

  const filtersValid = useMemo(() => {
    if (!filtersText.trim()) return true;
    try {
      const v = JSON.parse(filtersText);
      return v != null && typeof v === "object" && !Array.isArray(v);
    } catch {
      return false;
    }
  }, [filtersText]);

  const saveM = useMutation({
    mutationFn: async () => {
      const filters = filtersText.trim()
        ? (JSON.parse(filtersText) as Record<string, unknown>)
        : null;
      const body: NotificationRuleIn = {
        name: name.trim() || "Unnamed rule",
        description: description.trim() || null,
        enabled,
        event_kind: eventKind,
        filters,
        action: {
          level,
          title: title.trim() || "{event_kind}",
          message: message.trim() || null,
          channel,
        },
        cooldown_seconds: cooldown.trim() ? Number(cooldown) : null,
      };
      if (rule) {
        return notificationRulesApi.update(rule.id, body);
      } else {
        return notificationRulesApi.create(body);
      }
    },
    onSuccess: () => {
      toast.success(isNew ? "Rule created" : "Rule saved");
      onSaved();
    },
    onError: (e: Error) => toast.error(`Save failed: ${e.message}`),
  });

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-start justify-center p-4 overflow-y-auto"
      onClick={onClose}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby="rule-edit-title"
        initial={{ opacity: 0, y: 12, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, scale: 0.97 }}
        transition={{ type: "spring", stiffness: 320, damping: 28 }}
        onClick={(e) => e.stopPropagation()}
        className="bg-card rounded-xl border border-border shadow-2xl w-full max-w-2xl my-8"
      >
        <header className="px-5 py-4 border-b border-border flex items-center gap-2">
          <span aria-hidden className="text-xl">📐</span>
          <h3 id="rule-edit-title" className="text-base font-semibold">
            {isNew ? "New notification rule" : "Edit notification rule"}
          </h3>
          {rule?.is_builtin && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-muted-foreground font-mono">
              built-in
            </span>
          )}
          <span className="flex-1" />
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <form
          className="p-5 space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (!filtersValid) return;
            saveM.mutate();
          }}
        >
          <FormField label="Name" required>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              required
              className="w-full px-2.5 py-1.5 rounded border border-border bg-background"
            />
          </FormField>

          <FormField label="Description (optional)">
            <input
              type="text"
              value={description ?? ""}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-2.5 py-1.5 rounded border border-border bg-background"
              placeholder="What does this rule do?"
            />
          </FormField>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <FormField label="Event kind" hint="* = anything · run.* = wildcard">
              <select
                value={eventKind}
                onChange={(e) => setEventKind(e.target.value)}
                className="w-full px-2.5 py-1.5 rounded border border-border bg-background font-mono text-xs"
              >
                {eventKinds.map((k) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </select>
            </FormField>
            <FormField label="Cooldown (seconds, optional)" hint="Min gap between fires per target">
              <div className="relative">
                <input
                  type="text"
                  inputMode="numeric"
                  value={cooldown}
                  onChange={(e) => {
                    // Round-4 UX#3: previously silently stripped non-
                    // digits so pasting "10 min" rewrote to "10" with no
                    // feedback — the user thought they entered minutes
                    // but it was 10 seconds. Keep the same input shape
                    // but render a unit suffix so the read-back is
                    // unambiguous.
                    setCooldown(e.target.value.replace(/[^0-9]/g, ""));
                  }}
                  placeholder="e.g. 600"
                  className="w-full px-2.5 py-1.5 pr-10 rounded border border-border bg-background"
                />
                <span
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground pointer-events-none select-none"
                  aria-hidden
                >
                  s
                </span>
              </div>
            </FormField>
          </div>

          <FormField
            label="Filters (JSON, optional)"
            hint='e.g. {"pipeline_id": "01KR..."} — exact-match against event context'
          >
            <textarea
              value={filtersText}
              onChange={(e) => setFiltersText(e.target.value)}
              rows={3}
              placeholder="{}"
              className={[
                "w-full px-2.5 py-1.5 rounded border bg-background font-mono text-xs",
                filtersValid ? "border-border" : "border-rose-400",
              ].join(" ")}
            />
            {!filtersValid && (
              <p className="text-[11px] text-rose-600 dark:text-rose-400 mt-1">
                Must be valid JSON object (or empty).
              </p>
            )}
          </FormField>

          {/* Round-5 W4: dry-run the current event_kind + filters
              against the last 50 events so the user can see what
              would have fired BEFORE saving the rule. */}
          <TestRulePanel
            eventKind={eventKind}
            filters={filtersValid && filtersText.trim() ? JSON.parse(filtersText) : null}
          />

          <div className="rounded-lg border border-border bg-muted/20 p-3 space-y-3">
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-mono">
              Action
            </p>

            <div className="grid grid-cols-2 gap-3">
              <FormField label="Level">
                <select
                  value={level}
                  onChange={(e) => setLevel(e.target.value as RuleAction["level"])}
                  className="w-full px-2.5 py-1.5 rounded border border-border bg-background"
                >
                  {LEVEL_OPTIONS.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.emoji} {l.label}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label="Channel">
                <select
                  value={channel}
                  onChange={(e) => setChannel(e.target.value as RuleAction["channel"])}
                  className="w-full px-2.5 py-1.5 rounded border border-border bg-background"
                >
                  {CHANNEL_OPTIONS.map((c) => (
                    <option key={c.id} value={c.id} disabled={c.coming}>
                      {c.emoji} {c.label}{c.coming ? " (soon)" : ""}
                    </option>
                  ))}
                </select>
              </FormField>
            </div>

            <FormField
              label="Title template"
              required
              hint="Variables: {pipeline_name}, {target_label}, {error}, {error_type}, …"
            >
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                placeholder="Pipeline run failed: {pipeline_name}"
                className="w-full px-2.5 py-1.5 rounded border border-border bg-background font-mono text-xs"
              />
            </FormField>

            <FormField label="Message template (optional)">
              <textarea
                value={message ?? ""}
                onChange={(e) => setMessage(e.target.value)}
                rows={2}
                placeholder="{error_type}: {error}"
                className="w-full px-2.5 py-1.5 rounded border border-border bg-background font-mono text-xs"
              />
            </FormField>
          </div>

          {/* Round-6 UX#4: live preview of the rendered notification.
              Substitutes a representative sample context so the user
              can see what the final inbox row will read like BEFORE
              saving + waiting for a real event. */}
          {(title.trim() || (message ?? "").trim()) && (
            <div className="rounded-lg border border-border bg-muted/10 p-3">
              <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-mono mb-1.5">
                👀 Preview
              </p>
              <p className="text-sm font-medium">
                {renderTemplatePreview(
                  title.trim() || "{event_kind}",
                  eventKind,
                )}
              </p>
              {message && (
                <p className="text-xs text-muted-foreground mt-0.5 whitespace-pre-wrap">
                  {renderTemplatePreview(message, eventKind)}
                </p>
              )}
              <p className="text-[10px] text-muted-foreground/70 mt-1.5 italic">
                Sample context — real events will substitute their own values.
              </p>
            </div>
          )}

          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="rounded"
            />
            Enabled
          </label>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
            <button
              type="button"
              onClick={onClose}
              className="text-sm px-3 py-1.5 rounded hover:bg-muted text-muted-foreground"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!filtersValid || saveM.isPending}
              className="text-sm px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-700 text-white font-medium shadow-sm transition-colors disabled:opacity-50"
            >
              {saveM.isPending ? "Saving…" : isNew ? "Create" : "Save"}
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  );
}

function FormField({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground font-mono mb-1 block">
        {label}{required && <span className="text-rose-500"> *</span>}
      </span>
      {children}
      {hint && (
        <span className="text-[10px] text-muted-foreground/70 mt-0.5 block">
          {hint}
        </span>
      )}
    </label>
  );
}

// ---- Round-5 W4 test-rule preview ---------------------------------------

function TestRulePanel({
  eventKind,
  filters,
}: {
  eventKind: string;
  filters: Record<string, unknown> | null;
}) {
  const [result, setResult] = React.useState<{ sampled: number; matched: number; hits: Array<{ event_id: string; event_kind: string; created_at: string; context: Record<string, unknown> }>} | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const runTest = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await notificationRulesApi.test(
        { event_kind: eventKind, filters: filters ?? undefined },
        50,
      );
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="rounded-lg border border-border bg-muted/10 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground font-mono">
          🧪 Test against recent events
        </p>
        <button
          type="button"
          onClick={runTest}
          disabled={busy || !eventKind}
          className="text-[11px] px-2 py-1 rounded border border-border bg-card hover:bg-muted disabled:opacity-50"
        >
          {busy ? "Running…" : "Run dry-run"}
        </button>
      </div>
      {error && <p className="text-[11px] text-rose-600 dark:text-rose-400">{error}</p>}
      {result && (
        <div className="text-[11px] text-muted-foreground">
          <p>
            <strong className="text-foreground">{result.matched}</strong> of {result.sampled} recent events
            would have fired this rule.
          </p>
          {result.hits.length > 0 && (
            <ul className="mt-1.5 space-y-1 max-h-32 overflow-y-auto">
              {result.hits.slice(0, 10).map((h) => (
                <li key={h.event_id} className="font-mono text-[10px]">
                  {new Date(h.created_at).toLocaleTimeString()} · {h.event_kind}
                </li>
              ))}
            </ul>
          )}
          {result.matched === 0 && result.sampled > 0 && (
            <p className="mt-1 italic">
              No matches in the last {result.sampled} events. Loosen filters or wait for a real event.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Render a rule-template string with a representative sample context so
 * the editor's preview block has something concrete to show. Mirrors the
 * backend's `_render()` substitution shape (`{name}` only — no attribute
 * walking, no format specs).
 */
function renderTemplatePreview(template: string, eventKind: string): string {
  const sampleContext: Record<string, string> = {
    event_kind: eventKind,
    pipeline_id: "01HZZZZSAMPLEPIPELINEID0000",
    pipeline_name: "📊 Sample pipeline",
    run_id: "01HZZZZSAMPLERUNID0000000000",
    target_label: "owner@example.com",
    error: "ValueError: column 'price' not found",
    error_type: "ValueError",
    user_id: "user@example.com",
    severity: "warning",
    level: "warning",
  };
  return template.replace(
    /\{([A-Za-z_][A-Za-z0-9_]*)\}/g,
    (_full, key: string) => sampleContext[key] ?? `<sample ${key}>`,
  );
}
