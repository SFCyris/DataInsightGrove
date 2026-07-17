"""chord_diagram — circular relationship plot.

Each unique category gets a slice on a circle proportional to its
total flow (in + out). For each (source, target, value) edge, a
quadratic Bezier ribbon connects the corresponding arc segments
inside the circle. Colors match the source slice; alpha reflects
relative magnitude.
"""
from __future__ import annotations
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class ChordDiagramStep(Step):
    def execute_polars(self, inputs: dict[str, pl.DataFrame], params: dict[str, Any], ctx: PolarsContext | None = None) -> PolarsResult:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import matplotlib.path as mpath
        import matplotlib.patches as mpatches
        import numpy as np

        df = inputs["in"]
        s_col = params["sourceColumn"]; t_col = params["targetColumn"]; v_col = params["valueColumn"]
        title = params.get("title") or "Chord diagram"
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 1200); height = int(params.get("height") or 1200)

        clean = df.drop_nulls(subset=[s_col, t_col, v_col]).filter(pl.col(v_col) > 0)
        if clean.height == 0:
            raise ValueError("chord_diagram: no rows with positive value")
        edges = (clean.group_by([s_col, t_col]).agg(pl.col(v_col).sum().alias("__v")))
        src = [str(v) for v in edges[s_col].to_list()]
        tgt = [str(v) for v in edges[t_col].to_list()]
        vals = [float(v) for v in edges["__v"].to_list()]

        node_total = defaultdict(float)
        for s, t, v in zip(src, tgt, vals):
            node_total[s] += v; node_total[t] += v
        nodes = sorted(node_total.keys(), key=lambda n: -node_total[n])
        total = sum(node_total.values())
        # Allocate arc segments around the circle.
        gap = 0.02  # radians of gap between slices
        usable = 2 * math.pi - gap * len(nodes)
        node_arc: dict[str, tuple[float, float]] = {}  # name -> (start, end) in radians
        cursor = math.pi / 2  # start at the top
        for n in nodes:
            length = (node_total[n] / total) * usable
            node_arc[n] = (cursor, cursor - length)
            cursor -= length + gap

        cmap = cm.tab20
        node_color = {n: cmap(i / max(1, len(nodes) - 1)) for i, n in enumerate(nodes)}

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        # Outer arc slices.
        outer_r = 1.0; inner_r = 0.92
        for n in nodes:
            start, end = node_arc[n]
            theta = np.linspace(start, end, 50)
            x_outer = np.cos(theta) * outer_r; y_outer = np.sin(theta) * outer_r
            x_inner = np.cos(theta[::-1]) * inner_r; y_inner = np.sin(theta[::-1]) * inner_r
            ax.fill(np.concatenate([x_outer, x_inner]),
                     np.concatenate([y_outer, y_inner]),
                     color=node_color[n], edgecolor="white")
            mid = (start + end) / 2
            label_r = outer_r + 0.05
            ax.text(math.cos(mid) * label_r, math.sin(mid) * label_r, n,
                     ha="center", va="center", rotation=math.degrees(mid) - 90 if math.cos(mid) >= 0 else math.degrees(mid) + 90,
                     fontsize=9)

        # Ribbons for edges.
        used_out: dict[str, float] = defaultdict(float)
        used_in: dict[str, float] = defaultdict(float)
        for s, t, v in zip(src, tgt, vals):
            s_start, s_end = node_arc[s]
            t_start, t_end = node_arc[t]
            s_share = (v / node_total[s]) * (s_start - s_end)
            t_share = (v / node_total[t]) * (t_start - t_end)
            sa = s_start - used_out[s]
            ta = t_start - used_in[t]
            used_out[s] += s_share; used_in[t] += t_share

            # Source arc segment.
            theta_s = np.linspace(sa, sa - s_share, 30)
            xs1 = np.cos(theta_s) * inner_r; ys1 = np.sin(theta_s) * inner_r
            # Bezier curves through (0,0) connecting to target.
            theta_t = np.linspace(ta, ta - t_share, 30)
            xs2 = np.cos(theta_t) * inner_r; ys2 = np.sin(theta_t) * inner_r

            # Build a closed path: arc_s_forward → bezier → arc_t_reverse → bezier_back
            verts = list(zip(xs1, ys1))
            verts.append((0, 0))
            verts.extend(list(zip(xs2[::-1], ys2[::-1])))
            verts.append((0, 0))
            verts.append(verts[0])
            ax.fill([p[0] for p in verts], [p[1] for p in verts],
                     color=node_color[s], alpha=0.35, edgecolor="none")

        ax.set_xlim(-1.3, 1.3); ax.set_ylim(-1.3, 1.3); ax.set_aspect("equal")
        ax.axis("off"); ax.set_title(title)

        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height, "chart": "chord_diagram",
            "title": title, "n_nodes": len(nodes), "n_edges": len(src),
        }])


step = ChordDiagramStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
