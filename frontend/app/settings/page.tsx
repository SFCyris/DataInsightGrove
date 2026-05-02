"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { setSettings, useSettings, type Theme } from "@/lib/settings";
import { api, API_BASE } from "@/lib/api/client";
import type { SettingDescriptor, JdbcDriverRecord, GlobalWebhookRecord } from "@/lib/api/client";
import { buttonVariants, Button } from "@/components/ui/button";
import { DirectoryPickerModal } from "@/components/directory-picker-modal";

const THEMES: { id: Theme; emoji: string; label: string }[] = [
  { id: "system", emoji: "🖥️", label: "System" },
  { id: "light",  emoji: "☀️", label: "Light" },
  { id: "dark",   emoji: "🌙", label: "Dark" },
];

const SAMPLE_OPTIONS = [10_000, 50_000, 100_000, 500_000, 1_000_000];

type SectionId =
  | "appearance" | "preview" | "storage" | "performance"
  | "jdbc" | "webhooks" | "security" | "about";

const NAV: { id: SectionId; emoji: string; label: string; help: string }[] = [
  { id: "appearance",  emoji: "🎨", label: "Appearance",       help: "Theme + motion (per browser)" },
  { id: "preview",     emoji: "🦆", label: "Browser preview",  help: "DuckDB-WASM behavior" },
  { id: "storage",     emoji: "📁", label: "Storage & paths",  help: "Where data lives" },
  { id: "performance", emoji: "⚡", label: "Performance",      help: "Concurrency + threads" },
  { id: "jdbc",        emoji: "🔌", label: "JDBC drivers",     help: "Saved JAR + class registry" },
  { id: "webhooks",    emoji: "🔔", label: "Global webhooks",  help: "Fire on every run" },
  { id: "security",    emoji: "🔐", label: "Security & API",   help: "Endpoints + auth" },
  { id: "about",       emoji: "ℹ️", label: "About",            help: "Versions, license, links" },
];

export default function SettingsPage() {
  const reduce = useReducedMotion();
  const [section, setSection] = useState<SectionId>("appearance");

  // Hash-based deep-linking — /settings#jdbc lands on JDBC section.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash.replace("#", "") as SectionId;
    if (NAV.some((n) => n.id === hash)) setSection(hash);
    const onHash = () => {
      const h = window.location.hash.replace("#", "") as SectionId;
      if (NAV.some((n) => n.id === h)) setSection(h);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const fadeUp = reduce
    ? { initial: false as const, animate: { opacity: 1, y: 0 } }
    : {
        initial: { opacity: 0, y: 8 },
        animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 30 },
      };

  return (
    <main id="main" className="flex flex-1 min-h-0">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 border-r border-border bg-card/30 flex flex-col">
        <div className="px-5 py-5 flex items-center gap-3 border-b border-border">
          <span className="text-2xl select-none" role="img" aria-label="Settings">⚙️</span>
          <div>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground">DIG</p>
            <h1 className="text-base font-semibold tracking-tight leading-none">Settings</h1>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto py-2">
          {NAV.map((n) => (
            <button
              key={n.id}
              type="button"
              onClick={() => {
                setSection(n.id);
                if (typeof window !== "undefined") {
                  history.replaceState(null, "", `#${n.id}`);
                }
              }}
              className={[
                "w-full text-left px-4 py-2.5 flex items-start gap-3 transition-colors",
                section === n.id
                  ? "bg-emerald-50 dark:bg-emerald-900/20 border-r-2 border-emerald-500"
                  : "hover:bg-muted/40 border-r-2 border-transparent",
              ].join(" ")}
            >
              <span className="text-lg leading-none mt-0.5" aria-hidden>{n.emoji}</span>
              <span className="inline-flex flex-col">
                <span className="block text-sm font-medium">{n.label}</span>
                <span className="block text-[11px] text-muted-foreground leading-tight">{n.help}</span>
              </span>
            </button>
          ))}
        </nav>
        <div className="p-4 border-t border-border">
          <Link href="/" className={buttonVariants({ variant: "outline", size: "sm" })}>
            ← Home
          </Link>
        </div>
      </aside>

      {/* Section content */}
      <motion.section {...fadeUp} className="flex-1 overflow-y-auto p-8 max-w-4xl">
        {section === "appearance"  && <AppearanceSection />}
        {section === "preview"     && <PreviewSection />}
        {section === "storage"     && <ServerSettingsSection filter={["input_dir", "output_dir", "run_history_days"]} title="📁 Storage & paths" />}
        {section === "performance" && <ServerSettingsSection filter={["default_sample_rows", "default_preview_limit", "max_concurrent_runs", "duckdb_threads", "log_level", "auto_detect_index", "auto_detect_timezone"]} title="⚡ Performance & detection" />}
        {section === "jdbc"        && <JdbcSection />}
        {section === "webhooks"    && <WebhooksSection />}
        {section === "security"    && <SecuritySection />}
        {section === "about"       && <AboutSection />}
      </motion.section>
    </main>
  );
}

// ---- Section: Appearance --------------------------------------------------

function AppearanceSection() {
  const settings = useSettings();
  return (
    <Page title="🎨 Appearance" lede="Theme stays per-browser. Reduced motion is respected automatically when your OS asks for it.">
      <Card>
        <Field label="Theme" hint="Auto follows your OS preference.">
          <div className="flex gap-2">
            {THEMES.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setSettings({ theme: t.id })}
                className={[
                  "flex-1 rounded-lg border px-3 py-3 text-sm flex flex-col items-center gap-1 transition-colors",
                  settings.theme === t.id
                    ? "border-emerald-500/60 bg-emerald-50 dark:bg-emerald-900/20"
                    : "border-border hover:border-foreground/30",
                ].join(" ")}
              >
                <span className="text-xl" aria-hidden>{t.emoji}</span>
                <span>{t.label}</span>
              </button>
            ))}
          </div>
        </Field>
      </Card>
    </Page>
  );
}

// ---- Section: Browser preview --------------------------------------------

function PreviewSection() {
  const settings = useSettings();
  return (
    <Page title="🦆 Browser preview" lede="Controls the DuckDB-WASM live grid that recomputes as you edit.">
      <Card>
        <Field label="Auto-recompute on every edit"
          hint="When on, the editor's grid auto-runs DuckDB-WASM on every doc change (debounced 350ms). Turn off for very slow machines.">
          <Toggle on={settings.livePreview} onChange={(on) => setSettings({ livePreview: on })} />
        </Field>
        <Field label="Sample size" hint="Rows scanned by the in-browser engine. Lower = snappier; higher = more representative.">
          <div className="flex gap-1.5 flex-wrap">
            {SAMPLE_OPTIONS.map((n) => (
              <button
                key={n}
                type="button"
                onClick={() => setSettings({ sampleRows: n })}
                className={[
                  "rounded-md border px-2.5 py-1 text-xs tabular-nums transition-colors",
                  settings.sampleRows === n
                    ? "border-emerald-500/60 bg-emerald-50 dark:bg-emerald-900/20"
                    : "border-border hover:border-foreground/30",
                ].join(" ")}
              >
                {n.toLocaleString()}
              </button>
            ))}
          </div>
        </Field>
      </Card>
    </Page>
  );
}

// ---- Section: Server-side settings (storage, performance) -----------------

function ServerSettingsSection({ filter, title }: { filter: string[]; title: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings"], queryFn: api.listSettings });
  const settings = (q.data ?? []).filter((s) => filter.includes(s.key));
  const saveSetting = async (key: string, value: unknown) => {
    try {
      await api.setSetting(key, value);
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success("✅ Saved");
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    }
  };
  return (
    <Page title={title} lede="Server-side settings persist across all browsers and survive restarts. Stored in DIG's SQLite metadata DB.">
      <Card>
        {q.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {q.isError && (
          <p className="text-sm text-destructive">
            Couldn't reach the API ({(q.error as Error).message}). Restart the backend if you just deployed new tables.
          </p>
        )}
        {settings.map((s) => (
          <SettingRow key={s.key} setting={s} onSave={saveSetting} />
        ))}
      </Card>
    </Page>
  );
}

function SettingRow({ setting, onSave }: { setting: SettingDescriptor; onSave: (key: string, value: unknown) => void }) {
  const [draft, setDraft] = useState<string>(
    setting.value === null || setting.value === undefined ? "" : String(setting.value),
  );
  const [pickerOpen, setPickerOpen] = useState(false);
  const isDirty = draft !== (setting.value === null || setting.value === undefined ? "" : String(setting.value));

  if (setting.type === "boolean") {
    const on = Boolean(setting.value);
    return (
      <Field label={setting.label} hint={setting.help}>
        <Toggle on={on} onChange={(next) => onSave(setting.key, next)} />
      </Field>
    );
  }
  if (setting.type === "enum" && setting.options) {
    return (
      <Field label={setting.label} hint={setting.help}>
        <select
          value={String(setting.value ?? "")}
          onChange={(e) => onSave(setting.key, e.target.value)}
          className="rounded-md border border-input bg-background px-2 py-1 text-sm"
        >
          {setting.options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </Field>
    );
  }
  // path / integer / string — text input with explicit save. Path-type
  // settings additionally get a 📁 Browse button that opens the directory
  // picker modal anchored on the current value.
  return (
    <Field label={setting.label} hint={setting.help}>
      <div className="flex gap-2">
        <input
          type={setting.type === "integer" ? "number" : "text"}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={setting.default ? String(setting.default) : "Default"}
          className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono"
        />
        {setting.type === "path" && (
          <>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setPickerOpen(true)}
              title="Browse server filesystem"
            >
              📁 Browse
            </Button>
            <DirectoryPickerModal
              open={pickerOpen}
              // Open at the current draft value (lets users browse from
              // their in-progress edit, not just the saved value). Empty
              // → backend defaults to $HOME.
              initialPath={draft || (setting.value as string) || ""}
              forLabel={setting.label.toLowerCase()}
              onClose={() => setPickerOpen(false)}
              onSelect={(picked) => {
                // Picking commits the value directly — saves the round-trip
                // through the Save button. The user can still hand-edit
                // afterwards if they want to refine the path.
                setDraft(picked);
                onSave(setting.key, picked || null);
              }}
            />
          </>
        )}
        <Button
          size="sm"
          variant={isDirty ? "default" : "ghost"}
          disabled={!isDirty}
          onClick={() => {
            const value =
              setting.type === "integer"
                ? draft === "" ? null : Number(draft)
                : draft || null;
            onSave(setting.key, value);
          }}
        >
          Save
        </Button>
      </div>
    </Field>
  );
}

// ---- Section: JDBC drivers -----------------------------------------------

function JdbcSection() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["jdbc-drivers"], queryFn: api.listJdbcDrivers });
  const [draft, setDraft] = useState<{ id?: string; name: string; driverClass: string; jarPath: string; urlTemplate: string; notes: string } | null>(null);

  const empty = () => setDraft({ name: "", driverClass: "", jarPath: "", urlTemplate: "", notes: "" });

  const save = async () => {
    if (!draft) return;
    try {
      const body = {
        name: draft.name.trim(),
        driverClass: draft.driverClass.trim(),
        jarPath: draft.jarPath.trim(),
        urlTemplate: draft.urlTemplate.trim() || null,
        notes: draft.notes.trim() || null,
      };
      if (draft.id) await api.updateJdbcDriver(draft.id, body);
      else await api.createJdbcDriver(body);
      qc.invalidateQueries({ queryKey: ["jdbc-drivers"] });
      setDraft(null);
      toast.success("✅ Saved");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this driver entry? Pipelines that reference it by name will need to be re-pointed.")) return;
    try {
      await api.deleteJdbcDriver(id);
      qc.invalidateQueries({ queryKey: ["jdbc-drivers"] });
      toast.success("🗑️ Deleted");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <Page
      title="🔌 JDBC drivers"
      lede="Register a driver class + JAR once. Pipelines using the jdbc connector or export_to_jdbc step pick from this list instead of pasting paths."
    >
      <Card>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm text-muted-foreground">{q.data?.length ?? 0} registered</p>
          <Button size="sm" onClick={empty}>+ Add driver</Button>
        </div>
        {q.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {q.data && q.data.length === 0 && !draft && (
          <Empty
            title="No drivers yet"
            body="Add your first driver — Oracle, Snowflake, MS SQL Server, anything with a JDBC JAR."
          />
        )}
        <ul className="divide-y divide-border/60">
          {q.data?.map((d) => (
            <li key={d.id} className="py-3 flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">{d.name}</p>
                <p className="text-[11px] font-mono text-muted-foreground truncate" title={d.driverClass}>{d.driverClass}</p>
                <p className="text-[10px] text-muted-foreground/80 truncate" title={d.jarPath}>📦 {d.jarPath}</p>
                {d.urlTemplate && (
                  <p className="text-[10px] font-mono text-muted-foreground/80 truncate" title={d.urlTemplate}>🔗 {d.urlTemplate}</p>
                )}
              </div>
              <div className="flex gap-1 shrink-0">
                <Button size="sm" variant="ghost" onClick={() => setDraft({
                  id: d.id, name: d.name, driverClass: d.driverClass,
                  jarPath: d.jarPath, urlTemplate: d.urlTemplate ?? "", notes: d.notes ?? "",
                })}>Edit</Button>
                <Button size="sm" variant="ghost" onClick={() => remove(d.id)}>🗑️</Button>
              </div>
            </li>
          ))}
        </ul>

        {draft && (
          <div className="mt-3 p-4 rounded-lg border border-emerald-300/60 bg-emerald-50/40 dark:bg-emerald-900/10 space-y-3">
            <p className="text-sm font-medium">{draft.id ? "Edit driver" : "New driver"}</p>
            <Input label="Display name" placeholder="Oracle 19c"
                   value={draft.name} onChange={(v) => setDraft({ ...draft, name: v })} />
            <Input label="Driver class" placeholder="oracle.jdbc.OracleDriver" mono
                   value={draft.driverClass} onChange={(v) => setDraft({ ...draft, driverClass: v })} />
            <Input label="JAR path" placeholder="/Users/me/dig-drivers/ojdbc11.jar" mono
                   value={draft.jarPath} onChange={(v) => setDraft({ ...draft, jarPath: v })} />
            <Input label="URL template (optional)" placeholder="jdbc:oracle:thin:@//<host>:1521/<service>" mono
                   value={draft.urlTemplate} onChange={(v) => setDraft({ ...draft, urlTemplate: v })} />
            <Input label="Notes (optional)" placeholder="Compatible with our 12c + 19c instances"
                   value={draft.notes} onChange={(v) => setDraft({ ...draft, notes: v })} />
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={save}
                disabled={!draft.name.trim() || !draft.driverClass.trim() || !draft.jarPath.trim()}>
                💾 Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>Cancel</Button>
            </div>
          </div>
        )}
      </Card>
    </Page>
  );
}

// ---- Section: Global webhooks --------------------------------------------

function WebhooksSection() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["global-webhooks"], queryFn: api.listGlobalWebhooks });
  const [draft, setDraft] = useState<{
    id?: string; label: string; url: string; on: "always" | "succeeded" | "failed" | "triggered";
    secret: string; enabled: boolean;
  } | null>(null);

  const empty = () => setDraft({ label: "", url: "", on: "always", secret: "", enabled: true });

  const save = async () => {
    if (!draft) return;
    try {
      const body = {
        label: draft.label.trim() || null,
        url: draft.url.trim(),
        on: draft.on,
        secret: draft.secret.trim() || null,
        enabled: draft.enabled,
      };
      if (draft.id) await api.updateGlobalWebhook(draft.id, body);
      else await api.createGlobalWebhook(body);
      qc.invalidateQueries({ queryKey: ["global-webhooks"] });
      setDraft(null);
      toast.success("✅ Saved");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const remove = async (id: string) => {
    if (!confirm("Delete this webhook? It will no longer fire for any future runs.")) return;
    try {
      await api.deleteGlobalWebhook(id);
      qc.invalidateQueries({ queryKey: ["global-webhooks"] });
      toast.success("🗑️ Deleted");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const toggleEnabled = async (w: GlobalWebhookRecord) => {
    try {
      await api.updateGlobalWebhook(w.id, { ...w, enabled: !w.enabled });
      qc.invalidateQueries({ queryKey: ["global-webhooks"] });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <Page
      title="🔔 Global webhooks"
      lede="Fire on every pipeline's terminal status. Per-pipeline webhooks live with the pipeline; these are catch-all integrations like 'ping Slack on any failure'."
    >
      <Card>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm text-muted-foreground">{q.data?.length ?? 0} configured</p>
          <Button size="sm" onClick={empty}>+ Add webhook</Button>
        </div>
        {q.isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {q.data && q.data.length === 0 && !draft && (
          <Empty
            title="No global webhooks"
            body="Add your first to ping Slack / n8n / GitHub Actions / your own monitor when any pipeline finishes."
          />
        )}
        <ul className="divide-y divide-border/60">
          {q.data?.map((w) => (
            <li key={w.id} className="py-3 flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">{w.label || "(unlabeled)"}</span>
                  <span className={[
                    "text-[10px] px-1.5 py-0.5 rounded-full border",
                    w.on === "failed"
                      ? "border-rose-300/60 text-rose-600 dark:text-rose-300"
                      : w.on === "succeeded"
                        ? "border-emerald-300/60 text-emerald-600 dark:text-emerald-300"
                        : w.on === "triggered"
                          // Distinct color so users can spot at-a-glance which
                          // webhooks are step-driven vs. status-driven.
                          ? "border-violet-300/60 text-violet-600 dark:text-violet-300"
                          : "border-border text-muted-foreground",
                  ].join(" ")}>{w.on === "triggered" ? "🔔 triggered" : w.on}</span>
                  {!w.enabled && (
                    <span className="text-[10px] text-muted-foreground italic">paused</span>
                  )}
                  {w.secret && (
                    <span className="text-[10px] text-muted-foreground" title="HMAC-signed">🔐 signed</span>
                  )}
                </div>
                <p className="text-[11px] font-mono text-muted-foreground truncate mt-0.5" title={w.url}>{w.url}</p>
              </div>
              <div className="flex gap-1 shrink-0">
                <Button size="sm" variant="ghost" onClick={() => toggleEnabled(w)}>
                  {w.enabled ? "⏸" : "▶"}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setDraft({
                  id: w.id, label: w.label ?? "", url: w.url, on: (w.on as any) ?? "always",
                  secret: w.secret ?? "", enabled: w.enabled ?? true,
                })}>Edit</Button>
                <Button size="sm" variant="ghost" onClick={() => remove(w.id)}>🗑️</Button>
              </div>
            </li>
          ))}
        </ul>

        {draft && (
          <div className="mt-3 p-4 rounded-lg border border-emerald-300/60 bg-emerald-50/40 dark:bg-emerald-900/10 space-y-3">
            <p className="text-sm font-medium">{draft.id ? "Edit webhook" : "New webhook"}</p>
            <Input label="Label (optional)" placeholder="Slack #data-ops"
                   value={draft.label} onChange={(v) => setDraft({ ...draft, label: v })} />
            <Input label="URL" placeholder="https://hooks.slack.com/services/T…/B…/…" mono
                   value={draft.url} onChange={(v) => setDraft({ ...draft, url: v })} />
            <Field
              label="Fire when"
              hint="Always = both successes and failures · Triggered = only when an in-pipeline 🔔 Trigger webhook step calls it (never auto-fires)."
            >
              <select
                value={draft.on}
                onChange={(e) => setDraft({ ...draft, on: e.target.value as any })}
                className="rounded-md border border-input bg-background px-2 py-1 text-sm"
              >
                <option value="always">Always (success + failure)</option>
                <option value="succeeded">On success only</option>
                <option value="failed">On failure only</option>
                <option value="triggered">Triggered (only from inside a flow)</option>
              </select>
            </Field>
            <Input label="HMAC secret (optional)" placeholder="leave blank to skip signing" mono
                   value={draft.secret} onChange={(v) => setDraft({ ...draft, secret: v })}
                   help="When set, DIG sends X-DIG-Signature: sha256=<hex> so the receiver can verify the body." />
            <Field label="Enabled" hint="Disabled webhooks are kept in the list but don't fire.">
              <Toggle on={draft.enabled} onChange={(on) => setDraft({ ...draft, enabled: on })} />
            </Field>
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={save}
                disabled={!draft.url.startsWith("http")}>
                💾 Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>Cancel</Button>
            </div>
          </div>
        )}
      </Card>
    </Page>
  );
}

// ---- Section: Security ---------------------------------------------------

function SecuritySection() {
  return (
    <Page title="🔐 Security & API"
      lede="Bind host, port, and auth token are start-time settings — DIG re-reads them only on restart, so they're shown read-only here.">
      <Card>
        <Field label="API endpoint" hint="The address this UI talks to.">
          <code className="text-xs bg-muted px-2 py-1 rounded font-mono">{API_BASE}</code>
        </Field>
        <Field label="Auth token" hint="Required for non-loopback bind. Set via DIG_AUTH_TOKEN at server start.">
          <p className="text-xs text-muted-foreground">
            Loopback (localhost) deployments may run unauthenticated. For LAN
            access, generate a token with{" "}
            <code className="text-[11px] bg-muted px-1 py-0.5 rounded font-mono">
              python3 -c &apos;import secrets; print(secrets.token_urlsafe(32))&apos;
            </code>{" "}
            and set <code className="text-[11px] bg-muted px-1 py-0.5 rounded font-mono">DIG_AUTH_TOKEN</code>.
          </p>
        </Field>
      </Card>
    </Page>
  );
}

// ---- Section: About ------------------------------------------------------

function AboutSection() {
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });
  const conns = useQuery({ queryKey: ["connectors"], queryFn: api.listConnectorsTyped });
  const steps = useQuery({ queryKey: ["steps"], queryFn: api.listSteps });

  return (
    <Page title="ℹ️ About this install" lede="DataInsightGrove™ — self-hosted data preparation.">
      <Card>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <Stat label="Product" value="DataInsightGrove™ · DIG™" />
          <Stat label="Backend" value={health.data ? `${health.data.name} v${health.data.version} ✅` : "…"} />
          <Stat label="API endpoint" value={API_BASE} mono />
          <Stat label="License" value="AGPL-3.0-or-later" />
          <Stat label="Connectors" value={`${conns.data?.length ?? 0} loaded`} />
          <Stat label="Steps" value={`${steps.data?.length ?? 0} registered`} />
        </dl>
        <div className="flex flex-wrap gap-3 mt-4">
          <a href="https://github.com/SFCyris/DataInsightGrove" target="_blank" rel="noreferrer"
             className={buttonVariants({ variant: "outline", size: "sm" })}
             title="Canonical source repository (AGPL-3.0)">
            🐙 Source on GitHub
          </a>
          <a href={`${API_BASE}/docs`} target="_blank" rel="noreferrer"
             className={buttonVariants({ variant: "outline", size: "sm" })}>
            📡 Open Swagger UI
          </a>
          <a href={`${API_BASE}/openapi.json`} target="_blank" rel="noreferrer"
             className={buttonVariants({ variant: "ghost", size: "sm" })}>
            ⬇️ openapi.json
          </a>
        </div>
        <p className="text-[11px] text-muted-foreground/80 leading-relaxed pt-3 max-w-prose">
          DataInsightGrove™ and DIG™ are unregistered word-mark trademarks of Sebastian Cyris. The 🌳 emoji throughout the UI is generic Unicode (U+1F333) and is not claimed.
          Source licensed under AGPL-3.0-or-later. See{" "}
          <a href="https://github.com/SFCyris/DataInsightGrove/blob/main/TRADEMARK.md" target="_blank" rel="noreferrer"
             className="underline hover:text-foreground">TRADEMARK.md</a>{" "}
          for trademark notice and{" "}
          <a href="https://github.com/SFCyris/DataInsightGrove/blob/main/LICENSE" target="_blank" rel="noreferrer"
             className="underline hover:text-foreground">LICENSE</a>{" "}
          for full source-license terms.
        </p>
      </Card>

      <Card>
        <Field label="Replay onboarding" hint="Resets the home page tour and the column-menu first-time tooltip.">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              try {
                localStorage.removeItem("dig.tour.home");
                localStorage.removeItem("dig.tour.column_chevron");
              } catch {/* ignore */}
              window.location.href = "/";
            }}
          >
            🔄 Reset onboarding
          </Button>
        </Field>
      </Card>
    </Page>
  );
}

// ---- Tiny presentational helpers -----------------------------------------

function Page({ title, lede, children }: { title: string; lede?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
        {lede && <p className="text-sm text-muted-foreground mt-1 max-w-prose">{lede}</p>}
      </header>
      <div className="space-y-5">{children}</div>
    </div>
  );
}

function Card({ children }: { children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-border bg-card/50 p-5 space-y-4">
      {children}
    </section>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-[1fr_2fr] gap-3 items-start">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {hint && <p className="text-[11px] text-muted-foreground mt-1 leading-snug">{hint}</p>}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Input({
  label, value, onChange, placeholder, mono, help,
}: {
  label: string; value: string; onChange: (next: string) => void;
  placeholder?: string; mono?: boolean; help?: string;
}) {
  return (
    <Field label={label} hint={help}>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={[
          "w-full rounded-md border border-input bg-background px-2 py-1 text-sm",
          mono ? "font-mono" : "",
        ].join(" ")}
      />
    </Field>
  );
}

function Toggle({ on, onChange }: { on: boolean; onChange: (next: boolean) => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      onClick={() => onChange(!on)}
      className={[
        "h-6 w-10 rounded-full transition-colors relative",
        on ? "bg-emerald-500" : "bg-muted",
      ].join(" ")}
    >
      <span
        className={[
          "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-background shadow transition-transform",
          on ? "translate-x-4" : "translate-x-0",
        ].join(" ")}
      />
    </button>
  );
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <>
      <dt className="text-xs uppercase tracking-wider text-muted-foreground self-center">{label}</dt>
      <dd className={["text-sm font-medium break-all", mono ? "font-mono" : ""].join(" ")}>{value}</dd>
    </>
  );
}

function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="text-center py-8 text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{title}</p>
      <p className="mt-1 max-w-sm mx-auto">{body}</p>
    </div>
  );
}
