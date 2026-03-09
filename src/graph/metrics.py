"""
MetricsCalculator — computes centrality and cost metrics on a NetworkX graph.
"""
import networkx as nx
from typing import Dict, Any


class MetricsCalculator:
    """Computes graph metrics (centrality, cost share, etc.) for all nodes."""

    def __init__(self, G: nx.DiGraph):
        self.G = G

    def calculate(self) -> Dict[str, Dict[str, Any]]:
        degree_centrality = nx.degree_centrality(self.G)
        betweenness_centrality = nx.betweenness_centrality(self.G, weight="weight")

        metrics: Dict[str, Dict[str, Any]] = {}
        for node_id in self.G.nodes():
            nd = self.G.nodes[node_id]
            metrics[node_id] = {
                "degree_centrality": round(degree_centrality.get(node_id, 0.0), 4),
                "betweenness_centrality": round(betweenness_centrality.get(node_id, 0.0), 4),
                "in_degree": self.G.in_degree(node_id),
                "out_degree": self.G.out_degree(node_id),
                "cost_monthly": nd.get("cost_monthly", 0.0),
                "cost_share": 0.0,
            }

        total_cost = sum(m["cost_monthly"] for m in metrics.values())
        if total_cost > 0:
            for node_id in metrics:
                metrics[node_id]["cost_share"] = round(
                    (metrics[node_id]["cost_monthly"] / total_cost) * 100, 2
                )

        return metrics
