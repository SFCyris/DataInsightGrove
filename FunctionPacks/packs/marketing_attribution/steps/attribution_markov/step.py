"""attribution_markov — removal-effect attribution from a Markov transition matrix."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
import polars as pl
import numpy as np
from dig.engine.step import PolarsContext, PolarsResult, Step


class AttributionMarkovStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        df = inputs["in"]
        u = params["userColumn"]; c = params["channelColumn"]
        t = params["timestampColumn"]; conv = params["convertedColumn"]

        # Build journeys.
        sub = df.sort([u, t])
        journeys: list[tuple[list[str], bool]] = []
        for (uid,), grp in sub.group_by(u, maintain_order=True):
            channels = [str(x) for x in grp[c].to_list()]
            converted = bool(grp[conv].cast(pl.Boolean).any())
            journeys.append((channels, converted))

        # Build transition counts: state set = channels + START + CONVERT + NULL.
        states = set()
        for journey, _ in journeys:
            states.update(journey)
        states = sorted(states)
        all_states = ["START"] + list(states) + ["CONVERT", "NULL"]
        idx = {s: i for i, s in enumerate(all_states)}
        T = np.zeros((len(all_states), len(all_states)))
        for journey, converted in journeys:
            path = ["START", *journey, "CONVERT" if converted else "NULL"]
            for a, b in zip(path[:-1], path[1:]):
                T[idx[a], idx[b]] += 1
        # Normalise to probabilities.
        row_sums = T.sum(axis=1, keepdims=True); row_sums[row_sums == 0] = 1
        P = T / row_sums

        def _conversion_prob(P_mat):
            # Probability of reaching CONVERT from START via random walk.
            ic = idx["CONVERT"]; ist = idx["START"]
            # Iterate to convergence (small state space).
            v = np.zeros(len(all_states)); v[ist] = 1.0
            for _ in range(200):
                v = v @ P_mat
            return float(v[ic])

        baseline = _conversion_prob(P)
        # Removal effect per channel.
        results = []
        for ch in states:
            P2 = P.copy()
            i = idx[ch]
            # Re-route any incoming transition to NULL.
            null_idx = idx["NULL"]
            P2[i, :] = 0; P2[i, null_idx] = 1.0
            # Re-normalise — already a single-target row.
            removed = _conversion_prob(P2)
            results.append({"channel": ch, "removal_effect": baseline - removed})
        total_re = sum(r["removal_effect"] for r in results) or 1.0
        n_conv = sum(1 for _, c in journeys if c)
        for r in results:
            r["credited_conversions"] = (r["removal_effect"] / total_re) * n_conv
        out = pl.DataFrame(results).sort("credited_conversions", descending=True)
        return PolarsResult(output=out)


step = AttributionMarkovStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
