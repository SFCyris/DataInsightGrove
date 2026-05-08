"""Identity step — emits its input unchanged.

Primarily used by the sub-pipeline inliner: the wrapper node that
referenced ``pipeline:<id>`` is replaced by a passthrough whose input
points at the spliced terminal of the source pipeline. This keeps the
wrapper id alive in the flat DAG so:
  - the compile terminal-selection logic still finds it,
  - downstream nodes that read from the wrapper id keep working,
  - lineage / per-row tracing has a stable node id to attach to.

The default ``to_sql`` on the base Step class already does
``SELECT * FROM <first input>`` when no override is provided, so we
just instantiate the base class with our manifest. The DuckDB planner
inlines the resulting CTE during optimisation — zero runtime cost.
"""
from __future__ import annotations

import json
from pathlib import Path

from dig.engine.step import Step


class PassthroughStep(Step):
    """Identity — base class default `to_sql` does the right thing."""


step = PassthroughStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
