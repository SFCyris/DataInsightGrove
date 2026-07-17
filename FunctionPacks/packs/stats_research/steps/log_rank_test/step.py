"""log_rank_test — multi-group survival comparison."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class LogRankTestStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from lifelines.statistics import multivariate_logrank_test
        df = inputs["in"]
        d = params["durationColumn"]; e = params["eventColumn"]; g = params["groupColumn"]
        clean = df.drop_nulls(subset=[d, e, g])
        result = multivariate_logrank_test(
            clean[d].to_list(),
            clean[g].to_list(),
            event_observed=[int(bool(v)) for v in clean[e].to_list()],
        )
        out = pl.DataFrame([{
            "test": "multivariate log-rank",
            "test_statistic": float(result.test_statistic),
            "p_value": float(result.p_value),
            "n_groups": int(clean[g].n_unique()),
            "null_distribution": result.null_distribution,
        }])
        return PolarsResult(output=out)


step = LogRankTestStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
