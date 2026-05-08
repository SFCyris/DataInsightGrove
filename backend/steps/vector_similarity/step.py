from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dig.engine.step import Step, quote_ident


# Metric → DuckDB array function. DuckDB ships these natively as of v1.0;
# they all accept FIXED-SIZE arrays (DOUBLE[n]). Variable-length LIST
# columns can also be passed but performance is much better on FIXED.
_METRIC_FN = {
    "cosine":    "array_cosine_similarity",
    "dot":       "array_inner_product",
    "euclidean": "array_distance",
    "manhattan": "array_negative_inner_product",  # placeholder; manhattan computed inline below
}


_VALID_METRICS = ("cosine", "dot", "euclidean", "manhattan")


class VectorSimilarityStep(Step):
    def to_sql(self, params: dict[str, Any], inputs: dict[str, str]) -> str:
        src = inputs["in"]
        left = quote_ident(params["leftColumn"])
        right = quote_ident(params["rightColumn"])
        metric = params.get("metric", "cosine")
        if metric not in _VALID_METRICS:
            raise ValueError(f"metric must be one of {_VALID_METRICS}, got {metric!r}")
        out = params["outputColumn"]
        if not isinstance(out, str) or not out:
            raise ValueError("outputColumn is required")

        # We use DuckDB's list_* (vs array_*) functions because list_*
        # accepts both variable-length LIST<numeric> AND fixed-size
        # DOUBLE[N] inputs (auto-coerced). The array_* variants only
        # accept the fixed-size form, which would force users to know
        # the dimension at SQL-compile time. The list_* path is slightly
        # slower for very large vectors but works universally.
        #
        # Both inputs are wrapped in CAST(… AS DOUBLE[]) so the step
        # works regardless of how the upstream column is typed:
        #   • DOUBLE[]      → identity cast (free)
        #   • LIST<numeric> → element coercion to DOUBLE[]
        #   • VARCHAR with JSON-array text (e.g. "[0.1, 0.2]") →
        #     DuckDB parses the literal into a DOUBLE[] list
        # The CSV ingestion path leaves embedding columns as VARCHAR,
        # so this cast is what makes the bundled embeddings-demo
        # template work without an explicit upstream type-cast step.
        #
        # Manhattan (L1) doesn't have a native single-call form so we
        # inline it as SUM(ABS(a[i] - b[i])) via list_sum + list_transform.
        l_cast = f"CAST({left} AS DOUBLE[])"
        r_cast = f"CAST({right} AS DOUBLE[])"
        if metric == "cosine":
            expr = f"list_cosine_similarity({l_cast}, {r_cast})"
        elif metric == "dot":
            expr = f"list_inner_product({l_cast}, {r_cast})"
        elif metric == "euclidean":
            expr = f"list_distance({l_cast}, {r_cast})"
        else:  # manhattan
            # list_zip([a, b]) → [[a1, b1], [a2, b2], ...]; list_sum of the
            # ABS differences. Pre-condition: both lists must be the same
            # length, else DuckDB raises.
            expr = (
                f"list_sum(list_transform("
                f"  list_zip({l_cast}, {r_cast}),"
                f"  pair -> ABS(pair[1] - pair[2])"
                f"))"
            )

        return f"SELECT *, {expr} AS {quote_ident(out)} FROM {src}"

    def infer_schema(
        self, input_schemas: dict[str, dict[str, str]], params: dict[str, Any],
    ) -> dict[str, str]:
        s = dict(input_schemas.get("in", {}))
        out = params.get("outputColumn")
        if out:
            s[str(out)] = "double"
        return s


step = VectorSimilarityStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
