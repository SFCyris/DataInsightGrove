#!/usr/bin/env python3
"""End-to-end driver for the v1 50 GB benchmark.

Steps:
  1. Ingest data/inputs/ecommerce_benchmark.parquet as a DIG dataset
     via POST /datasets/from-uri (the file stays in place — DIG only
     records the URI in its catalog).
  2. POST a hand-built pipeline doc:
        filter_rows → derive_column → group_aggregate → sort_rows
                                                       → wkb_by_country
                                                       (boundary lookup)
     with 6 terminal nodes hanging off (3 file outputs + 3 charts).
  3. Trigger the run, poll until done.
  4. Print: total run time, output paths, file sizes, key metrics.

All HTTP calls go through the same /api proxy the browser uses, so this
also exercises the same-origin path end-to-end.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE = "https://127.0.0.1:3443/api"          # same-origin via TLS proxy → Next rewrite
TOKEN = (Path.home() / ".config/dig/auth.token").read_text().strip()

# Self-signed cert → relax verify for this script; production users use
# the system trust store and don't need this.
import ssl
_CTX = ssl._create_unverified_context()


def _http(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, context=_CTX, timeout=120) as r:
            txt = r.read().decode("utf-8")
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        print(f"\n[ERR] {method} {url}: HTTP {e.code}")
        print(e.read().decode("utf-8", errors="replace")[:800])
        sys.exit(1)


def step(idx: int, total: int, msg: str) -> None:
    print(f"[{idx}/{total}] {msg}", flush=True)


def main() -> int:
    dataset_path = REPO_ROOT / "data/inputs/ecommerce_benchmark.parquet"
    if not dataset_path.exists():
        print(f"FAIL: dataset not found at {dataset_path}")
        return 1
    size_gb = dataset_path.stat().st_size / 1024**3
    print(f"dataset: {dataset_path} ({size_gb:.2f} GB compressed Parquet)")

    # ---- 1. Ingest ---------------------------------------------------------
    step(1, 4, "Ingesting dataset via /datasets/from-uri ...")
    t0 = time.time()
    # Ingest is idempotent on name — if a previous run left a dataset with
    # the same name AND it's in a healthy state, reuse it. Otherwise import.
    existing = _http("GET", "/datasets")
    if isinstance(existing, dict):
        existing = existing.get("datasets") or existing.get("items") or []
    candidate = next(
        (d for d in existing if d.get("name") == "ecommerce-benchmark-50gb"
         and d.get("status") not in ("failed", "errored")),
        None,
    )
    if candidate is not None:
        ds = candidate
    else:
        ds = _http("POST", "/datasets/from-uri", {
            "name": "ecommerce-benchmark-50gb",
            "connector_id": "parquet",
            "uri": f"file://{dataset_path}",
            "options": {},
        })
    # Wait for profiling to complete (status: ready) — DIG profiles the
    # parquet on import (row count + column stats). For a 50 GB file the
    # row-count + min/max scan takes a couple of minutes.
    poll_n = 0
    while ds.get("status") not in ("ready", "failed", "errored"):
        time.sleep(2)
        ds = _http("GET", f"/datasets/{ds['id']}")
        poll_n += 1
        if poll_n % 5 == 0:
            print(f"     ... profiling ({poll_n*2}s, status={ds.get('status')})", flush=True)
    if ds.get("status") != "ready":
        print(f"FAIL: dataset ingest status={ds.get('status')} err={ds.get('error')}")
        return 1

    rows = ds.get("rowCount")
    rows_str = f"{rows:,}" if rows is not None else "(unknown)"
    cols = ds.get("columns") or []
    print(f"     dataset_id: {ds['id']}  rows: {rows_str}  cols: {len(cols)}  "
          f"ingest+profile: {time.time()-t0:.1f}s")

    ds_alias = f"ds_{ds['id'].lower()}"

    # ---- 2. Build the pipeline doc ----------------------------------------
    step(2, 4, "Building 5-step pipeline doc + 6 terminals ...")
    doc: dict = {
        "schemaVersion": 1,
        "id": "{{PIPELINE_ID}}",
        "name": "🚀 benchmark · 500M ecommerce events",
        "description": (
            "Validates DIG's ~50 GB-on-a-single-dataset claim. Five transform "
            "steps (filter → derive → group → sort → boundary lookup) then "
            "six terminals: parquet + csv + excel exports plus pareto / pie / "
            "choropleth visualisations."
        ),
        "datasets": [{
            "id": ds_alias,
            "connector": "parquet",
            # storageUri is DIG's canonical Parquet path after ingest;
            # sourceUri is the original file:// the user pointed us at.
            "uri": ds.get("storageUri") or ds.get("sourceUri"),
            "label": ds["name"],
        }],
        "nodes": [
            # ---- 5 transform steps ----------------------------------------
            {
                "id": "n_filter",
                "step": "filter_rows",
                "inputs": {"in": {"port": "out", "ref": ds_alias}},
                "outputs": ["out"],
                "params": {"predicate": "amount >= 5"},
                "ui": {"x": 100, "y": 100, "label": "🔍 amount ≥ 5"},
            },
            {
                "id": "n_revenue",
                "step": "derive_column",
                "inputs": {"in": {"port": "out", "ref": "n_filter"}},
                "outputs": ["out"],
                "params": {"name": "revenue", "expression": "amount * quantity"},
                "ui": {"x": 320, "y": 100, "label": "💰 revenue = amount × qty"},
            },
            {
                "id": "n_groupby",
                "step": "group_aggregate",
                "inputs": {"in": {"port": "out", "ref": "n_revenue"}},
                "outputs": ["out"],
                "params": {
                    "groupBy": ["country_code"],
                    "aggregates": [
                        {"column": "revenue",  "fn": "sum",   "as": "total_revenue"},
                        {"column": "revenue",  "fn": "count", "as": "order_count"},
                        {"column": "amount",   "fn": "mean",  "as": "aov"},
                    ],
                },
                "ui": {"x": 540, "y": 100, "label": "📊 by country"},
            },
            {
                "id": "n_sort",
                "step": "sort_rows",
                "inputs": {"in": {"port": "out", "ref": "n_groupby"}},
                "outputs": ["out"],
                "params": {"by": [{"column": "total_revenue", "direction": "desc"}]},
                "ui": {"x": 760, "y": 100, "label": "↕️ revenue desc"},
            },
            {
                "id": "n_geom",
                "step": "wkb_by_country",
                "inputs": {"in": {"port": "out", "ref": "n_sort"}},
                "outputs": ["out"],
                "params": {
                    "input_mode": "text",
                    "input_column": "country_code",
                    "output_column": "country_geom",
                    "resolution": "auto",
                },
                "ui": {"x": 980, "y": 100, "label": "🌍 country boundary"},
            },

            # ---- 3 file outputs (off n_sort, no geometry bloat) ----------
            {
                "id": "n_out_parquet",
                "step": "export_to_file",
                "inputs": {"in": {"port": "out", "ref": "n_sort"}},
                "outputs": ["out"],
                "params": {"format": "parquet", "path": "top_countries.parquet", "compression": "zstd"},
                "ui": {"x": 1200, "y": -60, "label": "💾 Parquet"},
            },
            {
                "id": "n_out_csv",
                "step": "export_to_file",
                "inputs": {"in": {"port": "out", "ref": "n_sort"}},
                "outputs": ["out"],
                "params": {"format": "csv", "path": "top_countries.csv"},
                "ui": {"x": 1200, "y": 60, "label": "💾 CSV"},
            },
            {
                "id": "n_out_xlsx",
                "step": "export_to_file",
                "inputs": {"in": {"port": "out", "ref": "n_sort"}},
                "outputs": ["out"],
                "params": {"format": "excel", "path": "top_countries.xlsx"},
                "ui": {"x": 1200, "y": 180, "label": "💾 Excel"},
            },

            # ---- 3 visualisations -----------------------------------------
            {
                "id": "n_chart_pareto",
                "step": "pareto_chart",
                "inputs": {"in": {"port": "out", "ref": "n_sort"}},
                "outputs": ["out"],
                "params": {
                    "label": "country_code",
                    "value": "total_revenue",
                    "top_n": 12,
                    "title": "Top countries · Pareto",
                },
                "ui": {"x": 1200, "y": 320, "label": "📈 Pareto"},
            },
            {
                "id": "n_chart_pie",
                "step": "pie_donut",
                "inputs": {"in": {"port": "out", "ref": "n_sort"}},
                "outputs": ["out"],
                "params": {
                    "labelColumn": "country_code",
                    "valueColumn": "total_revenue",
                    "variant": "donut",
                    "centerLabel": "Revenue",
                    "showPercents": True,
                    "title": "Revenue share by country",
                },
                "ui": {"x": 1200, "y": 460, "label": "🥧 Pie"},
            },
            {
                "id": "n_chart_map",
                "step": "export_to_map",
                "inputs": {"in": {"port": "out", "ref": "n_geom"}},
                "outputs": ["out"],
                "params": {
                    "mode": "choropleth",
                    "format": "lat_lon",
                    "location": "country_code",
                    "name_col": "country_geom_name",
                    "geometry_col": "country_geom",
                    "value_col": "total_revenue",
                    "title": "🌍 Revenue choropleth · 12 countries",
                    "color_scale": "viridis",
                    "tile_provider": "carto-light",
                    "format_out": "html",
                },
                "ui": {"x": 1200, "y": 600, "label": "🗺 Choropleth"},
            },
        ],
        "outputs": [
            {"id": "o_parquet", "name": "top_countries_parquet", "from": {"port": "out", "ref": "n_out_parquet"}},
            {"id": "o_csv",     "name": "top_countries_csv",     "from": {"port": "out", "ref": "n_out_csv"}},
            {"id": "o_xlsx",    "name": "top_countries_xlsx",    "from": {"port": "out", "ref": "n_out_xlsx"}},
            {"id": "o_pareto",  "name": "pareto_chart",          "from": {"port": "out", "ref": "n_chart_pareto"}},
            {"id": "o_pie",     "name": "pie_chart",             "from": {"port": "out", "ref": "n_chart_pie"}},
            {"id": "o_map",     "name": "choropleth",            "from": {"port": "out", "ref": "n_chart_map"}},
        ],
        "metadata": {"engineHints": {"prefer": "polars"}},
    }

    # POST the pipeline. The API doesn't have a "create from JSON" route
    # exposed by default; we use the same /pipelines POST endpoint the
    # canvas uses.
    res = _http("POST", "/pipelines", {"name": doc["name"], "document": doc})
    pid = res["id"]
    print(f"     pipeline_id: {pid}")

    # ---- 3. Run ------------------------------------------------------------
    step(3, 4, "Triggering run + polling ...")
    t0 = time.time()
    run = _http("POST", f"/pipelines/{pid}/runs", {})
    rid = run["id"]
    print(f"     run_id: {rid}  (polling every 2s)")

    last_progress = -1.0
    while True:
        time.sleep(2)
        r = _http("GET", f"/runs/{rid}")
        status = r.get("status")
        progress = r.get("progress") or 0
        if progress != last_progress:
            print(f"     [{int(time.time()-t0):3d}s] status={status} progress={progress:.0%}", flush=True)
            last_progress = progress
        if status in ("succeeded", "failed", "cancelled"):
            break

    elapsed = time.time() - t0
    if status != "succeeded":
        print(f"\nFAIL: run {status} after {elapsed:.1f}s")
        print("error:", r.get("error", "(none)"))
        return 1

    # ---- 4. Verify outputs -------------------------------------------------
    step(4, 4, f"Pipeline finished in {elapsed:.1f}s — inspecting outputs")
    run_dir = REPO_ROOT / "data" / "outputs" / rid
    print(f"\n  output dir: {run_dir}")
    if run_dir.exists():
        for p in sorted(run_dir.iterdir()):
            if p.is_file():
                size = p.stat().st_size
                size_str = (f"{size:>12,} B" if size < 1024
                            else f"{size/1024:>12.1f} KB" if size < 1024*1024
                            else f"{size/1024**2:>12.1f} MB" if size < 1024**3
                            else f"{size/1024**3:>12.1f} GB")
                print(f"    {p.name:<35} {size_str}")

    print(f"\n  total wall time: {elapsed:.1f}s "
          f"on {size_gb:.2f} GB compressed Parquet input")
    print(f"  pipeline URL: https://127.0.0.1:3443/pipelines/{pid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
