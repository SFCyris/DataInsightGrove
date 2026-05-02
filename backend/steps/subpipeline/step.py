"""Sub-pipeline step.

Embed another saved pipeline as a single step. Cycle detection via
PolarsContext.pipeline_chain.

The implementation calls back into `dig.engine.executor.execute_subpipeline`
which runs the referenced pipeline against an ephemeral run id and returns
the chosen output as a Polars DataFrame. The outer run record gets a sink
artifact pointing at the resolved pipeline_id for traceability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class SubpipelineStep(Step):
    def execute_polars(
        self,
        inputs: dict[str, pl.DataFrame],
        params: dict[str, Any],
        ctx: PolarsContext | None = None,
    ) -> PolarsResult:
        from dig.engine.executor import execute_subpipeline

        if ctx is None:
            raise RuntimeError("subpipeline: requires execution context")

        target_id = (params.get("pipeline_id") or "").strip()
        if not target_id:
            raise ValueError("subpipeline: 'pipeline_id' is required")
        if target_id in ctx.pipeline_chain:
            chain = " → ".join((*ctx.pipeline_chain, target_id))
            raise RuntimeError(f"subpipeline: cycle detected ({chain})")

        sample_rows = params.get("sample_rows")
        if sample_rows is not None:
            sample_rows = int(sample_rows)

        df, target_name = execute_subpipeline(
            target_id,
            output_id=(params.get("output_id") or None),
            sample_rows=sample_rows,
            chain=ctx.pipeline_chain,
        )

        return PolarsResult(
            output=df,
            artifacts=[{
                "kind": "subpipeline",
                "pipeline_id": target_id,
                "pipeline_name": target_name,
                "rows": df.height,
            }],
        )


step = SubpipelineStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
