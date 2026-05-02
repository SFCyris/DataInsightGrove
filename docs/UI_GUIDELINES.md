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
