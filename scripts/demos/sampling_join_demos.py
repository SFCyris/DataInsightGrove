"""Two end-to-end demos using the new sampling methods + Join step.

Run with the backend up on http://127.0.0.1:8090:

    .venv/bin/python scripts/demos/sampling_join_demos.py

Both demos are idempotent — running twice updates the existing
pipeline rather than duplicating it (matched by name prefix).

Demo 1 — Customer churn × orders, with stratified sampling
    Generates two synthetic datasets:
      • customers  ~5,000 rows, churn_status imbalanced ~12% churned
      • orders     ~30,000 rows, customer_id linked to the above
    Then a pipeline joins them on customer_id with INNER and sets
    `metadata.sampling = stratified by churn_status, size 5000`. The
    point: a uniform random sample of a 30K-row joined table would
    return ~3,600 churned-customer orders out of 30K — too few to
    spot patterns. Stratified by churn_status preserves the 12% in
    the sample, so the live preview shows BOTH classes proportionally.

Demo 2 — Server requests × incident alerts, with time-bucket sampling
    Generates two synthetic datasets with overlapping timestamps:
      • requests   ~25,000 rows, web-server requests (1-hour buckets
                   over 28 days; some hours much busier than others)
      • alerts     ~600 rows, monitoring incidents (sparse, also over
                   the same 28-day window)
    Joins on the hour-truncated timestamp with LEFT (keep all requests,
    flag the ones that were during alert windows). Sampling: time_bucket
    on `ts_hour` with `day` granularity, 50 rows per day. The point:
    head/random sampling on a multi-day log file with bursty traffic
    over-samples the busy hours; time_bucket gives every day equal
    representation so downstream trend visualizations stay legible.

Each demo prints its pipeline URL on success; open in the browser to
explore. The Join step's params panel surfaces:
  • Cardinality strip — left × right rows + estimated result + ratio
  • 6-icon ladder for join kind (inner / left / right / full / anti-L / anti-R)
  • Auto-detected key suggestions (with match-quality bars)
  • Column collisions panel (when both sides share non-key columns)
"""
from __future__ import annotations

import io
import json
import sys
import time
import uuid
from pathlib import Path
from urllib import request as urlreq
from urllib.error import HTTPError


_API = "http://127.0.0.1:8090"
_DATA_DIR = Path("data/datasets")  # backend's cache dir, relative to repo


# ── HTTP helpers ──────────────────────────────────────────────────


def _request(method: str, path: str, body: dict | None = None) -> dict:
    url = _API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urlreq.Request(
        url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urlreq.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except HTTPError as e:
        body_str = e.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {path} → {e.code}: {body_str}") from e


def _get(path: str) -> dict:
    return _request("GET", path, None)


def _list(path: str) -> list:
    val = _request("GET", path, None)
    return val if isinstance(val, list) else []


def _post(path: str, body: dict) -> dict:
    return _request("POST", path, body)


def _upload_csv(name: str, csv_bytes: bytes) -> dict:
    """Upload a CSV via multipart to POST /datasets — same path the
    file picker uses. Returns the registered dataset row (with
    server-assigned ULID + cached parquet ready for browser fetch).
    """
    boundary = "----dig-demo-" + uuid.uuid4().hex
    crlf = b"\r\n"

    def _part(disposition: str, value: bytes, content_type: str | None = None) -> bytes:
        head = f"--{boundary}\r\nContent-Disposition: {disposition}\r\n"
        if content_type:
            head += f"Content-Type: {content_type}\r\n"
        return head.encode() + crlf + value + crlf

    body = b""
    body += _part('form-data; name="name"', name.encode())
    body += _part('form-data; name="connector_id"', b"csv")
    body += _part('form-data; name="options"', b'{"delimiter": ",", "header": true}')
    body += _part(
        f'form-data; name="file"; filename="{name}.csv"',
        csv_bytes,
        content_type="text/csv",
    )
    body += f"--{boundary}--\r\n".encode()

    req = urlreq.Request(
        _API + "/datasets",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urlreq.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except HTTPError as e:
        raise SystemExit(
            f"upload {name!r} failed: {e.code} {e.read().decode('utf-8', errors='replace')}"
        ) from e


def _ensure_dataset(name: str, csv_bytes: bytes) -> dict:
    """Idempotent — finds an existing dataset with the same name, or
    uploads. Re-runs of the demo script reuse the previously-created
    DatasetRow rather than stacking duplicates."""
    rows = _list("/datasets")
    existing = next((r for r in rows if r.get("name") == name), None)
    if existing:
        return existing
    return _upload_csv(name, csv_bytes)


def _df_to_csv_bytes(df) -> bytes:
    """Polars DataFrame → utf-8 CSV bytes via the buffer interface
    (avoids round-tripping through a temp file)."""
    buf = io.BytesIO()
    df.write_csv(buf)
    return buf.getvalue()


# ── Idempotent helpers ────────────────────────────────────────────


def _find_pipeline_by_name_prefix(prefix: str) -> str | None:
    """Match by the demo's name prefix so re-runs replace, not stack."""
    pipelines = _list("/pipelines")
    for p in pipelines:
        if (p.get("name") or "").startswith(prefix):
            return p["id"]
    return None


def _save_or_update(name_prefix: str, name: str, doc: dict) -> str:
    """Create-or-replace a pipeline by name prefix."""
    existing = _find_pipeline_by_name_prefix(name_prefix)
    if existing:
        # Replace the existing doc.
        cur = _get(f"/pipelines/{existing}")
        doc["id"] = existing
        doc["name"] = name
        body = {
            "document": doc,
            "expectedEtag": cur["etag"],
            "triggeredBy": "import",
        }
        try:
            _request("PUT", f"/pipelines/{existing}", body)
            return existing
        except SystemExit:
            # Etag mismatch or similar — fall through to create new.
            pass
    res = _post("/pipelines", {"name": name, "document": doc})
    return res["id"]


# ── Demo 1: Customer churn × orders, stratified sampling ──────────


def _make_customers_orders_dfs():
    """Generate two synthetic Polars DataFrames: customers (imbalanced
    churn) + orders (linked by customer_id). Returns (customers_df,
    orders_df).
    """
    import polars as pl
    import random
    random.seed(42)

    n_customers = 5_000
    churn_rate = 0.12
    plans = ["free", "basic", "pro", "enterprise"]
    plan_weights = [0.40, 0.35, 0.20, 0.05]

    customers = []
    for i in range(n_customers):
        is_churned = random.random() < churn_rate
        customers.append({
            "customer_id": i + 1,
            "name": f"Customer {i+1:05d}",
            "churn_status": "churned" if is_churned else "active",
            "plan_tier": random.choices(plans, weights=plan_weights)[0],
            "signup_year": random.choice([2021, 2022, 2023, 2024]),
        })
    customers_df = pl.DataFrame(customers)

    orders = []
    order_id = 1
    for c in customers:
        n_orders = (
            random.randint(0, 3) if c["churn_status"] == "churned"
            else random.randint(2, 12)
        )
        for _ in range(n_orders):
            orders.append({
                "order_id": order_id,
                "customer_id": c["customer_id"],
                "total": round(random.uniform(15.0, 450.0), 2),
                "order_year": random.choice([2023, 2024, 2025]),
            })
            order_id += 1
    orders_df = pl.DataFrame(orders)
    return customers_df, orders_df


def _doc_dataset_entry(row: dict, label: str) -> dict:
    """Build a `datasets[]` entry from a registered DatasetRow. Uses
    the canonical `ds_<ulid_lowercase>` alias and connector='parquet'
    pointing at the cached parquet path (which is what the dataset
    picker would emit when adding the same dataset via the UI).
    """
    storage_uri = row.get("storageUri") or row.get("storage_uri")
    return {
        "id": f"ds_{row['id'].lower()}",
        "connector": "parquet",
        "uri": storage_uri,
        "label": label,
        "options": {},
    }


def demo1_churn_stratified() -> None:
    print("\n=== Demo 1: customer churn × orders, stratified sampling ===")
    print("Generating + uploading synthetic data…")
    customers_df, orders_df = _make_customers_orders_dfs()
    cust = _ensure_dataset(
        "demo · customers (churn imbalanced)",
        _df_to_csv_bytes(customers_df),
    )
    orders = _ensure_dataset(
        "demo · orders (linked to customers)",
        _df_to_csv_bytes(orders_df),
    )
    print(f"  customers: {cust['id']}  ({cust.get('rowCount')} rows)")
    print(f"  orders:    {orders['id']}  ({orders.get('rowCount')} rows)")

    doc = {
        "schemaVersion": 1,
        "datasets": [
            _doc_dataset_entry(cust, "customers"),
            _doc_dataset_entry(orders, "orders"),
        ],
        "nodes": [
            {
                "id": "n_join",
                "step": "join",
                "stepVersion": "1.1.0",
                "inputs": {
                    "left":  {"ref": f"ds_{cust['id'].lower()}"},
                    "right": {"ref": f"ds_{orders['id'].lower()}"},
                },
                "outputs": ["out"],
                "params": {
                    "kind": "inner",
                    "keys": [{"left": "customer_id", "right": "customer_id", "op": "="}],
                    "columnCollisions": "keep_both",
                    "suffixes": ["_cust", "_order"],
                },
                "ui": {"x": 220, "y": 240, "label": "🔗 customers ⋈ orders"},
            },
        ],
        "outputs": [],
        "metadata": {
            "sampling": {
                "method": "stratified",
                "size": 5_000,
                "column": "churn_status",
                "seed": 42,
            },
        },
    }
    pid = _save_or_update(
        "🔗 Demo 1 ·",
        "🔗 Demo 1 · Customer churn × orders (stratified)",
        doc,
    )
    print(f"  Pipeline: {pid}")
    print(f"  URL:      http://localhost:3000/pipelines/{pid}")
    print("  What to try:")
    print("   1. Focus the join. The cardinality strip shows ~5K customers ×")
    print("      ~30K orders → ~30K result (1.0× max input — no fan-out, ✓).")
    print("   2. Open 🧪 sampling — see 'Stratified by column' is selected with")
    print("      column=churn_status. Toggle to 'Random uniform' and watch the")
    print("      churned-row count in the live grid drop dramatically.")
    print("   3. Switch the join's column-collision rule from `keep_both` to")
    print("      `coalesce`. The duplicate `*_year` columns collapse to one.")


# ── Demo 2: IoT anomaly × ER load, time-bucket sampling ──────────


def _make_requests_alerts_dfs():
    """Generate two synthetic Polars DataFrames: web-server requests +
    incident alerts. Both span the same 28-day window so an INNER/LEFT
    join on hour-truncated `ts_hour` produces non-empty results.
    """
    import polars as pl
    import random
    from datetime import datetime, timedelta
    random.seed(7)

    base = datetime(2026, 1, 1, 0, 0)
    # Requests — bursty traffic: some hours have 50+ requests, others <5.
    requests = []
    rid = 1
    for d in range(28):
        for h in range(24):
            # Bursts: hours 9-12 + 18-22 are 5x heavier; off-hours quieter.
            heavy = (9 <= h <= 12) or (18 <= h <= 22)
            n = random.randint(20, 80) if heavy else random.randint(0, 8)
            for _ in range(n):
                ts = base + timedelta(days=d, hours=h, minutes=random.randint(0, 59))
                requests.append({
                    "request_id": rid,
                    "ts": ts,
                    "ts_hour": ts.replace(minute=0, second=0, microsecond=0),
                    "endpoint": random.choice(["/api/users", "/api/orders", "/api/search", "/api/checkout"]),
                    "status": random.choices([200, 200, 200, 200, 500, 404], k=1)[0],
                    "latency_ms": random.randint(20, 800),
                })
                rid += 1

    # Alerts — sparse incident events, ~25/day with peaks during heavy hours.
    alerts = []
    aid = 1
    for d in range(28):
        n_alerts = random.randint(15, 40)
        for _ in range(n_alerts):
            h = random.choices(range(24), weights=[1]*9 + [3]*4 + [1]*5 + [3]*5 + [1])[0]
            ts = base + timedelta(days=d, hours=h, minutes=random.randint(0, 59))
            alerts.append({
                "alert_id": aid,
                "ts": ts,
                "ts_hour": ts.replace(minute=0, second=0, microsecond=0),
                "severity": random.choices(["info", "warn", "critical"], weights=[5, 3, 1])[0],
                "service": random.choice(["api", "db", "cache", "queue"]),
            })
            aid += 1

    requests_df = pl.DataFrame(requests)
    alerts_df = pl.DataFrame(alerts)
    return requests_df, alerts_df


def demo2_requests_alerts_timebucket() -> None:
    print("\n=== Demo 2: server requests × alerts, time-bucket sampling ===")
    print("Generating + uploading synthetic data…")
    requests_df, alerts_df = _make_requests_alerts_dfs()
    req = _ensure_dataset(
        "demo · server requests (bursty traffic)",
        _df_to_csv_bytes(requests_df),
    )
    alert = _ensure_dataset(
        "demo · incident alerts",
        _df_to_csv_bytes(alerts_df),
    )
    print(f"  requests: {req['id']}  ({req.get('rowCount')} rows)")
    print(f"  alerts:   {alert['id']}  ({alert.get('rowCount')} rows)")

    doc = {
        "schemaVersion": 1,
        "datasets": [
            _doc_dataset_entry(req, "requests"),
            _doc_dataset_entry(alert, "alerts"),
        ],
        "nodes": [
            {
                "id": "n_join",
                "step": "join",
                "stepVersion": "1.1.0",
                "inputs": {
                    "left":  {"ref": f"ds_{req['id'].lower()}"},
                    "right": {"ref": f"ds_{alert['id'].lower()}"},
                },
                "outputs": ["out"],
                "params": {
                    "kind": "left",
                    "keys": [{"left": "ts_hour", "right": "ts_hour", "op": "="}],
                    "columnCollisions": "keep_both",
                    "suffixes": ["_req", "_alert"],
                },
                "ui": {"x": 220, "y": 240, "label": "🔗 requests ⋈ alerts (by hour)"},
            },
        ],
        "outputs": [],
        "metadata": {
            # Time-bucket sampling — 50 rows per day on the request
            # side's `ts_hour`. Without it, head/random would over-
            # represent the bursty hours (9-12, 18-22) since they
            # contribute 5× more rows than off-hours; the live preview
            # would look like "the system is always busy" when the
            # truth is "busy in 9 hours, quiet in 15." Time-bucket
            # gives every day equal representation.
            "sampling": {
                "method": "time_bucket",
                "size": 50,
                "timeColumn": "ts_hour",
                "bucket": "day",
                "seed": 42,
            },
        },
    }
    pid = _save_or_update(
        "🔗 Demo 2 ·",
        "🔗 Demo 2 · Requests × alerts (time-bucket)",
        doc,
    )
    print(f"  Pipeline: {pid}")
    print(f"  URL:      http://localhost:3000/pipelines/{pid}")
    print("  What to try:")
    print("   1. Focus the join — auto-detected `ts_hour ↔ ts_hour` suggestion")
    print("      should appear (same name, both timestamp). Click ➕ to accept.")
    print("   2. Cardinality strip: ~25K requests × ~600 alerts → ~Nx requests")
    print("      (most request-hours have NO alert → LEFT keeps them with NULLs).")
    print("   3. Open 🧪 sampling — see 'N rows per time bucket' with day +")
    print("      ts_hour. Switch to 'Random uniform' for comparison: random")
    print("      over-samples the bursty 9am-12pm + 6pm-10pm windows.")
    print("   4. Try kind=anti_left on the icon ladder — surfaces request hours")
    print("      that WEREN'T flagged with any alert (most of them).")


# ── Driver ────────────────────────────────────────────────────────


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    if not (repo_root / "data").exists():
        print(f"ERROR: expected to run from repo root; got {repo_root}", file=sys.stderr)
        sys.exit(1)
    # Health check.
    try:
        _get("/health")
    except SystemExit:
        print("Backend not reachable on", _API, file=sys.stderr)
        sys.exit(1)
    demo1_churn_stratified()
    time.sleep(0.5)
    demo2_requests_alerts_timebucket()
    print("\nDone. Open the URLs above to explore.")


if __name__ == "__main__":
    main()
