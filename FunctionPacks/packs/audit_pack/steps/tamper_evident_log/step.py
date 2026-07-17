"""tamper_evident_log — append-only Merkle-style chain log."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class TamperEvidentLogStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        log_path_raw = (params.get("logPath") or "audit_log.jsonl").strip()
        annotation = (params.get("annotation") or "").strip()

        log_path = Path(log_path_raw)
        if not log_path.is_absolute() and ctx is not None:
            log_path = ctx.out_dir / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Compute content hash for this entry.
        try:
            content = df.write_csv(include_header=True).encode("utf-8")
        except Exception:
            content = str(df.to_dicts()).encode("utf-8")
        content_hash = hashlib.sha256(content).hexdigest()

        # Read previous entry to chain.
        prev_hash = None
        prev_index = -1
        if log_path.exists():
            try:
                lines = log_path.read_text().splitlines()
                if lines:
                    prev = json.loads(lines[-1])
                    prev_hash = prev.get("entry_hash")
                    prev_index = prev.get("index", -1)
            except Exception:
                pass

        entry_index = prev_index + 1
        body = {
            "index": entry_index,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": ctx.run_id if ctx else None,
            "node_id": ctx.node_id if ctx else None,
            "rows": df.height,
            "columns": df.width,
            "content_sha256": content_hash,
            "annotation": annotation or None,
            "prev_entry_hash": prev_hash,
        }
        # Sign the entry: hash(prev_hash + body json).
        entry_payload = (str(prev_hash or "") + json.dumps(body, sort_keys=True)).encode("utf-8")
        entry_hash = hashlib.sha256(entry_payload).hexdigest()
        body["entry_hash"] = entry_hash

        with log_path.open("a") as f:
            f.write(json.dumps(body) + "\n")

        return PolarsResult(output=df, artifacts=[{
            "kind": "metrics",
            "label": f"Audit log entry #{entry_index}",
            "data": {**body, "log_path": str(log_path)},
        }])


step = TamperEvidentLogStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
