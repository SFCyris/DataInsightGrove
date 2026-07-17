"""delta_method_ratio — CI for ratio metric via delta method."""
from __future__ import annotations
import json
import math
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class DeltaMethodRatioStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from scipy import stats
        df = inputs["in"]
        g = params["groupColumn"]; num = params["numeratorColumn"]; den = params["denominatorColumn"]
        conf = float(params.get("confidence", 0.95))
        z = stats.norm.ppf(1 - (1 - conf) / 2)
        rows = []
        for (group_val,), grp in df.group_by(g):
            n_arr = np.asarray(grp[num].to_list(), dtype=float)
            d_arr = np.asarray(grp[den].to_list(), dtype=float)
            n = len(n_arr)
            mean_n = n_arr.mean(); mean_d = d_arr.mean()
            ratio = mean_n / mean_d if mean_d != 0 else float("nan")
            var_n = n_arr.var(ddof=1) if n > 1 else 0
            var_d = d_arr.var(ddof=1) if n > 1 else 0
            cov_nd = np.cov(n_arr, d_arr, ddof=1)[0, 1] if n > 1 else 0
            # Delta-method variance.
            var_ratio = (1 / (mean_d ** 2)) * var_n - (2 * mean_n / (mean_d ** 3)) * cov_nd + ((mean_n ** 2) / (mean_d ** 4)) * var_d
            se = math.sqrt(max(var_ratio / n, 0))
            rows.append({
                "group": str(group_val), "n": n,
                "ratio": ratio, "ci_lower": ratio - z * se, "ci_upper": ratio + z * se,
                "se": se,
            })
        return PolarsResult(output=pl.DataFrame(rows))


step = DeltaMethodRatioStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
