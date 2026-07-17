"""kaplan_meier — lifelines KM survival estimator (with optional group split)."""
from __future__ import annotations
import json
from pathlib import Path
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class KaplanMeierStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        from lifelines import KaplanMeierFitter
        df = inputs["in"]
        d = params["durationColumn"]; e = params["eventColumn"]
        g = params.get("groupColumn")
        clean = df.drop_nulls(subset=[d, e])
        rows = []

        def _fit(sub: pl.DataFrame, group_label: str = "(all)"):
            durations = sub[d].to_list()
            events = [int(bool(v)) for v in sub[e].to_list()]
            kmf = KaplanMeierFitter().fit(durations, events, label=group_label)
            sf = kmf.survival_function_; ci = kmf.confidence_interval_
            for t, sval in zip(sf.index, sf[group_label].to_list()):
                lo = float(ci.loc[t, ci.columns[0]]) if t in ci.index else None
                hi = float(ci.loc[t, ci.columns[1]]) if t in ci.index else None
                rows.append({
                    "group": group_label, "time": float(t),
                    "survival": float(sval), "ci_lower": lo, "ci_upper": hi,
                })

        if g and g in clean.columns:
            for (gv,), sub in clean.group_by(g):
                _fit(sub, str(gv))
        else:
            _fit(clean)
        return PolarsResult(output=pl.DataFrame(rows))


step = KaplanMeierStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
