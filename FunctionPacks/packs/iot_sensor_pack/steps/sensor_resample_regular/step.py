"""sensor_resample_regular — interpolate to a regular time grid."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class SensorResampleRegularStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        t = params["timestampColumn"]; v = params["valueColumn"]
        sensor = params.get("sensorColumn")
        interval = float(params.get("intervalSeconds", 60.0))

        def _resample(sub: pl.DataFrame) -> pl.DataFrame:
            sub = sub.sort(t)
            if sub.height < 2: return sub
            # Use Python datetime via timestamp() to avoid numpy/polars
            # datetime-unit mismatch (an earlier ns-based path overflowed
            # for far-future dates and round-tripped to year 58321).
            ts_py = sub[t].to_list()
            ts_secs = np.asarray([d.timestamp() for d in ts_py], dtype=float)
            vs = np.asarray(sub[v].to_list(), dtype=float)
            grid_secs = np.arange(ts_secs[0], ts_secs[-1] + 1e-9, interval)
            interp = np.interp(grid_secs, ts_secs, vs)
            tz = ts_py[0].tzinfo
            grid_dt = [datetime.fromtimestamp(s, tz=tz) for s in grid_secs]
            cols = {
                t: grid_dt,
                v: interp.tolist(),
            }
            if sensor and sensor in sub.columns:
                cols[sensor] = [sub[sensor][0]] * len(grid_secs)
            return pl.DataFrame(cols)

        if sensor and sensor in df.columns:
            chunks = []
            for _, sub in df.group_by(sensor):
                chunks.append(_resample(sub))
            out = pl.concat(chunks)
        else:
            out = _resample(df)
        return PolarsResult(output=out)


step = SensorResampleRegularStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
