# 🧪 Browser-demo build

A way to ship DIG to a static host (Vercel, Cloudflare Pages, GitHub Pages,
S3 + CloudFront, …) so prospects can try the editor *without installing
anything*. The DuckDB-WASM core already runs entirely in the browser; the
demo build is what makes the rest of the app accept that as the only
runtime.

This document describes the **foundation that landed in the codebase** and
the **per-endpoint shim work that's still to do** before a fully working
demo can be deployed.

## Why bother

The single biggest leak in DIG's PLG funnel is the gap between *"GitHub
visitor"* and *"first chart rendered"*. Asking a prospect to clone the
repo, install Python deps, build a Mac wrapper, and learn the pipeline
editor before they see anything compelling is a 30-minute commitment.
A zero-install demo collapses that to one click — they land on
`try.datainsightgrove.app`, see a live editor with a sample pipeline, and
form an opinion in 30 seconds. From there the conversion path is honest:
*"Like what you see? Install for real to keep your work, run on the
backend, use AI assistance, …"*

## What ships today (the foundation)

### Build flag

`NEXT_PUBLIC_DIG_DEMO=1` at build time turns on demo mode. Read once at
bundle compile via [`frontend/lib/demo-mode.ts`](../frontend/lib/demo-mode.ts):

```ts
import { isDemoMode, isHidden } from "@/lib/demo-mode";

if (isHidden("ai")) return null;        // hide the AI panel in demo builds
<RunButton disabled={isDemoMode()} />   // grey out backend-only buttons
```

The `DEMO_GATED` map in that file is the master checklist of what the
demo build hides:

| Feature key      | Hides                                                      |
|------------------|------------------------------------------------------------|
| `ai`             | AI panel · Suggest Fix · Explain · Pipeline Review         |
| `jdbc`           | Settings → JDBC drivers · the JDBC connector dropdown      |
| `runs`           | ▶ Run on backend button · run history · runs panel         |
| `scheduledRuns`  | Cron / hourly schedule UI                                  |
| `webhooks`       | Settings → Global webhooks                                 |
| `authSettings`   | Settings → Security & API (token mgmt is irrelevant)       |

### Banner

[`DemoBanner`](../frontend/components/demo-banner.tsx) renders at the top
of every page in demo builds. It's dismissable per session
(`sessionStorage`, not `localStorage`) so a hard refresh re-introduces
itself — that's the right behaviour for a stateless sandbox where users
returning after days forget what kind of build they're on.

### Wiring

Mounted unconditionally in [`frontend/app/layout.tsx`](../frontend/app/layout.tsx);
the `isDemoMode()` short-circuit means production builds elide the
component entirely.

## What still needs to land before a demo deploy

The flag and banner are *gates*. Before deploying you need a layer that
makes API calls work without a backend. Options, in order of effort:

1. **localStorage / IndexedDB shim** (recommended). A wrapper around
   [`request()`](../frontend/lib/api/client.ts) that intercepts paths
   like `/datasets`, `/pipelines`, `/health` and reads/writes from
   browser storage instead of fetching. Bundle the sample datasets and
   templates into the build so they're available without network. This
   is roughly a week of focused work.
2. **Static-export + read-only**. Ship a snapshot of one fully-built
   pipeline, served from disk; user can interact (filter, pivot, change
   chart kind via DuckDB-WASM) but can't add new steps. Faster to land
   (~2 days) but a much weaker demo.
3. **Stand up a tiny demo backend**. A small FastAPI deployment with
   per-session ephemeral SQLite. This is the same product as today,
   just hosted — the *operating cost* is the trade-off vs.
   localStorage's zero infra. Use this if you'd rather pay the hosting
   bill than write the shim.

## Deploy guide (when the shim lands)

```bash
# from repo root
cd frontend
pnpm install
NEXT_PUBLIC_DIG_DEMO=1 pnpm build

# Static-host the output
# Vercel / Netlify: point to frontend/, set NEXT_PUBLIC_DIG_DEMO=1 in env
# Cloudflare Pages: same; build cmd `pnpm build`, output `frontend/.next`
# GitHub Pages: requires next.config.js `output: "export"` (Next 16 supports this)
```

## Things to design before deploying

- **Reset path.** A "Reset demo to fresh" button somewhere visible — when
  a user spends 10 minutes making a mess, the easiest path home is one
  click. (`window.localStorage.clear()` + reload.)
- **Permalink format.** `?p=<base64url>` for sharing pipelines via URL
  without a backend. The `.dig.json` import path already exists; the
  shim just decodes the query param into the same envelope.
- **Telemetry sniff.** Add a tiny `/beacon` ping (anonymized) on first
  load and on first chart rendered. Without it, you can't prove the
  demo actually drives installs — and PLG without measurement is faith
  capital.

## Anti-patterns to avoid

- **Auto-saving demo work to localStorage and conflating it with real
  installs.** Users get confused when their demo pipeline shows up after
  an install. Keep the storage key prefix distinctive (`dig.demo.*` or
  similar) and have the install flow explicitly *not* import demo data.
- **Stub endpoints that return mock JSON.** Looks tempting; rots fast
  because the backend's response shape evolves. Either run the real
  backend or write the localStorage shim — don't fake it.
- **Skipping the banner.** Without it, users will hit run/AI/JDBC, get a
  cryptic failure, and leave. Visible "this is a sandbox" messaging up
  front is worth more than 100 graceful error states.
