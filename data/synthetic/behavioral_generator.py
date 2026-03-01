#!/usr/bin/env python3
"""
Behavioral Dataset Generator — reads existing architecture JSONs, builds
NetworkX dependency graphs, simulates thousands of traffic / load scenarios
via Monte Carlo, traces cause-effect chains through the graph, and outputs
a 50 000+ line JSONL behavioral dataset.

Each record captures:
  - The architecture and traffic scenario
  - The full cause→effect chain (cascade propagation)
  - Per-service stress metrics (CPU, memory, latency, IOPS, cost)
  - Structural pattern detection (centralization, depth, feedback loops, asymmetric scaling)
  - Amplification factor and risk classification
  - Probability distribution parameters for Monte Carlo analysis

Usage
-----
    python data/synthetic/behavioral_generator.py          # → data/behavioral/
    python data/synthetic/behavioral_generator.py --trials 8000  # more trials per arch
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx  # already in requirements.txt

# ────────────────────────────────── constants ──────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SYNTHETIC_DIR = SCRIPT_DIR
OUTPUT_DIR = SCRIPT_DIR.parent / "behavioral"

# Scaling behaviour per service type
# Each type has a *scaling_model* that controls how cost & latency react
# when the traffic multiplier grows.
SCALING_MODELS: Dict[str, Dict[str, Any]] = {
    "service":       {"cost_exp": 1.0,  "latency_exp": 0.7,  "cpu_base": 0.35, "mem_base": 0.40, "scale": "horizontal"},
    "database":      {"cost_exp": 1.6,  "latency_exp": 1.3,  "cpu_base": 0.45, "mem_base": 0.55, "scale": "vertical"},
    "cache":         {"cost_exp": 1.1,  "latency_exp": 0.4,  "cpu_base": 0.20, "mem_base": 0.60, "scale": "horizontal"},
    "storage":       {"cost_exp": 1.0,  "latency_exp": 0.3,  "cpu_base": 0.10, "mem_base": 0.15, "scale": "horizontal"},
    "serverless":    {"cost_exp": 1.0,  "latency_exp": 0.5,  "cpu_base": 0.30, "mem_base": 0.30, "scale": "horizontal"},
    "queue":         {"cost_exp": 1.0,  "latency_exp": 0.2,  "cpu_base": 0.10, "mem_base": 0.10, "scale": "horizontal"},
    "load_balancer": {"cost_exp": 1.0,  "latency_exp": 0.1,  "cpu_base": 0.15, "mem_base": 0.10, "scale": "horizontal"},
    "cdn":           {"cost_exp": 0.9,  "latency_exp": 0.1,  "cpu_base": 0.05, "mem_base": 0.05, "scale": "horizontal"},
    "search":        {"cost_exp": 1.4,  "latency_exp": 1.1,  "cpu_base": 0.40, "mem_base": 0.50, "scale": "vertical"},
    "batch":         {"cost_exp": 1.2,  "latency_exp": 0.9,  "cpu_base": 0.50, "mem_base": 0.45, "scale": "horizontal"},
}

# ────────────────────────────────── data classes ──────────────────────────
@dataclass
class ServiceStress:
    """Per-service stress metrics under a given traffic multiplier."""
    service_id: str
    service_name: str
    service_type: str
    baseline_cost: float
    stressed_cost: float
    cost_delta: float
    cost_delta_pct: float
    cpu_utilisation: float          # 0-1
    memory_utilisation: float       # 0-1
    latency_ms: float
    iops: float
    is_overloaded: bool             # cpu > 0.85 or mem > 0.90
    scaling_model: str              # horizontal / vertical
    pressure_received: float        # 0-1, how much upstream pressure reaches this node

@dataclass
class CascadeStep:
    """One cause → effect step in a cascade chain."""
    source: str
    target: str
    edge_type: str
    edge_weight: float
    pressure_propagated: float
    target_cpu_after: float
    target_latency_after: float

@dataclass
class StructuralPatterns:
    """Detected structural-risk patterns in the graph."""
    centralization_score: float          # 0-1
    centralization_hub: Optional[str]    # node with highest in-degree
    max_depth: int                        # longest simple path
    depth_chain: List[str]                # the longest chain
    has_cycles: bool
    cycles: List[List[str]]
    asymmetric_pairs: List[Dict[str, str]]  # [{horizontal: ..., vertical: ...}]
    dominant_pattern: str                    # centralization | depth | cycle | asymmetry | balanced

@dataclass
class BehavioralRecord:
    """A single row in the behavioural JSONL dataset."""
    record_id: str
    timestamp: str
    # Architecture
    architecture_name: str
    architecture_pattern: str
    architecture_complexity: str
    total_services: int
    total_dependencies: int
    baseline_cost_monthly: float
    # Scenario
    traffic_multiplier: float
    scenario_label: str          # e.g. "black_friday", "nightly_low", "gradual_ramp"
    time_of_day: str             # peak / off-peak / night
    # Graph metrics
    graph_density: float
    is_dag: bool
    avg_degree: float
    max_betweenness_node: str
    max_betweenness_value: float
    max_degree_node: str
    max_degree_value: float
    # Structural patterns
    structural_patterns: Dict[str, Any]
    # Cascade
    cascade_chain: List[Dict[str, Any]]
    cascade_depth: int
    cascade_width: int           # how many nodes affected
    # Stress results
    stressed_total_cost: float
    cost_growth_ratio: float     # stressed_cost / baseline_cost
    amplification_factor: float  # cost_growth_ratio / traffic_multiplier
    risk_class: str              # linear | superlinear | explosive
    overloaded_services: List[str]
    overload_probability: float  # estimated from noise
    # Per-service breakdown
    service_stress: List[Dict[str, Any]]
    # Monte Carlo distribution params (from multi-trial noise)
    mc_cost_mean: float
    mc_cost_std: float
    mc_cost_p95: float
    mc_overload_prob: float

# ────────────────────────────── graph builder ─────────────────────────────

class ArchitectureGraph:
    """Wraps a single architecture JSON into a NetworkX DiGraph and provides
    all the graph-theory analyses needed for behavioral simulation."""

    def __init__(self, arch_data: Dict[str, Any]):
        self.data = arch_data
        self.meta = arch_data["metadata"]
        self.G = nx.DiGraph()
        self._service_map: Dict[str, Dict] = {}
        self._build()

    # ── build ─────────────────────────────────────────────────────────
    def _build(self):
        for svc in self.data["services"]:
            sid = svc["id"]
            self._service_map[sid] = svc
            self.G.add_node(
                sid,
                name=svc["name"],
                type=svc["type"],
                cost=svc["cost_monthly"],
                owner=svc.get("owner", "unknown"),
                attributes=svc.get("attributes", {}),
            )
        for dep in self.data["dependencies"]:
            self.G.add_edge(
                dep["source"], dep["target"],
                type=dep["type"],
                weight=dep.get("weight", 1.0),
            )

    # ── metrics ───────────────────────────────────────────────────────
    def density(self) -> float:
        return nx.density(self.G)

    def is_dag(self) -> bool:
        return nx.is_directed_acyclic_graph(self.G)

    def avg_degree(self) -> float:
        if len(self.G) == 0:
            return 0
        return sum(d for _, d in self.G.degree()) / len(self.G)

    def degree_centrality(self) -> Dict[str, float]:
        return nx.degree_centrality(self.G)

    def betweenness_centrality(self) -> Dict[str, float]:
        return nx.betweenness_centrality(self.G, weight="weight")

    def top_node(self, metric_dict: Dict[str, float]) -> Tuple[str, float]:
        if not metric_dict:
            return ("", 0.0)
        node = max(metric_dict, key=metric_dict.get)
        return node, metric_dict[node]

    # ── structural patterns ───────────────────────────────────────────
    def detect_patterns(self) -> StructuralPatterns:
        # 1) Centralization — look at in-degree
        in_deg = dict(self.G.in_degree())
        max_in = max(in_deg.values()) if in_deg else 0
        n = len(self.G)
        centralization = 0.0
        hub = None
        if n > 1 and max_in > 0:
            centralization = sum(max_in - d for d in in_deg.values()) / ((n - 1) * (n - 2) + 0.001)
            centralization = min(centralization, 1.0)
            hub = max(in_deg, key=in_deg.get)

        # 2) Depth — longest simple path (DAG → topological, else BFS)
        longest_path: List[str] = []
        if self.is_dag():
            longest_path = nx.dag_longest_path(self.G)
        else:
            for source in self.G.nodes:
                for target in self.G.nodes:
                    if source != target:
                        try:
                            for p in nx.all_simple_paths(self.G, source, target, cutoff=10):
                                if len(p) > len(longest_path):
                                    longest_path = p
                        except nx.NetworkXError:
                            pass

        # 3) Feedback loops (cycles)
        cycles = list(nx.simple_cycles(self.G))
        cycles = [c for c in cycles if len(c) <= 8]  # cap for sanity

        # 4) Asymmetric scaling — find pairs where one is horizontal, other vertical
        asym_pairs = []
        for u, v in self.G.edges:
            u_type = self.G.nodes[u].get("type", "service")
            v_type = self.G.nodes[v].get("type", "service")
            u_scale = SCALING_MODELS.get(u_type, SCALING_MODELS["service"])["scale"]
            v_scale = SCALING_MODELS.get(v_type, SCALING_MODELS["service"])["scale"]
            if u_scale != v_scale:
                asym_pairs.append({"horizontal": u if u_scale == "horizontal" else v,
                                   "vertical": u if u_scale == "vertical" else v})

        # Dominant pattern
        scores = {
            "centralization": centralization,
            "depth": len(longest_path) / max(n, 1),
            "cycle": 1.0 if cycles else 0.0,
            "asymmetry": min(len(asym_pairs) / max(n, 1), 1.0),
        }
        dominant = max(scores, key=scores.get)
        if max(scores.values()) < 0.1:
            dominant = "balanced"

        return StructuralPatterns(
            centralization_score=round(centralization, 4),
            centralization_hub=hub,
            max_depth=len(longest_path),
            depth_chain=[self.G.nodes[n_]["name"] for n_ in longest_path] if longest_path else [],
            has_cycles=bool(cycles),
            cycles=[[self.G.nodes[n_]["name"] for n_ in c] for c in cycles[:5]],
            asymmetric_pairs=asym_pairs[:10],
            dominant_pattern=dominant,
        )

    # ── cascade propagation ───────────────────────────────────────────
    def simulate_cascade(self, traffic_mult: float, noise_std: float = 0.0
                         ) -> Tuple[List[CascadeStep], List[ServiceStress]]:
        """Propagate a traffic multiplier through the dependency graph using
        topological ordering (or BFS if cycles exist).  Returns the cascade
        chain and per-service stress."""

        pressure: Dict[str, float] = {}
        visited_order: List[str] = []

        # Determine traversal order
        if self.is_dag():
            order = list(nx.topological_sort(self.G))
        else:
            # BFS from roots
            roots = [n for n in self.G.nodes if self.G.in_degree(n) == 0]
            if not roots:
                roots = list(self.G.nodes)[:1]
            order = list(nx.bfs_tree(self.G, roots[0]).nodes) if roots else list(self.G.nodes)
            # Add any missing nodes
            for n in self.G.nodes:
                if n not in order:
                    order.append(n)

        # Seed entry-point pressure
        entry_nodes = [n for n in self.G.nodes if self.G.in_degree(n) == 0]
        if not entry_nodes:
            entry_nodes = order[:1]
        for n in entry_nodes:
            pressure[n] = traffic_mult

        cascade: List[CascadeStep] = []

        for node in order:
            if node not in pressure:
                # accumulate from predecessors
                pred_pressures = []
                for pred in self.G.predecessors(node):
                    w = self.G[pred][node].get("weight", 1.0)
                    pred_p = pressure.get(pred, 1.0)
                    pred_pressures.append(pred_p * w)
                pressure[node] = max(pred_pressures) if pred_pressures else 1.0

            # Add noise for Monte Carlo
            if noise_std > 0:
                noise = random.gauss(0, noise_std)
                pressure[node] = max(0.1, pressure[node] + noise * pressure[node])

            visited_order.append(node)

            # Record cascade edges
            for succ in self.G.successors(node):
                w = self.G[node][succ].get("weight", 1.0)
                prop = pressure[node] * w
                svc_type = self.G.nodes[succ].get("type", "service")
                model = SCALING_MODELS.get(svc_type, SCALING_MODELS["service"])
                cpu_after = min(1.0, model["cpu_base"] * (prop ** 0.8))
                lat_after = 5.0 * (prop ** model["latency_exp"])
                cascade.append(CascadeStep(
                    source=self.G.nodes[node]["name"],
                    target=self.G.nodes[succ]["name"],
                    edge_type=self.G[node][succ].get("type", "unknown"),
                    edge_weight=w,
                    pressure_propagated=round(prop, 4),
                    target_cpu_after=round(cpu_after, 4),
                    target_latency_after=round(lat_after, 2),
                ))

        # Compute per-service stress
        stress: List[ServiceStress] = []
        for node in visited_order:
            svc = self._service_map[node]
            svc_type = svc["type"]
            model = SCALING_MODELS.get(svc_type, SCALING_MODELS["service"])
            p = pressure.get(node, 1.0)

            baseline_cost = svc["cost_monthly"]
            stressed_cost = baseline_cost * (p ** model["cost_exp"])
            cpu = min(1.0, model["cpu_base"] * (p ** 0.8))
            mem = min(1.0, model["mem_base"] * (p ** 0.6))
            lat = 5.0 * (p ** model["latency_exp"])
            iops = max(100, 1000 * p * (1.0 if svc_type in ("database", "storage", "search") else 0.3))

            stress.append(ServiceStress(
                service_id=node,
                service_name=svc["name"],
                service_type=svc_type,
                baseline_cost=round(baseline_cost, 2),
                stressed_cost=round(stressed_cost, 2),
                cost_delta=round(stressed_cost - baseline_cost, 2),
                cost_delta_pct=round((stressed_cost - baseline_cost) / max(baseline_cost, 1) * 100, 2),
                cpu_utilisation=round(cpu, 4),
                memory_utilisation=round(mem, 4),
                latency_ms=round(lat, 2),
                iops=round(iops, 1),
                is_overloaded=cpu > 0.85 or mem > 0.90,
                scaling_model=model["scale"],
                pressure_received=round(p, 4),
            ))

        return cascade, stress


# ───────────────────────── scenario definitions ───────────────────────────

TRAFFIC_SCENARIOS = [
    # (label, multiplier_range, time_of_day)
    ("steady_state",     (0.9, 1.1),   "peak"),
    ("morning_ramp",     (1.1, 1.4),   "peak"),
    ("lunch_rush",       (1.3, 1.8),   "peak"),
    ("afternoon_plateau",(1.0, 1.3),   "peak"),
    ("evening_decline",  (0.6, 0.9),   "off-peak"),
    ("nightly_low",      (0.2, 0.5),   "night"),
    ("nightly_batch",    (0.4, 0.7),   "night"),
    ("weekend_dip",      (0.5, 0.8),   "off-peak"),
    ("gradual_ramp",     (1.2, 2.0),   "peak"),
    ("marketing_spike",  (1.8, 3.0),   "peak"),
    ("black_friday",     (2.5, 5.0),   "peak"),
    ("flash_sale",       (2.0, 4.0),   "peak"),
    ("ddos_simulation",  (3.0, 6.0),   "peak"),
    ("gradual_decline",  (0.3, 0.7),   "off-peak"),
    ("seasonal_growth",  (1.5, 2.5),   "peak"),
    ("capacity_test",    (2.0, 3.5),   "peak"),
    ("cold_start",       (0.1, 0.3),   "night"),
    ("burst_traffic",    (1.5, 4.5),   "peak"),
    ("api_stress",       (2.5, 5.5),   "peak"),
    ("data_migration",   (1.0, 1.5),   "night"),
]

# ───────────────────────── Monte Carlo runner ─────────────────────────────

MC_NOISE_TRIALS = 25  # noise trials per scenario to build distributions

def run_monte_carlo_trial(graph: ArchitectureGraph, traffic_mult: float
                          ) -> Tuple[float, int]:
    """One noisy trial.  Returns (total_cost, overloaded_count)."""
    _, stress = graph.simulate_cascade(traffic_mult, noise_std=0.08)
    total_cost = sum(s.stressed_cost for s in stress)
    overloaded = sum(1 for s in stress if s.is_overloaded)
    return total_cost, overloaded


# ───────────────────────── main generator ─────────────────────────────────

def generate_behavioral_dataset(
    synthetic_dir: Path = SYNTHETIC_DIR,
    output_dir: Path = OUTPUT_DIR,
    trials_per_arch: int = 6500,
) -> Path:
    """Read every architecture JSON, run Monte Carlo scenarios, and write
    the behavioural JSONL dataset."""

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "behavioral_dataset.jsonl"

    # Gather architecture files
    arch_files = sorted(synthetic_dir.glob("*.json"))
    arch_files = [f for f in arch_files if f.name != "architecture_summary.json"
                  and not f.name.startswith("architecture.")]

    print(f"📂 Found {len(arch_files)} architecture files")
    total_records = 0

    with open(out_path, "w") as fout:
        for af in arch_files:
            print(f"\n🔬 Processing {af.name} ...")
            with open(af) as fin:
                arch_data = json.load(fin)

            graph = ArchitectureGraph(arch_data)
            patterns = graph.detect_patterns()
            deg_c = graph.degree_centrality()
            bet_c = graph.betweenness_centrality()
            top_bet_node, top_bet_val = graph.top_node(bet_c)
            top_deg_node, top_deg_val = graph.top_node(deg_c)

            baseline_cost = sum(s["cost_monthly"] for s in arch_data["services"])
            arch_records = 0

            for trial_i in range(trials_per_arch):
                # Pick a random scenario
                scenario = random.choice(TRAFFIC_SCENARIOS)
                label, (lo, hi), tod = scenario
                traffic_mult = round(random.uniform(lo, hi), 3)

                # Primary cascade (no noise)
                cascade, stress = graph.simulate_cascade(traffic_mult, noise_std=0.0)
                stressed_cost = sum(s.stressed_cost for s in stress)
                cost_ratio = stressed_cost / max(baseline_cost, 1)
                amp_factor = cost_ratio / max(traffic_mult, 0.01)

                # Risk classification
                if amp_factor < 1.15:
                    risk = "linear"
                elif amp_factor < 1.8:
                    risk = "superlinear"
                else:
                    risk = "explosive"

                overloaded = [s.service_name for s in stress if s.is_overloaded]

                # Mini Monte Carlo for distribution params
                mc_costs = []
                mc_overloads = []
                for _ in range(MC_NOISE_TRIALS):
                    c, o = run_monte_carlo_trial(graph, traffic_mult)
                    mc_costs.append(c)
                    mc_overloads.append(o)

                mc_mean = sum(mc_costs) / len(mc_costs)
                mc_std = (sum((c - mc_mean) ** 2 for c in mc_costs) / len(mc_costs)) ** 0.5
                mc_p95 = sorted(mc_costs)[int(0.95 * len(mc_costs))]
                mc_overload_prob = sum(1 for o in mc_overloads if o > 0) / len(mc_overloads)

                record = BehavioralRecord(
                    record_id=str(uuid.uuid4()),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    architecture_name=arch_data["metadata"]["name"],
                    architecture_pattern=arch_data["metadata"]["pattern"],
                    architecture_complexity=arch_data["metadata"].get("complexity", "medium"),
                    total_services=len(arch_data["services"]),
                    total_dependencies=len(arch_data["dependencies"]),
                    baseline_cost_monthly=round(baseline_cost, 2),
                    traffic_multiplier=traffic_mult,
                    scenario_label=label,
                    time_of_day=tod,
                    graph_density=round(graph.density(), 4),
                    is_dag=graph.is_dag(),
                    avg_degree=round(graph.avg_degree(), 2),
                    max_betweenness_node=graph.G.nodes[top_bet_node]["name"] if top_bet_node else "",
                    max_betweenness_value=round(top_bet_val, 4),
                    max_degree_node=graph.G.nodes[top_deg_node]["name"] if top_deg_node else "",
                    max_degree_value=round(top_deg_val, 4),
                    structural_patterns=asdict(patterns),
                    cascade_chain=[asdict(c) for c in cascade],
                    cascade_depth=len(set(c.target for c in cascade)),
                    cascade_width=len(set(c.target for c in cascade) | set(c.source for c in cascade)),
                    stressed_total_cost=round(stressed_cost, 2),
                    cost_growth_ratio=round(cost_ratio, 4),
                    amplification_factor=round(amp_factor, 4),
                    risk_class=risk,
                    overloaded_services=overloaded,
                    overload_probability=round(mc_overload_prob, 3),
                    service_stress=[asdict(s) for s in stress],
                    mc_cost_mean=round(mc_mean, 2),
                    mc_cost_std=round(mc_std, 2),
                    mc_cost_p95=round(mc_p95, 2),
                    mc_overload_prob=round(mc_overload_prob, 3),
                )

                fout.write(json.dumps(asdict(record)) + "\n")
                arch_records += 1

            total_records += arch_records
            print(f"   ✅ {arch_records:,} records — {arch_data['metadata']['name']}")

    print(f"\n🎯 Total records: {total_records:,}")
    print(f"📄 Output: {out_path}")
    print(f"📦 Size: {out_path.stat().st_size / 1_048_576:.1f} MB")
    return out_path


# ───────────────────────── entry point ────────────────────────────────────
if __name__ == "__main__":
    trials = 6500
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--trials" and i + 2 < len(sys.argv):
            trials = int(sys.argv[i + 2])
    generate_behavioral_dataset(trials_per_arch=trials)
