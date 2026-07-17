# `FunctionPacks/` — the public first-party pack source library

This directory is the published source library for DIG's first-party step
packs. It's where DIG step packs are designed, built, and signed before they
ship as `.dpack` archives users can drop into their running DIG instance.

The pack sources, their bundled reference data, and the build tooling all
live here in the public repo. The `.dpack` build excludes `images/`,
`screenshots/`, and any `INTERNAL_NOTES.md` files, so the archive that
reaches users carries only what the pack needs at runtime.

---

## Why this layout

DIG accepts step packs as `.dpack` archives — zip files with a single
top-level pack directory inside (`pack.json` + `steps/<id>/manifest.json`
+ `steps/<id>/step.py` …). See the [pack format spec](#pack-format-spec)
below.

The packs DIG ships with need a single source of truth where their Python
source can be edited, linted, unit-tested, and built into a versioned
`.dpack` ready to hand out. Co-locating them in the main checkout keeps
cross-edits simple — a step pack's logic often mirrors a built-in step's,
so having both in the same tree is the highest-leverage arrangement.

So: this directory is the source library. Sources here. Built `.dpack`
artifacts land in `dist/`.

---

## Directory layout

```
FunctionPacks/
├── README.md                  ← you are here
├── packs/                     ← one subdirectory per pack source tree
│   └── statspack/             ← the source of statspack-x.y.z.dpack
│       ├── pack.json          ← pack manifest (ID, version, etc.)
│       ├── README.md          ← rendered in DIG's install dialog
│       ├── LICENSE            ← optional but strongly recommended
│       └── steps/
│           ├── t_test/
│           │   ├── manifest.json
│           │   └── step.py
│           ├── chi_square/
│           └── …
├── templates/
│   └── _pack_template/        ← copy this to start a new pack
│       ├── pack.json
│       ├── README.md
│       └── steps/
├── scripts/
│   ├── build_pack.py          ← packs/<id>/ → dist/<id>-<v>.dpack
│   ├── validate_pack.py       ← dry-run lint without building
│   └── import_example.py      ← examples/<demo>/ → live DIG pipeline
├── examples/                  ← worked example flows per pack
│   ├── time_series_pro/       ← stationarity diagnostics demo
│   ├── ts_retail_forecast/    ← 1 of 8 time-series killer demos
│   ├── ts_iot_anomaly/        ← rolling z-score anomaly detection
│   ├── ts_financial_volatility/
│   ├── ts_healthcare_vitals/
│   ├── ts_hospital_readmissions/
│   ├── ts_er_load_forecast/
│   ├── ts_housing_price_trend/
│   ├── ts_housing_inventory_anomaly/
│   └── _ts_demos_data/        ← generator scripts for the 8 ts_* CSVs
└── dist/                      ← built artifacts; safe to delete + rebuild
    └── statspack-1.0.0.dpack
```

**Examples** are loaded via `python3 FunctionPacks/scripts/import_example.py <demo_id>` — uploads the bundled `data.csv`, substitutes placeholders in `flow.dig.json`, and creates a live pipeline in your running DIG instance. See [`docs/tutorials/11-time-series-killer-demos.md`](../docs/tutorials/11-time-series-killer-demos.md) for the 8 time-series demos with rendered chart screenshots.

The directory split mirrors what shipping software looks like: `packs/` are
"source repos," `dist/` is "release artifacts," `templates/` is "scaffold,"
`scripts/` is the build tooling. Keep them separate so a `find dist -delete`
never wipes source.

---

## Quick start — building a new pack

### 1. Scaffold

```bash
cp -R FunctionPacks/templates/_pack_template FunctionPacks/packs/<your_pack_id>
```

Edit `packs/<your_pack_id>/pack.json`:

- Change `id` to match the directory name (lowercase, snake_case).
- Pick a clear `label` with an emoji prefix (DIG-house style).
- Set `version` to `0.1.0` for a first build.
- Update `description`, `author`, `license`.

### 2. Add steps

Each step is `packs/<pack_id>/steps/<step_id>/` containing `manifest.json`
and `step.py`. The format is **identical** to built-in steps under
`backend/steps/<step_id>/` — copy one of those as a starting point if you
want a working example.

When adding a step, also add its id to `pack.json`'s `steps[]` list. The
build script verifies these match.

### 3. Build

```bash
python3 FunctionPacks/scripts/build_pack.py statspack
# → writes dist/statspack-1.0.0.dpack
```

The script:

- Validates `pack.json` against `shared/schemas/pack-manifest.schema.json`
- Validates every `steps/<id>/manifest.json` against
  `shared/schemas/step-manifest.schema.json`
- Lints every `step.py` (same rules as the AI-generated step linter)
- Computes a sha256 of the resulting zip and stamps it back into the
  archive's `pack.json`
- Writes `dist/<pack_id>-<version>.dpack`

### 4. Test

Upload the resulting `.dpack` via DIG's **Settings → Step Packs** panel.
Review the contents in the install dialog. Click install. The pack's
steps appear in the in-pipeline picker tagged with the pack source
badge.

---

## Pack format spec

Every pack is a zip with a single top-level directory whose name equals
`pack.json:id`:

```
statspack-1.0.0.dpack       ← .dpack = zip; the version goes in the filename
└── statspack/
    ├── pack.json           ← required, at the pack root
    ├── README.md           ← optional, rendered during install
    ├── LICENSE             ← optional
    └── steps/
        ├── t_test/
        │   ├── manifest.json
        │   └── step.py
        └── …
```

`pack.json` shape (full schema in
`shared/schemas/pack-manifest.schema.json`):

```jsonc
{
  "id":          "statspack",
  "version":     "1.0.0",                   // semver
  "label":       "📐 Statistics Pack",
  "description": "Hypothesis tests, effect sizes, …",
  "author":      "DataInsightGrove",
  "license":     "AGPL-3.0",
  "homepage":    "https://github.com/SFCyris/DataInsightGrove",
  "minDigVersion": "0.6.0",
  "steps":          ["t_test", "anova", "chi_square", "ks_test"],
  "connectors":     [],
  "pythonRequirements": ["scipy>=1.11"],     // declared, never auto-installed
  "checksum":     "sha256:…"                 // stamped at build time
}
```

### Conventions for pack-shipped step IDs

- Use the same snake_case pattern as built-in steps.
- Namespacing isn't enforced, but consider prefixing your step IDs with
  the pack id when collisions are likely (e.g. `statspack_t_test` instead
  of `t_test`). DIG rejects installs that conflict with an already-loaded
  step.

### Python dependencies

`pythonRequirements[]` is **declared, not auto-installed**. DIG's install
dialog shows the operator the exact `pip install …` command to run before
the pack will work. Auto-pip from arbitrary packs is a server-side RCE
hazard — we don't do it.

If your pack relies on a heavy dep (scipy, sktime, …), document the
recommended install in the pack's `README.md` so users see it before
they hit the import error.

### Versioning

- `pack.json:version` is semver. Bump on every distributed change.
- The build script writes `dist/<id>-<version>.dpack`. Older versions
  remain in `dist/` until you delete them — keep them around so a user
  can roll back.
- DIG installs one version per pack id. Uploading a newer version of an
  already-installed pack triggers an "Update available" path, not a
  conflict.

---

## Lint rules (what `validate_pack.py` checks)

- `pack.json` validates against the schema.
- Every step's `manifest.json` validates against the step schema.
- Every step's `id` listed in `pack.json:steps[]` exists on disk and
  vice versa.
- `step.py` exports a `step` symbol.
- No `os.system`, `subprocess`, `eval`, `exec` in `step.py` (warn only —
  some steps legitimately shell out, but flag them for review).
- No directory traversal (`..`) in any path inside the archive.

---

## When to build a new pack vs. add to an existing one

**Add to an existing pack** when the new step is a natural sibling of
what the pack already does (`t_test` lives next to `anova` in
`statspack` — both are inferential stats).

**Start a new pack** when:

- The dependencies are different (a `geospatial-pro` pack pulls
  `geopandas`, `shapely`, `pyproj` — operators shouldn't have to install
  those just to get hypothesis tests).
- The audience is different (a `finance-pack` for financial-services
  features may want its own license / branding).
- The release cadence is different (a fast-moving experimental pack
  shouldn't drag along a stable, conservative one).

---

## What lives here vs. what ships in a `.dpack`

Published in this directory:

- `packs/*/` — pack sources (Python steps, manifests, reference data)
- `templates/_pack_template/` — the scaffold for a new pack
- `scripts/` — the build and validation tooling
- `examples/` — worked example flows per pack

Rebuildable, not tracked:

- `dist/*.dpack` — built artifacts (regenerate from source with
  `build_pack.py`)

Excluded from the built `.dpack` archive:

- `images/` and `screenshots/` — authoring assets, not needed at runtime
- `INTERNAL_NOTES.md` — maintainer notes kept out of the shipped archive

The DIG runtime that consumes these packs lives in the main tree:

- `shared/schemas/pack-manifest.schema.json` — the spec
- `backend/dig/api/packs.py` and friends — the runtime
- `frontend/app/settings/packs/` — the UI
