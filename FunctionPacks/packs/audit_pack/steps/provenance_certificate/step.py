"""provenance_certificate — emit a signed-style provenance JSON."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ProvenanceCertificateStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        issuer = (params.get("issuer") or "DataInsightGrove").strip()
        ds_name = (params.get("datasetName") or "").strip()
        if not ds_name:
            raise ValueError("provenance_certificate: datasetName is required")
        intended_use = (params.get("intendedUse") or "").strip()

        # Stable content hash.
        try:
            payload = df.write_csv(include_header=True).encode("utf-8")
        except Exception:
            payload = str(df.to_dicts()).encode("utf-8")
        content_hash = hashlib.sha256(payload).hexdigest()

        cert = {
            "kind": "provenance_certificate",
            "version": "1.0",
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "issuer": issuer,
            "dataset_name": ds_name,
            "intended_use": intended_use or None,
            "run_id": ctx.run_id if ctx else None,
            "node_id": ctx.node_id if ctx else None,
            "content_sha256": content_hash,
            "row_count": df.height,
            "column_count": df.width,
            "columns": df.columns,
            "dtypes": [str(df.schema[c]) for c in df.columns],
        }
        return PolarsResult(output=df, artifacts=[{
            "kind": "metrics",
            "label": f"Provenance certificate — {ds_name}",
            "data": cert,
        }])


step = ProvenanceCertificateStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
