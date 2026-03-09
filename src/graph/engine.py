"""
Core graph engine using NetworkX.
Calculates centrality, cost hotspots, critical paths.
"""
from typing import Dict, List, Any
import networkx as nx


SERVICE_TYPE_COLORS = {
    "service": "#6366f1",       # indigo - API services
    "database": "#10b981",      # emerald - databases
    "cache": "#f59e0b",         # amber - cache
    "storage": "#3b82f6",       # blue - S3/storage
    "serverless": "#8b5cf6",    # violet - lambda
    "queue": "#ec4899",         # pink - SQS
    "load_balancer": "#14b8a6", # teal - LB
    "cdn": "#f97316",           # orange - CDN
    "search": "#ef4444",        # red - search
    "batch": "#84cc16",         # lime - workers
    "vpc": "#6366f1",           # indigo - VPC
    "subnet": "#818cf8",        # light indigo - subnet
    "security_group": "#f43f5e",# rose - security group
    "gateway": "#14b8a6",       # teal - gateways
    "route_table": "#a855f7",   # purple - route tables
    "ecs_cluster": "#0ea5e9",   # sky - ECS cluster
    "container": "#06b6d4",     # cyan - containers
    "target_group": "#84cc16",  # lime - target groups
    "monitoring": "#f59e0b",    # amber - monitoring
    "notification": "#ec4899",  # pink - notifications
    "elastic_ip": "#10b981",    # emerald - EIPs
    "container_registry": "#0284c7", # blue - ECR
    "logging": "#64748b",       # slate - logging
    "iam_role": "#dc2626",      # red - IAM
}


class GraphEngine:
    """
    Builds a NetworkX directed graph from architecture data
    and computes graph metrics.
    """

    def __init__(self, architecture_data: Dict[str, Any]):
        self.data = architecture_data
        self.G = nx.DiGraph()
        self._build_graph()

    def _build_graph(self):
        """Build the directed graph from service and dependency lists."""
        for service in self.data.get("services", []):
            self.G.add_node(
                service["id"],
                name=service["name"],
                service_type=service.get("type", "service"),
                owner=service.get("owner", "unknown"),
                cost_monthly=service.get("cost_monthly", 0.0),
                environment=service.get("environment", "production"),
                attributes=service.get("attributes", {}),
                color=SERVICE_TYPE_COLORS.get(service.get("type", "service"), "#6b7280"),
            )

        for dep in self.data.get("dependencies", []):
            self.G.add_edge(
                dep["source"],
                dep["target"],
                dep_type=dep.get("type", "calls"),
                weight=dep.get("weight", 1.0),
            )

    def compute_metrics(self) -> Dict[str, Dict]:
        """Compute centrality and cost metrics for all nodes."""
        metrics = {}

        degree_centrality = nx.degree_centrality(self.G)
        betweenness_centrality = nx.betweenness_centrality(self.G, weight="weight")

        for node_id in self.G.nodes():
            node_data = self.G.nodes[node_id]
            metrics[node_id] = {
                "degree_centrality": round(degree_centrality.get(node_id, 0.0), 4),
                "betweenness_centrality": round(betweenness_centrality.get(node_id, 0.0), 4),
                "in_degree": self.G.in_degree(node_id),
                "out_degree": self.G.out_degree(node_id),
                "cost_monthly": node_data.get("cost_monthly", 0.0),
                "cost_share": 0.0,  # filled below
            }

        # Cost share as % of total
        total_cost = sum(m["cost_monthly"] for m in metrics.values())
        if total_cost > 0:
            for node_id in metrics:
                metrics[node_id]["cost_share"] = round(
                    (metrics[node_id]["cost_monthly"] / total_cost) * 100, 2
                )

        return metrics

    def get_graph_json(self) -> Dict[str, Any]:
        """Return the full graph as JSON-serializable dict with all metrics."""
        metrics = self.compute_metrics()
        total_cost = sum(d.get("cost_monthly", 0) for _, d in self.G.nodes(data=True))

        nodes = []
        for node_id, node_data in self.G.nodes(data=True):
            m = metrics.get(node_id, {})
            nodes.append({
                "id": node_id,
                "name": node_data.get("name", node_id),
                "type": node_data.get("service_type", "service"),
                "owner": node_data.get("owner", ""),
                "cost_monthly": node_data.get("cost_monthly", 0.0),
                "cost_share": m.get("cost_share", 0.0),
                "environment": node_data.get("environment", "production"),
                "attributes": node_data.get("attributes", {}),
                "color": node_data.get("color", "#6b7280"),
                "degree_centrality": m.get("degree_centrality", 0.0),
                "betweenness_centrality": m.get("betweenness_centrality", 0.0),
                "in_degree": m.get("in_degree", 0),
                "out_degree": m.get("out_degree", 0),
                "val": max(1, m.get("degree_centrality", 0.0) * 30) + 4,  # Node size
            })

        links = []
        for src, tgt, edge_data in self.G.edges(data=True):
            links.append({
                "source": src,
                "target": tgt,
                "type": edge_data.get("dep_type", "calls"),
                "weight": edge_data.get("weight", 1.0),
            })

        # Find critical (high betweenness) nodes
        sorted_by_betweenness = sorted(
            nodes, key=lambda n: n["betweenness_centrality"], reverse=True
        )
        critical_nodes = [n["id"] for n in sorted_by_betweenness[:3]]

        # Cost hotspots
        sorted_by_cost = sorted(nodes, key=lambda n: n["cost_monthly"], reverse=True)
        cost_hotspots = [n["id"] for n in sorted_by_cost[:3]]

        return {
            "nodes": nodes,
            "links": links,
            "metrics": {
                "total_services": len(nodes),
                "total_dependencies": len(links),
                "total_cost_monthly": round(total_cost, 2),
                "avg_degree": round(
                    sum(d for _, d in self.G.degree()) / max(1, len(nodes)), 2
                ),
                "critical_nodes": critical_nodes,
                "cost_hotspots": cost_hotspots,
                "is_dag": nx.is_directed_acyclic_graph(self.G),
                "density": round(nx.density(self.G), 4),
                "components": nx.number_weakly_connected_components(self.G),
            },
        }
