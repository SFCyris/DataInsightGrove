# UI guidelines — how DIG looks and behaves

This page is the design contract: the conventions every screen, dialog, and animation in DIG follows so the product feels like one tool instead of a patchwork of components. Read this if you're contributing UI changes, building a plugin whose label appears in the step library, or just curious why DIG uses so many emoji.

The TL;DR: **emojis as icons, motion to confirm causality, dark mode as a first-class citizen, friendly without being cute**. The rest of this doc explains each of those.

---

## Emojis as graphical elements

DIG uses **emoji as iconography** throughout the UI. They're cheap, universally rendered, accessible (via the underlying Unicode names), and let the product feel friendly without committing to a custom icon set. Use them in:

- **Step library labels.** Every step manifest's `label` should start with a category-appropriate emoji, e.g. `🔍 Filter rows`, `🔗 Join`, `🧮 Aggregate`.
- **Section headers** in panels.
- **Empty states.** A large emoji (3-5em) carries the empty state instead of stock illustration.
- **Status indicators.** ✅ success, ❌ error, ⏳ running, ⏸️ paused, 🟡 warning.
- **Visual brand element.** 🌳 (the generic Unicode tree, U+1F333) appears throughout the UI as decorative shorthand for "the Grove" — it is *not* a trademarked logo. We use it because it reads as a tree on every platform without us shipping artwork; the actual word marks are *DataInsightGrove* and *DIG*.
- **Profile cards.** 📊 numeric, 📅 dates, 🅰️ strings, ☑️ booleans, 🧱 nested.

## Category emoji conventions

| Category | Emoji | Used in |
|---|---|---|
| `ingest` | 📥 | step labels, palette grouping |
| `shape` | ✂️ | step labels |
| `clean` | 🧹 | step labels |
| `derive` | ➕ | step labels |
| `combine` | 🔗 | step labels |
| `aggregate` | 📊 | step labels |
| `output` | 📤 | step labels, sink picker |
| `custom` | 🧩 | user plugins |

## When NOT to use emoji

- **Inside data values.** Never auto-decorate user data with emoji — only chrome.
- **In file paths or identifiers.** Stays ASCII-safe.
- **In code identifiers.** Variable names, function names, and step `id` fields are snake_case ASCII.
- **In API schemas.** OpenAPI strings stay plain.

## Accessibility

Emojis carry their Unicode name as accessible label by default. When using an emoji as a sole graphical element (e.g. a status icon), wrap it with an explicit `aria-label`:

```tsx
<span role="img" aria-label="Success">✅</span>
```

For decorative emoji that accompanies text (e.g. `🔍 Filter rows`), no extra label is needed — the text is the label.

## Tone

Friendly without being cute. One emoji per element. No emoji-as-text-padding. No skin-tone variations on people emoji (use neutral metaphor emoji instead).

---

## Motion and animation

DIG aims for **modern, animated, fluid** UI throughout. Motion is meaningful, not decorative — it confirms causality (this caused that), maintains spatial continuity (this came from there), and makes feedback instant (the system noticed your input).

### Library

- **`motion`** (the modern Framer Motion) for component-level animations. Imported from `motion/react`.
- **`tw-animate-css`** (already installed by shadcn) for utility-class animations.
- **View Transitions API** for native cross-route transitions where the browser supports it.
- **`sonner`** (shadcn-integrated) for toasts.
- **`cmdk`** (shadcn-integrated) for the command palette.

### Principles

1. **Spring physics over linear easing.** Default to `motion`'s spring with `stiffness: 300, damping: 30` for UI; tighter for small affordances, looser for layout.
2. **Stagger lists** by ~30-50ms per item.
3. **Crossfade route changes**, never blank.
4. **Fade + slight slide** (4-8px) for panel mounts, ≤200ms.
5. **`prefers-reduced-motion: reduce`** is respected — wrap motion behind `useReducedMotion()` and degrade to opacity-only or no animation.
6. **Optimistic UI**: mutations update local cache before server confirms; rollback on error. Use TanStack Query's `optimisticUpdate`.
7. **Skeletons over spinners** for loading.
8. **Focus rings always visible** on keyboard focus; never `outline: none` without a replacement.
9. **Hover states subtle** — 1-2% scale, 0.5-1px lift, color shift. Never bouncy.
10. **Number transitions** — animate count changes (e.g. "10,234 rows → 7,891 rows" after a filter) using `NumberFlow` or a small motion-driven counter.

### Required interactions

- `cmd+k` opens the command palette from anywhere.
- `?` opens the keyboard shortcut cheatsheet overlay.
- `esc` closes any open overlay/dialog/menu.
- Every primary action has a visible keyboard shortcut hint (`⌘K`, `⌘⇧P`, etc.) in tooltips and menu items.

### Density and theme

- **Cozy** density by default; allow a "compact" toggle in settings later.
- **Dark mode is first-class** — every component must work in both. shadcn theming via CSS variables.
- **Color**: shadcn neutral palette + a single brand accent. No rainbow.
- **Typography**: Geist (already loaded). Use `tabular-nums` on numeric grids.

### When in doubt

If shipping a placeholder, label it as such in the UI itself ("placeholder — wire up later") rather than leaving a screen visually unfinished. Polish first — DIG isn't allowed to look unfinished even when it's incomplete.

---

## Transparent frontend/backend processing

**The user does not care where computation runs.** They click, edit, or
focus a step — they expect the right outcome to appear. Whether it
computed in DuckDB-WASM, in the backend, in a sub-pipeline expansion,
or via a fallback chain is an implementation detail that **must stay
invisible**.

Many tools fail this principle by leaking architecture into the UI:
"Run on backend", "Switch to server mode", "Live preview not
available". Each of those is a small failure of design — the tool
admitting its limitations and pushing the work onto the user. DIG
must not do this.

**Rules**:

1. **Never expose the WASM/backend choice as a routine UI state.**
   No "DuckDB-WASM can't run this", no "click Run on backend to see
   it" as a default surface. The dispatcher routes silently.
2. **Never block on a fallback button.** If the in-browser path
   fails, the frontend's dispatcher transparently calls the backend
   path and streams the result into the same surface (grid, chart,
   etc.). The user sees the outcome, not the routing.
3. **Architectural restrictions are bugs to engineer around, not
   labels to hang in the UI.** Polars-only steps fed by Polars-only
   steps need a recursive ancestor materializer; that's an
   engineering job, not a UX excuse.
4. **The only time it's OK to surface "ran on backend"** is as a
   tiny, dismissible badge (`🌐 via backend` chip on the live grid
   status row) for users who want to know — never as a CTA, never as
   an error.
5. **For genuinely-broken states** (bad params, missing source,
   syntax error) the warning UI is correct. But "this needs polars"
   / "this is a chart step" / "this depends on an upstream polars
   step" are NOT broken states — they're routine routing decisions.

This applies across every layer: editor preview, run executor, schema
inference, lineage, sub-pipeline composition. **If the system can
produce the answer, it should — without asking.**

The current dispatcher (`frontend/lib/engine/dispatcher.ts`) implements
this with a multi-tier fallback:

```
previewPipeline()
  ├─ chart-first step (export_to_image / forecast / seasonal_decompose)
  │   └→ /preview-step (image)        — backend pre-materializes Polars
  │                                      ancestors then renders the chart
  │
  ├─ WASM compile fails (browser engine 'polars' or 'none')
  │   ├─ visualize-category? → falls through to image-fallback
  │   └─ otherwise → /preview-step-rows (rows fallback, transparent)
  │
  ├─ SQL touches spatial extension
  │   └→ /preview (backend DuckDB with spatial loaded)
  │
  └─ default → DuckDB-WASM in browser
```

Whichever branch wins, the result lands in the same `<LiveGrid>` (or
`<StepImagePreview>` for charts) and the user is none the wiser.

## Loading states — `<PositiveLoader>` and the six principles

**Every in-progress state in DIG must use the shared
`<PositiveLoader>` component** (`frontend/components/positive-loader.tsx`).
Don't roll your own spinner; extend the shared component if you need
a new variant.

The component encodes six UX-perception principles, each load-bearing:

| Principle | Implementation |
|---|---|
| **No error language** | No ⚠️, no red/yellow. Stays warm — emerald shimmer, neutral text. In-progress is not failure. |
| **Animated focal point** | Rotating emoji every 700ms with spring-pop. Movement gives the eye something to track before text registers. |
| **RAIL latency staircase** | Doherty (~400ms) instant feel · Response (~2s) tip appears · Patience (~8s) longer recovery tip. Never silent for long. |
| **Indeterminate over false-progress** | Shimmer bar (1.6s loop) avoids lying about completion %. Only show determinate progress when there's a true bounded count. |
| **Elapsed timer** | Numbers help patience — "5s elapsed" feels finite vs unbounded silence. Kicks in after 1s, tabular-nums for stable width. |
| **Reduced motion respected** | OS or settings opt-out → static icon + text, no rotations, no shimmer. |

References: Don Norman's *The Design of Everyday Things* on system
feedback; Steven Hoober's *Designing Mobile Interfaces* on progress
affordances; Nielsen Norman Group's RAIL guidance on latency thresholds.

### Three preset variants

| Variant | Emoji | Default text | Use case |
|---|---|---|---|
| `computing` | 🔬 🧮 ✨ | Computing… | LLM calls, chart rendering |
| `rendering` | 🔎 ⚙ ✨ | Loading data… | Data fetches, page loads, lineage |
| `compiling` | 🛠 🔌 ⚙ | Compiling… | DAG/SQL compilation |

Three sizes: `sm` (badges, tight panels), `md` (default), `lg` (dialog
hero). Plus `<PositiveLoaderInline>` for compact single-line indicators.

### Where the shared loader is used today

- Page-level "Loading pipeline…" (`app/pipelines/[id]/page.tsx`)
- Chart-first focused step (`components/canvas/step-image-preview.tsx`)
- Live-grid empty state + recomputing badge (`components/grid/live-grid.tsx`)
- Dataset-grid initial mount (`components/grid/dataset-grid.tsx`)
- SQL view dialog (`components/canvas/sql-view.tsx`)
- AI explain pipeline drawer (`components/canvas/explain-pipeline.tsx`)
- Lineage drawer (`components/canvas/lineage-drawer.tsx`)

### When to deviate

Never. If you think a new loading state needs different framing,
extend the shared component (add a new variant or accept a `primary`
override) rather than rolling a one-off. The visual consistency is
itself a UX principle — users learn "rotating emoji + shimmer =
working" once and recognize it everywhere.

## Established patterns (v0.6.x)

### Back / home navigation — top-LEFT, always

Every top-level page has a back-or-home affordance in the **upper-left corner** of the page header. Same convention as macOS apps' window-level back button, browsers' back arrow, and the pipeline editor's `←` back button. Don't hide it in the bottom of a sidebar (settings used to do this — fixed) or stuff it on the right (datasets, pipelines, gallery used to do this — fixed).

Implementation: a tiny `<BackHome>` shared component lives at [`frontend/components/back-home.tsx`](../frontend/components/back-home.tsx). Pages with their own custom header (pipeline editor, datasets/[id]) embed `← Datasets` / `← Pipelines` in the same upper-left position.

### Bottom region — always reserved, glued to viewport

The pipeline editor's bottom region (🛤 Strip or 🕸 Graph view) is **pinned to the bottom of the browser viewport**, never pushed off-screen by tall data grids. The data grid above scrolls internally; the strip / graph stays visible.

- **Strip** has a deterministic 58px height — no resize handle, hard-set.
- **Graph** uses the persisted `graphHeight` (default 300px, range 120-700) with a 4px drag-resize handle above it. The handle is invisible until hover, cursor-row-resize, then shows a small `⋯` glyph centered.

Implementation: the editor's `<main>` uses `h-screen overflow-hidden` so `flex-col` children stay capped at the viewport. The bottom region uses `style={{ height: graphHeight }}` only when in graph view; strip view falls back to auto + `min-h-[40px]` so empty pipelines still reserve space.

### Step-source row tints in the picker

Three distinct tints distinguish where a step came from:

| Source | Row tint | Hover tooltip |
|---|---|---|
| Built-in | (no tint, neutral hover) | Step description |
| Pack step (`source: "pack:<id>"`) | Faint **violet** background | `<label> · 📦 <pack_id> — <description>` |
| Pipeline step (`source: "pipeline:<id>"`) | Faint **emerald** background | `<label> · 🪆 composite from another pipeline — <description>` |

Greyed (requirements unmet) state is opacity-based, not color-based, so it stacks correctly with any tint.

### Floating param-row toggles

The 🪆 **expose** pill in the param-form's label row is the model for "small toggle that lives next to the field it modifies, not in a separate panel." Two states:

- Default — neutral border, "🪆 expose" label
- Active — violet background + border, alias label ("🪆 filterExpr")

Click toggles between them. Don't add a separate "expose params" management page — the toggles are already in the right place.

### Status badges that double as actions

The sub-pipeline pin badge (`🪆 Sub-pipeline · pinned to v2`) shows status info AND houses the upgrade button when relevant. One component, three states (up-to-date / behind / unavailable). Avoids the trap of "info panel + separate action panel" duplication.

### Long-duration toasts for blocked actions

Cycle-detection errors get a **12-second toast** (vs the standard 4s) because the message includes a chain like `parent → dep → … → parent` that takes a moment to read + parse. Save-failure toasts that the user must address get the long duration. Routine confirmations stay short.

---

## SSR + hydration safety — the rules

DIG runs the same React tree two places: **on the server (Node)** during SSR, and **in your browser** when the page hydrates. They have to produce byte-identical HTML on first render or React throws a "hydration mismatch" warning and re-renders the entire subtree on the client (visible flicker, wasted CPU, the user briefly seeing wrong text). On Mac the WKWebView surfaces these as red error overlays.

There are exactly four ways code can produce different output on server vs first client render. **Memorize them.**

### The four traps

| Trap | What goes wrong | Where it can sneak in |
|---|---|---|
| **`window` / `document` / `localStorage` / `navigator` in render** | Server: `window` is `undefined`. Client: it exists. Anything reading it during render is `undefined` on server and a real value on client. | `<span>{window.location.port}</span>`, `useState(localStorage.getItem(...))`, `useState(window.matchMedia(...).matches)` |
| **`Date.now()` / `Math.random()` / `new Date()` in render** | Server and client run at different moments → different values. | `<span>{Date.now()}</span>`, ids generated inline, "X seconds ago" formatters that read `Date.now()` synchronously |
| **`.toLocaleString()` without an explicit locale** | Server defaults to Node's locale (usually `en-US`); client uses the user's browser locale. Result: `"1,234"` vs `"1.234"` vs `"1 234"`. Mismatch on every numeric cell. | `{n.toLocaleString()}`, `n.toLocaleString(undefined, {...})` (the `undefined` is the trap — it means "user's locale") |
| **Browser-extension or wrapper-injected attributes on `<html>` or `<body>`** | The wrapper sets attributes after the server-rendered HTML lands, before React hydrates. The DOM React inherits no longer matches what it rendered. | Mac wrapper injects `data-dig-mac="true"`. Some extensions add `bis_register`, `data-darkreader`, etc. |

### The four fixes

For each trap, exactly one fix is correct. Use it.

#### Trap 1 — runtime values from `window` / `document`

```tsx
// ❌ Broken
const port = typeof window !== "undefined" ? window.location.port : "?";
return <span>:{port}</span>;
// Server renders ":?"; client renders ":3100". Mismatch on hydrate.

// ✅ Correct
const [port, setPort] = useState<string>("…");   // server-safe placeholder
useEffect(() => {
  setPort(window.location.port || "80");
}, []);
return <span>:{port}</span>;
// Server: ":…". First client render: ":…" (same as server, hydration agrees).
// One tick later: useEffect runs, span becomes ":3100".
```

#### Trap 2 — time / randomness in render

```tsx
// ❌ Broken
return <span>updated {Math.round((Date.now() - run.startedMs) / 1000)}s ago</span>;

// ✅ Correct — clock state in a useEffect
const [now, setNow] = useState(0);             // 0 means "pre-mount"
useEffect(() => {
  setNow(Date.now());
  const t = setInterval(() => setNow(Date.now()), 30_000);
  return () => clearInterval(t);
}, []);
return <span>updated {now === 0 ? "…" : Math.round((now - run.startedMs) / 1000) + "s"} ago</span>;
```

See [`components/canvas/run-history.tsx`](../frontend/components/canvas/run-history.tsx) for the canonical implementation (`useNowMs`).

#### Trap 3 — locale-dependent number formatting

**Use the locale-pinned helpers — never `.toLocaleString()` without an explicit locale.**

```tsx
import { fmtInt, fmtFloat } from "@/lib/format-number";

// ❌ Broken
{rowCount.toLocaleString()}                     // user's locale
{(value).toLocaleString(undefined, {...})}       // explicit "use user's locale" — same trap

// ✅ Correct
{fmtInt(rowCount)}                               // pinned to en-US
{fmtFloat(value)}                                // pinned to en-US, 2dp
```

If you need a non-en-US locale for display, build the formatter inside a `useEffect`-backed state:

```tsx
const [fmt, setFmt] = useState<Intl.NumberFormat>(() => new Intl.NumberFormat("en-US"));
useEffect(() => {
  setFmt(new Intl.NumberFormat(navigator.language));
}, []);
```

#### Trap 4 — wrapper / extension attributes

When a wrapper script (the Mac `.app`'s WKUserScript injects `data-dig-mac="true"` on `<html>`) or a browser extension sets attributes on `<html>` or `<body>` before React hydrates, React's hydration check would scream. The fix is **`suppressHydrationWarning` scoped to that one element only**:

```tsx
<html lang="en" suppressHydrationWarning>
  ...
</html>
```

`suppressHydrationWarning` is React's official, documented escape hatch for "I know this attribute legitimately differs, and the difference is intentional." It does **not** propagate to children — anything inside `<body>` or any component still gets a full hydration check, so genuine bugs aren't masked.

### When in doubt

- If the value is **constant from the bundle** (env vars, schema-derived data) → safe to use in render directly.
- If the value comes from **the browser** (`window`, `localStorage`, `Date.now`, the user's locale) → put it behind `useEffect`.
- If the value comes from **the user's interaction** (right-click menu coordinates, keystroke state) → already safe; the component isn't mounted on first render.
- If the value comes from **a network fetch** (TanStack Query) → already safe; queries return `undefined` initially on both server and client and update via React's normal commit cycle.

### How to verify locally

```bash
./start.sh
# Open http://localhost:3100 in a regular browser. Open DevTools console.
# Hydration mismatches show as a "Hydration failed" error with a diff
# of the server vs client output. CI also runs the full SSR pass; PRs
# that introduce a mismatch will be flagged.
```

If you find a hydration error in existing code that one of the four fixes above doesn't cover, please [open an issue](https://github.com/SFCyris/DataInsightGrove/issues) — there may be a fifth trap we haven't documented yet.
