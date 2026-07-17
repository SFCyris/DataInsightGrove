# Third-party data licenses — geospatial_pack

Every reference dataset bundled in `data.zip` is listed below with its
license, attribution, and source. The same information is also encoded
machine-readably in `pack.json` → `resources.files[].license` /
`attribution` / `source` so pipeline exports can carry the chain.

## us_states_10m.parquet

- **License:** CC0-1.0 / Public Domain (U.S. Census Bureau works are not subject to copyright in the United States — see 17 U.S.C. § 105)
- **Source:** [topojson/us-atlas v3](https://github.com/topojson/us-atlas), `states-10m.json`
  - Upstream pulls from the U.S. Census Bureau's Cartographic Boundary
    Files (1:10,000,000 scale).
  - Fetched via `https://cdn.jsdelivr.net/npm/us-atlas@3/states-10m.json`
- **Packaged by:** Mike Bostock (topojson/us-atlas)
- **Coverage:** 50 states + DC + 5 territories (AS, GU, MP, PR, VI), 56 rows total
- **CRS:** WGS 84 (EPSG:4326)

## world_countries_110m.parquet

- **License:** Public Domain (Natural Earth data is in the public domain)
- **Source:** [topojson/world-atlas v2](https://github.com/topojson/world-atlas), `countries-110m.json`
  - Upstream pulls from [Natural Earth](https://www.naturalearthdata.com/)
    Admin 0 boundaries at 1:110,000,000 scale.
  - Fetched via `https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json`
- **Packaged by:** Mike Bostock (topojson/world-atlas), enriched with
  ISO 3166 alpha-2/alpha-3 codes from pycountry at build time.
- **Coverage:** 177 sovereign states / dependent territories
- **CRS:** WGS 84 (EPSG:4326)

## How to refresh

```bash
# Re-fetch the sources + regenerate the parquets
backend/.venv/bin/python FunctionPacks/packs/geospatial_pack/_build/build.py

# Repackage data.zip + update pack.json hashes
backend/.venv/bin/dig-pack build FunctionPacks/packs/geospatial_pack
```

The build is reproducible: the same upstream sources produce
byte-identical `data.zip` (fixed zip timestamps, deterministic
ordering). Bump `pack.json` → `version` whenever the underlying
upstream commit changes.
