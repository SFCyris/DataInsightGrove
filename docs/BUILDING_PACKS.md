# 📦 Building DIG step-packs

This guide covers writing a step-pack from scratch, including packs
that bundle **reference data** (lookup tables, geographic boundaries,
codebooks, etc.). The framework is fully local — no GitHub Actions,
no internet at runtime, no cloud registry.

## What is a pack?

A pack is a folder containing one or more steps (and optionally
connectors) that DIG loads as a unit. Packs live in `plugins/packs/`
once installed; they're authored in `Step-Pack-internal/packs/` (or
your own working tree).

```
my_pack/
├── pack.json          # manifest — id, version, steps, dependencies, resources
├── README.md          # narrative description for humans
├── LICENSES.md        # per-resource license + attribution roll-up
├── data.zip           # bundled reference data, lazy-extracted at runtime
├── steps/
│   └── my_step/
│       ├── manifest.json
│       └── step.py
├── connectors/        # optional
└── _build/            # dev-time only; gitignored except for build.py
    ├── sources.json
    ├── sources.lock.json
    ├── build.py
    └── sources/
```

## The `pack.json` manifest

The schema lives at [`shared/schemas/pack-manifest.schema.json`](../shared/schemas/pack-manifest.schema.json).
Required fields: `id`, `version`, `label`, `description`. See
`Step-Pack-internal/packs/geospatial_pack/pack.json` for a worked
example with reference data.

## Reference data: when and how

If your pack ships static reference data — boundary geometries,
codebooks, fixture rows, anything the steps look up rather than
receive on their inputs — declare it in `pack.json` under `resources`:

```jsonc
{
  "resources": {
    "archive": "data.zip",
    "sha256": "<filled by dig-pack build>",
    "files": [
      {
        "id": "my_lookup_table",
        "path": "my_lookup_table.parquet",
        "license": "CC0-1.0",
        "attribution": "Original author + dataset name",
        "source": "https://example.com/dataset or 'local hand-curated'",
        "description": "What this dataset is + how it's used"
      }
    ]
  }
}
```

### Why a zip?

A single `data.zip` is the unit of distribution:

- **Atomic install** — one file to verify, extract, or roll back
- **Single integrity check** — one sha256 instead of N
- **License + attribution travel inside the archive**
- **Clean source tree** — pack folder ships `data.zip`, not a binary
  tree (cleaner git diffs, simpler review)
- **Smaller pack tarball** for mixed text/binary content

The zip is **lazy-extracted** to `data/cache/pack_data/<pack_id>/<version>/`
on first use — no extraction cost on install if your pipeline never
uses those steps.

### Step code accesses data via `pack_data()`

```python
from dig.extensions.pack_data import pack_data

# Resolves to an absolute Path. Triggers the one-time extract on
# first call; subsequent calls hit a process-local cache.
parquet_path = pack_data("my_pack", "my_lookup_table")
```

Steps **never** accept a raw filesystem path from pipeline params —
they accept a resource id declared in `pack.json`. That's the
function-gating: a user can't load arbitrary files through your step.

## Source provenance: `_build/sources.json`

If your reference data comes from external sources (URLs, vendor CSVs,
upstream public datasets), declare them in `_build/sources.json`:

```jsonc
{
  "sources": [
    {
      "id": "us_states_10m",
      "type": "url",
      "url": "https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json",
      "description": "US Census TIGER boundaries via topojson/us-atlas"
    },
    {
      "id": "internal_zones",
      "type": "file",
      "path": "_build/sources/internal_zones.csv",
      "description": "Operations team's curated zone table — refreshed quarterly"
    },
    {
      "id": "small_lookup",
      "type": "inline",
      "data": [{"code": "A", "name": "Alpha"}, {"code": "B", "name": "Beta"}],
      "description": "Tiny mapping — inline avoids a separate file"
    }
  ]
}
```

Three source types:

- **`file`** — anything on local disk. CSVs, GeoJSON, shapefiles, hand-curated parquets.
- **`url`** — any HTTP(S) URL. Not GitHub-specific. Your internal artifact server, a vendor CDN, a static S3 bucket — anything addressable.
- **`inline`** — JSON literal in `sources.json`. Good for small mappings.

When you run `dig-pack build`, the CLI captures a sha256 + size for
every source into `_build/sources.lock.json`. **Commit that file.**
It's your audit trail: anyone cloning the repo can verify the bytes
your build consumed, even if the upstream URL later disappears.

## The build script: `_build/build.py`

This is YOUR script. It reads the sources, converts/normalises them,
and writes the result into `data/`. Run it locally any time you
refresh the data:

```bash
backend/.venv/bin/python Step-Pack-internal/packs/my_pack/_build/build.py
```

`build.py` is free to do whatever it needs — TopoJSON decoding, CSV
parsing, geometry simplification, joining multiple sources. The
contract is that it writes valid files to `data/`.

After `build.py` populates `data/`, the next step is packaging:

```bash
backend/.venv/bin/dig-pack build Step-Pack-internal/packs/my_pack
```

This:
1. Zips every file in `data/` (flat — no subdirectories) into `data.zip`
   with deterministic timestamps + ordering (reproducible builds)
2. Computes sha256 + sizes + parquet row counts
3. Rewrites `pack.json`'s `resources` block with the populated fields
4. Updates `_build/sources.lock.json` if `sources.json` exists

The result: `pack.json` + `data.zip` are committed together. Two
authors with the same `data/` produce byte-identical `data.zip` →
identical sha256 → straightforward review.

## Dev vs ship mode

The runtime resolver has two modes:

- **Dev mode** — pack folder contains a `data/` directory. Files are
  served directly. Use this while iterating on the data — no
  rebuild needed on every save.
- **Ship mode** — pack folder contains only `data.zip` (no `data/`).
  The runtime extracts the zip into the cache on first access.

When publishing a pack, ship only `data.zip`; gitignore `data/`. The
runtime picks the right mode automatically.

## CLI reference

```bash
dig-pack scaffold <name>                # Create a new pack skeleton
dig-pack build <pack_dir>               # Zip data/ + update pack.json
dig-pack build <pack_dir> --check       # Exit non-zero if rebuild would drift
dig-pack verify <pack_dir>              # Verify pack.json hashes match data.zip
dig-pack info <pack_dir>                # Pretty-print pack summary
dig-pack install <pack_dir>             # Force-extract data.zip now (vs lazy)
dig-pack list                           # List discovered packs + cache state
```

All commands are local-only. None require git, GitHub, or any CI vendor.

## Pre-publish workflow

Whatever fits your habits — git hook, Makefile target, manual
checklist:

```bash
# 1. Refresh sources + rebuild data
python Step-Pack-internal/packs/my_pack/_build/build.py

# 2. Repackage data.zip + update pack.json
dig-pack build Step-Pack-internal/packs/my_pack

# 3. Verify in-tree consistency
dig-pack verify Step-Pack-internal/packs/my_pack

# 4. Inspect for sanity
dig-pack info Step-Pack-internal/packs/my_pack

# 5. Commit pack.json, data.zip, _build/sources.lock.json
git add Step-Pack-internal/packs/my_pack/{pack.json,data.zip,_build/sources.lock.json}
```

`dig-pack build --check` in a pre-commit hook catches the common
"forgot to rebuild" error.

## Versioning policy

- **Patch** (`1.0.0 → 1.0.1`) — bugfix to a step's code, no schema change
- **Minor** (`1.0.0 → 1.1.0`) — new step added, new resource added, or
  reference data refreshed from upstream
- **Major** (`1.0.0 → 2.0.0`) — breaking change to a step's params or
  output schema, or to the resource schema

The pack's `version` is in the runtime cache path
(`data/cache/pack_data/<id>/<version>/`), so bumping the version
triggers a fresh extract. Old cache versions can be cleaned up
manually or via `dig-pack uninstall` (reserved).

## Worked example: `geospatial_pack`

See [`Step-Pack-internal/packs/geospatial_pack/`](../Step-Pack-internal/packs/geospatial_pack/)
for a complete pack that:

- Bundles US state + world country boundaries (~290 KB compressed)
- Decodes TopoJSON to Parquet at build time (TopoJSON parser inlined
  in `_build/build.py` — no runtime dependency)
- Provides `wkb_by_us_state` + `wkb_by_country` lookup steps with
  multi-modal input (text or lat/lon point)
- Uses Shapely STRtree for fast point-in-polygon at runtime
- Drives the housing demo's choropleth render

The complete flow — from `_build/sources.json` to `data.zip` to a
rendered choropleth in the housing demo — exercises every part of the
framework end-to-end.

## Adding a new lookup step (template)

A boundary-lookup step needs ~80 lines of code with the shared helpers
in `geospatial_pack/_lookup_common.py`:

```python
from dig.engine.step import PolarsContext, PolarsResult, Step
from dig.extensions.pack_data import pack_data
from _lookup_common import load_reference, resolve_row, output_columns_for

_KEY_ORDER = ["primary_key", "secondary_key", "name"]


def _dataset():
    path = pack_data("my_pack", "my_lookup_table")
    return load_reference(path, key_columns={
        "primary_key": "code_column",
        "secondary_key": "alt_code_column",
        "name": "display_name_column",
    })


class MyLookupStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        ds = _dataset()
        indices = [
            resolve_row(
                ds,
                input_mode=params.get("input_mode", "auto"),
                text_value=df[params["input_column"]][i] if params.get("input_column") else None,
                lat=df[params["lat_column"]][i] if params.get("lat_column") else None,
                lon=df[params["lon_column"]][i] if params.get("lon_column") else None,
                key_order=_KEY_ORDER,
            )
            for i in range(df.height)
        ]
        out = output_columns_for(
            ds.df, indices,
            output_column=params.get("output_column") or "my_geom",
            metadata_columns={"name": "display_name_column", "code": "code_column"},
        )
        return PolarsResult(output=df.with_columns([pl.Series(n, v) for n, v in out.items()]))
```

The helpers handle the multi-modal input + STRtree caching; the step
provides the dataset key order + output schema.
