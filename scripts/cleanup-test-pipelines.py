#!/usr/bin/env python3
"""Bulk-clean test/leftover pipelines + datasets via the live DIG API.

Targets things E2E runs and casual experimentation tend to leave behind:
  - Pipelines whose name starts with `e2e:` (the E2E harness)
  - Datasets whose name starts with `e2e:` (same)
  - Pipelines named just `t` or `untitled` (typical placeholders)
  - Pipelines with zero datasets AND zero nodes (abandoned drafts)

Defaults to **dry-run** — prints what would be deleted but doesn't touch
anything. Add `--apply` to actually execute the deletions.

Usage:
    python3 scripts/cleanup-test-pipelines.py            # dry run, default rules
    python3 scripts/cleanup-test-pipelines.py --apply    # actually delete
    python3 scripts/cleanup-test-pipelines.py --include-empty --apply
    python3 scripts/cleanup-test-pipelines.py --prefix demo: --apply
    python3 scripts/cleanup-test-pipelines.py --all       # nuclear: every pipeline + dataset
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

def _default_api_url() -> str:
    """Resolve the API URL from env > persisted config > built-in default.

    Single source of truth for the canonical default lives in
    `scripts/dig_config.py:DEFAULT` and `backend/dig/_settings.py:DEFAULTS`
    (the two intentionally agree). Don't hardcode another fallback here.
    """
    if v := os.environ.get("DIG_API"):
        return v
    try:
        # Use the canonical resolver — same code path as start.sh / stop.sh.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from dig_config import resolve  # type: ignore[import-not-found]
        cfg = resolve()
        return f"http://{cfg['api']['host']}:{cfg['api']['port']}"
    except Exception:
        # Belt-and-suspenders fallback if dig_config can't be imported (e.g.
        # script invoked from outside the repo). Matches DEFAULTS in both
        # backend/dig/_settings.py and scripts/dig_config.py.
        return "http://127.0.0.1:8090"


API_DEFAULT = _default_api_url()


def req(api: str, method: str, path: str, body=None, token: str | None = None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(f"{api}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            txt = resp.read().decode()
            return resp.status, (json.loads(txt) if txt else None)
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode()
        return e.code, body_txt


def classify_pipeline(p: dict, args) -> tuple[bool, str]:
    """Returns (should_delete, reason)."""
    name = (p.get("name") or "").strip()
    if args.all:
        return True, "--all flag"
    if name.startswith(args.prefix):
        return True, f"name starts with '{args.prefix}'"
    if name.lower() in ("t", "untitled", "test", ""):
        return True, f"placeholder name {name!r}"
    if args.include_empty and p.get("nodeCount", 0) == 0 and p.get("datasetCount", 0) == 0:
        return True, "empty pipeline (0 nodes, 0 datasets)"
    return False, ""


def classify_dataset(d: dict, args) -> tuple[bool, str]:
    name = (d.get("name") or "").strip()
    if args.all:
        return True, "--all flag"
    if name.startswith(args.prefix):
        return True, f"name starts with '{args.prefix}'"
    return False, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=API_DEFAULT, help=f"API base URL (default: {API_DEFAULT})")
    ap.add_argument("--token", default=os.environ.get("DIG_AUTH_TOKEN"), help="Bearer token (default: $DIG_AUTH_TOKEN)")
    ap.add_argument("--prefix", default="e2e:", help="Delete pipelines + datasets whose name starts with this prefix (default: 'e2e:')")
    ap.add_argument("--include-empty", action="store_true", help="Also delete pipelines with 0 nodes AND 0 datasets")
    ap.add_argument("--all", action="store_true", help="DANGER: delete EVERY pipeline and dataset (nuclear option)")
    ap.add_argument("--datasets-only", action="store_true", help="Only operate on datasets, not pipelines")
    ap.add_argument("--pipelines-only", action="store_true", help="Only operate on pipelines, not datasets")
    ap.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run, prints only)")
    args = ap.parse_args()

    if args.all and not args.apply:
        print("⚠️  --all in dry-run mode. Showing what WOULD be deleted; nothing actually goes away unless you add --apply.\n")

    # Liveness check.
    code, _ = req(args.api, "GET", "/health")
    if code != 200:
        print(f"✗ API at {args.api} not responding (status={code}). Is `make start` running?", file=sys.stderr)
        return 2

    deleted_p, deleted_d, kept_p, kept_d = 0, 0, 0, 0

    # ---- Pipelines ----
    if not args.datasets_only:
        code, pipelines = req(args.api, "GET", "/pipelines", token=args.token)
        if code != 200:
            print(f"✗ couldn't list pipelines: {code}", file=sys.stderr)
            return 2
        print(f"📋 {len(pipelines)} pipelines on the server\n")

        for p in pipelines:
            should, reason = classify_pipeline(p, args)
            tag = "DELETE" if should else "  keep"
            color = "🗑" if should else "  "
            print(
                f"  {color} [{tag}] "
                f"{p['id'][:8]}… {(p.get('name') or '?')[:40]:40}  "
                f"datasets={p.get('datasetCount', 0):2}  nodes={p.get('nodeCount', 0):2}  "
                f"{('— ' + reason) if reason else ''}"
            )
            if should:
                if args.apply:
                    code, _ = req(args.api, "DELETE", f"/pipelines/{p['id']}", token=args.token)
                    if code not in (200, 204):
                        print(f"      ⚠️  delete failed: {code}", file=sys.stderr)
                        continue
                deleted_p += 1
            else:
                kept_p += 1

    # ---- Datasets ----
    if not args.pipelines_only:
        code, datasets = req(args.api, "GET", "/datasets", token=args.token)
        if code != 200:
            print(f"✗ couldn't list datasets: {code}", file=sys.stderr)
        else:
            print(f"\n📦 {len(datasets)} datasets on the server\n")
            for d in datasets:
                should, reason = classify_dataset(d, args)
                tag = "DELETE" if should else "  keep"
                color = "🗑" if should else "  "
                rows = d.get("rowCount") or 0
                print(
                    f"  {color} [{tag}] "
                    f"{d['id'][:8]}… {(d.get('name') or '?')[:40]:40}  "
                    f"rows={rows:>8}  status={d.get('status', '?'):8}  "
                    f"{('— ' + reason) if reason else ''}"
                )
                if should:
                    if args.apply:
                        code, _ = req(args.api, "DELETE", f"/datasets/{d['id']}", token=args.token)
                        if code not in (200, 204):
                            print(f"      ⚠️  delete failed: {code}", file=sys.stderr)
                            continue
                    deleted_d += 1
                else:
                    kept_d += 1

    print()
    if args.apply:
        print(f"✅ Deleted {deleted_p} pipeline(s) + {deleted_d} dataset(s). Kept {kept_p} pipeline(s) + {kept_d} dataset(s).")
    else:
        print(f"📝 Dry run: would delete {deleted_p} pipeline(s) + {deleted_d} dataset(s). Re-run with --apply to execute.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
