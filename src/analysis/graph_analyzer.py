"""
Deep Graph Analyzer — per-node metrics, interesting-node identification,
rich context assembly, and narrative generation.

Pipeline:
  1. Compute graph metrics for every node (centrality, PageRank, clustering,
     degree, cost, cost-per-dependency).
  2. Identify "interesting" nodes that need deep analysis.
  3. For each interesting node, assemble full context (self, dependents,
     dependencies, peer comparison, patterns, risk).
  4. Convert each context into a human-readable narrative suitable for
     LLM consumption or direct display.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

logger = logging.getLogger(__name__)

# ─── Thresholds for "interesting" detection ─────────────────────────
CENTRALITY_THRESHOLD = 0.3       # top ~20 % (adaptive)
COST_THRESHOLD = 500.0           # expensive service
IN_DEGREE_THRESHOLD = 5          # many dependents
COST_ANOMALY_MULTIPLIER = 2.0    # >2x peer average
HEALTH_SCORE_DANGER = 60         # health below this is flagged
MAX_INTERESTING_NODES = 25       # cap for large graphs


# ─── Data classes ───────────────────────────────────────────────────

@dataclass
class NodeMetrics:
    """All computed metrics for a single node."""
    node_id: str
    name: str
    node_type: str
    betweenness_centrality: float = 0.0
    pagerank: float = 0.0
    clustering_coefficient: float = 0.0
    in_degree: int = 0
    out_degree: int = 0
    cost_monthly: float = 0.0
    cost_per_dependency: float = 0.0
    cost_share: float = 0.0
    health_score: float = 100.0
    risk_level: str = "low"
    cpu_utilization: Optional[float] = None
    memory_utilization: Optional[float] = None
    error_count: float = 0.0
    degree_centrality: float = 0.0


@dataclass
class DependencyInfo:
    """Compact description of a single dependency relationship."""
    node_id: str
    name: str
    node_type: str
    edge_type: str = "calls"
    weight: float = 1.0
    cost_monthly: float = 0.0
    health_score: float = 100.0
    risk_level: str = "low"


@dataclass
class PeerComparison:
    """How a node compares to its type-peers."""
    peer_type: str
    peer_count: int
    avg_cost: float = 0.0
    median_cost: float = 0.0
    this_cost: float = 0.0
    cost_ratio: float = 1.0   # this / avg
    avg_centrality: float = 0.0
    this_centrality: float = 0.0
    avg_health: float = 100.0
    this_health: float = 100.0


@dataclass
class NodeContext:
    """Full analysis context for a single interesting node."""
    node_id: str
    name: str
    node_type: str
    metrics: NodeMetrics
    # Why flagged
    interesting_reasons: List[str] = field(default_factory=list)
    # Relationships
    dependencies: List[DependencyInfo] = field(default_factory=list)
    dependents: List[DependencyInfo] = field(default_factory=list)
    # Patterns
    dependency_patterns: List[str] = field(default_factory=list)
    # Peer comparison
    peer_comparison: Optional[PeerComparison] = None
    # Behaviour
    behavioral_flags: List[str] = field(default_factory=list)
    # Risk
    cascading_failure_risk: str = "low"
    single_point_of_failure: bool = False
    # Generated narrative
    narrative: str = ""


@dataclass
class AnalysisReport:
    """Complete analysis output."""
    architecture_name: str = ""
    total_nodes: int = 0
    total_edges: int = 0
    total_cost: float = 0.0
    graph_density: float = 0.0
    is_dag: bool = True
    components: int = 1
    # Per-node metrics (all nodes)
    all_node_metrics: List[Dict[str, Any]] = field(default_factory=list)
    # Interesting nodes with full context
    interesting_nodes: List[Dict[str, Any]] = field(default_factory=list)
    # Summary stats
    summary: Dict[str, Any] = field(default_factory=dict)


# ═════════════════════════════════════════════════════════════════════
#  Graph Analyzer
# ═════════════════════════════════════════════════════════════════════

class GraphAnalyzer:
    """
    Performs deep structural + cost + behavioural analysis of an
    infrastructure graph.

    Accepts either:
      - A graph_data dict (with nodes/edges keys, from CUR transformer)
      - A raw architecture dict (with services/dependencies, from synthetic files)
    """

    def __init__(self, graph_data: Dict[str, Any]):
        self.raw = graph_data
        self.G = nx.DiGraph()
        self._node_attrs: Dict[str, Dict] = {}
        self._build_graph()

    # ── Graph construction ──────────────────────────────────────────

    def _build_graph(self):
        """Construct NetworkX DiGraph from either CUR graph or architecture format."""
        # CUR transformer format: nodes/edges
        nodes = self.raw.get("nodes", [])
        edges = self.raw.get("edges", [])

        # Fallback: architecture format (services/dependencies)
        if not nodes:
            nodes = self.raw.get("services", [])
        if not edges:
            edges = self.raw.get("dependencies", [])

        for n in nodes:
            nid = n.get("id", "")
            attrs = {
                "name": n.get("name", nid),
                "type": n.get("type", n.get("service_type", "service")),
                "cost_monthly": float(n.get("cost_monthly", 0)),
                "health_score": float(n.get("health_score", 100)),
                "risk_level": n.get("risk_level", "low"),
                "cpu_utilization": n.get("cpu_utilization"),
                "memory_utilization": n.get("memory_utilization"),
                "error_count": float(n.get("error_count", 0)),
                "instance_type": n.get("instance_type", ""),
                "region": n.get("region", ""),
                "environment": n.get("environment", "production"),
                "owner": n.get("owner", ""),
                "product_code": n.get("product_code", ""),
                "performance_metrics": n.get("performance_metrics", {}),
                "attributes": n.get("attributes", {}),
                "daily_costs": n.get("daily_costs", {}),
            }
            self.G.add_node(nid, **attrs)
            self._node_attrs[nid] = attrs

        for e in edges:
            src = e.get("source", "")
            tgt = e.get("target", "")
            if src in self.G and tgt in self.G:
                self.G.add_edge(
                    src, tgt,
                    type=e.get("type", e.get("dep_type", "calls")),
                    weight=float(e.get("weight", 1.0)),
                )

        logger.info("GraphAnalyzer built graph: %d nodes, %d edges",
                     self.G.number_of_nodes(), self.G.number_of_edges())

    # ═════════════════════════════════════════════════════════════════
    #  Step 1: Compute metrics for every node
    # ═════════════════════════════════════════════════════════════════

    def compute_all_metrics(self) -> Dict[str, NodeMetrics]:
        """Calculate centrality, PageRank, clustering, degree, cost metrics
        for every node in the graph."""
        if self.G.number_of_nodes() == 0:
            return {}

        # ── Centrality metrics ──
        betweenness = nx.betweenness_centrality(self.G, weight="weight")
        try:
            pagerank = nx.pagerank(self.G, weight="weight", max_iter=200)
        except nx.PowerIterationFailedConvergence:
            pagerank = {n: 1.0 / self.G.number_of_nodes() for n in self.G.nodes()}
        degree_cent = nx.degree_centrality(self.G)

        # Clustering coefficient on undirected projection
        G_und = self.G.to_undirected()
        clustering = nx.clustering(G_und)

        # Total cost for share calculation
        total_cost = sum(
            self.G.nodes[n].get("cost_monthly", 0) for n in self.G.nodes()
        )

        metrics: Dict[str, NodeMetrics] = {}

        for nid in self.G.nodes():
            nd = self.G.nodes[nid]
            in_deg = self.G.in_degree(nid)
            out_deg = self.G.out_degree(nid)
            total_deg = in_deg + out_deg
            cost = float(nd.get("cost_monthly", 0))

            m = NodeMetrics(
                node_id=nid,
                name=nd.get("name", nid),
                node_type=nd.get("type", "service"),
                betweenness_centrality=round(betweenness.get(nid, 0), 6),
                pagerank=round(pagerank.get(nid, 0), 6),
                clustering_coefficient=round(clustering.get(nid, 0), 4),
                in_degree=in_deg,
                out_degree=out_deg,
                cost_monthly=round(cost, 2),
                cost_per_dependency=round(cost / max(total_deg, 1), 2),
                cost_share=round((cost / total_cost * 100) if total_cost > 0 else 0, 2),
                health_score=float(nd.get("health_score", 100)),
                risk_level=nd.get("risk_level", "low"),
                cpu_utilization=nd.get("cpu_utilization"),
                memory_utilization=nd.get("memory_utilization"),
                error_count=float(nd.get("error_count", 0)),
                degree_centrality=round(degree_cent.get(nid, 0), 6),
            )
            metrics[nid] = m

        return metrics

    # ═════════════════════════════════════════════════════════════════
    #  Step 2: Identify interesting nodes
    # ═════════════════════════════════════════════════════════════════

    def identify_interesting_nodes(
        self,
        all_metrics: Dict[str, NodeMetrics],
    ) -> List[Tuple[str, List[str]]]:
        """Return list of (node_id, [reasons]) for nodes that deserve
        deep analysis.  Adaptive thresholds are used for small graphs."""

        if not all_metrics:
            return []

        # ── Adaptive thresholds ──
        centrality_values = [m.betweenness_centrality for m in all_metrics.values()]
        cost_values = [m.cost_monthly for m in all_metrics.values()]

        # Use percentile-based cutoff if graph is too small for absolute
        if len(centrality_values) > 5:
            p80_centrality = sorted(centrality_values)[int(len(centrality_values) * 0.8)]
            centrality_thresh = max(min(CENTRALITY_THRESHOLD, p80_centrality), 0.05)
        else:
            centrality_thresh = 0.05

        if cost_values:
            p80_cost = sorted(cost_values)[int(len(cost_values) * 0.8)]
            cost_thresh = max(min(COST_THRESHOLD, p80_cost), 10.0)
        else:
            cost_thresh = COST_THRESHOLD

        # ── Per-type average cost for anomaly detection ──
        type_costs: Dict[str, List[float]] = defaultdict(list)
        for m in all_metrics.values():
            if m.cost_monthly > 0:
                type_costs[m.node_type].append(m.cost_monthly)
        type_avg_cost = {
            t: statistics.mean(costs) for t, costs in type_costs.items() if costs
        }

        # ── Score each node ──
        scored: List[Tuple[str, List[str], float]] = []

        for nid, m in all_metrics.items():
            reasons: List[str] = []
            score = 0.0

            # High centrality
            if m.betweenness_centrality > centrality_thresh:
                reasons.append(
                    f"High centrality ({m.betweenness_centrality:.3f}) — "
                    f"top traffic bottleneck"
                )
                score += m.betweenness_centrality * 10

            # Expensive
            if m.cost_monthly > cost_thresh:
                reasons.append(
                    f"High cost (${m.cost_monthly:,.0f}/mo) — "
                    f"above ${cost_thresh:,.0f} threshold"
                )
                score += m.cost_monthly / 100

            # Many dependents
            if m.in_degree > IN_DEGREE_THRESHOLD:
                reasons.append(
                    f"Many dependents ({m.in_degree} services depend on it) — "
                    f"high blast radius"
                )
                score += m.in_degree * 2

            # Cost anomaly vs. type peers
            avg = type_avg_cost.get(m.node_type, 0)
            if avg > 0 and m.cost_monthly > avg * COST_ANOMALY_MULTIPLIER:
                ratio = m.cost_monthly / avg
                reasons.append(
                    f"Cost anomaly ({ratio:.1f}x the ${avg:,.0f} "
                    f"average for {m.node_type} services)"
                )
                score += ratio * 3

            # Behavioural anomaly — poor health
            if m.health_score < HEALTH_SCORE_DANGER:
                reasons.append(
                    f"Health alert (score {m.health_score:.0f}/100) — "
                    f"possible performance degradation"
                )
                score += (100 - m.health_score) / 10

            # High CPU
            if m.cpu_utilization is not None and m.cpu_utilization > 80:
                reasons.append(
                    f"CPU spike ({m.cpu_utilization:.0f}%) — "
                    f"may need scaling"
                )
                score += 3

            # Errors
            if m.error_count > 0:
                reasons.append(
                    f"Error activity ({m.error_count:.0f} errors detected)"
                )
                score += min(m.error_count, 10)

            # High PageRank
            avg_pr = statistics.mean(
                mm.pagerank for mm in all_metrics.values()
            ) if all_metrics else 0
            if m.pagerank > avg_pr * 2 and m.pagerank > 0.01:
                reasons.append(
                    f"High PageRank ({m.pagerank:.4f}) — structurally important"
                )
                score += 2

            if reasons:
                scored.append((nid, reasons, score))

        # Sort by composite score, cap at MAX
        scored.sort(key=lambda x: x[2], reverse=True)
        return [(nid, reasons) for nid, reasons, _ in scored[:MAX_INTERESTING_NODES]]

    # ═════════════════════════════════════════════════════════════════
    #  Step 3: Build rich context for each interesting node
    # ═════════════════════════════════════════════════════════════════

    def build_node_context(
        self,
        node_id: str,
        reasons: List[str],
        all_metrics: Dict[str, NodeMetrics],
    ) -> NodeContext:
        """Assemble full context for a single interesting node."""
        nd = self.G.nodes.get(node_id, {})
        m = all_metrics.get(node_id, NodeMetrics(node_id=node_id, name=node_id, node_type="service"))

        ctx = NodeContext(
            node_id=node_id,
            name=m.name,
            node_type=m.node_type,
            metrics=m,
            interesting_reasons=reasons,
        )

        # ── Dependencies (what this node depends on → successors in DiGraph) ──
        for succ in self.G.successors(node_id):
            edge_data = self.G.edges[node_id, succ]
            snd = self.G.nodes.get(succ, {})
            sm = all_metrics.get(succ)
            ctx.dependencies.append(DependencyInfo(
                node_id=succ,
                name=snd.get("name", succ),
                node_type=snd.get("type", "service"),
                edge_type=edge_data.get("type", "calls"),
                weight=edge_data.get("weight", 1.0),
                cost_monthly=float(snd.get("cost_monthly", 0)),
                health_score=float(snd.get("health_score", 100)),
                risk_level=snd.get("risk_level", "low"),
            ))

        # ── Dependents (what depends on this node → predecessors) ──
        for pred in self.G.predecessors(node_id):
            edge_data = self.G.edges[pred, node_id]
            pnd = self.G.nodes.get(pred, {})
            pm = all_metrics.get(pred)
            ctx.dependents.append(DependencyInfo(
                node_id=pred,
                name=pnd.get("name", pred),
                node_type=pnd.get("type", "service"),
                edge_type=edge_data.get("type", "calls"),
                weight=edge_data.get("weight", 1.0),
                cost_monthly=float(pnd.get("cost_monthly", 0)),
                health_score=float(pnd.get("health_score", 100)),
                risk_level=pnd.get("risk_level", "low"),
            ))

        # Sort dependents by weight (heaviest use first)
        ctx.dependents.sort(key=lambda d: d.weight, reverse=True)
        ctx.dependencies.sort(key=lambda d: d.weight, reverse=True)

        # ── Dependency patterns ──
        ctx.dependency_patterns = self._detect_dependency_patterns(node_id, ctx)

        # ── Peer comparison ──
        ctx.peer_comparison = self._build_peer_comparison(node_id, m, all_metrics)

        # ── Behavioural flags ──
        ctx.behavioral_flags = self._detect_behavioral_flags(node_id, nd, m)

        # ── Cascading failure risk ──
        ctx.cascading_failure_risk = self._assess_cascade_risk(node_id, m, ctx)
        ctx.single_point_of_failure = self._is_spof(node_id, m)

        # ── Generate narrative (Step 4) ──
        ctx.narrative = self._generate_narrative(ctx)

        return ctx

    # ── Pattern detection helpers ────────────────────────────────────

    def _detect_dependency_patterns(
        self,
        node_id: str,
        ctx: NodeContext,
    ) -> List[str]:
        """Identify architectural patterns around this node."""
        patterns: List[str] = []
        nd = self.G.nodes.get(node_id, {})
        node_type = nd.get("type", "service")

        # Fan-in pattern (many dependents, few dependencies)
        if len(ctx.dependents) > 3 and len(ctx.dependencies) <= 1:
            patterns.append(
                f"Fan-in bottleneck: {len(ctx.dependents)} services "
                f"converge on this single {node_type}"
            )

        # Fan-out pattern
        if len(ctx.dependencies) > 5:
            patterns.append(
                f"Fan-out sprawl: depends on {len(ctx.dependencies)} "
                f"downstream services — high coupling"
            )

        # No caching layer in front (database or storage without cache dependent)
        if node_type in ("database", "storage"):
            has_cache_upstream = any(
                self.G.nodes.get(d.node_id, {}).get("type") == "cache"
                for d in ctx.dependents
            )
            if not has_cache_upstream and len(ctx.dependents) > 2:
                patterns.append(
                    "No caching layer: multiple services hit this "
                    f"{node_type} directly without a cache"
                )

        # Single point of failure — no alternative paths
        if self._is_spof(node_id, ctx.metrics):
            patterns.append(
                "Single point of failure: removing this node would "
                "disconnect parts of the graph"
            )

        # Synchronous call pattern (high weight edges)
        heavy_callers = [d for d in ctx.dependents if d.weight >= 0.9]
        if heavy_callers:
            names = ", ".join(d.name for d in heavy_callers[:5])
            patterns.append(
                f"Heavy synchronous callers ({len(heavy_callers)}): {names}"
            )

        # Cross-type dependency (e.g., serverless → database)
        cross = Counter(d.node_type for d in ctx.dependencies)
        if len(cross) >= 3:
            types_str = ", ".join(f"{t}({c})" for t, c in cross.most_common())
            patterns.append(f"Cross-type dependencies: {types_str}")

        # Circular dependency
        for dep in ctx.dependencies:
            if self.G.has_edge(dep.node_id, node_id):
                patterns.append(
                    f"Circular dependency with {dep.name} "
                    f"(bidirectional edge detected)"
                )

        return patterns

    def _build_peer_comparison(
        self,
        node_id: str,
        m: NodeMetrics,
        all_metrics: Dict[str, NodeMetrics],
    ) -> PeerComparison:
        """Compare this node to peers of the same type."""
        peers = [
            pm for nid, pm in all_metrics.items()
            if pm.node_type == m.node_type and nid != node_id
        ]

        if not peers:
            return PeerComparison(
                peer_type=m.node_type, peer_count=0,
                this_cost=m.cost_monthly, this_centrality=m.betweenness_centrality,
                this_health=m.health_score,
            )

        peer_costs = [p.cost_monthly for p in peers]
        avg_cost = statistics.mean(peer_costs) if peer_costs else 0
        median_cost = statistics.median(peer_costs) if peer_costs else 0
        avg_cent = statistics.mean(p.betweenness_centrality for p in peers)
        avg_health = statistics.mean(p.health_score for p in peers)

        return PeerComparison(
            peer_type=m.node_type,
            peer_count=len(peers),
            avg_cost=round(avg_cost, 2),
            median_cost=round(median_cost, 2),
            this_cost=round(m.cost_monthly, 2),
            cost_ratio=round(m.cost_monthly / avg_cost, 2) if avg_cost > 0 else 0,
            avg_centrality=round(avg_cent, 6),
            this_centrality=round(m.betweenness_centrality, 6),
            avg_health=round(avg_health, 1),
            this_health=round(m.health_score, 1),
        )

    def _detect_behavioral_flags(
        self,
        node_id: str,
        nd: Dict,
        m: NodeMetrics,
    ) -> List[str]:
        """Detect behavioural anomalies from CloudWatch / performance data."""
        flags: List[str] = []

        cpu = m.cpu_utilization
        mem = m.memory_utilization
        errors = m.error_count

        if cpu is not None:
            if cpu > 90:
                flags.append(f"CRITICAL: CPU at {cpu:.0f}% — imminent saturation")
            elif cpu > 75:
                flags.append(f"WARNING: CPU at {cpu:.0f}% — approaching capacity")
            elif cpu < 10 and m.cost_monthly > 50:
                flags.append(
                    f"WASTE: CPU at {cpu:.0f}% but costs ${m.cost_monthly:.0f}/mo "
                    f"— over-provisioned"
                )

        if mem is not None:
            if mem > 90:
                flags.append(f"CRITICAL: Memory at {mem:.0f}% — OOM risk")
            elif mem > 75:
                flags.append(f"WARNING: Memory at {mem:.0f}% — high utilization")

        if errors > 10:
            flags.append(f"ERROR SPIKE: {errors:.0f} errors detected — investigate immediately")
        elif errors > 0:
            flags.append(f"Errors present: {errors:.0f} errors in monitoring window")

        if m.health_score < 40:
            flags.append(
                f"HEALTH CRITICAL: Score {m.health_score:.0f}/100 — "
                f"service degradation likely"
            )
        elif m.health_score < 70:
            flags.append(
                f"Health degraded: Score {m.health_score:.0f}/100"
            )

        # Cost trend analysis from daily_costs
        daily = nd.get("daily_costs", {})
        if isinstance(daily, dict) and len(daily) >= 3:
            vals = list(daily.values())
            try:
                recent = statistics.mean(vals[-3:])
                older = statistics.mean(vals[:-3]) if len(vals) > 3 else recent
                if older > 0 and recent > older * 1.5:
                    flags.append(
                        f"Cost trending UP: recent avg ${recent:.2f}/day vs "
                        f"${older:.2f}/day earlier (+{((recent/older)-1)*100:.0f}%)"
                    )
            except Exception:
                pass

        # Performance metrics deep-dive
        perf = nd.get("performance_metrics", {})
        if isinstance(perf, dict):
            latency = perf.get("latency", perf.get("Latency", {}).get("value"))
            if latency is not None and latency > 500:
                flags.append(f"High latency: {latency:.0f}ms — user impact likely")

            throttles = perf.get("throttles", perf.get("ThrottledRequests", {}).get("value", 0))
            if throttles and float(throttles) > 0:
                flags.append(f"Throttling detected: {float(throttles):.0f} throttled requests")

            conn = perf.get("DatabaseConnections", {}).get("value")
            if conn is not None and float(conn) > 80:
                flags.append(f"Connection pool pressure: {float(conn):.0f} active connections")

        return flags

    def _assess_cascade_risk(
        self,
        node_id: str,
        m: NodeMetrics,
        ctx: NodeContext,
    ) -> str:
        """Estimate cascading failure risk level."""
        score = 0

        # More dependents = higher risk
        score += min(len(ctx.dependents), 10) * 2

        # High centrality = more traffic flows through
        score += m.betweenness_centrality * 20

        # Poor health amplifies risk
        if m.health_score < 50:
            score += 5
        elif m.health_score < 70:
            score += 3

        # Single point of failure
        if ctx.single_point_of_failure:
            score += 8

        # Heavy callers with high weight
        heavy = sum(1 for d in ctx.dependents if d.weight >= 0.8)
        score += heavy * 2

        # Errors present
        if m.error_count > 0:
            score += min(m.error_count, 5)

        if score >= 20:
            return "critical"
        elif score >= 12:
            return "high"
        elif score >= 6:
            return "moderate"
        return "low"

    def _is_spof(self, node_id: str, m: NodeMetrics) -> bool:
        """Check if removing this node would increase the number of
        weakly connected components (i.e., it's a bridge / articulation point)."""
        if self.G.number_of_nodes() <= 2:
            return m.in_degree > 0

        G_und = self.G.to_undirected()
        # NetworkX articulation point check
        try:
            aps = set(nx.articulation_points(G_und))
            return node_id in aps
        except Exception:
            return False

    # ═════════════════════════════════════════════════════════════════
    #  Step 4: Convert context to narrative
    # ═════════════════════════════════════════════════════════════════

    def _generate_narrative(self, ctx: NodeContext) -> str:
        """Convert a NodeContext into a structured, human-readable narrative."""
        m = ctx.metrics
        lines: List[str] = []

        # ── Header ──
        lines.append(f"═══ {ctx.name} Analysis ═══")
        lines.append("")

        # ── Overview ──
        lines.append("OVERVIEW:")
        type_label = ctx.node_type.replace("_", " ").title()
        lines.append(
            f"  {ctx.name} is a {type_label} service "
            f"costing ${m.cost_monthly:,.2f}/month."
        )
        if ctx.single_point_of_failure:
            lines.append(
                "  ⚠ SINGLE POINT OF FAILURE — removing this node "
                "disconnects parts of the architecture."
            )
        if ctx.interesting_reasons:
            lines.append("  Flagged because:")
            for r in ctx.interesting_reasons:
                lines.append(f"    • {r}")
        lines.append("")

        # ── Structural Position ──
        lines.append("STRUCTURAL POSITION:")
        lines.append(f"  Betweenness centrality: {m.betweenness_centrality:.4f} "
                      f"({self._centrality_label(m.betweenness_centrality)})")
        lines.append(f"  PageRank: {m.pagerank:.4f} "
                      f"({self._pagerank_label(m.pagerank)})")
        lines.append(f"  Clustering coefficient: {m.clustering_coefficient:.4f}")
        lines.append(f"  In-degree: {m.in_degree} services depend on it")
        lines.append(f"  Out-degree: {m.out_degree} services it depends on")
        lines.append(f"  Degree centrality: {m.degree_centrality:.4f}")
        lines.append(f"  Cascading failure risk: {ctx.cascading_failure_risk.upper()}")
        lines.append("")

        # ── Dependents (what depends on this node) ──
        if ctx.dependents:
            lines.append(f"DEPENDENTS ({len(ctx.dependents)} services depend on this):")
            for i, d in enumerate(ctx.dependents, 1):
                health_tag = ""
                if d.health_score < 70:
                    health_tag = f" [DEGRADED {d.health_score:.0f}%]"
                lines.append(
                    f"  {i}. {d.name} ({d.node_type}) "
                    f"— {d.edge_type}, weight {d.weight:.1f}, "
                    f"${d.cost_monthly:,.2f}/mo{health_tag}"
                )
        else:
            lines.append("DEPENDENTS: None (leaf node or terminal service)")
        lines.append("")

        # ── Dependencies (what this node depends on) ──
        if ctx.dependencies:
            lines.append(f"DEPENDENCIES ({len(ctx.dependencies)} downstream services):")
            for i, d in enumerate(ctx.dependencies, 1):
                lines.append(
                    f"  {i}. {d.name} ({d.node_type}) "
                    f"— {d.edge_type}, weight {d.weight:.1f}, "
                    f"${d.cost_monthly:,.2f}/mo"
                )
        else:
            lines.append("DEPENDENCIES: None (root service)")
        lines.append("")

        # ── Dependency Patterns ──
        if ctx.dependency_patterns:
            lines.append("ARCHITECTURAL PATTERNS:")
            for p in ctx.dependency_patterns:
                lines.append(f"  ⚡ {p}")
            lines.append("")

        # ── Peer Comparison ──
        if ctx.peer_comparison and ctx.peer_comparison.peer_count > 0:
            pc = ctx.peer_comparison
            lines.append("PEER COMPARISON:")
            lines.append(f"  Type: {pc.peer_type} ({pc.peer_count} peers)")
            lines.append(f"  This cost: ${pc.this_cost:,.2f}/mo")
            lines.append(f"  Peer avg cost: ${pc.avg_cost:,.2f}/mo "
                          f"(median ${pc.median_cost:,.2f})")
            if pc.cost_ratio > 1:
                lines.append(f"  Cost ratio: {pc.cost_ratio:.1f}x peer average "
                              f"{'⚠ OVER-SPENDING' if pc.cost_ratio > 2 else ''}")
            else:
                lines.append(f"  Cost ratio: {pc.cost_ratio:.1f}x peer average "
                              f"(below average)")
            lines.append(f"  Peer avg centrality: {pc.avg_centrality:.4f} "
                          f"(this: {pc.this_centrality:.4f})")
            lines.append(f"  Peer avg health: {pc.avg_health:.0f}% "
                          f"(this: {pc.this_health:.0f}%)")
            lines.append("")

        # ── Behavioural Flags ──
        if ctx.behavioral_flags:
            lines.append("BEHAVIORAL ANALYSIS:")
            for flag in ctx.behavioral_flags:
                prefix = "🔴" if flag.startswith("CRITICAL") else \
                         "🟡" if flag.startswith("WARNING") else \
                         "🟠" if flag.startswith("ERROR") or flag.startswith("WASTE") else "🔵"
                lines.append(f"  {prefix} {flag}")
            lines.append("")

        # ── Cost Analysis ──
        lines.append("COST ANALYSIS:")
        lines.append(f"  Monthly cost: ${m.cost_monthly:,.2f}")
        lines.append(f"  Cost share: {m.cost_share:.1f}% of total architecture")
        lines.append(f"  Cost per dependency: ${m.cost_per_dependency:,.2f}")
        if ctx.peer_comparison and ctx.peer_comparison.cost_ratio > 2:
            lines.append(
                f"  ⚠ {ctx.peer_comparison.cost_ratio:.1f}x more expensive "
                f"than similar {ctx.peer_comparison.peer_type} services"
            )
        lines.append("")

        # ── Risk Assessment ──
        lines.append("RISK ASSESSMENT:")
        lines.append(f"  Health score: {m.health_score:.0f}/100")
        lines.append(f"  Risk level: {m.risk_level.upper()}")
        lines.append(f"  Cascading failure risk: {ctx.cascading_failure_risk.upper()}")
        lines.append(f"  SPOF: {'YES' if ctx.single_point_of_failure else 'No'}")
        blast_radius = len(ctx.dependents)
        if blast_radius > 0:
            pct = (blast_radius / max(self.G.number_of_nodes(), 1)) * 100
            lines.append(f"  Blast radius: {blast_radius} services ({pct:.0f}% of architecture)")
        lines.append("")

        return "\n".join(lines)

    def _centrality_label(self, c: float) -> str:
        if c > 0.5:
            return "critical bottleneck"
        elif c > 0.3:
            return "significant bottleneck"
        elif c > 0.1:
            return "moderate traffic hub"
        return "low centrality"

    def _pagerank_label(self, pr: float) -> str:
        if pr > 0.1:
            return "highly important"
        elif pr > 0.05:
            return "important"
        elif pr > 0.02:
            return "moderately important"
        return "typical"

    # ═════════════════════════════════════════════════════════════════
    #  Full analysis pipeline — entry point
    # ═════════════════════════════════════════════════════════════════

    def analyze(self) -> AnalysisReport:
        """Run the complete 4-step analysis pipeline and return the report."""
        meta = self.raw.get("metadata", {})

        # Step 1: Compute metrics
        all_metrics = self.compute_all_metrics()

        # Step 2: Identify interesting nodes
        interesting = self.identify_interesting_nodes(all_metrics)

        # Step 3 & 4: Build context + narrative
        interesting_contexts: List[NodeContext] = []
        for node_id, reasons in interesting:
            ctx = self.build_node_context(node_id, reasons, all_metrics)
            interesting_contexts.append(ctx)

        # ── Build report ──
        total_cost = sum(m.cost_monthly for m in all_metrics.values())

        # Summary statistics
        centrality_vals = [m.betweenness_centrality for m in all_metrics.values()]
        cost_vals = [m.cost_monthly for m in all_metrics.values()]
        health_vals = [m.health_score for m in all_metrics.values()]

        # Type distribution
        type_dist = Counter(m.node_type for m in all_metrics.values())

        # Risk distribution
        risk_dist = Counter(m.risk_level for m in all_metrics.values())

        # SPOF count
        spof_count = sum(1 for ctx in interesting_contexts if ctx.single_point_of_failure)

        # Top bottlenecks (by betweenness)
        sorted_by_centrality = sorted(
            all_metrics.values(),
            key=lambda m: m.betweenness_centrality,
            reverse=True,
        )
        top_bottlenecks = [
            {"node_id": m.node_id, "name": m.name,
             "centrality": m.betweenness_centrality}
            for m in sorted_by_centrality[:5]
        ]

        # Top cost hotspots
        sorted_by_cost = sorted(
            all_metrics.values(),
            key=lambda m: m.cost_monthly,
            reverse=True,
        )
        top_cost_hotspots = [
            {"node_id": m.node_id, "name": m.name,
             "cost_monthly": m.cost_monthly, "cost_share": m.cost_share}
            for m in sorted_by_cost[:5]
        ]

        # Top cascade risks
        cascade_risks = [
            {"node_id": ctx.node_id, "name": ctx.name,
             "risk": ctx.cascading_failure_risk,
             "dependents": len(ctx.dependents),
             "spof": ctx.single_point_of_failure}
            for ctx in interesting_contexts
            if ctx.cascading_failure_risk in ("critical", "high")
        ]

        try:
            is_dag = nx.is_directed_acyclic_graph(self.G)
        except Exception:
            is_dag = True

        report = AnalysisReport(
            architecture_name=meta.get("name", "Unknown"),
            total_nodes=self.G.number_of_nodes(),
            total_edges=self.G.number_of_edges(),
            total_cost=round(total_cost, 2),
            graph_density=round(nx.density(self.G), 4) if self.G.number_of_nodes() > 0 else 0,
            is_dag=is_dag,
            components=nx.number_weakly_connected_components(self.G),
            all_node_metrics=[asdict(m) for m in all_metrics.values()],
            interesting_nodes=[asdict(ctx) for ctx in interesting_contexts],
            summary={
                "total_interesting": len(interesting_contexts),
                "spof_count": spof_count,
                "avg_centrality": round(statistics.mean(centrality_vals), 4) if centrality_vals else 0,
                "max_centrality": round(max(centrality_vals), 4) if centrality_vals else 0,
                "avg_cost": round(statistics.mean(cost_vals), 2) if cost_vals else 0,
                "max_cost": round(max(cost_vals), 2) if cost_vals else 0,
                "avg_health": round(statistics.mean(health_vals), 1) if health_vals else 100,
                "min_health": round(min(health_vals), 1) if health_vals else 100,
                "type_distribution": dict(type_dist.most_common()),
                "risk_distribution": dict(risk_dist.most_common()),
                "top_bottlenecks": top_bottlenecks,
                "top_cost_hotspots": top_cost_hotspots,
                "cascade_risks": cascade_risks,
            },
        )

        return report
