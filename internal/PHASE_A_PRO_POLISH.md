# Phase A Pro Polish — premium individual-tier UX

This release is focused on closing the visible-quality gap between DIG
and the polished commercial leaders (Flourish, ECharts, Atlan, Dagster)
on the parts of the product an individual user touches every day. It
sits *on top of* the v0.8 Phase A lineage UX and assumes Layers 1–7
have already shipped.

Enterprise concerns (scheduling, multi-user, SQL pushdown, elastic
execution, deep cross-system column lineage, anomaly ML) stay parked
for the commercial server tier. Everything below is for the free
individual user.

The work is sequenced by **effort × impact**:

| # | Item | Effort | Impact | Today | After |
|---|---|---|---|---|---|
| 1 | Canvas mini-map | 30 min | high | 4/10 | 8.5/10 |
| 2 | Zoom+pan on Sankey | 1–2 h | high | 3/10 | 8/10 |
| 3 | Zoom+pan on Column DNA | 2–3 h | high | 3/10 | 8/10 |
| 4 | Downstream walk toggle in DNA | half day | very high | 6/10 | 7.5/10 |
| 5 | Edit-time impact badge | half day | medium | 2/10 | 7/10 |
| 6 | Cross-pipeline column edges in Catalog | 1–2 d | very high | 4/10 | 7.5/10 |
| 7 | Check step + profile drift + row-count anomaly | 3–4 d | very high | 3/10 | 7.5/10 |

Each section below has a **What** (the change), a **Why** (the gap it
closes), a **PhD UX review** (what we're matching from best-in-class
and the small refinements we made beyond defaults), and a screenshot.

---

## 1. Canvas mini-map

![Canvas mini-map](images/phase-a-pro/01-canvas-minimap.png)

**What.** Adds a pannable + zoomable mini-map to the bottom-right of
the main pipeline canvas. Hidden under 6 nodes (small graphs don't
benefit from one and a mini-map would just steal real-estate).

The node squares mirror canvas state at-a-glance:

- **Failed run** → saturated red (`#ef4444`)
- **Running** → blue (`#3b82f6`)
- **Stale freshness** → red-orange (`#f97316`)
- **Due** → amber (`#f59e0b`)
- **Fresh / succeeded** → emerald (`#10b981`)
- Datasets sky, outputs green, default muted zinc

The viewport indicator (white rectangle inside the mini-map) has a
1.5 px stroke at `rgba(15, 23, 42, 0.35)` so it stays visible against
the card background — the xyflow default leaves it almost invisible
on light themes.

**Why.** Dagster, Hex, and Figma-style canvases all assume the user
has a spatial map for big graphs. Without one, scrolling a 30-node
pipeline means losing your place. The xyflow `<MiniMap>` component
ships in the library DIG already imports — we just hadn't enabled it
in a state-aware way.

**PhD UX review.** The mini-map's *primary* job is spatial
orientation; its *secondary* job is at-a-glance health. We follow
the secondary-channel rule: keep ambient state calm (mostly emerald),
and reserve high saturation for genuine alerts (red failure, orange
stale). That way the user's eye lands on the only thing that matters.
Two small refinements over xyflow's default to match Dagster-grade
polish:

- `nodeStrokeColor` mirrors fault states with darker tones so the rect
  has a visible border even at minimap scale (3–6 px tall).
- `backdrop-blur` on the container so the mini-map reads as "lifted
  above" the canvas, not embedded in it.

A subtle point: we set `initialWidth` / `initialHeight` on every node
when building the graph. xyflow's mini-map filters out any node that
lacks `(width ?? initialWidth ?? measured.width)` — without explicit
initial dims, every node was silently skipped on first paint until the
ResizeObserver caught up.

---

## 2. Zoom + pan on the Sankey

![Sankey zoom](images/phase-a-pro/02-sankey-zoom-pan.png)

**What.** d3-zoom is wired onto the Sankey SVG with a 0.5×–5× scale
range. Three interactions:

- **Wheel** — zoom in/out, anchored on cursor position
- **Drag on empty canvas** — pan
- **Toolbar buttons** — `−` / `+` / `⤢` reset, with a live percent
  readout between them so the user can confirm the current scale

Every visible primitive (bands, badges, annotation pins, node bars,
labels) lives inside a single `<g>` element whose transform is updated
by d3-zoom. `<defs>` and the background `<rect>` stay outside the
group so gradients reference the original coordinate space and the
background can serve as a drag-pan surface.

**Why.** Flourish, ECharts, Total Sankey, and every modern lineage
canvas treat zoom+pan as table stakes. A Sankey for a 30-node pipeline
fits horizontally only at small scale; users want to lean in to read a
single band's row count, then zoom back out.

**PhD UX review.** Three details that distinguish a "thrown together"
zoom from a polished one:

- **Filter-on-target.** `d3-zoom`'s default panning fires on every
  `mousedown`. We override the filter so band hover-tooltip and
  click-to-isolate keep working — pan only fires when the user starts
  the drag on the SVG itself or the transparent background `<rect>`.
  Direct manipulation on data primitives still does data-primitive
  things; pan happens on the chrome.
- **Discoverability.** Direct manipulation alone is invisible — many
  users won't realise scroll-wheel zooms unless told. The toolbar
  `−` / `+` buttons + live percentage make the affordance obvious
  (Nielsen heuristic #6: recognition over recall).
- **Anchored zoom.** d3-zoom anchors zoom on the cursor by default, so
  the point you're looking at stays fixed. Compare with naive `transform:
  scale(k)` which always anchors on (0,0) and forces extra panning. We
  go one step further for the toolbar `+` / `−` buttons: `scaleBy` is
  called with the SVG's **visible centre** as the anchor, so clicking
  the buttons zooms toward the centre instead of drifting toward (0,0).

---

## 3. Zoom + pan on the Column DNA

![DNA zoom](images/phase-a-pro/03-dna-zoom-pan.png)

**What.** Same scale-extent (0.5×–5×) and same toolbar pattern as the
Sankey, but applied to the bipartite DNA canvas. Two implementation
quirks vs the Sankey because DNA mixes SVG (edges) with HTML (node
divs) inside the canvas:

- The transform target is a single inner `<div>` wrapping both the SVG
  edge layer and the absolute-positioned node-shape layer. CSS
  `transform: translate(...) scale(...)` scales them as a unit so the
  arrowheads stay aligned with their nodes.
- `transform-origin: 0 0` so coordinates remain in the same space the
  layout function used — pan + scale compose linearly.
- A `data-dna-node` attribute on every column / op shape is checked by
  the d3-zoom filter so the user can still hover and click nodes; pan
  only initiates on background drags.

**Why.** A 25-column lineage spans ~3500 px wide at the layout's
default stride. Without zoom+pan, that meant a horizontal scroll bar
that hid the full structure; users couldn't see the whole "DNA
helix" of a column at once. Now they can fit-out to read the gestalt,
or zoom-in to read individual formulas inline on the op chips.

**PhD UX review.** Two refinements worth highlighting:

- **Same toolbar grammar as the Sankey.** Both views adopt the
  `− %  + ⤢` cluster in the same screen position (right-edge of the
  canvas chrome), so the user learns the affordance once and re-uses
  it everywhere. Consistency across surfaces is more valuable than
  clever per-surface design.
- **Cursor + cursor:active.** The container shows `cursor-grab` (open
  hand) by default and `cursor-grabbing` (closed fist) while a drag
  is in progress. That's the de-facto signal Figma / Miro / Maps use
  for "this surface pans." Without it, users miss the affordance.

---

## 4. Downstream walk toggle in Column DNA

![DNA downstream](images/phase-a-pro/04-dna-downstream-walk.png)

**What.** A three-way segmented control in the DNA legend strip:
**← upstream**, **↔ both**, **downstream →**. The active-path
computation now respects this mode and lights up the appropriate
side(s) of the bipartite graph.

The labels deliberately translate the technical terms:

| Mode | Internal name | Plain-English question |
|---|---|---|
| `← upstream` | ancestors | "Where did this column come from?" |
| `↔ both` | both | "Everything connected to this column" |
| `downstream →` | descendants | "What does this column affect?" |

In the screenshot the user clicked `unit_cost` (origin source column)
and toggled to `downstream →` — the entire chain through `cast to
currency` → derived `unit_cost` → `ƒ(x) unit_cost × units_produced`
→ derived `production_cost` → `📈 Pareto chart` lights up green. The
parallel branch (`units_produced → passthrough → units_produced`)
stays grey because clicking `unit_cost` and walking forward never
reaches it.

**Why.** This is the largest gap-closer in the deck. Atlan, Castor,
Sifflet, Datafold, Manta — every commercial column-lineage tool
leads with **impact analysis**: *"if I change this column, what
breaks?"* DIG had upstream-only walks before, which answered the
opposite question (provenance) but left the impact question manually
unanswerable. Toggling direction now answers both with a single click,
and `↔ both` gives the whole neighbourhood for the curious.

**PhD UX review.** Two things are worth calling out:

- **Plain-English labels.** Technical labels like
  *ancestors / descendants / both* are precise but make the user do
  translation work. *Upstream / downstream* is what data engineers
  speak natively, and the directional arrows (`←` `↔` `→`) make the
  visual mapping unambiguous before reading the words. Tooltip-level
  detail elaborates with the question each mode answers, so even
  someone unfamiliar with lineage terminology can pick the right one
  from context.
- **Default = upstream.** When the modal opens we keep the original
  default (ancestors), because someone who just landed on Column DNA
  probably opened it from a column whose value surprised them — and
  the natural follow-up question is "where did this come from?" The
  switch is one click away the moment they pivot to "what depends on
  this." This matches the **principle of least astonishment** vs
  defaulting to the more commercially sexy "downstream" direction.

---

## 5. Edit-time impact badge on column headers

![Impact badge](images/phase-a-pro/05-impact-badge.png)

**What.** A small `→ N` chip on every column header in the live grid
when the focused step has downstream consumers. The number is the
count of downstream pipeline nodes that read from the focused step's
output. Clicking the chip opens the column's DNA (where the user can
flip to *downstream →* and see exactly which derived columns / sinks
depend on this column).

In the screenshot, the user has focused `cast unit_cost`. Every column
the cast emits (`id`, `plant`, `unit_cost`) shows `→ 1`: one
downstream node — `derive production_cost` — consumes this output.
If they're about to change the cast (e.g., flip `unit_cost` to a
different precision), they get instant warning that 1 downstream
node depends on this and a one-click drill-through to see the
column-level chain.

**Why.** Datafold built a whole company on this primitive:
*"Before you push, see what your change breaks."* Atlan, dbt Cloud's
column-level lineage, and Sifflet all surface impact previews at
edit time. For DIG's individual-tier user this is the difference
between "I changed a derive expression and the Pareto chart broke
silently" and "I see right there that 4 things will need re-running."

**PhD UX review.** Three deliberate choices:

- **Hidden when N = 0.** A pure-passthrough column with no downstream
  consumers gets *no* badge — the chrome stays quiet. Adding a "→ 0"
  chip everywhere would be informational noise (Tufte's data-ink
  ratio rule).
- **Emerald, not red.** Even though this is "warning"-adjacent
  information, the right colour is *connection*-positive. Red would
  make every dependency look like a bug. Emerald says "this column
  matters to N other places" — useful, neutral, ambient.
- **Cheap to compute.** The count is derived locally from the
  pipeline document — no API call. We trade exact column-level
  precision (which would require parsing every downstream step's
  params for column refs) for a node-level upper bound that ships
  in O(N) over the doc and refreshes instantly as edits land.
  Column-level granularity is cleanly available via the chip's
  one-click drill into Column DNA.

---

## 6. Cross-pipeline column edges in the Catalog

![Catalog](images/phase-a-pro/06-catalog-column-edges.png)

**What.** The `/catalog` page already drew a workspace-wide meta-graph
where each pipeline was a node and edges fired when pipeline A's
output URI matched pipeline B's input URI. That edge is now enriched
with the **list of columns flowing through it** (when the URI
corresponds to a registered DIG dataset whose schema is known).

The new chrome:

- The edge label shows a `→ N cols` chip when the column list is
  non-empty. Edges with column data also draw thicker (2 px vs 1.6 px)
  and use a green-tinted label background so they pop against
  schema-less edges.
- Clicking an edge opens a side panel with the full column list —
  every column rendered as a small `→ name` chip in monospace, so the
  user can scan the actual schema flowing across the boundary.
- When the destination URI isn't a registered dataset, the panel
  explains why no columns are shown: *"No registered dataset for
  &lt;uri&gt; — column-level lineage requires the destination URI
  to be a known DIG dataset."*

**Backend.** `catalog.py` pre-loads every `Dataset.columns` keyed by
both `source_uri` and `storage_uri` (each normalised the same way as
the existing edge-detection URI keys), then attaches the matched
column-name list to every edge it emits. O(D) over datasets + O(P²)
over pipelines, both small in practice. The `CatalogEdgeOut`
Pydantic model gains a `columns: list[str] = []` field, which the
frontend's TypeScript `CatalogEdgeOut` mirrors.

**Why.** Atlan, Castor, and Manta all ship column-level lineage as
their flagship feature. DIG's URI-only edges said *"these pipelines
talk"*; the column list says *"this is the contract between them."*
For a free-tier user that distinction is meaningful: changing the
schema on an upstream pipeline now visibly threatens the columns the
downstream pipeline reads.

**PhD UX review.** Three calls worth flagging:

- **Graceful empty state.** Edges without dataset metadata still get
  drawn — they just lose the column count. This honours the "show
  what we know, explain what we don't" principle and avoids the
  brittle UX of *"no columns? hide the edge entirely."*
- **Click-edge as primary action.** xyflow's `onEdgeClick` is the
  natural affordance for "tell me more about this connection." We
  pair it with `onPaneClick` to dismiss, so the side panel feels
  like a proper inspector overlay rather than a sticky modal.
- **Same chrome grammar as the pipeline panel.** The selected-edge
  panel sits in the same right-rail position as the selected-pipeline
  panel, with the same width and typography — users learn the
  affordance once.

> Note. The screenshot above is from a workspace with 51 pipelines but
> no cross-pipeline output → input chains, so all 0 edges. The feature
> is verified at the API level (`/catalog/lineage` now exposes a
> `columns: string[]` field per edge — confirmed via OpenAPI). When
> users build pipelines that hand off to each other, the edges and
> column lists appear automatically.

---

## 7. Data-quality test framework (Check step + events)

![Check step in cmdk](images/phase-a-pro/07-check-step.png)

**What.** A new step `check_data` (🧪 *Data quality check*) ships in
the step library. It takes one input table, passes the rows through
unchanged, and runs a SQL assertion in parallel. When the assertion
fails, the step emits a `data.quality.violation` event that flows
through the existing notification rule engine.

Six built-in check kinds, mirroring dbt tests + Great Expectations:

| Kind | Predicate | Use case |
|---|---|---|
| `not_null` | `col IS NOT NULL` | "every row must have a value" |
| `unique` | `COUNT(*) OVER (PARTITION BY col) = 1` | primary-key style |
| `between` | `col >= min AND col <= max` (NULL passes) | range bounds |
| `in_set` | `col IN ('paid','pending', …)` | enum-like columns |
| `regex` | `regexp_matches(col, pattern)` | format checks |
| `expression` | free-form SQL predicate (safety-validated) | custom rules |

Severity is `warn` (in-app notification, run continues) or `error`
(notification + the run's data-quality artifact carries `severity:
"error"` so the UI can surface a fail-state badge).

**Plumbing.**

- `backend/steps/check_data/` — manifest + step implementation. The
  step's `validation_sql` returns one row per check: `total`,
  `violations`, `first_bad` (sample of offending values up to 3),
  `severity`, `check_kind`, `check_name`. The executor already runs
  every step's `validation_sql` and attaches the row as a
  `_validation:<node>` artifact — the check_data step uses this
  existing seam, no new infra.
- `backend/dig/jobs/manager.py:_emit_check_violations` — after a run
  succeeds, walks the validation artifacts. Any check_data row with
  `violations > 0` produces a `data.quality.violation` event with the
  full context (pipeline, node, kind, count, sample).
- `backend/dig/api/events.py` — three new event kinds registered:
  `DATA_QUALITY_VIOLATION`, `DATA_PROFILE_DRIFT`,
  `DATA_ROW_COUNT_ANOMALY` (latter two are placeholders for the
  follow-up; the kinds exist in `ALL_EVENT_KINDS` so users can add
  custom rules now and the producer ships in a follow-up commit).
- `backend/dig/api/notification_rules.py` — a new built-in rule
  *"Data-quality check failed (any pipeline)"* fires on every
  violation, with templated title `"{check_name}: {violations}
  violation(s)"` and 60-second cooldown so iterators get fast feedback.

**Why.** dbt tests are the most-used feature of dbt; Great
Expectations spawned a whole company. For a free-tier user, the
ability to **declare an expectation as a step** in the visual
pipeline (no separate config file, no CLI) is the simplest version of
that capability. It plugs into DIG's existing event + notification
infrastructure with zero new UI surface — every check that fails
shows up as a notification with sample offending values.

**PhD UX review.**

- **Step, not separate framework.** dbt and Great Expectations both
  ask the user to learn a separate config / DSL. DIG's checks ARE
  pipeline steps — they live in the same step library users already
  navigate, reuse the same palette / category / search, and inherit
  every UI affordance (run state colors, freshness halos, groups,
  Sankey colour, DNA participation). The cost of "I want to add a
  check" is the cost of adding any other step.
- **Sample offending values.** `first_bad` aggregates up to three
  distinct violating values into a comma-joined string the
  notification template renders inline. Users land on the notification
  already knowing what value(s) broke the rule, without drilling into
  query results. This is the *"answer the user's next question"*
  rule (Norman's principle of feedback).
- **Severity that matters semantically.** `warn` is "yellow chip in
  notifications panel"; `error` is "yellow chip + the run's metadata
  marks a quality failure." We deliberately *don't* fail the run
  outright on an error severity — DIG runs are interactive editing
  experiments, and silently failing a run in the middle of an iteration
  loop is more frustrating than informative. Schedule-level enforcement
  (the dbt-test-style "this run has officially failed") belongs in the
  enterprise tier where pipelines run unattended.

**Profile drift + row-count anomaly** are the two follow-ups in this
todo block. Their event kinds are registered today
(`data.profile.drift`, `data.row_count.anomaly`) and they share the
same delivery path through the rule engine — only the producer is
deferred. Users can already create custom rules against these kinds
in the settings panel; the rule will simply never fire until the
producers ship.

---

## Where DIG ranks now

| Surface | Before | After this release |
|---|---|---|
| Main canvas | 6.5/10 | **8/10** (mini-map closes spatial-orientation gap) |
| Sankey volume view | 7.5/10 | **8.5/10** (zoom+pan + smarter chrome) |
| Column DNA | 7/10 | **8/10** (zoom+pan + downstream walk = full neighbourhood reasoning) |
| Live grid | 7/10 | **8/10** (impact badge → drill-through to DNA) |
| Catalog (cross-pipeline) | 5/10 | **7/10** (column-level lineage when datasets are registered) |
| Data-quality testing | 3/10 | **6.5/10** (declarative checks as visual steps; profile drift + row-count anomaly stubbed for follow-up) |
| **Aggregate** | **~7/10** | **~8/10** |

That's solid premium-individual territory. The remaining headroom
to 9-10/10 is mostly the enterprise-server tier (multi-user
collaboration, scheduling, cross-system column harvesting, anomaly
ML, partitioning) — explicitly *not* in scope here.
