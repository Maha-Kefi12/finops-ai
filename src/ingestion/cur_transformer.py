"""
CUR → Graph Transformer
========================
Takes parsed CUR data + CloudWatch metrics and produces a graph-ready
JSON structure with nodes, edges, and dependencies.

Pipeline flow:
  Raw CUR JSON → Parsed CUR → + CloudWatch Metrics → Transformed JSON
  → Nodes + Edges + Dependencies → Neo4j Graph

Edge inference rules:
  1. VPC containment: subnets → VPC, security groups → VPC
  2. Compute → Database: EC2/ECS/Lambda that share subnets/SGs with RDS
  3. Load Balancer → Compute: ALB/NLB → EC2/ECS targets
  4. Compute → Cache: services in same VPC/subnet as ElastiCache
  5. Compute → Queue: Lambda/ECS → SQS (event source mappings)
  6. API Gateway → Compute: gateway → Lambda/ECS integrations
  7. Compute → Storage: services → S3 (IAM role-based inference)
  8. Monitoring → All: CloudWatch → monitored resources
  9. CDN → Load Balancer: CloudFront → ALB origins
  10. Cost correlation: resources with correlated daily cost patterns
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
#  Type constants
# ─────────────────────────────────────────────────────────────────────
COMPUTE_TYPES = {"compute", "container", "serverless", "batch", "ecs_cluster"}
DATA_TYPES = {"database", "cache", "storage", "search", "streaming"}
NETWORK_TYPES = {"load_balancer", "gateway", "cdn", "dns", "networking", "vpc", "subnet", "security_group"}
SUPPORT_TYPES = {"monitoring", "logging", "notification", "security", "devops", "iam_role", "container_registry"}


class CURTransformer:
    """Transform parsed CUR data + CloudWatch metrics into a graph-ready structure."""

    def __init__(
        self,
        parsed_cur: Dict[str, Any],
        cloudwatch_metrics: Optional[Dict[str, Dict]] = None,
        region: str = "us-east-1",
    ):
        self.parsed = parsed_cur
        self.metrics = cloudwatch_metrics or {}
        self.region = region

    def transform(self) -> Dict[str, Any]:
        """Transform CUR + metrics into full graph structure.

        Returns:
            {
                "metadata": {...},
                "nodes": [...],
                "edges": [...],
                "raw_cur_summary": {...},
                "performance_summary": {...},
            }
        """
        resources = self.parsed.get("resources", [])
        summary = self.parsed.get("summary", {})

        # Stage 1: Build nodes from CUR resources
        nodes = self._build_nodes(resources)

        # Stage 2: Infer edges (dependencies)
        edges = self._infer_edges(nodes)

        # Stage 3: Compute node-level graph metrics
        nodes = self._enrich_with_metrics(nodes, edges)

        # Stage 4: Build performance summary
        perf_summary = self._build_performance_summary(nodes)

        total_cost = sum(n.get("cost_monthly", 0) for n in nodes)

        return {
            "metadata": {
                "name": f"CUR Analysis ({self.region})",
                "pattern": "cur_discovered",
                "complexity": "high" if len(nodes) >= 30 else "medium" if len(nodes) >= 10 else "low",
                "environment": "production",
                "region": self.region,
                "source": "cur",
                "total_services": len(nodes),
                "total_dependencies": len(edges),
                "total_cost_monthly": round(total_cost, 2),
                "billing_period_start": summary.get("billing_period_start"),
                "billing_period_end": summary.get("billing_period_end"),
            },
            "nodes": nodes,
            "edges": edges,
            "raw_cur_summary": summary,
            "services_breakdown": self.parsed.get("services_breakdown", []),
            "daily_costs": self.parsed.get("daily_costs", []),
            "performance_summary": perf_summary,
        }

    def _build_nodes(self, resources: List[Dict]) -> List[Dict]:
        """Build graph nodes from CUR resources, enriched with CloudWatch metrics."""
        nodes = []

        for res in resources:
            rid = res.get("discovered_id") or res.get("resource_id") or str(hashlib.md5(
                f"{res.get('product_code', '')}:{res.get('usage_type', '')}".encode()
            ).hexdigest()[:12])

            node_type = res.get("resource_type", "service")
            cost = res.get("unblended_cost", 0)

            # Get CloudWatch metrics for this resource
            cw_metrics = self.metrics.get(rid, {})
            health_score = cw_metrics.get("_health_score", 100)

            # Risk level based on cost + health
            risk_level = self._compute_risk_level(cost, health_score, node_type)

            node = {
                "id": rid,
                "name": res.get("name", rid),
                "type": node_type,
                "product_code": res.get("product_code", ""),
                "instance_type": res.get("instance_type", ""),
                "region": res.get("region", self.region),
                "cost_monthly": round(cost, 2),
                "cost_daily_avg": round(cost / 30, 2) if cost > 0 else 0,
                "usage_amount": res.get("usage_amount", 0),
                "line_item_count": res.get("line_item_count", 0),
                "daily_costs": res.get("daily_costs", {}),
                # Performance metrics
                "health_score": health_score,
                "risk_level": risk_level,
                "cpu_utilization": cw_metrics.get("CPUUtilization", {}).get("value", None),
                "memory_utilization": cw_metrics.get("MemoryUtilization", {}).get("value", None),
                "error_count": cw_metrics.get("Errors", {}).get("value", 0),
                "performance_metrics": self._extract_perf_metrics(cw_metrics),
                "environment": "production",
                "owner": "",
                "attributes": {
                    "operation": res.get("operation", ""),
                    "usage_type": res.get("usage_type", ""),
                    **({"cloudwatch": True} if cw_metrics else {}),
                },
            }
            nodes.append(node)

        return nodes

    def _infer_edges(self, nodes: List[Dict]) -> List[Dict]:
        """Infer dependency edges between nodes based on resource types and patterns."""
        edges: List[Dict] = []
        edge_set: Set[str] = set()

        node_map = {n["id"]: n for n in nodes}
        type_groups: Dict[str, List[str]] = defaultdict(list)
        for n in nodes:
            type_groups[n["type"]].append(n["id"])

        # Rule 1: Load Balancer → Compute
        for lb_id in type_groups.get("load_balancer", []):
            for compute_id in (
                type_groups.get("compute", []) +
                type_groups.get("container", []) +
                type_groups.get("serverless", [])
            ):
                self._add_edge(edges, edge_set, lb_id, compute_id, "routes_to", 1.0)

        # Rule 2: Compute → Database
        for compute_type in ["compute", "container", "serverless"]:
            for c_id in type_groups.get(compute_type, []):
                for db_id in type_groups.get("database", []):
                    self._add_edge(edges, edge_set, c_id, db_id, "queries", 0.9)

        # Rule 3: Compute → Cache
        for compute_type in ["compute", "container", "serverless"]:
            for c_id in type_groups.get(compute_type, []):
                for cache_id in type_groups.get("cache", []):
                    self._add_edge(edges, edge_set, c_id, cache_id, "caches_via", 0.7)

        # Rule 4: Compute → Queue
        for compute_type in ["compute", "container", "serverless"]:
            for c_id in type_groups.get(compute_type, []):
                for q_id in type_groups.get("queue", []):
                    self._add_edge(edges, edge_set, c_id, q_id, "publishes_to", 0.6)

        # Rule 5: API Gateway → Compute
        for gw_id in type_groups.get("gateway", []):
            for compute_type in ["compute", "container", "serverless"]:
                for c_id in type_groups.get(compute_type, []):
                    self._add_edge(edges, edge_set, gw_id, c_id, "invokes", 0.8)

        # Rule 6: CDN → Load Balancer
        for cdn_id in type_groups.get("cdn", []):
            for lb_id in type_groups.get("load_balancer", []):
                self._add_edge(edges, edge_set, cdn_id, lb_id, "origin", 0.9)

        # Rule 7: Compute → Storage
        for compute_type in ["compute", "container", "serverless"]:
            for c_id in type_groups.get(compute_type, []):
                for s_id in type_groups.get("storage", []):
                    self._add_edge(edges, edge_set, c_id, s_id, "reads_writes", 0.5)

        # Rule 8: Queue → Compute (consumers)
        for q_id in type_groups.get("queue", []):
            for c_id in type_groups.get("serverless", []):
                self._add_edge(edges, edge_set, q_id, c_id, "triggers", 0.7)

        # Rule 9: Notification → Compute
        for n_id in type_groups.get("notification", []):
            for c_id in type_groups.get("serverless", []):
                self._add_edge(edges, edge_set, n_id, c_id, "notifies", 0.5)

        # Rule 10: Cost correlation edges (nodes with similar daily cost patterns)
        correlated = self._find_cost_correlations(nodes)
        for src, tgt, strength in correlated:
            if f"{src}|{tgt}" not in edge_set and f"{tgt}|{src}" not in edge_set:
                self._add_edge(edges, edge_set, src, tgt, "cost_correlated", round(strength, 2))

        # Rule 11: VPC containment
        for subnet_id in type_groups.get("subnet", []):
            for vpc_id in type_groups.get("vpc", []) + type_groups.get("networking", []):
                self._add_edge(edges, edge_set, subnet_id, vpc_id, "belongs_to", 1.0)

        # Rule 12: Security group → VPC
        for sg_id in type_groups.get("security_group", []):
            for vpc_id in type_groups.get("vpc", []) + type_groups.get("networking", []):
                self._add_edge(edges, edge_set, sg_id, vpc_id, "attached_to", 1.0)

        return edges

    def _add_edge(
        self,
        edges: List[Dict],
        edge_set: Set[str],
        source: str,
        target: str,
        dep_type: str,
        weight: float,
    ):
        """Add an edge if it doesn't already exist."""
        key = f"{source}|{target}"
        if key in edge_set or source == target:
            return
        edge_set.add(key)
        edges.append({
            "source": source,
            "target": target,
            "type": dep_type,
            "weight": weight,
        })

    def _find_cost_correlations(self, nodes: List[Dict], threshold: float = 0.7) -> List[Tuple[str, str, float]]:
        """Find pairs of resources with correlated daily cost patterns."""
        correlations = []

        # Only consider nodes with daily cost data
        nodes_with_costs = [
            n for n in nodes
            if n.get("daily_costs") and len(n["daily_costs"]) >= 3
        ]

        if len(nodes_with_costs) < 2:
            return correlations

        # Limit to top 20 most expensive to avoid O(n²) explosion
        nodes_with_costs.sort(key=lambda n: n.get("cost_monthly", 0), reverse=True)
        nodes_with_costs = nodes_with_costs[:20]

        for i, n1 in enumerate(nodes_with_costs):
            for n2 in nodes_with_costs[i + 1:]:
                if n1["type"] == n2["type"]:
                    continue  # same-type correlation is trivial
                corr = self._pearson_correlation(n1["daily_costs"], n2["daily_costs"])
                if corr and corr > threshold:
                    correlations.append((n1["id"], n2["id"], corr))

        return correlations[:10]  # Limit to strongest 10

    def _pearson_correlation(self, costs_a: Dict[str, float], costs_b: Dict[str, float]) -> Optional[float]:
        """Compute Pearson correlation between two daily cost time series."""
        common_dates = set(costs_a.keys()) & set(costs_b.keys())
        if len(common_dates) < 3:
            return None

        dates = sorted(common_dates)
        a = [costs_a[d] for d in dates]
        b = [costs_b[d] for d in dates]

        n = len(a)
        mean_a = sum(a) / n
        mean_b = sum(b) / n

        cov = sum((a[i] - mean_a) * (b[i] - mean_b) for i in range(n))
        std_a = math.sqrt(sum((x - mean_a) ** 2 for x in a))
        std_b = math.sqrt(sum((x - mean_b) ** 2 for x in b))

        if std_a == 0 or std_b == 0:
            return None

        return cov / (std_a * std_b)

    def _enrich_with_metrics(self, nodes: List[Dict], edges: List[Dict]) -> List[Dict]:
        """Compute graph centrality metrics for each node."""
        # Build simple adjacency for degree/centrality
        in_degree: Dict[str, int] = defaultdict(int)
        out_degree: Dict[str, int] = defaultdict(int)
        total_cost = sum(n.get("cost_monthly", 0) for n in nodes)

        for e in edges:
            out_degree[e["source"]] += 1
            in_degree[e["target"]] += 1

        n = max(len(nodes) - 1, 1)
        for node in nodes:
            nid = node["id"]
            node["in_degree"] = in_degree.get(nid, 0)
            node["out_degree"] = out_degree.get(nid, 0)
            node["degree_centrality"] = round((in_degree.get(nid, 0) + out_degree.get(nid, 0)) / n, 4)
            node["cost_share"] = round((node.get("cost_monthly", 0) / total_cost * 100) if total_cost > 0 else 0, 2)

        return nodes

    def _compute_risk_level(self, cost: float, health_score: int, node_type: str) -> str:
        """Compute risk level from cost, health, and type."""
        risk_score = 0

        # Cost-based risk
        if cost > 100:
            risk_score += 3
        elif cost > 50:
            risk_score += 2
        elif cost > 10:
            risk_score += 1

        # Health-based risk
        if health_score < 50:
            risk_score += 3
        elif health_score < 70:
            risk_score += 2
        elif health_score < 85:
            risk_score += 1

        # Critical types get higher risk
        if node_type in ("database", "load_balancer"):
            risk_score += 1

        if risk_score >= 5:
            return "critical"
        elif risk_score >= 3:
            return "high"
        elif risk_score >= 2:
            return "medium"
        return "low"

    def _extract_perf_metrics(self, cw_metrics: Dict) -> Dict[str, Any]:
        """Extract key performance metrics from CloudWatch data."""
        perf = {}
        skip_keys = {"resource_id", "resource_name", "resource_type",
                      "_collection_time", "_health_score", "_estimated"}
        for key, value in cw_metrics.items():
            if key in skip_keys:
                continue
            if isinstance(value, dict) and "value" in value:
                perf[key] = {
                    "value": value["value"],
                    "unit": value.get("unit", ""),
                    "average": value.get("average", 0),
                }
        return perf

    def _build_performance_summary(self, nodes: List[Dict]) -> Dict[str, Any]:
        """Build an overall performance summary from all nodes."""
        total_nodes = len(nodes)
        healthy = sum(1 for n in nodes if n.get("health_score", 100) >= 80)
        degraded = sum(1 for n in nodes if 50 <= n.get("health_score", 100) < 80)
        unhealthy = sum(1 for n in nodes if n.get("health_score", 100) < 50)

        cpu_values = [n["cpu_utilization"] for n in nodes if n.get("cpu_utilization") is not None]
        mem_values = [n["memory_utilization"] for n in nodes if n.get("memory_utilization") is not None]

        risk_counts = defaultdict(int)
        for n in nodes:
            risk_counts[n.get("risk_level", "low")] += 1

        return {
            "total_resources": total_nodes,
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "avg_health_score": round(sum(n.get("health_score", 100) for n in nodes) / max(total_nodes, 1), 1),
            "avg_cpu_utilization": round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else None,
            "avg_memory_utilization": round(sum(mem_values) / len(mem_values), 1) if mem_values else None,
            "risk_distribution": dict(risk_counts),
        }
