"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { confirmAction } from "@/lib/confirm-toast";
import {
  setSettings,
  useSettings,
  useExpertise,
  type Theme,
  type ExpertiseLevel,
  EXPERTISE_LABEL,
  EXPERTISE_DESCRIPTION,
  AUTO_PROMOTE_THRESHOLD,
} from "@/lib/settings";
import { api, aiApi } from "@/lib/api/client";
import type { SettingDescriptor, JdbcDriverRecord, GlobalWebhookRecord, AiProbeOut } from "@/lib/api/client";
import { useApiBase } from "@/lib/use-api-base";
import { buttonVariants, Button } from "@/components/ui/button";
import { DirectoryPickerModal } from "@/components/directory-picker-modal";
import { PathPickerField } from "@/components/path-picker-field";
import { PacksSection } from "@/components/settings/packs-section";
import { NotificationsSection } from "@/components/settings/notifications-section";
import { NotificationRulesSection } from "@/components/settings/notification-rules-section";
import { fmtInt } from "@/lib/format-number";
import { fmtVersion } from "@/lib/format-version";
import { useDocumentTitle } from "@/lib/use-document-title";
import { PositiveLoaderInline } from "@/components/positive-loader";

const THEMES: { id: Theme; emoji: string; label: string }[] = [
  { id: "system", emoji: "🖥️", label: "System" },
  { id: "light",  emoji: "☀️", label: "Light" },
  { id: "dark",   emoji: "🌙", label: "Dark" },
];

const SAMPLE_OPTIONS = [10_000, 50_000, 100_000, 500_000, 1_000_000];

type SectionId =
  | "appearance" | "expertise" | "preview" | "storage" | "performance"
  | "ai" | "jdbc" | "webhooks" | "packs" | "notifications" | "notification-rules"
  | "security" | "server" | "about";

const NAV: { id: SectionId; emoji: string; label: string; help: string }[] = [
  { id: "appearance",  emoji: "🎨", label: "Appearance",       help: "Theme + motion (per browser)" },
  { id: "expertise",   emoji: "🌱", label: "Expertise mode",   help: "Beginner / Builder / Engineer" },
  { id: "preview",     emoji: "⚡", label: "Live preview",     help: "How the grid recomputes as you edit" },
  { id: "storage",     emoji: "📁", label: "Storage & paths",  help: "Where data lives" },
  { id: "performance", emoji: "⚡", label: "Performance",      help: "Concurrency + threads" },
  { id: "server",      emoji: "🔧", label: "Server & TLS",     help: "Ports, logs, HTTPS — needs restart" },
  { id: "ai",          emoji: "✨", label: "AI assistant",     help: "Local Ollama or BYOK provider" },
  { id: "jdbc",        emoji: "🔌", label: "JDBC drivers",     help: "Saved JAR + class registry" },
  { id: "webhooks",    emoji: "🔔", label: "Global webhooks",  help: "Fire on every run" },
  { id: "packs",         emoji: "📦", label: "Step Packs",       help: "Add/remove step plugin bundles" },
  { id: "notifications",      emoji: "🔔", label: "Notifications",      help: "System + runtime event log" },
  { id: "notification-rules", emoji: "📐", label: "Notification rules", help: "Trigger rules: events → notifications" },
  { id: "security",           emoji: "🔐", label: "Security & API",     help: "Endpoints + auth" },
  { id: "about",       emoji: "ℹ️", label: "About",            help: "Versions, license, links" },
];

export default function SettingsPage() {
  useDocumentTitle('Settings');
  const reduce = useReducedMotion();
  const [section, setSection] = useState<SectionId>("appearance");
  const [settingsQuery, setSettingsQuery] = useState("");

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
    <main id="main" className="flex flex-1 min-h-0 flex-col lg:flex-row">
      {/* Sidebar — Round-4 UX#3: the ``w-64 shrink-0`` aside combined
          with the ``max-w-4xl p-8`` content forced horizontal scroll on
          viewports below ~880px. Stack the sidebar above the content
          on narrow screens instead, with the nav running in a
          scrollable horizontal strip so all sections stay reachable. */}
      <aside className="lg:w-64 lg:shrink-0 border-r border-border bg-card/30 flex flex-col">
        {/* Top-left back/home — same convention as every other page. */}
        <div className="px-3 pt-3 pb-1">
          <Link href="/" className={buttonVariants({ variant: "ghost", size: "sm" })}>
            ← Home
          </Link>
        </div>
        <div className="px-5 py-4 flex items-center gap-3 border-b border-border">
          <span className="text-2xl select-none" role="img" aria-label="Settings">⚙️</span>
          <div>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground">DIG</p>
            <h1 className="text-base font-semibold tracking-tight leading-none">Settings</h1>
          </div>
        </div>
        {/* Round-5 W5: in-page settings search. Fuzzy-matches the label
            + help fields of each NAV entry and dims the rows that don't
            match. Empty query keeps every row visible (default). */}
        <div className="px-3 py-2 border-b border-border">
          <input
            type="search"
            value={settingsQuery}
            onChange={(e) => setSettingsQuery(e.target.value)}
            placeholder="Search settings…"
            aria-label="Search settings"
            className="w-full px-2 py-1.5 text-xs rounded-md border border-input bg-background focus:outline-none focus:ring-2 focus:ring-ring/40"
          />
        </div>
        <nav className="flex-1 overflow-x-auto lg:overflow-y-auto py-2 flex lg:flex-col">
          {NAV.filter((n) => {
            const q = settingsQuery.trim().toLowerCase();
            if (!q) return true;
            return (
              n.label.toLowerCase().includes(q) ||
              n.help.toLowerCase().includes(q) ||
              n.id.toLowerCase().includes(q)
            );
          }).map((n) => (
            <button
              key={n.id}
              type="button"
              onClick={() => {
                setSection(n.id);
                if (typeof window !== "undefined") {
                  history.replaceState(null, "", `#${n.id}`);
                }
              }}
              aria-current={section === n.id ? "page" : undefined}
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
      </aside>

      {/* Section content */}
      <motion.section {...fadeUp} className="flex-1 overflow-y-auto p-8 max-w-4xl">
        {section === "appearance"  && <AppearanceSection />}
        {section === "expertise"   && <ExpertiseSection />}
        {section === "preview"     && <PreviewSection />}
        {section === "storage"     && <ServerSettingsSection filter={["input_dir", "output_dir", "run_history_days"]} title="📁 Storage & paths" />}
        {section === "performance" && <ServerSettingsSection filter={["default_sample_rows", "default_preview_limit", "max_concurrent_runs", "duckdb_threads", "log_level", "auto_detect_index", "auto_detect_timezone"]} title="⚡ Performance & detection" />}
        {section === "server"      && <ServerSettingsSection
          filter={["logDir", "log.maxBytes", "log.backupCount", "tls.enabled", "tls.autoTrust", "api.httpsPort", "web.httpsPort"]}
          title="🔧 Server & TLS"
          lede="Boot-time configuration — read by scripts/dig-start.sh + the TLS proxy. Changes here write to ~/.config/dig/config.json and take effect on the next restart."
        />}
        {section === "ai"          && <AiSection />}
        {section === "jdbc"        && <JdbcSection />}
        {section === "webhooks"    && <WebhooksSection />}
        {section === "packs"         && <PacksSection />}
        {section === "notifications"      && <NotificationsSection />}
        {section === "notification-rules" && <NotificationRulesSection />}
        {section === "security"           && <SecuritySection />}
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

// ---- Section: Expertise mode ---------------------------------------------

const EXPERTISE_LEVELS: ExpertiseLevel[] = ["beginner", "builder", "engineer"];

function ExpertiseSection() {
  const { level, auto, actionCount, setLevel } = useExpertise();
  const settings = useSettings();
  return (
    <Page
      title="🌱 Expertise mode"
      lede="DIG progressively reveals complexity as you grow. Switch any time — never a wizard, always reversible."
    >
      <Card>
        <Field
          label="Mode"
          hint={
            auto
              ? `Auto-promotes to Builder after ${AUTO_PROMOTE_THRESHOLD} actions. You're at ${actionCount}.`
              : "Auto-promotion is off — you're driving."
          }
        >
          <div className="flex flex-col gap-2">
            {EXPERTISE_LEVELS.map((id) => (
              <button
                key={id}
                type="button"
                onClick={() => setLevel(id)}
                className={[
                  "rounded-lg border px-4 py-3 text-left transition-colors",
                  level === id
                    ? "border-emerald-500/60 bg-emerald-50 dark:bg-emerald-900/20"
                    : "border-border hover:border-foreground/30",
                ].join(" ")}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-sm">{EXPERTISE_LABEL[id]}</span>
                  {level === id && (
                    <span className="text-[10px] uppercase tracking-widest text-emerald-700 dark:text-emerald-400">
                      Current
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                  {EXPERTISE_DESCRIPTION[id]}
                </p>
              </button>
            ))}
          </div>
        </Field>
      </Card>
      <Card>
        <Field
          label="Compact grid headers"
          hint="Hide inline sparklines + summary stats in column headers. Useful on dense screens; stats remain available in the profile drawer."
        >
          <Toggle
            on={settings.compactHeaders}
            onChange={(on) => setSettings({ compactHeaders: on })}
          />
        </Field>
      </Card>
      <p className="text-xs text-muted-foreground mt-4 leading-relaxed">
        Engineer mode unlocks the Live SQL toggle, lineage graph, raw JSON view, and auto-review on save. Beginner mode is forgiving — every advanced affordance has a "show me more" promote-for-this-session affordance, so you'll never hit a wall.
      </p>
    </Page>
  );
}

// ---- Section: Browser preview --------------------------------------------

function PreviewSection() {
  const settings = useSettings();
  return (
    <Page title="⚡ Live preview" lede="Controls the live grid that recomputes as you edit.">
      <Card>
        <Field label="Auto-recompute on every edit"
          hint="When on, the editor's grid recomputes on every change (debounced 350ms). Turn off for very slow machines.">
          <Toggle on={settings.livePreview} onChange={(on) => setSettings({ livePreview: on })} />
        </Field>
        <Field label="Sample size" hint="Rows scanned for the live preview. Lower = snappier; higher = more representative.">
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
                {fmtInt(n)}
              </button>
            ))}
          </div>
        </Field>
      </Card>
    </Page>
  );
}

// ---- Section: Server-side settings (storage, performance) -----------------

function ServerSettingsSection({ filter, title, lede }: { filter: string[]; title: string; lede?: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings"], queryFn: api.listSettings });
  const settings = (q.data ?? []).filter((s) => filter.includes(s.key));
  const saveSetting = async (key: string, value: unknown) => {
    try {
      const result = await api.setSetting(key, value);
      qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success(
        result?.requires_restart
          ? "✅ Saved · restart DIG for it to take effect"
          : "✅ Saved",
      );
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    }
  };
  return (
    <Page title={title} lede={lede ?? "Server-side settings persist across all browsers and survive restarts. Stored in DIG's SQLite metadata DB."}>
      <Card>
        {q.isLoading && <PositiveLoaderInline variant="rendering" text="Loading…" size="sm" />}
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
  const fieldId = `setting-${setting.key}`;
  if (setting.type === "enum" && setting.options) {
    return (
      <Field label={setting.label} hint={setting.help} htmlFor={fieldId}>
        <select
          id={fieldId}
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
  // path / integer / float / string / secret — text input with explicit save.
  // Path-type settings additionally get a 📁 Browse button.
  // Secret-type values arrive masked from the backend (e.g. "sk-…abcd"); we
  //   treat any user input as a NEW value to save, and show a placeholder
  //   that confirms a value is set without revealing it.
  const isSecret = setting.type === "secret";
  const inputType = isSecret ? "password"
    : setting.type === "integer" || setting.type === "float" ? "number"
    : "text";
  const placeholder = isSecret
    ? (setting.value ? `Set: ${String(setting.value)} — type to replace` : "Not set")
    : (setting.default ? String(setting.default) : "Default");
  return (
    <Field label={setting.label} hint={setting.help} htmlFor={fieldId}>
      <div className="flex gap-2">
        <input
          id={fieldId}
          type={inputType}
          step={setting.type === "float" ? "any" : undefined}
          // Secret fields start blank — the backend's masked value is shown
          // in the placeholder, never as the editable text. This avoids the
          // user accidentally saving the masked stub as the real key.
          value={isSecret ? draft : draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={placeholder}
          // Suppress browser + extension password-managers on this field.
          // API keys aren't login credentials and shouldn't trigger Save /
          // Generate / Manage Passwords UI. The four attributes cover
          // every major manager:
          //   autoComplete="off"   — Firefox built-in + Chrome
          //   data-1p-ignore       — 1Password
          //   data-lpignore        — LastPass
          //   data-form-type=other — Bitwarden, Edge built-in
          // Use a unique `name` so Firefox doesn't bleed credentials from
          // adjacent forms (was offering the user's saved login email
          // as if it were a username for this form).
          name={isSecret ? `dig-secret-${setting.key}` : undefined}
          autoComplete="off"
          data-1p-ignore={isSecret ? "true" : undefined}
          data-lpignore={isSecret ? "true" : undefined}
          data-form-type={isSecret ? "other" : undefined}
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
              initialPath={draft || (setting.value as string) || ""}
              forLabel={setting.label.toLowerCase()}
              onClose={() => setPickerOpen(false)}
              onSelect={(picked) => {
                setDraft(picked);
                onSave(setting.key, picked || null);
              }}
            />
          </>
        )}
        <Button
          size="sm"
          variant={isDirty || (isSecret && draft) ? "default" : "ghost"}
          disabled={!isDirty && !(isSecret && draft)}
          onClick={() => {
            // Round-9 fix: a secret with an empty draft used to replace
            // the stored secret with "" (silent wipe). Now if the user
            // clicks Save on a secret with blank input, no-op — they
            // can always use the explicit Clear button when one exists.
            if (isSecret && !draft) {
              toast.info("Secret unchanged — type a new value to replace it.");
              return;
            }
            const value =
              setting.type === "integer"
                ? draft === "" ? null : Number(draft)
                : setting.type === "float"
                  ? draft === "" ? null : Number(draft)
                  : draft || (isSecret ? "" : null);
            onSave(setting.key, value);
            // After saving a secret, clear the input so the masked
            // placeholder takes over again — visual confirmation it landed.
            if (isSecret) setDraft("");
          }}
        >
          Save
        </Button>
      </div>
    </Field>
  );
}

// ---- Section: AI assistant -----------------------------------------------

function AiSection() {
  const qc = useQueryClient();
  // Pull the existing settings store; the seven ai_* keys live alongside
  // the rest of the server-side prefs. We render them with the same
  // SettingRow component used by Storage / Performance / etc.
  const settingsQ = useQuery({ queryKey: ["settings"], queryFn: api.listSettings });
  // Round-6 UX#4: re-ordered so the api_key sits right after provider —
  // BYOK providers (Anthropic / OpenAI) need the key BEFORE the /models
  // fetch can populate the endpoint + model dropdowns. The previous
  // order (endpoint → model → api_key) made first-run confusing
  // because the user had to leave the key blank and come back.
  const aiKeys = [
    "ai_enabled", "ai_provider", "ai_allow_nonlocal", "ai_api_key", "ai_endpoint", "ai_model",
    "ai_max_tokens", "ai_temperature", "ai_ping_interval_s",
  ];
  const aiSettings = (settingsQ.data ?? []).filter((s) => aiKeys.includes(s.key));
  aiSettings.sort((a, b) => aiKeys.indexOf(a.key) - aiKeys.indexOf(b.key));

  // Pull the configured endpoint so we know whether to even try fetching
  // the model list. Empty endpoint → don't poll (per user spec: "if no
  // endpoint set, do nothing").
  const endpointSetting = aiSettings.find((s) => s.key === "ai_endpoint");
  const endpointValue = endpointSetting?.value ? String(endpointSetting.value) : "";
  // The non-local toggle gates whether a cloud / LAN endpoint can be
  // reached at all. Include it in the model-fetch key so flipping it ON
  // immediately re-attempts the /models call against a cloud provider
  // (which the backend would otherwise reject while the toggle was off).
  const allowNonlocal = Boolean(aiSettings.find((s) => s.key === "ai_allow_nonlocal")?.value);

  // Fetch the available models when an endpoint is configured. Re-fetches
  // when the endpoint OR the non-local toggle changes. Silent on failure:
  // the backend returns an empty list rather than raising, so the UI just
  // falls back to the free-text input with no error.
  const modelsQ = useQuery({
    queryKey: ["ai-models", endpointValue, allowNonlocal],
    queryFn: aiApi.listModels,
    enabled: Boolean(endpointValue),
    staleTime: 60_000,  // models don't change minute-to-minute
    refetchOnWindowFocus: false,
  });
  const availableModels = modelsQ.data?.models ?? [];

  const onSave = async (key: string, value: unknown) => {
    try {
      await api.setSetting(key, value);
      qc.invalidateQueries({ queryKey: ["settings"] });
      // Saving the endpoint should re-trigger the model fetch — invalidate
      // explicitly so the new endpoint's models load right away rather
      // than waiting for the next staleTime expiry.
      if (key === "ai_endpoint" || key === "ai_api_key" || key === "ai_provider") {
        qc.invalidateQueries({ queryKey: ["ai-models"] });
      }
      toast.success("Saved");
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    }
  };

  // Test connection — calls /ai/probe.
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<AiProbeOut | null>(null);
  const onProbe = async () => {
    setProbing(true);
    setProbeResult(null);
    try {
      const result = await aiApi.probe();
      setProbeResult(result);
    } catch (e) {
      setProbeResult({ ok: false, error: (e as Error).message });
    } finally {
      setProbing(false);
    }
  };

  return (
    <Page
      title="✨ AI assistant"
      lede="Optional. Pluggable LLM provider for natural-language pipeline help. Default = local (Ollama on your machine, fully private). Bring-your-own-key for Anthropic / OpenAI / Groq / etc."
    >
      <Card>
        {settingsQ.isLoading ? (
          <PositiveLoaderInline variant="rendering" text="Loading settings…" size="sm" />
        ) : aiSettings.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            ⚠️ AI settings not found on the backend. Restart the backend after a recent upgrade.
          </p>
        ) : (
          <div className="space-y-2">
            {aiSettings.map((s) =>
              s.key === "ai_model" ? (
                <ModelPickerRow
                  key={s.key}
                  setting={s}
                  models={availableModels}
                  isFetchingModels={modelsQ.isFetching}
                  onSave={onSave}
                />
              ) : (
                <SettingRow key={s.key} setting={s} onSave={onSave} />
              ),
            )}
          </div>
        )}
      </Card>

      <Card>
        <Field
          label="Test connection"
          hint="Sends a tiny ping to the configured endpoint with the configured model. Use after changing the endpoint, the model, or pulling a new local model."
        >
          <div className="flex items-center gap-3">
            <Button onClick={onProbe} disabled={probing} variant="outline" size="sm">
              {probing ? "⏳ Probing…" : "🔌 Test connection"}
            </Button>
            {probeResult && (
              probeResult.ok ? (
                <span className="text-xs text-emerald-600 dark:text-emerald-400">
                  ✓ {probeResult.model ?? "model"} replied: <span className="font-mono">{probeResult.reply ?? "(empty)"}</span>
                </span>
              ) : (
                <span className="text-xs text-rose-600 dark:text-rose-400">
                  ✗ {probeResult.error ?? "Unknown error"}
                </span>
              )
            )}
          </div>
        </Field>
      </Card>

      <Card>
        <Field label="Quick start: local Ollama" hint="The recommended setup — runs on your machine, no cloud, no API key.">
          <ol className="text-xs text-muted-foreground space-y-1 list-decimal pl-4">
            <li>Install Ollama: <code className="text-foreground/80 font-mono bg-muted px-1 rounded">brew install ollama</code> (macOS) or <a className="underline" href="https://ollama.com/download" target="_blank" rel="noopener noreferrer">ollama.com/download</a></li>
            <li>Start the server: <code className="text-foreground/80 font-mono bg-muted px-1 rounded">ollama serve</code> (or just open the Ollama app)</li>
            <li>Pull a model: <code className="text-foreground/80 font-mono bg-muted px-1 rounded">ollama pull gemma3:4b</code> (~3&nbsp;GB, edge-optimized)</li>
            <li>Above: provider = <strong>local</strong>, endpoint stays at the default, model = <span className="font-mono">gemma3:4b</span>, enable, then Test connection</li>
          </ol>
        </Field>
      </Card>
    </Page>
  );
}

/**
 * Model picker — a real `<select>` populated from the endpoint's /models,
 * with a "Custom…" fallback that flips to a text input when the user
 * wants to type a model name not yet pulled locally (or when the
 * endpoint doesn't expose /models).
 *
 * Why a select (not a datalist text input): browsers heuristically treat
 * a text input adjacent to a type=password field as a username, then
 * offer password-manager autofill UI on it. A `<select>` is unambiguous
 * — no autofill, no inline suggestion strip, real keyboard semantics.
 */
function ModelPickerRow({
  setting, models, isFetchingModels, onSave,
}: {
  setting: SettingDescriptor;
  models: string[];
  isFetchingModels: boolean;
  onSave: (key: string, value: unknown) => void;
}) {
  const current = setting.value === null || setting.value === undefined ? "" : String(setting.value);
  const [draft, setDraft] = useState<string>(current);
  // Custom mode = user typed a model name not in the fetched list.
  // Auto-detect on first render: if the saved value isn't in models,
  // start in custom mode so the input is editable.
  const inList = !current || models.includes(current);
  const [customMode, setCustomMode] = useState<boolean>(!inList);
  const isDirty = draft !== current;

  // When models load AFTER the initial render and the saved value is
  // present in the fetched list, drop out of custom mode automatically.
  useEffect(() => {
    if (!isFetchingModels && current && models.includes(current) && customMode && draft === current) {
      setCustomMode(false);
    }
    // Only re-run when the inputs change — ignore draft so the user
    // toggling custom mode manually isn't reverted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [models, isFetchingModels, current]);

  return (
    <Field label={setting.label} hint={setting.help}>
      <div className="flex gap-2">
        {customMode ? (
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder={setting.default ? String(setting.default) : "model-id"}
            className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono"
            name="dig-ai-model"
            autoComplete="off"
            data-1p-ignore="true"
            data-lpignore="true"
            data-form-type="other"
          />
        ) : (
          <select
            value={draft}
            onChange={(e) => {
              if (e.target.value === "__custom__") {
                setCustomMode(true);
                setDraft("");
              } else {
                setDraft(e.target.value);
              }
            }}
            className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono"
            name="dig-ai-model"
            autoComplete="off"
          >
            {/* Allow blank as the explicit "use server default" choice. */}
            {!draft && <option value="">— pick a model —</option>}
            {/* If the saved value isn't in the fetched list (rare race),
                still show it so the user sees the truth. */}
            {draft && !models.includes(draft) && (
              <option value={draft}>{draft} (current)</option>
            )}
            {models.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
            <option value="__custom__">✏️ Custom… (type a model name)</option>
          </select>
        )}
        {customMode && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => { setCustomMode(false); setDraft(current); }}
            title="Cancel — return to dropdown"
          >
            ↩
          </Button>
        )}
        <Button
          size="sm"
          variant={isDirty ? "default" : "ghost"}
          disabled={!isDirty}
          onClick={() => onSave(setting.key, draft || null)}
        >
          Save
        </Button>
      </div>
      {/* Status line. */}
      {isFetchingModels ? (
        <p className="text-[10px] text-muted-foreground mt-1">⏳ Fetching available models from endpoint…</p>
      ) : models.length > 0 ? (
        <p className="text-[10px] text-muted-foreground mt-1">
          ↓ {models.length} model{models.length === 1 ? "" : "s"} found at endpoint
          {customMode && " — switch back to dropdown to pick from the list"}
        </p>
      ) : (
        <p className="text-[10px] text-muted-foreground mt-1">
          ⚠️ Endpoint didn&apos;t return a model list — type a model name manually.
        </p>
      )}
    </Field>
  );
}

// ---- Section: JDBC drivers -----------------------------------------------

function JdbcSection() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["jdbc-drivers"], queryFn: api.listJdbcDrivers });
  const [draft, setDraft] = useState<{
    id?: string; name: string; driverClass: string; jarPath: string;
    urlTemplate: string; notes: string;
    // "upload" = copy a JAR into DIG's managed library (recommended);
    // "reference" = point at an existing path on the server (advanced).
    jarMode: "upload" | "reference"; jarFile: File | null; managed: boolean;
  } | null>(null);
  // Inline connection-test state — kept on the same component as the draft
  // form so the test result lives next to the inputs that drove it. URL/
  // creds are intentionally NOT part of `draft` because they're ad-hoc
  // (only used to run the test), never persisted to the driver record.
  const [testOpen, setTestOpen] = useState(false);
  const [testInputs, setTestInputs] = useState({ url: "", username: "", password: "" });
  const [testResult, setTestResult] = useState<import("@/lib/api/client").JdbcTestResult | null>(null);
  const [testing, setTesting] = useState(false);

  // Reset test state when the user switches between drivers / opens the
  // form for a new entry; otherwise the green check from one driver
  // misleadingly carries over to the next.
  const resetTest = () => {
    setTestOpen(false);
    setTestInputs({ url: "", username: "", password: "" });
    setTestResult(null);
  };

  const empty = () => {
    resetTest();
    setDraft({
      name: "", driverClass: "", jarPath: "", urlTemplate: "", notes: "",
      jarMode: "upload", jarFile: null, managed: false,
    });
  };

  const runTest = async () => {
    if (!draft) return;
    setTesting(true);
    setTestResult(null);
    try {
      const out = await api.testJdbcDriver({
        driverClass: draft.driverClass.trim(),
        jarPath: draft.jarPath.trim(),
        url: testInputs.url.trim() || null,
        username: testInputs.username || null,
        password: testInputs.password || null,
      });
      setTestResult(out);
    } catch (e) {
      // testJdbcDriver only throws on network / 5xx — surface it the same
      // way as a failed test so the user has one place to look.
      setTestResult({ ok: false, message: (e as Error).message });
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    if (!draft) return;
    const name = draft.name.trim();
    const driverClass = draft.driverClass.trim();
    const urlTemplate = draft.urlTemplate.trim() || null;
    const notes = draft.notes.trim() || null;
    if (!name || !driverClass) {
      toast.error("Display name and driver class are required");
      return;
    }
    try {
      if (!draft.id) {
        // ── Create ──
        if (draft.jarMode === "upload") {
          if (!draft.jarFile) {
            toast.error("Choose a .jar file to upload (or switch to “Reference a path”)");
            return;
          }
          await api.uploadJdbcDriver(draft.jarFile, {
            name, driverClass,
            urlTemplate: urlTemplate ?? undefined, notes: notes ?? undefined,
          });
        } else {
          if (!draft.jarPath.trim()) { toast.error("Enter the JAR path to reference"); return; }
          await api.createJdbcDriver({ name, driverClass, jarPath: draft.jarPath.trim(), urlTemplate, notes });
        }
      } else {
        // ── Edit ── (metadata; managed keeps its library JAR, referenced
        // keeps/edits its path. Swapping a managed JAR = delete + re-upload.)
        await api.updateJdbcDriver(draft.id, {
          name, driverClass, jarPath: draft.jarPath.trim(), urlTemplate, notes,
        });
      }
      qc.invalidateQueries({ queryKey: ["jdbc-drivers"] });
      setDraft(null);
      toast.success("✅ Saved");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const remove = async (id: string) => {
    const ok = await confirmAction({
      title: "Delete this JDBC driver entry?",
      description: "Pipelines that reference it by name will need to be re-pointed.",
      confirmLabel: "Delete",
    });
    if (!ok) return;
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
        {q.isLoading && <PositiveLoaderInline variant="rendering" text="Loading…" size="sm" />}
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
                <p className="text-sm font-medium truncate flex items-center gap-1.5">
                  {d.name}
                  <span
                    className="text-[9px] uppercase tracking-wide px-1 py-px rounded border border-border text-muted-foreground"
                    title={d.managed ? "Uploaded into DIG's managed library" : "References a file path on the server"}
                  >
                    {d.managed ? "📦 library" : "🔗 path"}
                  </span>
                </p>
                <p className="text-[11px] font-mono text-muted-foreground truncate" title={d.driverClass}>{d.driverClass}</p>
                <p className="text-[10px] text-muted-foreground/80 truncate" title={d.jarPath}>
                  {d.managed ? "📦" : "🔗"} {d.jarPath}
                </p>
                {d.urlTemplate && (
                  <p className="text-[10px] font-mono text-muted-foreground/80 truncate" title={d.urlTemplate}>🔗 {d.urlTemplate}</p>
                )}
              </div>
              <div className="flex gap-1 shrink-0">
                <Button size="sm" variant="ghost" onClick={() => {
                  resetTest();
                  setDraft({
                    id: d.id, name: d.name, driverClass: d.driverClass,
                    jarPath: d.jarPath, urlTemplate: d.urlTemplate ?? "", notes: d.notes ?? "",
                    jarMode: d.managed ? "upload" : "reference", jarFile: null, managed: !!d.managed,
                  });
                }}>Edit</Button>
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
            {/* ── Driver JAR ──────────────────────────────────────────
                Primary (recommended): upload the JAR into DIG's managed
                library so it travels with DIG's state. Advanced: reference
                an existing path on the server (no copy). Editing a managed
                driver shows the library file read-only (swap = delete +
                re-upload). */}
            {draft.id && draft.managed ? (
              <Field label="Driver JAR" hint="Stored in DIG's managed library. To replace it, delete this driver and upload a new JAR.">
                <div className="flex items-center gap-2 text-sm rounded-md border border-input bg-muted/40 px-3 py-2">
                  <span aria-hidden>📦</span>
                  <span className="font-mono truncate" title={draft.jarPath}>
                    {draft.jarPath.split("/").pop()}
                  </span>
                  <span className="ml-auto text-[10px] uppercase tracking-wide text-muted-foreground">in library</span>
                </div>
              </Field>
            ) : !draft.id ? (
              <Field label="Driver JAR" hint="Upload copies the JAR into DIG's managed library (recommended — it travels with backups + moves). Reference points at a path already on the server.">
                <div className="space-y-2">
                  {/* mode toggle */}
                  <div className="inline-flex rounded-md border border-input overflow-hidden text-xs">
                    {(["upload", "reference"] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setDraft({ ...draft, jarMode: m })}
                        className={[
                          "px-3 py-1.5 transition-colors",
                          draft.jarMode === m
                            ? "bg-emerald-500/15 text-foreground font-medium"
                            : "text-muted-foreground hover:bg-muted/50",
                        ].join(" ")}
                      >
                        {m === "upload" ? "📦 Upload a JAR" : "🔗 Reference a path"}
                      </button>
                    ))}
                  </div>
                  {draft.jarMode === "upload" ? (
                    <div className="flex items-center gap-3">
                      <label className={buttonVariants({ variant: "outline", size: "sm" }) + " cursor-pointer"}>
                        📁 Choose .jar…
                        <input
                          type="file"
                          accept=".jar,application/java-archive"
                          className="hidden"
                          onChange={(e) => {
                            const f = e.target.files?.[0] ?? null;
                            // Auto-fill the display name from the filename if blank.
                            setDraft({
                              ...draft, jarFile: f,
                              name: draft.name || (f ? f.name.replace(/\.jar$/i, "") : ""),
                            });
                          }}
                        />
                      </label>
                      <span className="text-xs text-muted-foreground truncate">
                        {draft.jarFile ? `📦 ${draft.jarFile.name} (${(draft.jarFile.size / 1024 / 1024).toFixed(1)} MB)` : "No file chosen"}
                      </span>
                    </div>
                  ) : (
                    <PathPickerField
                      value={draft.jarPath}
                      onChange={(v) => setDraft({ ...draft, jarPath: v })}
                      mode="file"
                      extensions={[".jar"]}
                      forLabel="JDBC driver JAR"
                      placeholder="/Users/me/dig-drivers/ojdbc11.jar"
                    />
                  )}
                </div>
              </Field>
            ) : (
              <Field label="JAR path" hint="The referenced .jar on the DIG server. Browse opens at the folder of the current path, or your home directory if blank.">
                <PathPickerField
                  value={draft.jarPath}
                  onChange={(v) => setDraft({ ...draft, jarPath: v })}
                  mode="file"
                  extensions={[".jar"]}
                  forLabel="JDBC driver JAR"
                  placeholder="/Users/me/dig-drivers/ojdbc11.jar"
                />
              </Field>
            )}
            <Input label="URL template (optional)" placeholder="jdbc:oracle:thin:@//<host>:1521/<service>" mono
                   value={draft.urlTemplate} onChange={(v) => setDraft({ ...draft, urlTemplate: v })} />
            <Input label="Notes (optional)" placeholder="Compatible with our 12c + 19c instances"
                   value={draft.notes} onChange={(v) => setDraft({ ...draft, notes: v })} />
            {/* ── 🔌 Test connection ─────────────────────────────────
                Lets the user verify the driver class + JAR path work
                BEFORE saving (and BEFORE attempting a real ingest at
                pipeline time, which is where bad creds normally surface
                with a much noisier error). The URL + credentials live on
                this collapsible panel only — they're not part of the
                saved driver record because they tend to vary per
                environment / per dataset.

                A brand-new *uploaded* driver has no on-disk path until it's
                saved, so Test connection waits until then (save → Edit →
                Test). Referenced drivers + saved drivers can test
                immediately. */}
            {!draft.jarPath.trim() ? (
              <div className="border-t border-emerald-300/30 pt-3">
                <p className="text-[11px] text-muted-foreground">
                  🔌 Save the driver first, then re-open it to <strong>Test connection</strong> — the uploaded JAR needs to land in the library before it can be loaded.
                </p>
              </div>
            ) : (
            <div className="border-t border-emerald-300/30 pt-3">
              <button
                type="button"
                onClick={() => setTestOpen((v) => !v)}
                aria-expanded={testOpen}
                className="text-xs font-medium text-foreground/80 hover:text-foreground flex items-center gap-1.5"
              >
                <span>🔌 Test connection</span>
                <span className="text-muted-foreground" aria-hidden>{testOpen ? "▴" : "▾"}</span>
                {testResult && (
                  <span className={[
                    "ml-2 text-[11px] tabular-nums",
                    testResult.ok ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400",
                  ].join(" ")}>
                    {testResult.ok ? "✓" : "✗"} {testResult.ok && testResult.latencyMs != null ? `${testResult.latencyMs}ms` : ""}
                  </span>
                )}
              </button>
              {testOpen && (
                <div className="mt-2 space-y-2">
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    The URL + credentials here are <strong>used only for this test</strong> — they aren't saved to the driver record. Pipelines that use this driver supply their own URL and creds at ingest time.
                  </p>
                  <Input
                    label="JDBC URL"
                    placeholder={draft.urlTemplate || "jdbc:postgresql://host:5432/dbname"}
                    mono
                    value={testInputs.url}
                    onChange={(v) => { setTestInputs({ ...testInputs, url: v }); setTestResult(null); }}
                  />
                  <Input
                    label="Username (optional)"
                    placeholder="dig"
                    value={testInputs.username}
                    onChange={(v) => { setTestInputs({ ...testInputs, username: v }); setTestResult(null); }}
                  />
                  <PasswordInput
                    label="Password (optional)"
                    value={testInputs.password}
                    onChange={(v) => { setTestInputs({ ...testInputs, password: v }); setTestResult(null); }}
                  />
                  <div className="flex gap-2 items-center">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={runTest}
                      disabled={
                        testing ||
                        !draft.driverClass.trim() ||
                        !draft.jarPath.trim()
                      }
                    >
                      {testing ? "⏳ Testing…" : "🔌 Run test"}
                    </Button>
                    {testing && (
                      <span className="text-[11px] text-muted-foreground">
                        Up to 15s timeout
                      </span>
                    )}
                  </div>
                  {testResult && (
                    <div
                      className={[
                        "rounded-md border p-2.5 text-xs space-y-0.5",
                        testResult.ok
                          ? "border-emerald-300/60 bg-emerald-50/60 text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-100"
                          : "border-rose-300/60 bg-rose-50/60 text-rose-900 dark:border-rose-700 dark:bg-rose-950/40 dark:text-rose-100",
                      ].join(" ")}
                    >
                      <p className="font-medium">
                        {testResult.ok ? "✅ " : "❌ "}{testResult.message}
                      </p>
                      {testResult.serverInfo && (
                        <p className="text-[11px] opacity-80 font-mono">
                          {testResult.serverInfo}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
            )}
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={save}
                disabled={
                  !draft.name.trim() || !draft.driverClass.trim() ||
                  // Upload mode needs a chosen file; every other mode needs a path.
                  (draft.jarMode === "upload" && !draft.id ? !draft.jarFile : !draft.jarPath.trim())
                }>
                💾 Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => { setDraft(null); resetTest(); }}>Cancel</Button>
            </div>
          </div>
        )}
      </Card>
    </Page>
  );
}

/** Password input with a show/hide toggle. Uses the same Field wrapper as
 *  the rest of the settings form so the label column / input column line
 *  up across rows. */
function PasswordInput({ label, value, onChange }: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const [show, setShow] = useState(false);
  const inputId = `pwd-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <Field label={label} htmlFor={inputId}>
      <div className="flex items-stretch rounded-md border border-input focus-within:ring-2 focus-within:ring-ring/40 overflow-hidden">
        <input
          id={inputId}
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete="off"
          className="flex-1 bg-background px-2 py-1 text-sm font-mono outline-none"
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          aria-label={show ? "Hide password" : "Show password"}
          className="px-2 text-xs text-muted-foreground hover:text-foreground border-l border-input"
        >
          {show ? "🙈" : "👁"}
        </button>
      </div>
    </Field>
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
    const ok = await confirmAction({
      title: "Delete this webhook?",
      description: "It will no longer fire for any future runs.",
      confirmLabel: "Delete",
    });
    if (!ok) return;
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
        {q.isLoading && <PositiveLoaderInline variant="rendering" text="Loading…" size="sm" />}
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
                <option value="triggered">Triggered (only from inside a pipeline)</option>
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
  const apiBaseRendered = useApiBase();
  return (
    <Page title="🔐 Security & API"
      lede="Bind host, port, and auth token are start-time settings — DIG re-reads them only on restart, so they're shown read-only here.">
      <Card>
        <Field label="API endpoint" hint="The address this UI talks to.">
          <code
            className="text-xs bg-muted px-2 py-1 rounded font-mono"
            suppressHydrationWarning
          >
            {apiBaseRendered}
          </code>
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
  const apiBaseRendered = useApiBase();
  // Round-9 fix: navigate via Next router instead of `window.location.href`
  // so unsaved settings drafts on other sections aren't blown away by a
  // full page reload.
  const router = useRouter();

  return (
    <Page title="ℹ️ About this install" lede="DataInsightGrove™ — self-hosted data preparation.">
      <Card>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <Stat label="Product" value="DataInsightGrove™ · DIG™" />
          <Stat label="Backend" value={health.data ? `${health.data.name} v${fmtVersion(health.data.version)} ✅` : "…"} />
          <Stat label="API endpoint" value={apiBaseRendered} mono />
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
          <a href={`${apiBaseRendered}/docs`} target="_blank" rel="noreferrer"
             className={buttonVariants({ variant: "outline", size: "sm" })}
             suppressHydrationWarning>
            📡 Open Swagger UI
          </a>
          <a href={`${apiBaseRendered}/openapi.json`} target="_blank" rel="noreferrer"
             className={buttonVariants({ variant: "ghost", size: "sm" })}
             suppressHydrationWarning>
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
        <Field label="Replay onboarding" hint="Resets the home page tour, the editor tour, and the column-menu first-time tooltip.">
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              try {
                // Round-3 operational finding: previously this reset only
                // the home + column-chevron tours, missing dig.tour.editor.v1.
                // Operators clicking "Reset onboarding" expected EVERY
                // first-run hint to reappear; the editor tour silently stayed
                // marked done.
                localStorage.removeItem("dig.tour.home");
                localStorage.removeItem("dig.tour.column_chevron");
                localStorage.removeItem("dig.tour.editor.v1");
              } catch {/* ignore */}
              toast.success("Onboarding reset — opening home");
              router.push("/");
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

function Field({ label, hint, htmlFor, children }: { label: string; hint?: string; htmlFor?: string; children: React.ReactNode }) {
  // When `htmlFor` is supplied, render the label as a real <label> bound to
  // the single control it wraps — clicking the label focuses the control and
  // screen readers announce the pairing. Fields that wrap a toggle / button /
  // multi-control block omit `htmlFor` and keep the plain <p> (there's no one
  // control to associate, and <label> around several would be ambiguous).
  return (
    <div className="grid grid-cols-1 sm:grid-cols-[1fr_2fr] gap-3 items-start">
      <div>
        {htmlFor ? (
          <label htmlFor={htmlFor} className="text-sm font-medium cursor-pointer">{label}</label>
        ) : (
          <p className="text-sm font-medium">{label}</p>
        )}
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
