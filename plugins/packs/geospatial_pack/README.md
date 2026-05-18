# 🌍 Geospatial Pack

The full geographic toolkit. Pairs with the built-in `convert_coordinates`,
`geo_distance`, and `export_to_map` for spatial joins, geometry parsing,
spatial indexing, projected-CRS work, reverse geocoding, map-matching,
and **boundary lookups** for choropleth rendering.

## Steps

| Step | Purpose |
| --- | --- |
| `parse_geometry`    | Convert WKT or GeoJSON text into a typed geometry column |
| `spatial_join`      | Join two inputs on a spatial predicate (within / contains / intersects / touches / covers) |
| `geohash_cell`      | Add a geohash or H3 cell id for spatial-index aggregation |
| `vincenty_distance` | Geodesic distance + initial bearing on the WGS84 ellipsoid (more accurate than Haversine for long distances) |
| `crs_transform`     | Reproject coordinates between any two pyproj-recognised CRSes (EPSG codes, PROJ strings, WKT) |
| `reverse_geocode`   | Resolve lat/lon to country / state via bundled lookup table — no network call |
| `map_match`         | Snap input points to the nearest reference point (bus stops, sensor sites, store fronts) |
| `wkb_by_us_state`   *(new in v1.0.0)* | US state code / name / lat·lon → WKB MULTIPOLYGON, ready for `export_to_map` choropleth |
| `wkb_by_country`    *(new in v1.0.0)* | ISO country code / name / lat·lon → WKB MULTIPOLYGON of the country |

## Bundled reference data

As of v1.0.0 the pack ships ~290 KB of compressed boundary data.

| Resource | Source | Coverage |
| --- | --- | --- |
| `us_states_10m` | US Census TIGER 10m, via topojson/us-atlas v3 | 56 rows (50 states + DC + 5 territories) |
| `world_countries_110m` | Natural Earth 110m, via topojson/world-atlas v2 | 177 sovereign states + dependencies |

Both sources are public domain. See [LICENSES.md](./LICENSES.md) for
full attribution. The bundled `data.zip` is lazy-extracted on first
use, cached under `data/cache/pack_data/geospatial_pack/<version>/`.
To refresh from upstream, run `_build/build.py` then `dig-pack build`.

## Requirements

```bash
pip install "shapely>=2.0" "geographiclib>=2.0" "pyproj>=3.6" "geohash2>=1.1" "h3>=4.0" "reverse_geocoder>=1.5" "scipy>=1.11"
```

DIG installs these automatically when you install the pack.

## Example use cases

### A · Real-estate listings inside school catchment areas
A property dataset has lat/lon for every listing; a separate file has
school district polygons in GeoJSON. Tag each listing with the school
district it falls in.

```
csv (listings.csv)            ─┐
                                ├─ spatial_join (within)
csv (school_districts.geojson) ─┤    left geometry: listings.point
  └─ parse_geometry             │    right geometry: districts.geometry
        format: geojson         │
        source: geometry_str   ─┘
                              → group_aggregate (median price by district)
                              → export_to_map (one marker per district centroid)
```

`parse_geometry` turns the GeoJSON text column into a usable
geometry; `spatial_join` with predicate `within` is the
point-in-polygon check.

### B · Delivery zones — which deliveries belong to which depot zone
Same shape as A but inverted predicate: depot zones (polygons) contain
delivery points.

```
csv (deliveries.csv)  → ...
                      ─┐
                       ├─ spatial_join (contains)
csv (depot_zones.wkt) ─┤    predicate: contains
  └─ parse_geometry    │    left: zones, right: deliveries
        format: wkt   ─┘
                      → group_aggregate (count by zone, sum by zone)
                      → expectations (every delivery joined exactly one zone)
```

Adding the `expectations` check at the end turns the join into a
contract: if any delivery falls outside every zone, the run fails
loudly instead of silently dropping rows.

### C · IoT heatmap with H3 buckets
Stream of lat/lon sensor readings; visualise density at city scale.

```
csv (readings.csv) → geohash_cell (system: h3, precision: 8)
                   → group_aggregate (count by cell, mean(value) by cell)
                   → convert_coordinates (cell → centroid lat/lon, via your
                                           hexagon-id-to-centroid lookup)
                   → export_to_map (size by count, color by mean)
```

H3 at precision 8 gives ~0.7 km² hexes — a usable heatmap resolution
for city-scale data without the ragged edges of geohash rectangles.

### D · Transatlantic flight times — Vincenty replaces Haversine
You're computing flight times between continental airports. Haversine
(the built-in `geo_distance`) is fine for sub-100 km work but
underestimates by up to 0.5% over transatlantic distances. For
schedule planning that's hours of error per fleet per day.

```
csv (flights.csv) → vincenty_distance
                       lat1Column: origin_lat,  lon1Column: origin_lon
                       lat2Column: dest_lat,    lon2Column: dest_lon
                       outputBearing: true
                  → derive_column (flight_hours = distance_m / (avg_groundspeed_mps * 3600))
                  → group_aggregate (sum flight_hours by aircraft)
```

The `outputBearing` toggle adds the initial heading from origin to
destination — useful for flight-plan visualisations and for spotting
routes that cross unusual geographic features.

### E · Mapping European postcodes into a national grid
Real-estate analytics across the UK with proper area calculations needs
British National Grid coordinates (EPSG:27700) instead of WGS84
lat/lon (EPSG:4326).

```
csv (uk_postcodes.csv) → crs_transform
                            xColumn: longitude, yColumn: latitude
                            sourceCrs: EPSG:4326
                            targetCrs: EPSG:27700
                            outputXColumn: bng_easting
                            outputYColumn: bng_northing
                       → group_aggregate (count by 1km bng cell)
                       → export_to_file (bng_density.parquet)
```

`crs_transform` accepts any EPSG code; common targets include
`EPSG:32633` (UTM zone 33N for central Europe), `EPSG:2154`
(Lambert-93 for France), `EPSG:3857` (Web Mercator).

### F · Detecting border-crossing GPS pings
Each GPS ping should stay inside a country's polygon between fixes.
Find pings that don't.

```
csv (gps_pings.csv) → ...
                    ─┐
                     ├─ spatial_join (within, left_outer)
csv (countries.wkt) ─┘    Result has NULL country for every ping
                          that fell outside every polygon.
                    → filter_rows (country IS NULL)
                    → export_to_file (anomalous_pings.csv)
```

`left_outer` join keeps every ping; the NULL country column flags
the anomalies.

### G · Choropleth from a metric-per-state table

Drop the hand-maintained polygon CSV and lean on the bundled atlas.

```
csv (housing_listings.csv) → group_aggregate (mean price by state)
                           → wkb_by_us_state
                                input_mode: text
                                input_column: state            # 2-letter USPS
                                output_column: state_geom
                           → export_to_map
                                mode: choropleth
                                geometry_col: state_geom
                                value_col: avg_price
                                color_scale: viridis
```

The lookup adds `state_geom` (WKB) plus `state_geom_name`,
`state_geom_code`, `state_geom_fips`, `state_geom_centroid_lat`,
`state_geom_centroid_lon`. The auto-detect input also accepts state
names ("California") or FIPS codes ("06") — case-insensitive. Set
`input_mode: point` (and `lat_column` / `lon_column`) for reverse
lookup from coordinates.

`wkb_by_country` works the same way for world maps — input is ISO
alpha-2 / alpha-3 / numeric / name, or lat/lon.

## Changelog

### 1.0.0 — 2026-05-13

- Add `wkb_by_us_state` and `wkb_by_country` — first-class boundary
  lookup with multi-modal input (code / name / lat·lon) and STRtree
  point-in-polygon under the hood.
- Bundle `data.zip` (~290 KB) with US state + world country
  geometries as parquet. Pack now uses the new pack-data framework
  (`shared/schemas/pack-manifest.schema.json` → `resources`).
- Housing demo migrated to use `wkb_by_us_state` instead of joining
  against a hand-maintained CSV of state polygons.

### 0.2.0 — 2026-05-10

- Add `reverse_geocode` — lat/lon → country/state via bundled lookup
  table (no external network call).
- Add `map_match` — snap input points to the nearest point in a
  reference table (named known locations).
- Pack renamed from `geo_pro` → `geospatial_pack` to match the
  ROADMAP slot.

### 0.1.0 — 2026-05-09

- Initial release: `parse_geometry`, `spatial_join`, `geohash_cell`,
  `vincenty_distance`, `crs_transform`.
