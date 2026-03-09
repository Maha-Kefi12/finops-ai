"""
GraphBuilder — creates a NetworkX DiGraph from architecture data.
"""
import networkx as nx
from typing import Dict, Any


class GraphBuilder:
    """Builds a NetworkX directed graph from raw architecture JSON."""

    def __init__(self, architecture_data: Dict[str, Any]):
        self.data = architecture_data

    def build(self) -> nx.DiGraph:
        G = nx.DiGraph()

        for svc in self.data.get("services", []):
            G.add_node(
                svc["id"],
                name=svc.get("name", svc["id"]),
                service_type=svc.get("type", "service"),
                owner=svc.get("owner", "unknown"),
                cost_monthly=svc.get("cost_monthly", 0.0),
                environment=svc.get("environment", "production"),
                attributes=svc.get("attributes", {}),
            )

        for dep in self.data.get("dependencies", []):
            G.add_edge(
                dep["source"],
                dep["target"],
                dep_type=dep.get("type", "calls"),
                weight=dep.get("weight", 1.0),
            )

        return G
