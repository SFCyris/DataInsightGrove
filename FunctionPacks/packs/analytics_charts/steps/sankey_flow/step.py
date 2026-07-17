"""sankey_flow — static Sankey from (source, target, value) edges.

Layout: levelize the DAG (longest-path-from-source), place each
node's box at its level, then draw cubic Bezier curves between
adjacent levels with width proportional to the edge value.
"""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
import polars as pl
from dig.engine.step import PolarsContext, PolarsResult, Step


class SankeyFlowStep(Step):
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
        title = params.get("title") or "Sankey flow"
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 1600); height = int(params.get("height") or 900)

        clean = df.drop_nulls(subset=[s_col, t_col, v_col]).filter(pl.col(v_col) > 0)
        if clean.height == 0:
            raise ValueError("sankey_flow: no rows with positive value")

        # Sum edges with the same (source, target).
        edges = (clean.group_by([s_col, t_col])
                       .agg(pl.col(v_col).sum().alias("__v")))
        src = [str(v) for v in edges[s_col].to_list()]
        tgt = [str(v) for v in edges[t_col].to_list()]
        vals = [float(v) for v in edges["__v"].to_list()]

        # Levelize: source-only nodes are level 0; each node's level is
        # 1 + max(parent levels). Cycles are broken by capping iteration.
        in_neighbours: dict[str, list[str]] = defaultdict(list)
        out_neighbours: dict[str, list[str]] = defaultdict(list)
        for s, t in zip(src, tgt):
            out_neighbours[s].append(t); in_neighbours[t].append(s)
        all_nodes = sorted(set(src) | set(tgt))
        level = {n: 0 for n in all_nodes if not in_neighbours[n]}
        for _ in range(50):  # bounded iteration guards against cycles
            changed = False
            for n in all_nodes:
                if not in_neighbours[n]:
                    continue
                parent_levels = [level[p] for p in in_neighbours[n] if p in level]
                if parent_levels:
                    new_lvl = max(parent_levels) + 1
                    if level.get(n) != new_lvl:
                        level[n] = new_lvl
                        changed = True
            if not changed:
                break
        for n in all_nodes:
            level.setdefault(n, 0)
        n_levels = max(level.values()) + 1

        # Per-level node ordering by sum of incoming + outgoing flows.
        node_flow = defaultdict(float)
        for s, t, v in zip(src, tgt, vals):
            node_flow[s] += v; node_flow[t] += v
        levels: dict[int, list[str]] = defaultdict(list)
        for n in sorted(all_nodes, key=lambda x: -node_flow[x]):
            levels[level[n]].append(n)

        # Layout: each level occupies a column at fixed x. Boxes are
        # stacked vertically, total height = node_flow.
        node_y: dict[str, tuple[float, float]] = {}  # name -> (y_top, y_bottom)
        x_pad = 0.05; box_w = 0.02
        col_xs = np.linspace(x_pad, 1 - x_pad, n_levels)
        max_flow_per_level = max(sum(node_flow[n] for n in lvl) for lvl in levels.values())
        for lvl_idx, names in levels.items():
            cursor = 0.95
            for n in names:
                share = node_flow[n] / max_flow_per_level
                box_h = share * 0.9
                node_y[n] = (cursor, cursor - box_h)
                cursor -= box_h + 0.01

        # Render.
        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        cmap = cm.tab20
        node_color = {n: cmap(i / max(1, len(all_nodes) - 1)) for i, n in enumerate(all_nodes)}
        # Boxes.
        for n in all_nodes:
            top, bot = node_y[n]
            x = col_xs[level[n]]
            rect = mpatches.Rectangle((x, bot), box_w, top - bot,
                                      facecolor=node_color[n], edgecolor="white", linewidth=1)
            ax.add_patch(rect)
            ax.text(x + box_w + 0.01, (top + bot) / 2, n, va="center", ha="left", fontsize=9)

        # Curves: per (s, t) edge, draw a Bezier from src right edge to
        # tgt left edge with width proportional to value. We track how
        # much of each node's vertical extent has already been "used"
        # by previous edges so curves don't overlap within a node.
        used_out: dict[str, float] = defaultdict(float)
        used_in: dict[str, float] = defaultdict(float)
        for s, t, v in zip(src, tgt, vals):
            s_top, s_bot = node_y[s]
            t_top, t_bot = node_y[t]
            s_share = (v / node_flow[s]) * (s_top - s_bot)
            t_share = (v / node_flow[t]) * (t_top - t_bot)
            sy = s_top - used_out[s] - s_share / 2
            ty = t_top - used_in[t] - t_share / 2
            used_out[s] += s_share; used_in[t] += t_share
            x0 = col_xs[level[s]] + box_w; x1 = col_xs[level[t]]
            # Cubic Bezier control points midway.
            verts = [(x0, sy + s_share / 2),
                     ((x0 + x1) / 2, sy + s_share / 2),
                     ((x0 + x1) / 2, ty + t_share / 2),
                     (x1, ty + t_share / 2),
                     (x1, ty - t_share / 2),
                     ((x0 + x1) / 2, ty - t_share / 2),
                     ((x0 + x1) / 2, sy - s_share / 2),
                     (x0, sy - s_share / 2),
                     (x0, sy + s_share / 2)]
            codes = [mpath.Path.MOVETO,
                     mpath.Path.CURVE4, mpath.Path.CURVE4, mpath.Path.CURVE4,
                     mpath.Path.LINETO,
                     mpath.Path.CURVE4, mpath.Path.CURVE4, mpath.Path.CURVE4,
                     mpath.Path.CLOSEPOLY]
            patch = mpatches.PathPatch(mpath.Path(verts, codes),
                                        facecolor=node_color[s], alpha=0.4, edgecolor="none")
            ax.add_patch(patch)

        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off"); ax.set_title(title)
        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height, "chart": "sankey_flow",
            "title": title, "n_nodes": len(all_nodes), "n_edges": len(src),
        }])


step = SankeyFlowStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
