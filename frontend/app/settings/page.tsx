"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
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
import { api, aiApi, API_BASE } from "@/lib/api/client";
import type { SettingDescriptor, JdbcDriverRecord, GlobalWebhookRecord, AiProbeOut } from "@/lib/api/client";
import { buttonVariants, Button } from "@/components/ui/button";
import { DirectoryPickerModal } from "@/components/directory-picker-modal";
import { fmtInt } from "@/lib/format-number";

const THEMES: { id: Theme; emoji: string; label: string }[] = [
  { id: "system", emoji: "🖥️", label: "System" },
  { id: "light",  emoji: "☀️", label: "Light" },
  { id: "dark",   emoji: "🌙", label: "Dark" },
];

const SAMPLE_OPTIONS = [10_000, 50_000, 100_000, 500_000, 1_000_000];

type SectionId =
  | "appearance" | "expertise" | "preview" | "storage" | "performance"
  | "ai" | "jdbc" | "webhooks" | "security" | "about";

const NAV: { id: SectionId; emoji: string; label: string; help: string }[] = [
  { id: "appearance",  emoji: "🎨", label: "Appearance",       help: "Theme + motion (per browser)" },
  { id: "expertise",   emoji: "🌱", label: "Expertise mode",   help: "Beginner / Builder / Engineer" },
  { id: "preview",     emoji: "🦆", label: "Browser preview",  help: "DuckDB-WASM behavior" },
  { id: "storage",     emoji: "📁", label: "Storage & paths",  help: "Where data lives" },
  { id: "performance", emoji: "⚡", label: "Performance",      help: "Concurrency + threads" },
  { id: "ai",          emoji: "✨", label: "AI assistant",     help: "Local Ollama or BYOK provider" },
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
        {section === "expertise"   && <ExpertiseSection />}
        {section === "preview"     && <PreviewSection />}
        {section === "storage"     && <ServerSettingsSection filter={["input_dir", "output_dir", "run_history_days"]} title="📁 Storage & paths" />}
        {section === "performance" && <ServerSettingsSection filter={["default_sample_rows", "default_preview_limit", "max_concurrent_runs", "duckdb_threads", "log_level", "auto_detect_index", "auto_detect_timezone"]} title="⚡ Performance & detection" />}
        {section === "ai"          && <AiSection />}
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
    <Field label={setting.label} hint={setting.help}>
      <div className="flex gap-2">
        <input
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
  const aiKeys = [
    "ai_enabled", "ai_provider", "ai_endpoint", "ai_model",
    "ai_api_key", "ai_max_tokens", "ai_temperature",
  ];
  const aiSettings = (settingsQ.data ?? []).filter((s) => aiKeys.includes(s.key));
  aiSettings.sort((a, b) => aiKeys.indexOf(a.key) - aiKeys.indexOf(b.key));

  // Pull the configured endpoint so we know whether to even try fetching
  // the model list. Empty endpoint → don't poll (per user spec: "if no
  // endpoint set, do nothing").
  const endpointSetting = aiSettings.find((s) => s.key === "ai_endpoint");
  const endpointValue = endpointSetting?.value ? String(endpointSetting.value) : "";

  // Fetch the available models when an endpoint is configured. Re-fetches
  // when the endpoint changes (settings query is invalidated on every
  // save → the queryKey below picks up the new endpointValue). Silent on
  // failure: the backend returns an empty list rather than raising, so
  // the UI just falls back to the free-text input with no error.
  const modelsQ = useQuery({
    queryKey: ["ai-models", endpointValue],
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
          <p className="text-xs text-muted-foreground">Loading…</p>
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
            <li>Pull a model: <code className="text-foreground/80 font-mono bg-muted px-1 rounded">ollama pull gemma4:e4b</code> (~7&nbsp;GB, 128K context, edge-optimized)</li>
            <li>Above: provider = <strong>local</strong>, endpoint stays at the default, model = <span className="font-mono">gemma4:e4b</span>, enable, then Test connection</li>
          </ol>
        </Field>
      </Card>
    </Page>
  );
}

/**
 * Custom row for the ai_model setting — text input + datalist of models
 * fetched from the configured endpoint's /v1/models. The datalist works
 * exactly like a normal text input: user can type anything (including
 * model names not yet pulled locally), but autocomplete suggests known
 * options. When no models are returned (endpoint unreachable, blank,
 * or doesn't support /models), we silently fall back to plain text input.
 */
function ModelPickerRow({
  setting, models, isFetchingModels, onSave,
}: {
  setting: SettingDescriptor;
  models: string[];
  isFetchingModels: boolean;
  onSave: (key: string, value: unknown) => void;
}) {
  const [draft, setDraft] = useState<string>(
    setting.value === null || setting.value === undefined ? "" : String(setting.value),
  );
  const isDirty = draft !== (setting.value === null || setting.value === undefined ? "" : String(setting.value));
  const datalistId = `${setting.key}-models`;

  return (
    <Field label={setting.label} hint={setting.help}>
      <div className="flex gap-2">
        <input
          type="text"
          list={datalistId}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={setting.default ? String(setting.default) : "Default"}
          className="flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm font-mono"
          // Suppress browser password-manager autofill on this field. Firefox
          // heuristically offers password-manager UI on text inputs that
          // sit next to a type=password field (the API key below); the
          // attributes below tell every major manager (Firefox built-in,
          // 1Password, LastPass, Bitwarden) to leave this one alone.
          name="dig-ai-model"
          autoComplete="off"
          data-1p-ignore="true"
          data-lpignore="true"
          data-form-type="other"
        />
        {/* HTML5 datalist — browser shows the suggestions on focus / type.
            When the array is empty (endpoint silent or unreachable) the
            input behaves exactly like a plain text input, no extra UI. */}
        <datalist id={datalistId}>
          {models.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        <Button
          size="sm"
          variant={isDirty ? "default" : "ghost"}
          disabled={!isDirty}
          onClick={() => onSave(setting.key, draft || null)}
        >
          Save
        </Button>
      </div>
      {/* Status line: shows what we found, lets the user understand
          why the dropdown might be empty. */}
      {isFetchingModels ? (
        <p className="text-[10px] text-muted-foreground mt-1">⏳ Fetching available models from endpoint…</p>
      ) : models.length > 0 ? (
        <p className="text-[10px] text-muted-foreground mt-1">
          ↓ {models.length} model{models.length === 1 ? "" : "s"} available at endpoint — type to filter, or pick from the dropdown
        </p>
      ) : null}
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
