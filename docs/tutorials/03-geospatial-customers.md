# 🌍 Tutorial 3 — Geospatial customer mapping

**Goal:** join customers to a city lookup table, build a `geographic` column from latitude/longitude, compute distances from each customer to a reference city (San Francisco), and bucket customers by distance.

**Dataset:** [`samples/customers-demo.csv`](../../samples/customers-demo.csv) + [`samples/cities-demo.csv`](../../samples/cities-demo.csv).

**Features in focus:** join · pack_struct + cast to `geographic` · geo_distance · pipeline diff · column lineage

**Estimated time:** 20 minutes.

---

## Why this tutorial exists

Geospatial work historically involved PostGIS or a separate library. DIG ships first-class spatial types (`geographic`, `cartesian2d`, `cartesian3d`, `polar2d`) backed by DuckDB's spatial extension. Once two columns become a `geographic`-typed column, every spatial step (distance, bbox, contains, buffer) is a one-step add.

This tutorial walks the canonical "(LAT, LON) → spatial column → distance" pattern.

---

## Steps

1. **Import** both datasets if you haven't.

2. **New pipeline:** `Customer distance from SF`.

3. **Join customers ← cities.** Add the customers dataset, then add `join` step. Set:
   - **Left:** `customers-demo`
   - **Right:** `cities-demo`
   - **Type:** `left`
   - **On:** `country = country`

   > 💡 **Real-world wrinkle:** customers has `UK`, cities has `GB` for the same country. The join will silently miss those rows. This is exactly the kind of issue the AI Reviewer catches (run `🔍 Review` after step 6 — the reviewer flags "Country code mismatch: customers uses UK, cities uses GB"). For now, accept the mismatch and note it as a real-data lesson.

4. **Inspect the joined preview.** You'll see the customer row + matched city row (lat/lon). Right-click the new `latitude` column header → **🔗 Trace lineage** to confirm where it came from. Helpful when you join three datasets and need to remember which one supplied which column.

   *(After the join the live grid grows the city columns: city, lat, lon, population. Right-click any new column header → 🔗 Trace lineage to confirm it came from cities-demo.)*

5. **Smart-pick suggestion: pack & cast to geographic.** Look at the right-side hints panel — when DIG sees a `(LAT, LON)` pair in the same step's output, it surfaces a one-click composite hint:

   *(The hints panel surfaces the composite hint as a clickable card on the right side of the editor. Per-tutorial screenshot pending.)*

   Click it. DIG inserts two steps in one move: `pack_struct` (builds a `{lat, lon}` struct) and `cast_type` (casts that struct to the `geographic` meta-type). The new column appears with the 🌍 icon in the header.

6. **Add `geo_distance` step.** Set:
   - **From column:** the new `customer_location` (geographic-typed)
   - **To column:** literal — type `POINT(-122.4194 37.7749)` for San Francisco
   - **Output column:** `distance_km_from_sf`
   - **Unit:** `kilometers`

7. **Add `bin_numeric` step to bucket customers.** Set:
   - **Column:** `distance_km_from_sf`
   - **Bins:** `0,500,2000,8000,Infinity`
   - **Labels:** `same-city, regional, continental, intercontinental`
   - **Output column:** `distance_bucket`

8. **Add `group_aggregate`.** Set:
   - **By:** `distance_bucket`
   - **Aggregations:**
     - `customer_id` · `count` · alias `n_customers`
     - `monthly_revenue` · `sum` · alias `total_revenue`

9. **Add `export_to_image`.** Bar chart, x = `distance_bucket`, y = `total_revenue`, title = `Revenue by distance from SF`.

10. **▶️ Run on backend.** The chart appears in artifacts.

   *(Per-tutorial chart screenshot pending — produced as PNG in the artifacts panel below the grid after the run.)*

---

## Pipeline diff: try a different reference point

Switch the SF coordinate in `geo_distance` to London (`POINT(-0.1276 51.5074)`). Save. Click **↔ Compare**.

The diff drawer shows a single `param_changed` entry on the geo_distance step with `(-122.4194 37.7749) → (-0.1276 51.5074)`. Side-by-side panes make it visually obvious only one thing changed; nothing else in the pipeline shifted.

   ![Pipeline diff — side-by-side showing the changed param](../images/tutorials/advanced/06-orders-diff-side-by-side.png)
   *(Side-by-side diff view shown from the orders tutorial — your tutorial-3 diff will look identical except the `param_changed` row sits on the `geo_distance` step.)*

---

## What "transparent backend fallback" means

When you save with the `geographic` column, DIG's editor preview tries to run in DuckDB-WASM but the spatial extension isn't bundled with the WASM build. Watch the status badge under the preview grid: it briefly flips to ⚙️ Backend before showing results. This is the transparent fallback — same SQL, run on the backend instead. Engineer mode shows this in the SQL view: scroll to the bottom and you'll see the spatial functions explicitly.

> 💡 Click **`{ } SQL`** in the toolbar (Engineer mode only) to see the compiled query. The CTE labels match the pipeline node IDs so you can read SQL ↔ visual nodes by eye.

---

## Share

**🔗 Share**:
- **Title:** Customer distance from a reference city
- **Tags:** geospatial, customers, geographic
- **Visibility:** Public

The recipient picks their own reference point in the geo_distance step. The cities-demo dataset is bundled in the share so the pipeline runs without extra setup.

---

## What you learned

- `pack_struct` + `cast_type` as the "compose then constrain" pattern for meta-types.
- The `geographic` meta-type and DuckDB spatial functions (geo_distance).
- Smart-pick hints surface composite operations from the column profile.
- Backend transparent fallback for WASM-incompatible SQL.
- Pipeline diff makes single-param changes immediately legible.

> 💡 **Tip:** All four spatial meta-types (`geographic`, `cartesian2d`, `cartesian3d`, `polar2d`) accept the same `cast_type` pattern. The hints panel surfaces appropriate composites when it detects matching column pairs (LAT/LON for geographic, X/Y for cartesian2d, R/THETA for polar2d, etc.).
