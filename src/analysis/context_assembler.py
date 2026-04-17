"""
Architecture Context Assembler
==============================
Takes the output of GraphAnalyzer (per-node metrics, interesting nodes,
narratives) and assembles the full 8-section Architecture Context Package
that gets fed to the LLM for recommendation generation.

Sections:
  1. Architecture Overview
  2. Critical Services (top by centrality)
  3. Cost Analysis
  4. Architectural Anti-Patterns
  5. Risk Assessment
  6. Behavioral Anomalies
  7. Historical Trends
  8. Dependency Analysis
"""

from __future__ import annotations

import logging
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

# PDF best practices are now loaded via src.llm.pdf_knowledge

logger = logging.getLogger(__name__)


# ─── Data classes ───────────────────────────────────────────────────

@dataclass
class CostOutlier:
    node_id: str
    name: str
    node_type: str
    actual_cost: float
    expected_cost: float
    ratio: float
    reason: str


@dataclass
class AntiPattern:
    name: str
    severity: str  # critical | high | medium | low
    description: str
    affected_nodes: List[str]
    recommendation: str
    estimated_savings: float = 0.0


@dataclass
class RiskItem:
    name: str
    severity: str
    description: str
    impact: str
    likelihood: str = "medium"
    affected_nodes: List[str] = field(default_factory=list)


@dataclass
class Anomaly:
    name: str
    severity: str
    node_id: str
    node_name: str
    description: str
    evidence: List[str]
    impact: str


@dataclass
class CriticalDependency:
    source: str
    target: str
    impact_count: int
    description: str


@dataclass
class WasteItem:
    category: str
    description: str
    estimated_monthly: float
    affected_nodes: List[str]


@dataclass
class ArchitectureContextPackage:
    """The complete 8-section context package fed to the LLM."""

    # Section 1: Architecture Overview
    architecture_name: str = ""
    total_services: int = 0
    total_cost_monthly: float = 0.0
    total_dependencies: int = 0
    avg_centrality: float = 0.0
    architecture_type: str = "microservices"
    service_breakdown: Dict[str, Dict] = field(default_factory=dict)  # type → {count, cost}
    geographic_distribution: Dict[str, int] = field(default_factory=dict)  # region/az → count
    cross_az_dependency_count: int = 0

    # Section 2: Critical Services
    critical_services: List[Dict] = field(default_factory=list)

    # Section 3: Cost Analysis
    top_expensive: List[Dict] = field(default_factory=list)
    cost_outliers: List[Dict] = field(default_factory=list)
    waste_detected: List[Dict] = field(default_factory=list)
    total_waste_monthly: float = 0.0

    # Section 4: Architectural Anti-Patterns
    anti_patterns: List[Dict] = field(default_factory=list)

    # Section 5: Risk Assessment
    risks: List[Dict] = field(default_factory=list)

    # Section 6: Behavioral Anomalies
    anomalies: List[Dict] = field(default_factory=list)

    # Section 7: Historical Trends
    cost_trends: Dict[str, Any] = field(default_factory=dict)
    growth_trajectory: Dict[str, Any] = field(default_factory=dict)

    # Section 8: Dependency Analysis
    critical_dependencies: List[Dict] = field(default_factory=list)
    circular_dependencies: List[Dict] = field(default_factory=list)
    orphaned_services: List[str] = field(default_factory=list)
    deep_chains: List[Dict] = field(default_factory=list)

    # Section 9: Graph RAG - Grounded Best Practices & Docs
    rag_best_practices: List[str] = field(default_factory=list)
    rag_relevant_docs: List[Dict[str, str]] = field(default_factory=list)  # {source, content}

    # Legacy keys for client.py compatibility
    bottleneck_nodes: List[Dict] = field(default_factory=list)
    single_points_of_failure: List[Dict] = field(default_factory=list)
    cascade_risks: List[Dict] = field(default_factory=list)

    # Raw data for LLM
    interesting_node_narratives: List[str] = field(default_factory=list)


class ContextAssembler:
    """
    Assembles the full Architecture Context Package from a GraphAnalyzer
    report.

    Usage:
        from src.analysis.graph_analyzer import GraphAnalyzer
        analyzer = GraphAnalyzer(graph_data)
        report = analyzer.analyze()
        assembler = ContextAssembler(graph_data, report)
        ctx_pkg = assembler.assemble()
    """

    def __init__(self, graph_data: Dict[str, Any], analysis_report):
        """
        Parameters
        ----------
        graph_data : dict
            Raw graph data (with nodes/edges or services/dependencies)
        analysis_report : AnalysisReport (dataclass) or dict
            Output from GraphAnalyzer.analyze()
        """
        self.raw = graph_data
        self.report = analysis_report if isinstance(analysis_report, dict) else asdict(analysis_report)
        self.metadata = graph_data.get("metadata", {})

        # Build lookup maps
        self._node_map: Dict[str, Dict] = {}
        for n in self.report.get("all_node_metrics", []):
            self._node_map[n["node_id"]] = n

        self._interesting_map: Dict[str, Dict] = {}
        for n in self.report.get("interesting_nodes", []):
            self._interesting_map[n["node_id"]] = n

        # Edges
        self._edges = graph_data.get("edges", graph_data.get("dependencies", []))

        # Raw nodes for attributes beyond metrics
        self._raw_nodes: Dict[str, Dict] = {}
        for n in graph_data.get("nodes", graph_data.get("services", [])):
            self._raw_nodes[n.get("id", "")] = n

    # ═════════════════════════════════════════════════════════════════
    #  Main entry
    # ═════════════════════════════════════════════════════════════════

    def assemble(self) -> ArchitectureContextPackage:
        """Build the complete 8-section context package."""
        pkg = ArchitectureContextPackage()

        self._section1_overview(pkg)
        self._section2_critical_services(pkg)
        self._section3_cost_analysis(pkg)
        self._section4_anti_patterns(pkg)
        self._section5_risk_assessment(pkg)
        self._section6_anomalies(pkg)
        self._section7_trends(pkg)
        self._section8_dependencies(pkg)
        
        # Section 9: Graph RAG - Index and retrieve grounded best practices
        self._section9_rag_docs(pkg)

        # Populating legacy keys for client.py
        pkg.bottleneck_nodes = [
            {"name": s["name"], "centrality": s["centrality"], "in_degree": s["in_degree"]}
            for s in pkg.critical_services
        ]
        pkg.single_points_of_failure = [
            {"name": s["name"]}
            for s in pkg.critical_services if s.get("single_point_of_failure")
        ]
        # Risks often contain cascade info
        for r in pkg.risks:
            if "Cascading Failure" in r["name"]:
                pkg.cascade_risks.append({
                    "name": r["name"],
                    "risk": r["severity"],
                    "description": r["description"]
                })

        # Attach narratives for LLM context
        for n in self.report.get("interesting_nodes", []):
            if n.get("narrative"):
                pkg.interesting_node_narratives.append(n["narrative"])

        return pkg

    # ═════════════════════════════════════════════════════════════════
    #  Section 1: Architecture Overview
    # ═════════════════════════════════════════════════════════════════

    def _section1_overview(self, pkg: ArchitectureContextPackage):
        summary = self.report.get("summary", {})

        pkg.architecture_name = self.report.get("architecture_name", self.metadata.get("name", "Unknown"))
        pkg.total_services = self.report.get("total_nodes", 0)
        pkg.total_cost_monthly = self.report.get("total_cost", 0)
        pkg.total_dependencies = self.report.get("total_edges", 0)
        pkg.avg_centrality = summary.get("avg_centrality", 0)

        # Detect architecture type
        type_dist = summary.get("type_distribution", {})
        n_services = sum(type_dist.values()) if type_dist else 1
        if n_services > 30:
            pkg.architecture_type = "large-scale microservices"
        elif type_dist.get("serverless", 0) > n_services * 0.4:
            pkg.architecture_type = "serverless"
        elif type_dist.get("container", 0) + type_dist.get("ecs_cluster", 0) > n_services * 0.3:
            pkg.architecture_type = "containerized"
        else:
            pkg.architecture_type = "microservices"

        # Service breakdown by type
        type_costs: Dict[str, Dict] = defaultdict(lambda: {"count": 0, "cost": 0.0})
        for nid, m in self._node_map.items():
            t = m.get("node_type", "service")
            type_costs[t]["count"] += 1
            type_costs[t]["cost"] += m.get("cost_monthly", 0)
        pkg.service_breakdown = {
            t: {"count": v["count"], "cost": round(v["cost"], 2)}
            for t, v in sorted(type_costs.items(), key=lambda x: x[1]["cost"], reverse=True)
        }

        # Geographic distribution
        region_counts: Dict[str, int] = Counter()
        for nid, raw in self._raw_nodes.items():
            region = raw.get("region") or raw.get("attributes", {}).get("availability_zone", "")
            if region:
                region_counts[region] += 1
        if region_counts:
            pkg.geographic_distribution = dict(region_counts.most_common())

        # Cross-AZ dependencies
        cross_az = 0
        for e in self._edges:
            src_raw = self._raw_nodes.get(e.get("source", ""), {})
            tgt_raw = self._raw_nodes.get(e.get("target", ""), {})
            src_az = src_raw.get("region") or src_raw.get("attributes", {}).get("availability_zone", "")
            tgt_az = tgt_raw.get("region") or tgt_raw.get("attributes", {}).get("availability_zone", "")
            if src_az and tgt_az and src_az != tgt_az:
                cross_az += 1
        pkg.cross_az_dependency_count = cross_az

    # ═════════════════════════════════════════════════════════════════
    #  Section 2: Critical Services (Top 5 by centrality)
    # ═════════════════════════════════════════════════════════════════

    def _section2_critical_services(self, pkg: ArchitectureContextPackage):
        sorted_nodes = sorted(
            self._node_map.values(),
            key=lambda m: m.get("betweenness_centrality", 0),
            reverse=True,
        )
        for m in sorted_nodes[:5]:
            nid = m["node_id"]
            interesting = self._interesting_map.get(nid, {})

            severity_label = "CRITICAL BOTTLENECK" if m.get("betweenness_centrality", 0) > 0.4 else \
                             "MAJOR BOTTLENECK" if m.get("betweenness_centrality", 0) > 0.2 else \
                             "MODERATE"

            svc_entry = {
                "node_id": nid,
                "name": m.get("name", nid),
                "type": m.get("node_type", "service"),
                "centrality": round(m.get("betweenness_centrality", 0), 4),
                "severity_label": severity_label,
                "cost_monthly": round(m.get("cost_monthly", 0), 2),
                "cost_share": round(m.get("cost_share", 0), 1),
                "in_degree": m.get("in_degree", 0),
                "out_degree": m.get("out_degree", 0),
                "pagerank": round(m.get("pagerank", 0), 4),
                "health_score": round(m.get("health_score", 100), 1),
                "risk_level": m.get("risk_level", "low"),
                "narrative": interesting.get("narrative", ""),
                "dependents_count": len(interesting.get("dependents", [])),
                "dependencies_count": len(interesting.get("dependencies", [])),
                "dependency_patterns": interesting.get("dependency_patterns", []),
                "behavioral_flags": interesting.get("behavioral_flags", []),
                "cascading_failure_risk": interesting.get("cascading_failure_risk", "low"),
                "single_point_of_failure": interesting.get("single_point_of_failure", False),
            }

            # Peer comparison
            peer = interesting.get("peer_comparison")
            if peer:
                svc_entry["peer_comparison"] = {
                    "peer_count": peer.get("peer_count", 0),
                    "avg_cost": round(peer.get("avg_cost", 0), 2),
                    "cost_ratio": round(peer.get("cost_ratio", 1), 1),
                }

            pkg.critical_services.append(svc_entry)

    # ═════════════════════════════════════════════════════════════════
    #  Section 3: Cost Analysis
    # ═════════════════════════════════════════════════════════════════

    def _section3_cost_analysis(self, pkg: ArchitectureContextPackage):
        summary = self.report.get("summary", {})

        # Top 5 expensive
        hotspots = summary.get("top_cost_hotspots", [])
        pkg.top_expensive = hotspots[:5]

        # Cost outliers — nodes >2x their type average
        type_costs: Dict[str, List[float]] = defaultdict(list)
        for m in self._node_map.values():
            if m.get("cost_monthly", 0) > 0:
                type_costs[m.get("node_type", "service")].append(m["cost_monthly"])
        type_avg = {t: statistics.mean(costs) for t, costs in type_costs.items() if costs}

        outliers = []
        for m in self._node_map.values():
            t = m.get("node_type", "service")
            avg = type_avg.get(t, 0)
            cost = m.get("cost_monthly", 0)
            if avg > 0 and cost > avg * 2 and cost > 10:
                outliers.append({
                    "node_id": m["node_id"],
                    "name": m.get("name", m["node_id"]),
                    "type": t,
                    "actual_cost": round(cost, 2),
                    "expected_cost": round(avg, 2),
                    "ratio": round(cost / avg, 1),
                    "reason": self._infer_cost_outlier_reason(m),
                })
        outliers.sort(key=lambda x: x["ratio"], reverse=True)
        pkg.cost_outliers = outliers[:10]

        # Waste detection
        waste_items = []
        total_waste = 0.0

        # 1. Overprovisioned (high cost, low CPU)
        overprovisioned = []
        for m in self._node_map.values():
            cpu = m.get("cpu_utilization")
            cost = m.get("cost_monthly", 0)
            if cpu is not None and cpu < 15 and cost > 20:
                savings = cost * (1 - cpu / 60)  # if right-sized to 60% target
                overprovisioned.append(m.get("name", m["node_id"]))
                total_waste += savings
        if overprovisioned:
            waste_items.append({
                "category": "Overprovisioned Resources",
                "description": f"{len(overprovisioned)} resources with <15% CPU utilization",
                "estimated_monthly": round(total_waste, 2),
                "affected_nodes": overprovisioned[:10],
            })

        # 2. Cross-AZ data transfer
        if pkg.cross_az_dependency_count > 3:
            transfer_cost = pkg.cross_az_dependency_count * 5.0  # ~$5/dep/mo estimate
            waste_items.append({
                "category": "Cross-AZ Data Transfer",
                "description": (
                    f"{pkg.cross_az_dependency_count} cross-AZ dependencies detected, "
                    f"generating unnecessary transfer costs"
                ),
                "estimated_monthly": round(transfer_cost, 2),
                "affected_nodes": [],
            })
            total_waste += transfer_cost

        # 3. Low utilization expensive services
        for m in self._node_map.values():
            health = m.get("health_score", 100)
            cost = m.get("cost_monthly", 0)
            cpu = m.get("cpu_utilization")
            if cpu is not None and cpu < 5 and cost > 50:
                waste_items.append({
                    "category": "Idle Expensive Service",
                    "description": (
                        f"{m.get('name', m['node_id'])} has {cpu:.0f}% CPU "
                        f"but costs ${cost:.2f}/mo"
                    ),
                    "estimated_monthly": round(cost * 0.7, 2),
                    "affected_nodes": [m.get("name", m["node_id"])],
                })
                total_waste += cost * 0.7

        pkg.waste_detected = waste_items
        pkg.total_waste_monthly = round(total_waste, 2)

    # ═════════════════════════════════════════════════════════════════
    #  Section 4: Architectural Anti-Patterns
    # ═════════════════════════════════════════════════════════════════

    def _section4_anti_patterns(self, pkg: ArchitectureContextPackage):
        patterns = []

        # 1. Cross-AZ chatty communication
        if pkg.cross_az_dependency_count > 3:
            patterns.append({
                "name": "Cross-AZ Chatty Communication",
                "severity": "high",
                "description": (
                    f"Detected {pkg.cross_az_dependency_count} cross-AZ dependencies. "
                    f"High-frequency cross-AZ calls increase latency and data transfer costs."
                ),
                "affected_nodes": [],
                "recommendation": (
                    "Co-locate tightly-coupled services in the same AZ. "
                    "Use read replicas or caches in each AZ for data services."
                ),
                "estimated_savings": pkg.cross_az_dependency_count * 5.0,
            })

        # 2. Missing cache layer — databases hit directly by >2 services
        for m in self._node_map.values():
            if m.get("node_type") in ("database", "storage") and m.get("in_degree", 0) > 2:
                interesting = self._interesting_map.get(m["node_id"], {})
                dep_patterns = interesting.get("dependency_patterns", [])
                if any("No caching layer" in p for p in dep_patterns):
                    patterns.append({
                        "name": "Missing Cache Layer",
                        "severity": "medium",
                        "description": (
                            f"{m.get('name', m['node_id'])} is hit directly by "
                            f"{m.get('in_degree', 0)} services with no caching layer."
                        ),
                        "affected_nodes": [m.get("name", m["node_id"])],
                        "recommendation": (
                            "Add a Redis/Memcached cache in front. "
                            "Potential 70-85% hit rate on read-heavy workloads."
                        ),
                        "estimated_savings": m.get("cost_monthly", 0) * 0.3,
                    })

        # 3. Single points of failure
        spofs = [
            n for n in self.report.get("interesting_nodes", [])
            if n.get("single_point_of_failure")
        ]
        if spofs:
            names = [n.get("name", n["node_id"]) for n in spofs]
            patterns.append({
                "name": "Single Points of Failure",
                "severity": "critical",
                "description": (
                    f"{len(spofs)} services with no redundancy: {', '.join(names[:5])}. "
                    f"Removing any one disconnects the architecture graph."
                ),
                "affected_nodes": names[:10],
                "recommendation": (
                    "Add replicas, failover targets, or circuit breakers. "
                    "For databases: read replicas. For services: multi-AZ deployment."
                ),
                "estimated_savings": 0,
            })

        # 4. Fan-in bottleneck
        for n in self.report.get("interesting_nodes", []):
            dep_patterns = n.get("dependency_patterns", [])
            if any("Fan-in" in p for p in dep_patterns):
                patterns.append({
                    "name": "Fan-In Bottleneck",
                    "severity": "high",
                    "description": (
                        f"{n.get('name', n['node_id'])} receives traffic from "
                        f"{len(n.get('dependents', []))} services — "
                        f"centrality {n.get('metrics', {}).get('betweenness_centrality', 0):.4f}"
                    ),
                    "affected_nodes": [n.get("name", n["node_id"])],
                    "recommendation": (
                        "Introduce load balancing, sharding, or event-driven patterns "
                        "to distribute load."
                    ),
                    "estimated_savings": 0,
                })

        # 5. Circular dependencies
        for n in self.report.get("interesting_nodes", []):
            dep_patterns = n.get("dependency_patterns", [])
            for p in dep_patterns:
                if "Circular" in p:
                    patterns.append({
                        "name": "Circular Dependency",
                        "severity": "medium",
                        "description": p,
                        "affected_nodes": [n.get("name", n["node_id"])],
                        "recommendation": (
                            "Break circular dependencies with event queues or "
                            "mediator patterns to prevent deadlock risks."
                        ),
                        "estimated_savings": 0,
                    })

        pkg.anti_patterns = patterns

    # ═════════════════════════════════════════════════════════════════
    #  Section 5: Risk Assessment
    # ═════════════════════════════════════════════════════════════════

    def _section5_risk_assessment(self, pkg: ArchitectureContextPackage):
        risks = []
        summary = self.report.get("summary", {})
        cascade_risks = summary.get("cascade_risks", [])

        # 1. Cascading failure risk
        if cascade_risks:
            names = [r["name"] for r in cascade_risks[:3]]
            worst = cascade_risks[0]
            risks.append({
                "name": "Cascading Failure Risk",
                "severity": "critical" if worst.get("risk") == "critical" else "high",
                "description": (
                    f"Critical path through {', '.join(names)}. "
                    f"If {worst['name']} fails, {worst.get('dependents', 0)} services are affected "
                    f"({round(worst.get('dependents', 0) / max(pkg.total_services, 1) * 100)}% of architecture)."
                ),
                "impact": f"{worst.get('dependents', 0)} services down, potential full outage",
                "likelihood": "medium",
                "affected_nodes": names,
            })

        # 2. Scalability ceiling (high CPU nodes)
        high_cpu = [
            m for m in self._node_map.values()
            if m.get("cpu_utilization") is not None and m["cpu_utilization"] > 70
        ]
        if high_cpu:
            names = [m.get("name", m["node_id"]) for m in high_cpu[:5]]
            risks.append({
                "name": "Scalability Ceiling",
                "severity": "high",
                "description": (
                    f"{len(high_cpu)} services running above 70% CPU: {', '.join(names)}. "
                    f"At 1.3x current traffic these may saturate."
                ),
                "impact": "Service degradation or outage under traffic spikes",
                "likelihood": "high",
                "affected_nodes": names,
            })

        # 3. Cost explosion risk
        total_cost = pkg.total_cost_monthly
        if total_cost > 0:
            # Estimate 2x traffic cost — non-linear due to bottlenecks
            bottleneck_count = len([
                m for m in self._node_map.values()
                if m.get("betweenness_centrality", 0) > 0.2
            ])
            multiplier = 2.0 + bottleneck_count * 0.5
            projected_2x = total_cost * multiplier
            risks.append({
                "name": "Cost Explosion Risk",
                "severity": "high" if multiplier > 3 else "medium",
                "description": (
                    f"At 2x traffic: Expected ${total_cost * 2:,.0f}, "
                    f"Projected ${projected_2x:,.0f} due to {bottleneck_count} bottleneck amplifiers. "
                    f"Non-linear cost growth through centrality hotspots."
                ),
                "impact": f"${projected_2x - total_cost * 2:,.0f} over-budget at scale",
                "likelihood": "medium",
                "affected_nodes": [],
            })

        # 4. SPOFs
        spof_count = summary.get("spof_count", 0)
        if spof_count > 0:
            risks.append({
                "name": "Single Point of Failure",
                "severity": "critical" if spof_count >= 3 else "high",
                "description": (
                    f"{spof_count} services identified as single points of failure. "
                    f"No redundancy or failover configured."
                ),
                "impact": "Architecture partition if any SPOF fails",
                "likelihood": "low",
                "affected_nodes": [
                    n.get("name", n["node_id"])
                    for n in self.report.get("interesting_nodes", [])
                    if n.get("single_point_of_failure")
                ][:5],
            })

        # 5. Low health services
        min_health = summary.get("min_health", 100)
        if min_health < 60:
            unhealthy = [
                m for m in self._node_map.values()
                if m.get("health_score", 100) < 60
            ]
            names = [m.get("name", m["node_id"]) for m in unhealthy[:5]]
            risks.append({
                "name": "Service Health Degradation",
                "severity": "high",
                "description": (
                    f"{len(unhealthy)} services with health scores below 60%: "
                    f"{', '.join(names)}. Active degradation in progress."
                ),
                "impact": "User-facing errors, latency spikes",
                "likelihood": "high",
                "affected_nodes": names,
            })

        pkg.risks = risks

    # ═════════════════════════════════════════════════════════════════
    #  Section 6: Behavioral Anomalies
    # ═════════════════════════════════════════════════════════════════

    def _section6_anomalies(self, pkg: ArchitectureContextPackage):
        anomalies = []

        for n in self.report.get("interesting_nodes", []):
            flags = n.get("behavioral_flags", [])
            if not flags:
                continue

            for flag in flags:
                severity = "critical" if flag.startswith("CRITICAL") else \
                           "high" if flag.startswith("WARNING") or flag.startswith("ERROR") else \
                           "medium" if flag.startswith("WASTE") else "low"

                anomalies.append({
                    "name": self._anomaly_title(flag),
                    "severity": severity,
                    "node_id": n["node_id"],
                    "node_name": n.get("name", n["node_id"]),
                    "description": flag,
                    "evidence": [flag],
                    "impact": self._anomaly_impact(flag, n),
                })

        # Sort by severity
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        anomalies.sort(key=lambda a: sev_order.get(a["severity"], 4))
        pkg.anomalies = anomalies[:15]

    # ═════════════════════════════════════════════════════════════════
    #  Section 7: Historical Trends
    # ═════════════════════════════════════════════════════════════════

    def _section7_trends(self, pkg: ArchitectureContextPackage):
        # Aggregate daily cost trends from raw nodes
        all_daily: Dict[str, float] = defaultdict(float)
        for nid, raw in self._raw_nodes.items():
            daily = raw.get("daily_costs", {})
            if isinstance(daily, dict):
                for date, cost in daily.items():
                    all_daily[date] += float(cost)

        if all_daily:
            sorted_days = sorted(all_daily.items())
            costs = [c for _, c in sorted_days]
            n = len(costs)

            if n >= 3:
                third = n // 3
                p1 = round(sum(costs[:third]) / max(third, 1) * 30, 2)
                p2 = round(sum(costs[third:2*third]) / max(third, 1) * 30, 2)
                p3 = round(sum(costs[2*third:]) / max(n - 2*third, 1) * 30, 2)

                growth_rate = round(((p3 / p1) - 1) * 100, 1) if p1 > 0 else 0
                trend = "INCREASING" if growth_rate > 10 else \
                        "DECREASING" if growth_rate < -10 else "STABLE"

                pkg.cost_trends = {
                    "data_points": len(sorted_days),
                    "early_period_monthly": p1,
                    "mid_period_monthly": p2,
                    "recent_period_monthly": p3,
                    "growth_rate_pct": growth_rate,
                    "trend": trend,
                    "daily_avg": round(sum(costs) / n, 2),
                }

                # 90-day projection
                if p3 > 0:
                    projected = round(p3 * (1 + growth_rate / 100), 2)
                    pkg.growth_trajectory = {
                        "current_monthly": p3,
                        "projected_90d": projected,
                        "growth_rate": f"+{growth_rate}%" if growth_rate > 0 else f"{growth_rate}%",
                        "trend": trend,
                    }

    # ═════════════════════════════════════════════════════════════════
    #  Section 8: Dependency Analysis
    # ═════════════════════════════════════════════════════════════════

    def _section8_dependencies(self, pkg: ArchitectureContextPackage):
        import networkx as nx

        # Build directed graph
        G = nx.DiGraph()
        for n in self._node_map.values():
            G.add_node(n["node_id"], name=n.get("name", n["node_id"]))
        for e in self._edges:
            src = e.get("source", "")
            tgt = e.get("target", "")
            if src in G and tgt in G:
                G.add_edge(src, tgt, type=e.get("type", "calls"))

        # Critical dependencies (if broken → most impact)
        critical_deps = []
        for src, tgt in G.edges():
            # Count how many nodes become unreachable if this edge is removed
            G_copy = G.copy()
            G_copy.remove_edge(src, tgt)
            orig_components = nx.number_weakly_connected_components(G)
            new_components = nx.number_weakly_connected_components(G_copy)
            if new_components > orig_components:
                impact = G.number_of_nodes()  # rough impact
            else:
                # Count descendants of target that lose reachability from root
                impact = len(nx.descendants(G, tgt)) if tgt in G else 0

            src_name = G.nodes[src].get("name", src) if src in G.nodes else src
            tgt_name = G.nodes[tgt].get("name", tgt) if tgt in G.nodes else tgt

            critical_deps.append({
                "source": src_name,
                "target": tgt_name,
                "impact_count": impact,
                "description": f"If {src_name} → {tgt_name} breaks, {impact} downstream services affected",
            })
        critical_deps.sort(key=lambda x: x["impact_count"], reverse=True)
        pkg.critical_dependencies = critical_deps[:10]

        # Circular dependencies
        try:
            cycles = list(nx.simple_cycles(G))
            for cycle in cycles[:5]:
                names = [G.nodes[n].get("name", n) for n in cycle]
                pkg.circular_dependencies.append({
                    "nodes": names,
                    "description": " → ".join(names) + " → " + names[0],
                })
        except Exception:
            pass

        # Orphaned services (no in-edges and no out-edges, excluding roots)
        for nid in G.nodes():
            if G.in_degree(nid) == 0 and G.out_degree(nid) == 0:
                pkg.orphaned_services.append(G.nodes[nid].get("name", nid))

        # Deep chains (depth > 4)
        try:
            dag = G.copy()
            # Remove cycles for longest path analysis
            while True:
                try:
                    cycle = nx.find_cycle(dag)
                    dag.remove_edge(*cycle[0][:2])
                except nx.NetworkXNoCycle:
                    break

            longest = nx.dag_longest_path(dag)
            if len(longest) > 4:
                names = [dag.nodes[n].get("name", n) for n in longest]
                pkg.deep_chains.append({
                    "depth": len(longest),
                    "chain": " → ".join(names),
                    "description": f"{len(longest)}-hop chain: brittleness risk",
                })
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════
    #  Helpers
    # ═════════════════════════════════════════════════════════════════

    def _section9_rag_docs(self, pkg: ArchitectureContextPackage):
        """Section 9: Graph RAG - Retrieve and ground with documentation.

        Uses the fast pdf_knowledge module (size-limited, cached) instead of
        DocIndexer which hangs on large PDFs.
        """
        try:
            from src.llm.pdf_knowledge import retrieve_relevant_chunks

            # Collect service types from the architecture
            service_types = list({
                m.get("node_type", "service")
                for m in self._node_map.values()
            })

            categories = ["cost optimization", "right-sizing", "security",
                          "reliability", "performance", "well-architected"]

            # Add architecture-specific terms
            if pkg.cross_az_dependency_count > 3:
                categories.append("cross-az data transfer")
            if pkg.total_waste_monthly > 100:
                categories.append("waste unused resources")

            context = retrieve_relevant_chunks(
                service_types=service_types[:10],
                categories=categories,
                max_chars=3000,
            )

            if context:
                pkg.rag_best_practices = [context]
                pkg.rag_relevant_docs = [{"source": "pdf_knowledge", "content": context[:500], "score": 1.0}]
                logger.info("✓ Loaded %d chars of PDF best-practice context", len(context))
            else:
                logger.warning("No PDF best-practice context retrieved")

        except Exception as e:
            logger.warning("Error in _section9_rag_docs: %s", e)

    def _infer_cost_outlier_reason(self, m: Dict) -> str:
        cpu = m.get("cpu_utilization")
        errors = m.get("error_count", 0)
        health = m.get("health_score", 100)

        if cpu is not None and cpu > 80:
            return f"High CPU utilization ({cpu:.0f}%) — auto-scaling or heavy load"
        if cpu is not None and cpu < 10:
            return f"Very low CPU ({cpu:.0f}%) — likely over-provisioned"
        if errors > 10:
            return f"Error activity ({errors:.0f}) — possibly retry storms inflating usage"
        if health < 50:
            return f"Degraded health ({health:.0f}%) — may be in error-recovery loop"
        return "Cost exceeds type average — investigate instance sizing and reserved capacity"

    def _anomaly_title(self, flag: str) -> str:
        if "CPU" in flag:
            return "CPU Utilization Anomaly"
        if "Memory" in flag or "OOM" in flag:
            return "Memory Pressure"
        if "ERROR" in flag or "Error" in flag:
            return "Error Rate Spike"
        if "WASTE" in flag:
            return "Resource Waste Detected"
        if "Cost trending" in flag:
            return "Cost Trend Anomaly"
        if "latency" in flag.lower():
            return "Latency Anomaly"
        if "Throttl" in flag:
            return "Throttling Detected"
        if "Connection" in flag:
            return "Connection Pool Pressure"
        if "Health" in flag:
            return "Health Score Alert"
        return "Behavioral Anomaly"

    def _anomaly_impact(self, flag: str, node: Dict) -> str:
        name = node.get("name", node["node_id"])
        dependents = len(node.get("dependents", []))
        if dependents > 0:
            return f"Affects {dependents} upstream services that depend on {name}"
        return f"May degrade {name} performance and incur additional costs"

    # ═════════════════════════════════════════════════════════════════
    #  Render to text (for LLM prompt)
    # ═════════════════════════════════════════════════════════════════

    def render_context_text(self, pkg: ArchitectureContextPackage) -> str:
        """Render the full context package as structured text for the LLM."""
        lines = []

        # Section 1
        lines.append("═" * 55)
        lines.append("SECTION 1: ARCHITECTURE OVERVIEW")
        lines.append("═" * 55)
        lines.append(f"Architecture: {pkg.architecture_name}")
        lines.append(f"Total Services: {pkg.total_services}")
        lines.append(f"Total Monthly Cost: ${pkg.total_cost_monthly:,.2f}")
        lines.append(f"Total Dependencies: {pkg.total_dependencies} edges")
        lines.append(f"Average Centrality: {pkg.avg_centrality:.4f}")
        lines.append(f"Architecture Type: {pkg.architecture_type}")
        lines.append("")
        lines.append("Service Breakdown by Type:")
        for t, info in pkg.service_breakdown.items():
            lines.append(f"  - {t}: {info['count']} services, ${info['cost']:,.2f} total")
        if pkg.cross_az_dependency_count > 0:
            lines.append(f"\nCross-AZ dependencies: {pkg.cross_az_dependency_count} (problem!)")
        lines.append("")

        # Section 2
        lines.append("═" * 55)
        lines.append("SECTION 2: CRITICAL SERVICES (Top 5 by Centrality)")
        lines.append("═" * 55)
        for i, svc in enumerate(pkg.critical_services, 1):
            lines.append(f"\n{i}. {svc['name']} ({svc['centrality']:.4f} centrality) — {svc['severity_label']}")
            lines.append(f"   Type: {svc['type']}, Cost: ${svc['cost_monthly']:,.2f}/mo ({svc['cost_share']:.1f}%)")
            lines.append(f"   In-degree: {svc['in_degree']}, Out-degree: {svc['out_degree']}")
            lines.append(f"   Health: {svc['health_score']:.0f}%, Risk: {svc['risk_level']}")
            lines.append(f"   Cascade risk: {svc['cascading_failure_risk']}")
            if svc.get("single_point_of_failure"):
                lines.append("   ⚠ SINGLE POINT OF FAILURE")
            if svc.get("dependency_patterns"):
                for p in svc["dependency_patterns"][:3]:
                    lines.append(f"   Pattern: {p}")
        lines.append("")

        # Section 3
        lines.append("═" * 55)
        lines.append("SECTION 3: COST ANALYSIS")
        lines.append("═" * 55)
        lines.append("\nTop 5 Expensive Services:")
        for i, h in enumerate(pkg.top_expensive, 1):
            pct = round(h.get("cost_monthly", 0) / max(pkg.total_cost_monthly, 1) * 100, 1)
            lines.append(f"  {i}. {h['name']}: ${h.get('cost_monthly', 0):,.2f} ({pct}%)")

        if pkg.cost_outliers:
            lines.append("\nCost Outliers (>2x expected):")
            for o in pkg.cost_outliers:
                lines.append(f"  - {o['name']}: Expected ${o['expected_cost']:,.2f}, Actual ${o['actual_cost']:,.2f} ({o['ratio']}x)")
                lines.append(f"    Reason: {o['reason']}")

        if pkg.waste_detected:
            lines.append("\nWaste Detected:")
            for w in pkg.waste_detected:
                lines.append(f"  - {w['category']}: ${w['estimated_monthly']:,.2f}/month")
                lines.append(f"    {w['description']}")
            lines.append(f"  Total waste: ${pkg.total_waste_monthly:,.2f}/month")
        lines.append("")

        # Section 4
        lines.append("═" * 55)
        lines.append("SECTION 4: ARCHITECTURAL ANTI-PATTERNS")
        lines.append("═" * 55)
        for i, ap in enumerate(pkg.anti_patterns, 1):
            lines.append(f"\nAnti-Pattern {i}: {ap['name']} ({ap['severity'].upper()})")
            lines.append(f"  {ap['description']}")
            lines.append(f"  Recommendation: {ap['recommendation']}")
            if ap.get("estimated_savings", 0) > 0:
                lines.append(f"  Estimated savings: ${ap['estimated_savings']:,.2f}/month")
        lines.append("")

        # Section 5
        lines.append("═" * 55)
        lines.append("SECTION 5: RISK ASSESSMENT")
        lines.append("═" * 55)
        for i, r in enumerate(pkg.risks, 1):
            lines.append(f"\nRisk {i}: {r['name']} ({r['severity'].upper()})")
            lines.append(f"  {r['description']}")
            lines.append(f"  Impact: {r['impact']}")
            lines.append(f"  Likelihood: {r.get('likelihood', 'medium')}")
        lines.append("")

        # Section 6
        lines.append("═" * 55)
        lines.append("SECTION 6: BEHAVIORAL ANOMALIES")
        lines.append("═" * 55)
        for i, a in enumerate(pkg.anomalies[:10], 1):
            lines.append(f"\nAnomaly {i}: {a['name']} ({a['severity'].upper()})")
            lines.append(f"  Service: {a['node_name']}")
            lines.append(f"  {a['description']}")
            lines.append(f"  Impact: {a['impact']}")
        lines.append("")

        # Section 7
        lines.append("═" * 55)
        lines.append("SECTION 7: HISTORICAL TRENDS")
        lines.append("═" * 55)
        if pkg.cost_trends:
            t = pkg.cost_trends
            lines.append(f"  Data points: {t.get('data_points', 0)} days")
            lines.append(f"  Early period: ${t.get('early_period_monthly', 0):,.2f}/mo")
            lines.append(f"  Recent period: ${t.get('recent_period_monthly', 0):,.2f}/mo")
            lines.append(f"  Growth rate: {t.get('growth_rate_pct', 0):.1f}%")
            lines.append(f"  Trend: {t.get('trend', 'N/A')}")
        if pkg.growth_trajectory:
            g = pkg.growth_trajectory
            lines.append(f"  Projected (90d): ${g.get('projected_90d', 0):,.2f}/mo")
        else:
            lines.append("  Insufficient data for trend analysis")
        lines.append("")

        # Section 8
        lines.append("═" * 55)
        lines.append("SECTION 8: DEPENDENCY ANALYSIS")
        lines.append("═" * 55)
        if pkg.critical_dependencies:
            lines.append("\nMost Critical Dependencies (if broken, highest impact):")
            for i, d in enumerate(pkg.critical_dependencies[:5], 1):
                lines.append(f"  {i}. {d['source']} → {d['target']} (impacts {d['impact_count']} services)")

        if pkg.circular_dependencies:
            lines.append(f"\nCircular Dependencies: {len(pkg.circular_dependencies)} detected")
            for cd in pkg.circular_dependencies:
                lines.append(f"  ⚠ {cd['description']}")
        else:
            lines.append("\nCircular Dependencies: None detected ✓")

        if pkg.orphaned_services:
            lines.append(f"\nOrphaned Services: {', '.join(pkg.orphaned_services)}")
        else:
            lines.append("\nOrphaned Services: None detected ✓")

        if pkg.deep_chains:
            lines.append("\nDeeply Nested Chains (depth > 4):")
            for dc in pkg.deep_chains:
                lines.append(f"  {dc['chain']} ({dc['depth']}-hop chain)")
        lines.append("")

        return "\n".join(lines)
