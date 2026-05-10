# Phase A Pro Polish — Release 2

Builds on the v0.8 baseline + the earlier Phase A pro polish release
(see `docs/PHASE_A_PRO_POLISH.md`). This release ships the four
follow-up items the prior PhD-UX review flagged:

1. **Profile drift + row-count anomaly producers** — completes the
   data-quality story: the rule engine + event kinds existed; this
   release adds the producers that emit those events automatically.
2. **URL-encoded interactive state** — every drilled-in view
   (Sankey, Column DNA) now persists to the URL so users can refresh,
   share, or bookmark.
3. **Workspace search + tags** — cmdk searches columns across the
   workspace; pipelines now carry tags that filter the catalog.
4. **Profile-drawer depth** — percentiles, std-dev, suspicious-data
   warnings, click-to-filter on top-N values, click-to-range-filter
   on histogram bars.

Each section below has **What** / **Why** / **PhD UX review** /
**Patent posture (cross-referenced to PRIOR_ART_MAP.md)** /
**Additional analytics value worth noting**.

---

## 1. Profile drift + row-count anomaly producers

**What.** After every successful run, two automatic detectors compare
the run's metrics against history:

- **Schema drift.** For each pipeline node that ran in *both* the
  current run and the immediately-prior succeeded run, diff the
  output column lists. Emit `data.profile.drift` for every node
  whose columns were added or removed.
- **Row-count anomaly.** For each node, compute the z-score of the
  current `rows_out` against the last 5 succeeded runs' values.
  Emit `data.row_count.anomaly` when |z| ≥ 2.0 AND |Δ%| ≥ 10%.

Both events flow through the existing rule engine. Two new built-in
rules are seeded on startup so users see in-app notifications without
any config:

- *"Schema drift detected (any pipeline)"* — 5-minute cooldown.
- *"Row-count anomaly (any pipeline)"* — 5-minute cooldown.

**Why.** The earlier release shipped the `check_data` step
(declarative DQ assertions). Profile drift + row-count anomaly are
the **implicit** data-quality signals — they fire even when the user
*didn't* declare any expectations. Together, they close the loop:
*"DIG warns me about data problems both when I asked and when I
didn't think to ask."*

**PhD UX review.**

- **Conservative defaults.** Z-threshold 2.0 + 10% noise floor. The
  user editing a pipeline iteratively expects row counts to wobble;
  spamming notifications during normal editing burns trust. Defaults
  err on the side of "don't fire unless something is meaningfully
  weird."
- **Five-minute cooldown.** A single bad run shouldn't fire ten times
  if the user re-runs while debugging. The cooldown is template-
  scoped (per pipeline + node + check) so unrelated nodes still get
  fast alerts.
- **Plain-text summary ready to read.** The notification template
  fields (`{summary}`, `{z_score}`, `{added}`, `{removed}`) are
  pre-rendered server-side so the in-app row reads as one human
  sentence — *"plant_total ▲ 73% vs avg (4 → 7 rows)"* — not a JSON
  blob.
- **Compute-once, deliver-many.** The detector runs in
  `JobManager._emit_drift_events`, walks the artifacts already
  attached by the executor, and produces N events. The per-event
  template + cooldown work happens inside the rule engine, not
  duplicated per detector. Single source of truth for delivery.

**Patent posture.** § 11 of `PRIOR_ART_MAP.md` flags
data-observability vendors (Monte Carlo, Datadog, Bigeye, Anomalo) as
holding active filings. Mitigations followed in this implementation:

- We use **only classical statistics** (z-score against historical
  mean and stddev) — textbook content from the early 1900s, not
  patentable subject matter under § 101 abstract-idea analysis.
- **No ML / autothreshold / band-fitting**. The Monte Carlo /
  Bigeye-style "learn what's normal for this column" is explicitly
  out of scope; that's where the patents cluster.
- **Schema diff is a set comparison**, prior art back to GNU `diff`
  (1974). The DIG implementation uses literal Python set
  arithmetic — `set(a) - set(b)` — so the technique is unambiguous.
- **Per-event cooldown** is foundational rule-engine prior art (Esper
  CEP 2006, Drools 2001).

**Additional analytics value worth noting (beyond the v1).**

- **Distribution drift** (mean / median / stddev shifts), not just
  schema drift. The plumbing exists in `nodeMetrics.columns` →
  could extend to `nodeMetrics.column_stats` for numeric columns.
- **Per-step opt-out** via a `dq_settings` block in the pipeline doc:
  *"don't alert on this aggregate's row count, the variance is
  expected."*
- **Trend visualisation** in the notifications panel: instead of
  "pipeline X had a row anomaly," let the user click through to a
  sparkline of the last 10 runs' row counts. That's the obvious
  next step.
- **Correlation hints** — if two anomalies fire in the same run AND
  the affected nodes are connected, prepend "*upstream node Y also
  drifted*" to the message. This is rule-engine territory, not new
  detection logic.

---

## 2. URL-encoded interactive state

![Sankey state in URL — drill + filter survive a reload](images/phase-a-pro/02-sankey-zoom-pan.png)

**What.** A small generic hook `useURLState` syncs a JSON-serialisable
state object to a single URL search parameter. Wired into:

- **Sankey** (`?sk=…`) — drill, sink visibility, op-kind filter
  chips, compare-runs mode.
- **Column DNA** (`?dna=…`) — active node, walk direction.

Plus a **"🔗 Copy link"** button on each surface that copies the
current URL with state encoded.

The encoding is JSON → URL-safe base64. Default state omits the param
entirely so URLs stay clean for "I haven't drilled into anything yet."

**Why.** Every powerful surface DIG ships was session-only before this
release. A user finding a violating value at 3 pm couldn't come back
to the same view tomorrow. URL-encoded state is the cheapest possible
fix — no DB schema, no auth model, no sync machinery. One hook,
one share-link button per surface.

**PhD UX review.**

- **Single-param-per-surface.** `?sk=` for Sankey, `?dna=` for DNA.
  This means the URL is human-decodable (you can see *which* surface
  has state pinned without parsing the blob), and surfaces compose
  cleanly when the user drills into multiple at once.
- **Debounced writes (180 ms).** Dragging zoom doesn't spam
  `replaceState`. The "Copy link" button awaits the debounce window
  before reading the URL so the latest state is captured.
- **`replaceState` not `pushState`.** The browser back-button shouldn't
  walk through every drill click. URL state is observability, not
  navigation history.
- **Graceful decode.** Any JSON parse error falls back to the
  default. URLs are user-mutable; we never crash on garbage input.
- **Default-state omission** keeps clean URLs clean. Users hate seeing
  long opaque tokens in their address bar when nothing's been drilled.

**Patent posture.** URL-as-state is foundational web infrastructure
(HTTP RFC 3986, HTML5 History API). No risk. § 31 of
`PRIOR_ART_MAP.md` covers the underlying stack (Next.js, React,
TanStack Query, all MIT).

**Additional analytics value worth noting.**

- **"Copy link" → markdown link** rather than just URL. Power users
  want to paste into Notion / GitHub PR descriptions; "Sankey: [link]"
  is more useful than the bare URL.
- **History of URL states** — track the last 5 distinct states the
  user has been in, expose them as "Recent views" in a dropdown.
  Atlan does this; it's a small feature with big "it remembers what
  I was looking at" value.
- **Saved views** as named bookmarks. URL → name + persist to
  localStorage → reload from a "Saved views" panel.
- **Server-side persistence of saved views** is enterprise-tier
  territory (multi-user, share with teammate). Free-tier individual
  is fine on localStorage.
- **Embed mode.** Dashboards / blog posts often want a frozen iframe
  of the lineage view. A `?embed=1` query param could hide the
  toolbar + close button, leaving just the visualisation. Trivial
  add on top of the URL state.

---

## 3. Workspace search + tags

![Workspace cmdk searching for "plant"](images/phase-a-pro/09-workspace-cmdk.png)
![Catalog with tag filter chips for #revenue and #testbed](images/phase-a-pro/10-catalog-tags.png)

**What.** Three connected pieces:

- **Backend `/search?q=…` endpoint** — substring search across
  pipelines (name + description + tags), datasets (name + tags), and
  columns (across all dataset profiles). Re-ranks by exact ▶ prefix
  ▶ substring match. Returns up to 50 hits.
- **Pipeline tag editor** in the editor toolbar — chip-style add/
  remove with autocomplete from the workspace's known tags. Persists
  via `PUT /search/pipelines/{id}/tags`.
- **Catalog tag-filter chips** — a strip below the catalog header
  showing every workspace tag. Selected tags intersect (AND) to filter
  pipeline nodes; the catalog graph re-flows around the visible
  subset.
- **cmdk integration** — the workspace command palette (Cmd+K) now
  surfaces column hits + tag hits from `/search` alongside the
  existing pipelines + datasets + steps groups.

**Why.** When a workspace has > 15 pipelines, *finding things* becomes
the bottleneck. The catalog browses; it doesn't search. *"Where do we
use `customer_email`?"* and *"Show me pipelines tagged `revenue` whose
last run failed"* are the day-to-day questions a free-tier user can't
answer today. Tags + workspace search make both possible.

**PhD UX review.**

- **Substring search, not fuzzy.** Substring is predictable: type
  `plant`, get every place that string appears. Fuzzy ranking has
  surprising failure modes (typos rank above exact matches) and
  fights mental models. We can move to a real index (sqlite FTS,
  tantivy) when workspace size grows past ~500 entities. For
  individual-tier workspaces, substring is faster + clearer.
- **Tag normalisation.** Tags are lowercased + trimmed + restricted
  to alphanumerics + dashes + underscores. So `Revenue` and
  `revenue` collapse, and we never end up with `Revenue ` vs
  `revenue` showing up as two tags. The constraint is enforced
  server-side AND surfaced in the editor input as a hint.
- **Autocomplete from existing tags.** Add-tag input pre-loads the
  workspace's tag list and shows suggestions as the user types. Cuts
  duplicate-tag spam *before* it lands in the DB.
- **Same chip grammar everywhere.** Pipeline editor → catalog filter
  → search results → cmdk. One visual vocabulary for "this is a
  tag," consistent across the app. (Linear / Notion / Atlan all do
  this; users learn the affordance once.)
- **Filter intersection (AND), not union (OR).** Best-in-class tools
  let users tighten their search by adding more tags. Atlan does
  AND, Notion does AND, Linear does AND. We followed the tradition.

**Patent posture.** § 22 of `PRIOR_ART_MAP.md` covers the search
primitives. Substring search is Unix `grep` (1974). Tag systems are
foundational — Linear, Notion, Trello, GitHub Issues all have them.
Autocomplete on a tag input is foundational web UX.
Intersection-vs-union is a settled design pattern in faceted-search
literature (Tunkelang 2009, *Faceted Search*).
**No specific patent risk identified.**

**Additional analytics value worth noting.**

- **Saved searches.** *"Pipelines tagged `revenue` AND last run is
  failed"* is exactly the workflow people want bookmarked.
  Implementation: serialise the tag-filter set + status filter into a
  URL state (synergy with feature 2!), expose as "Save this search"
  via cmdk.
- **Tag inheritance.** Pipelines that *read from* a dataset tagged
  `revenue` could automatically inherit a soft `revenue:input` tag.
  Atlan does this for governance; we could do it for navigation.
- **Tag-based notification rules.** *"Alert me on any pipeline tagged
  `production` whose run fails."* The notification rule engine
  already supports filters; adding `tags: [...]` to filters is one
  rule_engine.py change.
- **Recently-used tags** in the editor input. Most users churn through
  2-3 tags repeatedly; surfacing them at the top of the autocomplete
  list cuts type-ahead time substantially.
- **Column-level tags** (next milestone). The grid already has the
  surface (column header chips). Apply the same chip model + tag
  store keyed by `(dataset_id, column_name)`. Cross-system column
  lineage requires this (Atlan-style governance).

---

## 4. Profile-drawer depth

![Profile drawer with percentiles, std-dev, click-to-filter top-N](images/phase-a-pro/08-profile-drawer.png)

**What.** The column profile drawer (opens on column-name click)
gains four new sections:

- **Suspicious-data warnings** at the top of the drawer:
  - `⚠️ Over 50% NULLs` (high-null-rate)
  - `⚠️ N% NULLs` (≥ 5%)
  - `🟰 Single distinct value (constant)`
  - `🔑 Every row has a unique value (likely a key)`
  - `🎯 N outliers (|z| > 3)`
- **Std-dev** added to the stats grid alongside mean / median / min /
  max.
- **Percentile breakdown** for numeric columns: P25 / P50 / P75 /
  P90 / P95 in a 5-cell grid.
- **Click-to-filter** affordance on top-N values (button-style row
  with hover underline + tooltip; click inserts a `filter_eq` step
  on the column action stream).
- **Click-to-range-filter** on histogram bars (cursor: pointer; click
  inserts a `filter_rows` step with the SQL predicate `column >= bar.x0
  AND column < bar.x1`).

**Why.** A *data-preparation* tool's column drawer is one of the most-
used surfaces. Trifacta and pandas-profiling set the bar high. DIG's
drawer was good but shallow vs. those: histogram + top-N + a few
stats. This release closes most of the depth gap on the **statistics
the user can read off the data**, while explicitly *not* attempting
the **suggested-transformation features that Trifacta has patents on.**

**PhD UX review.**

- **Warnings first, then stats.** Suspicious-data warnings render at
  the top of the drawer so the user lands on the most-actionable
  signal first. Inverted-pyramid information design (Norman, *Design
  of Everyday Things*).
- **Suspicious heuristics, not "smart suggestions."** Each warning is
  a pure-stats threshold the user could read off the numbers — *"50%
  NULLs"* is just `nullPct > 0.5`. We deliberately *don't* recommend
  *"you should impute these with the median"* (Trifacta-patent
  territory). The drawer surfaces facts; it doesn't make suggestions.
- **Clickable values are visually marked.** Top-N rows render as
  buttons with hover underline + cursor change; histogram bars get
  pointer cursor + tooltip. Affordances are explicit (Nielsen #6).
  When the parent doesn't pass `onValueFilter` / `onRangeFilter`, the
  same content renders as read-only — no half-broken interactions.
- **Percentiles laid out as a grid.** P25–P95 in 5 equal cells with
  fixed-width tabular-nums for vertical scanning. The user reads
  vertically across percentiles, not horizontally through prose.
- **No proprietary "data quality score."** Best-in-class commercial
  tools (Sifflet, Monte Carlo) compute a single aggregate
  *"data-quality score"* per column. We deliberately don't — those
  scores are reductive (you lose the *which* of why this column is
  suspicious) and they're patent-adjacent territory. Surface the
  actual signals; let the user form their own assessment.

**Patent posture.** Trifacta / Alteryx have substantial patents on
**predictive transformation suggestion** — *"this column has 5% nulls,
suggest imputing with median."* Mitigations:

- DIG **does not suggest transforms**. The drawer surfaces statistics
  + warnings; explicit cast / drop / filter actions remain in the
  separate column-action menu (existing prior art back to KNIME +
  Alteryx pre-Trifacta-patent-era).
- All statistics implemented are **textbook descriptive statistics**:
  mean, median, percentiles, standard deviation, z-score outliers.
  Prior art back to Tukey 1977 (*Exploratory Data Analysis*).
- The **histogram** is a 20-equal-bin discretisation (algorithm from
  any intro-stats course); click-to-filter is set theory + SQL
  BETWEEN, prior art back to SQL itself.
- "Suspicious" warnings are **fixed-threshold deterministic rules**,
  not learned models. Each is a one-line predicate on already-
  computed stats.

§ 5 + § 21 of `PRIOR_ART_MAP.md` covers the prior art for column
profiling + the explicit avoidance of Trifacta-patent territory.
**No specific patent risk introduced by this release.**

**Additional analytics value worth noting (deferred to follow-ups).**

- **Missing-pattern timeline.** Plot null vs non-null cells across the
  row-position axis. Reveals "the last 200 rows have suddenly become
  NULL" patterns that summary stats hide.
- **Per-column correlation panel.** For numeric columns, show a small
  bar chart of |Pearson correlation| with every other numeric
  column. Tukey 1977 again, no patent risk. High-value for
  understanding which columns *move together*.
- **Skew + kurtosis.** Mean + median tell you something; skew tells
  you **why** they disagree. Two more pure-stats fields, fits in the
  same percentile grid.
- **Sample-vs-population indicator** in the drawer header. Currently
  every stat is "from the in-grid sample" — when the user is on the
  full dataset (not a 100k row preview), a small badge would
  reinforce that "this is what the actual data looks like."
- **Peer-column comparison.** *"Compared to other numeric columns,
  this one has 4× the null rate."* Useful at first inspection. Pure
  arithmetic; no patent risk.
- **Trend across runs** for the same column. *"Null rate has been
  rising for 3 runs."* Synergy with feature 1 (drift detection) — the
  same data is collected; just different presentation.

---

## Aggregate ranking — where DIG stands now

| Surface | Before R1 | After R1 (prior release) | After R2 (this release) |
|---|---|---|---|
| Main canvas | 6.5/10 | 8/10 | 8/10 |
| Sankey volume view | 7.5/10 | 8.5/10 | 8.5/10 (URL state) |
| Column DNA | 7/10 | 8/10 | 8/10 (URL state) |
| Live grid + impact | 7/10 | 8/10 | 8/10 |
| Catalog | 5/10 | 7/10 | **8/10** (tag filter) |
| Data-quality testing | 3/10 | 6.5/10 | **7.5/10** (drift + anomaly) |
| **Workspace search** | n/a | n/a | **7.5/10** (new surface) |
| **Profile drawer** | 6/10 | 6/10 | **8/10** (depth + click-to-filter) |
| **Aggregate** | ~7/10 | ~8/10 | **~8.5/10** |

That's solid premium-individual territory. Remaining headroom to
9-10/10 is now mostly the enterprise-server tier (multi-user,
scheduling, cross-system column harvesting, anomaly ML, mobile,
real-time collaboration) — explicitly out of scope per the
free-tier-individual product positioning.

---

*Document maintained alongside the code. Update screenshots via
`python3 scripts/capture_doc_screenshots.py {minimap,sankey-zoom,
dna-zoom,dna-downstream,impact-badge,catalog,check-step,
profile-drawer,workspace-cmdk,catalog-tags}` (or omit to capture
all).*
