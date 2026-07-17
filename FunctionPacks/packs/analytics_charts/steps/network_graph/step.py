"""network_graph — force-directed network plot via networkx + matplotlib."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import polars as pl

from dig.engine.step import PolarsContext, PolarsResult, Step


class NetworkGraphStep(Step):
    def execute_polars(self, inputs, params, ctx=None):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.cm as cm
        import networkx as nx

        df = inputs["in"]
        s_col = params["sourceColumn"]; t_col = params["targetColumn"]
        v_col = params.get("valueColumn")
        community = bool(params.get("communityDetection", True))
        title = params.get("title", "Network graph")
        fmt = (params.get("format") or "png").lower()
        width = int(params.get("width") or 1400); height = int(params.get("height") or 1000)

        clean = df.drop_nulls(subset=[s_col, t_col])
        if clean.height == 0:
            raise ValueError("network_graph: no rows after drop_nulls")
        G = nx.Graph()
        for src, tgt in zip(clean[s_col].to_list(), clean[t_col].to_list()):
            G.add_edge(str(src), str(tgt))
        if v_col and v_col in clean.columns:
            for src, tgt, val in zip(clean[s_col].to_list(), clean[t_col].to_list(), clean[v_col].to_list()):
                if val is not None:
                    G[str(src)][str(tgt)]["weight"] = float(val)

        # Spring layout — positions stabilise after ~50 iterations for
        # graphs up to a few hundred nodes.
        pos = nx.spring_layout(G, seed=42, k=1.0 / max(1, G.number_of_nodes() ** 0.5))

        # Community detection.
        node_color: list[float] = []
        if community and G.number_of_nodes() >= 3:
            try:
                comms = list(nx.community.greedy_modularity_communities(G))
                node_to_comm = {n: i for i, c in enumerate(comms) for n in c}
                cmap = cm.tab10 if len(comms) <= 10 else cm.tab20
                node_color = [cmap(node_to_comm.get(n, 0) / max(1, len(comms) - 1)) for n in G.nodes()]
            except Exception:
                node_color = ["#10b981"] * G.number_of_nodes()
        else:
            node_color = ["#10b981"] * G.number_of_nodes()

        # Edge widths.
        if v_col:
            weights = [G[u][v].get("weight", 1.0) for u, v in G.edges()]
            wmax = max(weights) if weights else 1.0
            edge_widths = [0.5 + 3 * (w / wmax) for w in weights]
        else:
            edge_widths = 0.8

        # Node size by degree.
        degrees = dict(G.degree())
        max_deg = max(degrees.values()) if degrees else 1
        node_size = [200 + 800 * (degrees[n] / max_deg) for n in G.nodes()]

        fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
        nx.draw_networkx_edges(G, pos, ax=ax, width=edge_widths, alpha=0.4, edge_color="#374151")
        nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_color, node_size=node_size,
                                edgecolors="white", linewidths=1.5)
        # Label only the high-degree nodes to avoid clutter.
        if G.number_of_nodes() <= 30:
            label_nodes = list(G.nodes())
        else:
            top_k = sorted(degrees.items(), key=lambda x: -x[1])[:20]
            label_nodes = [n for n, _ in top_k]
        nx.draw_networkx_labels(G, pos, labels={n: n for n in label_nodes}, ax=ax,
                                 font_size=9, font_color="#111827")
        ax.set_title(title); ax.axis("off")

        out = ctx.out_dir / f"{ctx.node_id or self.id}.{fmt}" if ctx else Path(f"{self.id}.{fmt}")
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, bbox_inches="tight"); plt.close(fig)
        return PolarsResult(output=df, artifacts=[{
            "kind": "image", "format": fmt, "path": str(out),
            "width": width, "height": height, "chart": "network_graph",
            "title": title, "n_nodes": G.number_of_nodes(), "n_edges": G.number_of_edges(),
        }])


step = NetworkGraphStep(json.loads((Path(__file__).parent / "manifest.json").read_text()))
