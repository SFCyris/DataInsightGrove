#!/usr/bin/env python3
"""End-to-end validator — create + run pipelines exercising every step.

What this does:
  1. Uploads two real datasets via /datasets (small + larger).
  2. For each step in the registry, builds a minimal pipeline that uses it
     against the appropriate dataset, then validates + runs it via the API.
  3. Records pass/fail per step + a one-line reason on failure.
  4. Cleans up.

Run while the DIG backend is up (default :8080):
    python3 scripts/e2e_validate.py

Exit code 0 if all steps pass, 1 otherwise. Prints a final summary table.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

REPO = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8080"


# ---- HTTP helpers ----------------------------------------------------------

def req(method: str, path: str, body: Any = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    h = {"Accept": "application/json"}
    if data:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(f"{API}{path}", data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            body = json.loads(body)
        except Exception:
            pass
        return e.code, body


def upload_csv(path: Path, name: str) -> str:
    """Multipart upload via stdlib. Returns dataset id."""
    import mimetypes, uuid
    boundary = f"----dig{uuid.uuid4().hex}"
    body = bytearray()
    def part(field: str, value: str) -> None:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{field}"\r\n\r\n'.encode())
        body.extend(value.encode()); body.extend(b"\r\n")
    part("name", name)
    part("connector_id", "csv")
    part("options", '{"delimiter":",","header":true}')
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode()
    )
    body.extend(b"Content-Type: text/csv\r\n\r\n")
    body.extend(path.read_bytes()); body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    r = urllib.request.Request(
        f"{API}/datasets",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(r, timeout=60) as resp:
        ds = json.loads(resp.read())
    # Wait for ingest.
    for _ in range(30):
        c, d = req("GET", f"/datasets/{ds['id']}")
        if d.get("status") == "ready":
            return ds["id"]
        time.sleep(0.3)
    raise RuntimeError(f"dataset {ds['id']} never became ready")


def run_pipeline(doc: dict[str, Any], sample_rows: int | None = None) -> tuple[str, dict[str, Any]]:
    """Create a pipeline doc, run it, return (pipeline_id, final run dict)."""
    code, p = req("POST", "/pipelines", {"name": doc.get("name", "e2e"), "document": doc})
    if code != 201:
        raise RuntimeError(f"create failed: {code} {p}")
    pid = p["id"]
    body = {"sampleRows": sample_rows} if sample_rows else {}
    code, run = req("POST", f"/pipelines/{pid}/runs", body)
    if code != 202:
        raise RuntimeError(f"run start failed: {code} {run}")
    rid = run["id"]
    for _ in range(60):
        time.sleep(0.4)
        code, r = req("GET", f"/runs/{rid}")
        if r["status"] in ("succeeded", "failed"):
            return pid, r
    return pid, r  # timed out → return last seen


# ---- Pipeline doc fragments ------------------------------------------------

def doc(name: str, datasets: list[dict[str, Any]], nodes: list[dict[str, Any]],
        outputs: list[dict[str, Any]], metadata: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
    return {
        "schemaVersion": 1, "id": "PLACEHOLDER", "name": name,
        "datasets": datasets, "nodes": nodes, "outputs": outputs,
        "metadata": metadata or {},
    }


def ds(id_: str, uri: str) -> dict[str, Any]:
    return {"id": id_, "connector": "parquet", "uri": uri}


def node(id_: str, step: str, params: dict[str, Any], in_ref: str = "ds",
         port: str = "in", inputs: dict[str, dict[str, str]] | None = None,
         ) -> dict[str, Any]:
    return {
        "id": id_, "step": step, "stepVersion": "1.0.0",
        "inputs": inputs or {port: {"ref": in_ref}},
        "outputs": ["out"], "params": params,
    }


def out(node_id: str, name: str = "out") -> list[dict[str, Any]]:
    return [{"id": "o", "name": name, "from": {"ref": node_id}}]


# ---- Per-step pipeline factories -------------------------------------------
# Each factory returns a pipeline doc that exercises one step. Most build a
# single-node pipeline; combine steps build two-input ones.

def factory_single(step: str, params: dict[str, Any]):
    """Trivial: dataset → step → output."""
    def make(uri: str, _uri2: str | None = None):
        return doc(f"e2e:{step}", [ds("ds", uri)],
                   [node("n", step, params)], out("n"))
    return make


# Datasets are stored as parquet under the cached path. We need column names
# that match. The customers dataset has these columns:
CUSTOMERS_COLS = ["customer_id", "name", "email", "country", "plan",
                  "signup_date", "last_login", "monthly_revenue", "status"]
SALES_COLS = ["date", "region", "product", "orders", "revenue"]
FLOWERS_COLS = ["petal_length", "petal_width", "sepal_length", "sepal_width", "species"]
STOCK_COLS = ["date", "ticker", "close", "volume"]


PIPELINES: dict[str, Any] = {
    # Shape category --------------------------------------------------------
    "filter_rows": factory_single(
        "filter_rows", {"predicate": '"status" = \'active\''}
    ),
    "select_columns": factory_single(
        "select_columns", {"columns": ["customer_id", "name", "country"]}
    ),
    "rename_columns": factory_single(
        "rename_columns", {"mapping": [{"from": "country", "to": "iso"}]}
    ),
    "sort_rows": factory_single(
        "sort_rows", {"by": [{"column": "monthly_revenue", "direction": "desc"}]}
    ),
    "sample_rows": factory_single(
        "sample_rows", {"n": 10, "seed": 42}
    ),
    "split_column": factory_single(
        "split_column", {"column": "email", "delimiter": "@"}
    ),

    # Clean ------------------------------------------------------------------
    "cast_type": factory_single(
        "cast_type", {"column": "monthly_revenue", "targetType": "double"}
    ),
    "clean_whitespace": factory_single(
        "clean_whitespace", {"column": "name", "collapse": True, "lowercase": False}
    ),
    "coalesce_columns": factory_single(
        "coalesce_columns", {"columns": ["email", "name"], "as": "contact"}
    ),
    "deduplicate": factory_single(
        "deduplicate", {"columns": ["country"], "keep": "first"}
    ),
    "expectations": factory_single(
        "expectations",
        {"rules": [
            {"kind": "not_null", "column": "customer_id"},
            {"kind": "in", "column": "status", "values": ["active", "churned", "trial"]},
        ], "fail_on_violation": False},
    ),
    "replace_text": factory_single(
        "replace_text", {"column": "name", "find": "User ", "replace": "Customer "}
    ),
    "round_to_n": factory_single(
        "round_to_n", {"column": "monthly_revenue", "decimals": 0}
    ),
    "upper_string": factory_single(
        "upper_string", {"column": "country"}
    ),

    # Derive -----------------------------------------------------------------
    "bin_numeric": factory_single(
        "bin_numeric", {"column": "monthly_revenue", "bins": 4, "as": "rev_bin"}
    ),
    "derive_column": factory_single(
        "derive_column", {"name": "is_premium",
                          "expression": "CASE WHEN \"plan\" = 'enterprise' THEN 1 ELSE 0 END"}
    ),
    "extract_date_parts": factory_single(
        "extract_date_parts", {"column": "signup_date", "parts": ["year", "month"]}
    ),
    "extract_pattern": factory_single(
        "extract_pattern", {"column": "email", "pattern": "@(.+)$", "as": "domain"}
    ),
    "zscore": factory_single(
        "zscore", {"column": "monthly_revenue", "output_column": "rev_z"}
    ),

    # ML / stats (uses flowers dataset for numeric features) -----------------
    "pca": factory_single(
        "pca", {"columns": FLOWERS_COLS[:4], "n_components": 2,
                "color_by": "species", "render": True}
    ),
    "kmeans": factory_single(
        "kmeans", {"columns": FLOWERS_COLS[:4], "k": 3, "render": True}
    ),
    "dbscan": factory_single(
        "dbscan", {"columns": FLOWERS_COLS[:2], "eps": 0.5, "min_samples": 5, "render": True}
    ),
    "tsne": factory_single(
        "tsne", {"columns": FLOWERS_COLS[:4], "perplexity": 10,
                 "max_rows": 150, "color_by": "species", "render": True}
    ),
    "umap": factory_single(
        "umap", {"columns": FLOWERS_COLS[:4], "n_neighbors": 10,
                 "color_by": "species", "render": True}
    ),
    "linear_regression": factory_single(
        "linear_regression", {"y": "petal_length",
                              "x_columns": ["petal_width", "sepal_length"], "render": True}
    ),
    "correlation_matrix": factory_single(
        "correlation_matrix", {"columns": FLOWERS_COLS[:4], "method": "pearson", "render": True}
    ),

    # Time-series (uses stock dataset) --------------------------------------
    "resample": factory_single(
        "resample", {"time_column": "date", "interval": "7d",
                     "aggregations": [{"column": "close", "fn": "mean", "as": "close_mean"}]}
    ),
    "rolling": factory_single(
        "rolling", {"time_column": "date",
                    "windows": [{"column": "close", "fn": "mean", "window": 7,
                                 "as": "close_ma7"}]}
    ),
    "seasonal_decompose": factory_single(
        "seasonal_decompose", {"time_column": "date", "value_column": "close",
                               "model": "additive", "period": 7, "render": True}
    ),
    "forecast": factory_single(
        "forecast", {"time_column": "date", "value_column": "close", "horizon": 14,
                     "method": "holt_winters", "seasonal_period": 7, "render": True}
    ),

    # Aggregate --------------------------------------------------------------
    "group_aggregate": factory_single(
        "group_aggregate",
        {"groupBy": ["country"],
         "aggregates": [{"fn": "count", "as": "n"},
                         {"fn": "sum", "column": "monthly_revenue", "as": "revenue"}]},
    ),
    "pivot_wider": factory_single(
        "pivot_wider", {"id": ["country"], "names": "plan",
                        "values": "monthly_revenue", "agg": "sum"}
    ),
    "pivot_longer": factory_single(
        "pivot_longer", {"id": ["customer_id"], "value_cols": ["monthly_revenue"],
                         "names_to": "metric", "values_to": "amount"}
    ),
    "window_aggregate": factory_single(
        "window_aggregate",
        {"fn": "row_number", "as": "rank",
         "partitionBy": ["country"],
         "orderBy": [{"column": "monthly_revenue", "direction": "desc"}]},
    ),

    # Combine — needs special two-input handling ----------------------------
    # join + union + subpipeline → handled below in run_two_input_specials()
    # Output -----------------------------------------------------------------
    "export_to_file": factory_single(
        "export_to_file", {"format": "csv", "path": "e2e-out.csv"}
    ),
    "export_to_image": factory_single(
        "export_to_image", {"kind": "bar_counts", "x": "country",
                            "title": "Customers per country", "format": "png"}
    ),
    # export_to_db needs SQLite available with a writable path; tested separately.
}


# ---- Main ------------------------------------------------------------------

def main() -> int:
    print("📦 Uploading datasets…")
    customers = REPO / "samples" / "customers-demo.csv"
    flowers = REPO / "samples" / "flowers-demo.csv"
    stock = REPO / "samples" / "stock-demo.csv"

    cust_id = upload_csv(customers, "e2e:customers")
    flow_id = upload_csv(flowers, "e2e:flowers")
    stock_id = upload_csv(stock, "e2e:stock")

    # Resolve the cached parquet URIs.
    def cached_uri(ds_id: str) -> str:
        c, d = req("GET", f"/datasets/{ds_id}")
        return d["storageUri"]

    URI_CUST = cached_uri(cust_id)
    URI_FLOW = cached_uri(flow_id)
    URI_STOCK = cached_uri(stock_id)
    print(f"   customers: {cust_id}")
    print(f"   flowers:   {flow_id}")
    print(f"   stock:     {stock_id}\n")

    # Step → which dataset to use as ds_id input.
    DATASET_FOR_STEP = {
        # ML / stats need numeric columns
        "pca": URI_FLOW, "kmeans": URI_FLOW, "dbscan": URI_FLOW,
        "tsne": URI_FLOW, "umap": URI_FLOW, "linear_regression": URI_FLOW,
        "correlation_matrix": URI_FLOW,
        # Time-series need date column
        "resample": URI_STOCK, "rolling": URI_STOCK,
        "seasonal_decompose": URI_STOCK, "forecast": URI_STOCK,
    }

    results: list[tuple[str, str, str]] = []   # (step, status, detail)
    pids_to_clean: list[str] = []

    for step_id, factory in PIPELINES.items():
        uri = DATASET_FOR_STEP.get(step_id, URI_CUST)
        try:
            d = factory(uri)
            pid, run = run_pipeline(d)
            pids_to_clean.append(pid)
            if run["status"] == "succeeded":
                results.append((step_id, "✅ pass", f"{run.get('elapsedMs','?')}ms"))
            else:
                err = (run.get("error") or "no error").splitlines()[0][:120]
                results.append((step_id, "❌ FAIL", err))
        except Exception as e:
            results.append((step_id, "💥 ERROR", str(e)[:120]))
        # Print progressively so a long run is observable.
        print(f"  {results[-1][1]:8} {step_id:30} {results[-1][2]}")

    # Combine: join (customers ⨝ customers self-join), union, subpipeline ---
    print("\n📦 Two-input + composition steps…")

    # join: customers ⨝ flowers — silly but exercises the join code.
    try:
        join_doc = doc(
            "e2e:join",
            [ds("c", URI_CUST), ds("f", URI_FLOW)],
            [{
                "id": "n", "step": "join", "stepVersion": "1.0.0",
                "inputs": {"left": {"ref": "c"}, "right": {"ref": "f"}},
                "outputs": ["out"],
                "params": {
                    "on": [{"left": "country", "right": "species"}],
                    "how": "left",
                },
            }],
            out("n"),
        )
        pid, run = run_pipeline(join_doc, sample_rows=200)
        pids_to_clean.append(pid)
        results.append(("join", "✅ pass" if run["status"] == "succeeded" else "❌ FAIL",
                        run.get("elapsedMs", "?") if run["status"] == "succeeded"
                        else (run.get("error") or "")[:120]))
    except Exception as e:
        results.append(("join", "💥 ERROR", str(e)[:120]))
    print(f"  {results[-1][1]:8} join")

    # union: customers ∪ customers (same dataset, twice)
    try:
        union_doc = doc(
            "e2e:union",
            [ds("c", URI_CUST)],
            [
                node("n_a", "select_columns", {"columns": ["customer_id", "country"]}, in_ref="c"),
                node("n_b", "select_columns", {"columns": ["customer_id", "country"]}, in_ref="c"),
                {
                    "id": "n", "step": "union", "stepVersion": "1.0.0",
                    "inputs": {"top": {"ref": "n_a"}, "bottom": {"ref": "n_b"}},
                    "outputs": ["out"], "params": {},
                },
            ],
            out("n"),
        )
        pid, run = run_pipeline(union_doc)
        pids_to_clean.append(pid)
        results.append(("union", "✅ pass" if run["status"] == "succeeded" else "❌ FAIL",
                        run.get("elapsedMs", "?") if run["status"] == "succeeded"
                        else (run.get("error") or "")[:120]))
    except Exception as e:
        results.append(("union", "💥 ERROR", str(e)[:120]))
    print(f"  {results[-1][1]:8} union")

    # subpipeline: an inner pipeline + an outer that calls it.
    try:
        inner_doc = doc("e2e:inner",
                        [ds("ds", URI_CUST)],
                        [node("nf", "filter_rows", {"predicate": '"status" = \'active\''})],
                        out("nf"))
        c, inner = req("POST", "/pipelines", {"name": "e2e:inner", "document": inner_doc})
        if c != 201: raise RuntimeError(f"create inner failed: {inner}")
        inner_pid = inner["id"]
        pids_to_clean.append(inner_pid)

        outer_doc = doc("e2e:outer",
                        [],  # subpipeline doesn't need its own dataset
                        [{"id": "ns", "step": "subpipeline", "stepVersion": "1.0.0",
                          "inputs": {}, "outputs": ["out"],
                          "params": {"pipeline_id": inner_pid}}],
                        out("ns"))
        pid, run = run_pipeline(outer_doc)
        pids_to_clean.append(pid)
        results.append(("subpipeline", "✅ pass" if run["status"] == "succeeded" else "❌ FAIL",
                        run.get("elapsedMs", "?") if run["status"] == "succeeded"
                        else (run.get("error") or "")[:120]))
    except Exception as e:
        results.append(("subpipeline", "💥 ERROR", str(e)[:120]))
    print(f"  {results[-1][1]:8} subpipeline")

    # export_to_db (sqlite to /tmp)
    print("\n📦 export_to_db (sqlite)…")
    try:
        import os, tempfile
        sqlite_path = Path(tempfile.gettempdir()) / "dig_e2e.sqlite"
        if sqlite_path.exists(): sqlite_path.unlink()
        db_doc = doc("e2e:export_to_db",
                     [ds("c", URI_CUST)],
                     [node("n", "export_to_db",
                           {"uri": f"sqlite:///{sqlite_path}", "table": "customers",
                            "if_exists": "replace"}, in_ref="c")],
                     out("n"))
        pid, run = run_pipeline(db_doc)
        pids_to_clean.append(pid)
        results.append(("export_to_db", "✅ pass" if run["status"] == "succeeded" else "❌ FAIL",
                        run.get("elapsedMs", "?") if run["status"] == "succeeded"
                        else (run.get("error") or "")[:120]))
    except Exception as e:
        results.append(("export_to_db", "💥 ERROR", str(e)[:120]))
    print(f"  {results[-1][1]:8} export_to_db")

    # ---- Cleanup -----------------------------------------------------------
    print("\n🧹 Cleaning up…")
    for pid in pids_to_clean:
        req("DELETE", f"/pipelines/{pid}")
    for ds_id in (cust_id, flow_id, stock_id):
        req("DELETE", f"/datasets/{ds_id}")

    # ---- Summary -----------------------------------------------------------
    passed = sum(1 for _, s, _ in results if s.startswith("✅"))
    failed = len(results) - passed
    print(f"\n{'='*70}")
    print(f"E2E SUMMARY:  {passed} pass · {failed} fail · {len(results)} total")
    print('='*70)
    if failed:
        print("\nFailures:")
        for step, status, detail in results:
            if not status.startswith("✅"):
                print(f"  {status} {step:30} {detail}")

    # JSON dump for the doc
    out_path = REPO / "scripts" / "e2e_results.json"
    out_path.write_text(json.dumps({
        "results": [{"step": s, "status": st, "detail": d} for s, st, d in results],
        "passed": passed, "failed": failed, "total": len(results),
    }, indent=2))
    print(f"\n📝 Wrote {out_path.relative_to(REPO)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
