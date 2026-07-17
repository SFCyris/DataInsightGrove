#!/usr/bin/env python3
"""Import a Step-Pack example flow into a running DIG instance.

Usage:
    python3 FunctionPacks/scripts/import_example.py <pack_id>
    python3 FunctionPacks/scripts/import_example.py --all

What it does, end-to-end:

  1. Locates FunctionPacks/examples/<pack_id>/.
  2. Uploads each CSV in that directory as a DIG dataset (via POST /datasets).
  3. Reads flow.dig.json, substitutes:
       {{DATASET_ID}}  → ds_<dataset_ulid_lowercase>     (single-dataset flows)
       {{DATASET_URI}} → file:///…/data/datasets/<ULID>.parquet
       {{DATASET_<NAME>_ID}}  / _URI → matching CSV named data_<name>.csv
                          (multi-dataset flows like business_charts)
  4. Creates a new pipeline via POST /pipelines.
  5. Prints the pipeline URL for direct opening in the browser.

Why a script: the placeholder format makes the JSONs portable, but
substitution by hand is error-prone (the ds_<ulid_lowercase> convention
is critical for the frontend reverse-lookup). This automates it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EXAMPLES = ROOT / "FunctionPacks" / "examples"
DEFAULT_API = os.environ.get("DIG_API", "http://127.0.0.1:8190")


def _post_multipart(api_base: str, url: str, fields: dict[str, str], file_path: Path) -> dict:
    import io
    boundary = "----dig" + os.urandom(8).hex()
    body = io.BytesIO()
    for k, v in fields.items():
        body.write(f"--{boundary}\r\n".encode())
        body.write(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode())
        body.write(v.encode())
        body.write(b"\r\n")
    body.write(f"--{boundary}\r\n".encode())
    body.write(
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode(),
    )
    body.write(b"Content-Type: application/octet-stream\r\n\r\n")
    body.write(file_path.read_bytes())
    body.write(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        api_base + url,
        data=body.getvalue(),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def _post_json(api_base: str, url: str, payload: dict) -> dict:
    req = urllib.request.Request(
        api_base + url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _upload_dataset(api_base: str, csv_path: Path, label: str | None = None) -> dict:
    return _post_multipart(
        api_base,
        "/datasets",
        {"name": label or csv_path.stem, "connector_id": "csv", "options": "{}"},
        csv_path,
    )


def _resolve_placeholders(flow_text: str, csv_to_dataset: dict[Path, dict]) -> str:
    """Map placeholder names → values.

    Single-dataset flows: replace {{DATASET_ID}} / {{DATASET_URI}}.
    Multi-dataset flows: each CSV named `data_<name>.csv` corresponds
    to placeholder `{{DATASET_<NAME>_ID}}` / `_URI`.
    """
    out = flow_text
    for csv_path, dataset in csv_to_dataset.items():
        ulid_lower = dataset["id"].lower()
        ds_id = f"ds_{ulid_lower}"
        ds_uri = dataset["storageUri"]

        stem = csv_path.stem  # e.g. 'data_revenue_bridge' or 'data'
        if stem == "data":
            out = out.replace("{{DATASET_ID}}", ds_id)
            out = out.replace("{{DATASET_URI}}", ds_uri)
        elif stem.startswith("data_"):
            name = stem[len("data_"):].upper()
            out = out.replace(f"{{{{DATASET_{name}_ID}}}}", ds_id)
            out = out.replace(f"{{{{DATASET_{name}_URI}}}}", ds_uri)
    return out


def import_one(pack_id: str, api_base: str) -> str:
    example_dir = EXAMPLES / pack_id
    if not example_dir.is_dir():
        raise SystemExit(f"no example dir: {example_dir}")
    flow_path = example_dir / "flow.dig.json"
    if not flow_path.exists():
        raise SystemExit(f"missing {flow_path}")

    csvs = sorted(example_dir.glob("*.csv"))
    if not csvs:
        raise SystemExit(f"no CSVs in {example_dir}")

    print(f"📦 importing {pack_id}")
    csv_to_dataset: dict[Path, dict] = {}
    for csv in csvs:
        print(f"  uploading {csv.name} …", end=" ", flush=True)
        ds = _upload_dataset(api_base, csv, label=f"{pack_id} · {csv.stem}")
        print(f"id={ds['id']}  rows={ds.get('rowCount')}")
        csv_to_dataset[csv] = ds

    flow_text = flow_path.read_text()
    flow_text = _resolve_placeholders(flow_text, csv_to_dataset)
    # Sanity: any leftover placeholders are a bug.
    if "{{DATASET_" in flow_text:
        leftovers = [
            seg.split("}}")[0] for seg in flow_text.split("{{DATASET_")[1:]
        ]
        raise SystemExit(
            f"unresolved placeholders in {flow_path.name}: "
            f"{['{{DATASET_' + s + '}}' for s in leftovers]}",
        )
    document = json.loads(flow_text)
    document.pop("id", None)  # backend assigns the real pipeline id

    pipeline = _post_json(
        api_base,
        "/pipelines",
        {"name": document.get("name") or f"{pack_id} demo", "document": document},
    )
    pid = pipeline["id"]
    url = f"http://localhost:3100/pipelines/{pid}"
    print(f"  ✓ pipeline created: {pid}")
    print(f"  → open: {url}")
    return url


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("packs", nargs="*", help="pack id(s); use --all for all 13")
    ap.add_argument("--all", action="store_true", help="import every example dir")
    ap.add_argument("--api", default=DEFAULT_API, help=f"DIG API base (default {DEFAULT_API})")
    args = ap.parse_args()

    if args.all:
        targets = sorted(d.name for d in EXAMPLES.iterdir() if d.is_dir())
    elif args.packs:
        targets = args.packs
    else:
        ap.print_help()
        return 2

    for t in targets:
        try:
            import_one(t, args.api)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"  ✗ {t}: {e}", file=sys.stderr)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
