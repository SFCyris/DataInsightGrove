"""Phase A lineage testbed — non-trivial pipeline that exercises Layers 1-4.

Run with the backend up on http://127.0.0.1:8090:

    .venv/bin/python scripts/demos/phase_a_lineage_testbed.py

Idempotent — re-running updates the existing pipeline + datasets in
place (matched by name prefix). Open the printed pipeline URL after
running to validate the layers visually.

The story:

    Three plant-cost source datasets — production, labor, utilities —
    join into a single per-plant total_cost. Total = production_cost +
    labor_cost + energy_cost; each subterm is itself derived. Final
    step aggregates by plant.

What each layer should show:

  Layer 1 (run-state strip + clock chip)
      Every node carries a green strip after the run. The terminal
      group_aggregate node shows row count + relative time.

  Layer 2 (freshness halo)
      The terminal `cost_summary` node has a freshness policy declared
      (sla=2h, warn_at=30m). After the run, halo is green; after 90m
      it flips amber; after 2h it flips red.

  Layer 3 (column-anywhere trace)
      Hover the `total_cost` column header in the live grid → every
      canvas node EXCEPT the lineage chain (sources → derives →
      aggregate) dims to ~22% opacity. Hover `plant` → only the
      production source + final aggregate light up (it passes through
      unchanged).

  Layer 4 (groups)
      A node group named "Cost calculation" wraps the 4 derive steps
      that build production_cost, labor_cost, energy_cost, total_cost.
      Dashed border carries the group's worst-case freshness color.

Pipeline structure (10 steps + 3 sources + 1 group + 1 terminal):

   📥 production  ─┐
                   ├─ 🔗 join_pl ─→ ➕ derive labor_cost ─┐
   📥 labor       ─┘                                        │
                                                            ├─ ➕ total_cost ─→ 🧮 by plant ─→ 📊 cost_summary
   📥 utilities ──→ ➕ derive energy_cost ──────────────────┘
                  + ➕ derive production_cost
"""
from __future__ import annotations

import io
import json
import random
import sys
import time
import uuid
from pathlib import Path
from urllib import request as urlreq
from urllib.error import HTTPError, URLError


_API = "http://127.0.0.1:8090"
_PIPELINE_NAME = "Phase A lineage testbed — plant cost analysis"
_RNG_SEED = 42

# When the backend was started in --global / --lan mode, it requires a
# bearer token. The DIG-managed token lives at ~/.config/dig/auth.token
# (or via DIG_AUTH_TOKEN env). Pick whichever is present; fall through
# silently in --local mode where no auth is enforced.
def _auth_headers() -> dict[str, str]:
    import os
    from pathlib import Path
    tok = os.environ.get("DIG_AUTH_TOKEN")
    if not tok:
        p = Path.home() / ".config" / "dig" / "auth.token"
        if p.exists():
            tok = p.read_text().strip()
    return {"Authorization": f"Bearer {tok}"} if tok else {}


_AUTH = _auth_headers()


# ── HTTP helpers ──────────────────────────────────────────────────


def _request(method: str, path: str, body: dict | None = None) -> dict:
    url = _API + path
    data = json.dumps(body).encode() if body is not None else None
    headers = dict(_AUTH)
    if data:
        headers["Content-Type"] = "application/json"
    req = urlreq.Request(
        url, data=data, method=method,
        headers=headers,
    )
    try:
        with urlreq.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except HTTPError as e:
        body_str = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {path} → {e.code}: {body_str}") from e
    except URLError as e:
        raise SystemExit(f"backend not reachable at {_API} — start it with ./start.sh") from e


def _get(path: str) -> dict:
    return _request("GET", path, None)


def _list(path: str) -> list:
    val = _request("GET", path, None)
    return val if isinstance(val, list) else []


def _post(path: str, body: dict) -> dict:
    return _request("POST", path, body)


def _put(path: str, body: dict) -> dict:
    return _request("PUT", path, body)


def _upload_csv(name: str, csv_bytes: bytes) -> dict:
    """Upload a CSV via multipart to POST /datasets — same path the file
    picker uses. Returns the registered dataset row."""
    boundary = "----dig-testbed-" + uuid.uuid4().hex
    crlf = b"\r\n"

    def _part(disposition: str, value: bytes, content_type: str | None = None) -> bytes:
        head = f"--{boundary}\r\nContent-Disposition: {disposition}\r\n"
        if content_type:
            head += f"Content-Type: {content_type}\r\n"
        return head.encode() + crlf + value + crlf

    body = b""
    body += _part(f'form-data; name="file"; filename="{name}.csv"', csv_bytes, "text/csv")
    body += _part('form-data; name="connector"', b"csv")
    body += _part('form-data; name="label"', name.encode())
    body += f"--{boundary}--\r\n".encode()

    headers = dict(_AUTH)
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    req = urlreq.Request(
        _API + "/datasets",
        data=body,
        method="POST",
        headers=headers,
    )
    with urlreq.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


# ── synthetic data ────────────────────────────────────────────────


def _generate_csvs() -> dict[str, bytes]:
    """Three small CSVs, ~80 rows each, reproducible via _RNG_SEED.

    Each row keys on (id, plant). Plants: 4 names. IDs: a-001..a-080.
    Some rows in `labor` have unusual overtime that the pipeline will
    smooth via derive — useful for demoing column trace.
    """
    rng = random.Random(_RNG_SEED)
    plants = ["Aurora", "Beacon", "Cypress", "Delta"]
    ids = [f"a-{i:03d}" for i in range(1, 81)]

    # production.csv: how many units each (id, plant) made + per-unit cost
    prod = io.StringIO()
    prod.write("id,plant,units_produced,unit_cost\n")
    for i in ids:
        plant = rng.choice(plants)
        units = rng.randint(50, 800)
        unit_cost = round(rng.uniform(2.5, 18.0), 2)
        prod.write(f"{i},{plant},{units},{unit_cost}\n")

    # labor.csv: hours worked + base wage + overtime adjustment
    labor = io.StringIO()
    labor.write("id,plant,hours,base_wage,overtime\n")
    for i in ids:
        # Use the same plant assignment by re-seeding the per-row choice
        # from the id — keeps the join key consistent.
        plant_rng = random.Random(_RNG_SEED + hash(i))
        plant = plant_rng.choice(plants)
        hours = round(rng.uniform(20, 200), 1)
        base_wage = round(rng.uniform(15.0, 45.0), 2)
        overtime = round(rng.uniform(0, 600), 2)
        labor.write(f"{i},{plant},{hours},{base_wage},{overtime}\n")

    # utilities.csv: fuel + material handling
    util = io.StringIO()
    util.write("id,plant,fuel,material_handling\n")
    for i in ids:
        plant_rng = random.Random(_RNG_SEED + hash(i))
        plant = plant_rng.choice(plants)
        fuel = round(rng.uniform(50, 800), 2)
        mat = round(rng.uniform(100, 2200), 2)
        util.write(f"{i},{plant},{fuel},{mat}\n")

    return {
        "phase_a_production": prod.getvalue().encode(),
        "phase_a_labor": labor.getvalue().encode(),
        "phase_a_utilities": util.getvalue().encode(),
    }


# ── pipeline construction ─────────────────────────────────────────


def _doc_dataset_entry(row: dict, label: str) -> dict:
    """Build a datasets[] entry — uses ds_<ulid_lower> alias + parquet
    connector pointing at the cached parquet path (matches what the
    dataset picker would emit via the UI)."""
    storage_uri = row.get("storageUri") or row.get("storage_uri")
    return {
        "id": f"ds_{row['id'].lower()}",
        "connector": "parquet",
        "uri": storage_uri,
        "label": label,
        "options": {},
    }


def _build_pipeline_doc(
    pipeline_id: str,
    ds_production: str,
    ds_labor: str,
    ds_utilities: str,
    ds_production_row: dict,
    ds_labor_row: dict,
    ds_utilities_row: dict,
) -> dict:
    """Construct the pipeline document. Hand-built rather than via the
    pipeline API's add-step calls so we get exact control over node ids
    + freshness + groups in one shot."""
    nodes: list[dict] = [
        # cast unit_cost to currency (demos column-lineage with type change)
        {
            "id": "cast_unit_cost",
            "step": "cast_type",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"ref": ds_production, "port": "out"}},
            "outputs": ["out"],
            "params": {"column": "unit_cost", "targetType": "currency"},
            "ui": {"x": 320, "y": 80, "label": "cast unit_cost → currency"},
        },
        # production_cost = unit_cost * units_produced
        {
            "id": "derive_production_cost",
            "step": "derive_column",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"ref": "cast_unit_cost", "port": "out"}},
            "outputs": ["out"],
            "params": {
                "name": "production_cost",
                "expression": '"unit_cost" * "units_produced"',
            },
            "ui": {"x": 600, "y": 80, "label": "derive production_cost"},
        },
        # join production + labor on (id, plant)
        {
            "id": "join_pl",
            "step": "join",
            "stepVersion": "1.3.0",
            "inputs": {
                "left": {"ref": "derive_production_cost", "port": "out"},
                "right": {"ref": ds_labor, "port": "out"},
            },
            "outputs": ["out"],
            "params": {
                "kind": "inner",
                "keys": [
                    {"left": "id", "right": "id", "op": "="},
                    {"left": "plant", "right": "plant", "op": "="},
                ],
                "columnCollisions": "keep_left",
            },
            "ui": {"x": 880, "y": 80, "label": "join production ⨝ labor"},
        },
        # labor_cost = (base_wage * hours) + overtime
        {
            "id": "derive_labor_cost",
            "step": "derive_column",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"ref": "join_pl", "port": "out"}},
            "outputs": ["out"],
            "params": {
                "name": "labor_cost",
                "expression": '("base_wage" * "hours") + "overtime"',
            },
            "ui": {"x": 1160, "y": 80, "label": "derive labor_cost"},
        },
        # join with utilities on (id, plant)
        {
            "id": "join_util",
            "step": "join",
            "stepVersion": "1.3.0",
            "inputs": {
                "left": {"ref": "derive_labor_cost", "port": "out"},
                "right": {"ref": ds_utilities, "port": "out"},
            },
            "outputs": ["out"],
            "params": {
                "kind": "inner",
                "keys": [
                    {"left": "id", "right": "id", "op": "="},
                    {"left": "plant", "right": "plant", "op": "="},
                ],
                "columnCollisions": "keep_left",
            },
            "ui": {"x": 1440, "y": 80, "label": "join + utilities"},
        },
        # energy_cost = fuel + material_handling
        {
            "id": "derive_energy_cost",
            "step": "derive_column",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"ref": "join_util", "port": "out"}},
            "outputs": ["out"],
            "params": {
                "name": "energy_cost",
                "expression": '"fuel" + "material_handling"',
            },
            "ui": {"x": 1720, "y": 80, "label": "derive energy_cost"},
        },
        # total_cost = production_cost + labor_cost + energy_cost
        {
            "id": "derive_total_cost",
            "step": "derive_column",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"ref": "derive_energy_cost", "port": "out"}},
            "outputs": ["out"],
            "params": {
                "name": "total_cost",
                "expression": '"production_cost" + "labor_cost" + "energy_cost"',
            },
            "ui": {"x": 2000, "y": 80, "label": "derive total_cost"},
        },
        # group_aggregate by plant — final summary
        {
            "id": "cost_summary",
            "step": "group_aggregate",
            "stepVersion": "1.0.0",
            "inputs": {"in": {"ref": "derive_total_cost", "port": "out"}},
            "outputs": ["out"],
            "params": {
                "groupBy": ["plant"],
                "aggregates": [
                    {"fn": "sum", "column": "total_cost", "as": "plant_total"},
                    {"fn": "sum", "column": "production_cost", "as": "plant_production"},
                    {"fn": "sum", "column": "labor_cost", "as": "plant_labor"},
                    {"fn": "sum", "column": "energy_cost", "as": "plant_energy"},
                    {"fn": "count"},
                ],
            },
            # Freshness policy on the terminal node — drives Layer 2 halo.
            "ui": {
                "x": 2280, "y": 80,
                "label": "cost summary by plant",
                "freshness": {"sla": "2h", "warn_at": "30m"},
            },
        },
    ]

    return {
        "schemaVersion": 1,
        "id": pipeline_id,
        "name": _PIPELINE_NAME,
        "description": (
            "Phase A lineage UX testbed — exercises run-state, freshness, "
            "column trace, and groups across a multi-source cost calculation."
        ),
        "datasets": [
            _doc_dataset_entry(ds_production_row, "production"),
            _doc_dataset_entry(ds_labor_row, "labor"),
            _doc_dataset_entry(ds_utilities_row, "utilities"),
        ],
        "nodes": nodes,
        "outputs": [],
        # Phase A Layer 4 — group the cost-calculation steps so the user
        # sees the dashed boundary on the canvas.
        "groups": [
            {
                "id": "g_cost_calc",
                "label": "Cost calculation",
                "node_ids": [
                    "derive_production_cost",
                    "derive_labor_cost",
                    "derive_energy_cost",
                    "derive_total_cost",
                ],
                "ui": {"collapsed": False},
            },
        ],
        "metadata": {},
        "webhooks": [],
    }


# ── orchestration ─────────────────────────────────────────────────


def _find_or_create_pipeline(name: str) -> str:
    """Idempotent: if a pipeline with this name exists, return its id;
    otherwise create + return."""
    existing = _list("/pipelines?limit=200")
    for p in existing:
        if p.get("name") == name:
            return p["id"]
    created = _post("/pipelines", {"name": name})
    return created["id"]


def _put_pipeline_document(pipeline_id: str, doc: dict, etag: int) -> dict:
    """Save the pipeline document. Uses the conditional PUT with etag."""
    return _put(
        f"/pipelines/{pipeline_id}",
        {"document": doc, "expectedEtag": etag},
    )


def main() -> None:
    print("→ checking backend...")
    try:
        _get("/health")
    except SystemExit as e:
        print(e)
        sys.exit(1)
    print("  ✓ backend reachable")

    # ── Step 1: synthesize + upload datasets (idempotent by name) ──
    print("→ uploading sample CSVs...")
    csvs = _generate_csvs()

    # The /datasets endpoint returns datasets keyed on "name", not "label".
    # Cache the full row so we can extract storageUri later for the pipeline doc.
    existing_ds = {d.get("name", ""): d for d in _list("/datasets?limit=500")}
    ds_rows: dict[str, dict] = {}
    for label, raw in csvs.items():
        if label in existing_ds:
            ds_rows[label] = existing_ds[label]
            print(f"  ✓ {label} (existing, id={existing_ds[label]['id'][-8:]})")
        else:
            res = _upload_csv(label, raw)
            ds_rows[label] = res
            print(f"  ✓ {label} (new, id={res['id'][-8:]})")

    # ── Step 2: pipeline ──
    print("→ creating pipeline (idempotent)...")
    pid = _find_or_create_pipeline(_PIPELINE_NAME)
    print(f"  ✓ pipeline id: {pid}")

    p = _get(f"/pipelines/{pid}")
    etag = p.get("etag", 0)

    # The pipeline document refs datasets via the canonical
    # ds_<ulid_lower> alias (NOT the raw ULID).
    def _alias(row: dict) -> str:
        return f"ds_{row['id'].lower()}"

    doc = _build_pipeline_doc(
        pipeline_id=pid,
        ds_production=_alias(ds_rows["phase_a_production"]),
        ds_labor=_alias(ds_rows["phase_a_labor"]),
        ds_utilities=_alias(ds_rows["phase_a_utilities"]),
        ds_production_row=ds_rows["phase_a_production"],
        ds_labor_row=ds_rows["phase_a_labor"],
        ds_utilities_row=ds_rows["phase_a_utilities"],
    )
    _put_pipeline_document(pid, doc, etag)
    print(f"  ✓ saved pipeline document ({len(doc['nodes'])} nodes, {len(doc['groups'])} groups)")

    # ── Step 3: run it (so node_metrics populates) ──
    print("→ running pipeline (so canvas Layer 1 has run-state to render)...")
    run = _post(f"/pipelines/{pid}/runs", {})
    run_id = run["id"]
    print(f"  ✓ run queued: {run_id}")

    # Poll until terminal — keep it brief; at most 30s for this small data.
    for _ in range(60):
        time.sleep(0.5)
        r = _get(f"/runs/{run_id}")
        if r["status"] in ("succeeded", "failed"):
            print(f"  ✓ run {r['status']}")
            if r["status"] == "failed":
                print(f"    error: {r.get('error', '?')[:300]}")
            break
    else:
        print("  ⚠ run did not finish within 30s — check the pipeline manually")

    print()
    print("✅ Testbed ready. Open in the browser:")
    print(f"   http://localhost:3000/pipelines/{pid}")
    print()
    print("What to look for, layer by layer:")
    print("  • Layer 1 — every step has a green strip; cost_summary chips show row count + time ago")
    print("  • Layer 2 — cost_summary has a green halo (turns amber after 90m, red after 2h)")
    print("  • Layer 3 — hover `total_cost` column header → canvas dims off-lineage nodes")
    print("  • Layer 4 — dashed 'Cost calculation' group around the 4 derive steps")


if __name__ == "__main__":
    main()
