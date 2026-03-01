"""
Monte Carlo Simulation Engine — runs thousands of noisy traffic trials
on an architecture graph to produce probability distributions for:
  - Cost overruns
  - Service overloads
  - Cascade formation
  - Amplification factors

This is the statistical backbone: instead of asking "What happens at 2× traffic?",
we ask "How likely is instability?" across a distribution of possible futures.
"""

from __future__ import annotations

import json
import math
import random
import statistics
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import networkx as nx

from .behavior_models import get_model
from .amplification import analyze_cascade, CascadeAnalysis


@dataclass
class TrialResult:
    """Result of a single Monte Carlo trial."""
    trial_id: int
    traffic_multiplier: float
    total_cost: float
    cost_ratio: float
    amplification: float
    overloaded_count: int
    overloaded_services: List[str]
    worst_node: str
    worst_cpu: float
    worst_latency_ms: float


@dataclass
class MonteCarloDistribution:
    """Statistical summary of Monte Carlo trials."""
    n_trials: int
    traffic_mult_mean: float
    traffic_mult_std: float

    # Cost distribution
    cost_mean: float
    cost_std: float
    cost_p5: float
    cost_p25: float
    cost_median: float
    cost_p75: float
    cost_p95: float
    cost_p99: float
    cost_max: float

    # Amplification distribution
    amp_mean: float
    amp_std: float
    amp_p95: float
    amp_max: float

    # Risk probabilities
    prob_overload: float           # P(any service overloaded)
    prob_superlinear: float        # P(amplification > 1.15)
    prob_explosive: float          # P(amplification > 1.8)
    prob_cascade: float            # P(>3 services overloaded)
    prob_cost_2x: float            # P(cost > 2× baseline)
    prob_cost_5x: float            # P(cost > 5× baseline)

    # Most-at-risk nodes
    most_overloaded_node: str
    overload_frequency: float      # % of trials this node overloaded
    risk_ranking: List[Dict[str, Any]]  # [{node, overload_pct, avg_amp}]


@dataclass
class MonteCarloReport:
    """Full Monte Carlo report for an architecture."""
    architecture_name: str
    architecture_pattern: str
    baseline_cost: float
    n_services: int
    n_dependencies: int

    # Scenario-level distributions
    scenario_distributions: Dict[str, MonteCarloDistribution]

    # Overall risk assessment
    overall_risk_class: str
    overall_instability_score: float  # 0-1
    top_risk_nodes: List[Dict[str, Any]]
    root_cause_summary: str

    # Raw trial data (optional, for downstream analysis)
    raw_trials: Optional[List[Dict]] = None


class MonteCarloSimulator:
    """Runs Monte Carlo simulations on architecture graphs."""

    def __init__(self, arch_data: Dict[str, Any]):
        self.data = arch_data
        self.meta = arch_data["metadata"]
        self.G = nx.DiGraph()
        self._build_graph()
        self.baseline_cost = sum(s["cost_monthly"] for s in arch_data["services"])

    def _build_graph(self):
        for svc in self.data["services"]:
            self.G.add_node(svc["id"], **{
                "name": svc["name"],
                "type": svc["type"],
                "cost": svc["cost_monthly"],
                "owner": svc.get("owner", "unknown"),
            })
        for dep in self.data["dependencies"]:
            self.G.add_edge(dep["source"], dep["target"],
                            type=dep["type"],
                            weight=dep.get("weight", 1.0))

    def run_trial(self, traffic_mult: float, noise_std: float = 0.08) -> TrialResult:
        """Run a single noisy trial."""

        # Determine traversal order
        if nx.is_directed_acyclic_graph(self.G):
            order = list(nx.topological_sort(self.G))
        else:
            entry = [n for n in self.G.nodes if self.G.in_degree(n) == 0]
            if not entry:
                entry = [list(self.G.nodes)[0]]
            from collections import deque
            vis = set()
            order = []
            q = deque(entry)
            while q:
                nd = q.popleft()
                if nd in vis:
                    continue
                vis.add(nd)
                order.append(nd)
                for s in self.G.successors(nd):
                    if s not in vis:
                        q.append(s)
            for nd in self.G.nodes:
                if nd not in vis:
                    order.append(nd)

        # Pressure propagation with noise
        pressure = {}
        entries = [n for n in self.G.nodes if self.G.in_degree(n) == 0]
        if not entries:
            entries = order[:1]
        for e in entries:
            pressure[e] = traffic_mult

        for nd in order:
            if nd not in pressure:
                preds = list(self.G.predecessors(nd))
                if preds:
                    pressure[nd] = max(
                        pressure.get(p, 1.0) * self.G[p][nd].get("weight", 1.0)
                        for p in preds
                    )
                else:
                    pressure[nd] = 1.0
            # Add noise
            noise = random.gauss(0, noise_std) * pressure[nd]
            pressure[nd] = max(0.1, pressure[nd] + noise)

        # Compute per-service metrics
        total_cost = 0.0
        overloaded = []
        worst_cpu = 0.0
        worst_lat = 0.0
        worst_node = ""

        for nd in order:
            data = self.G.nodes[nd]
            model = get_model(data.get("type", "service"))
            p = pressure.get(nd, 1.0)
            cost = model.stressed_cost(data.get("cost", 0), p)
            total_cost += cost

            cpu = model.cpu(p)
            lat = model.latency(p)

            if model.is_overloaded(p):
                overloaded.append(data.get("name", nd))
            if cpu > worst_cpu:
                worst_cpu = cpu
                worst_lat = lat
                worst_node = data.get("name", nd)

        cost_ratio = total_cost / max(self.baseline_cost, 1)
        amp = cost_ratio / max(traffic_mult, 0.01)

        return TrialResult(
            trial_id=0,
            traffic_multiplier=traffic_mult,
            total_cost=round(total_cost, 2),
            cost_ratio=round(cost_ratio, 4),
            amplification=round(amp, 4),
            overloaded_count=len(overloaded),
            overloaded_services=overloaded,
            worst_node=worst_node,
            worst_cpu=round(worst_cpu, 4),
            worst_latency_ms=round(worst_lat, 2),
        )

    def run_scenario(self, label: str, mult_range: Tuple[float, float],
                     n_trials: int = 1000) -> MonteCarloDistribution:
        """Run N trials for a traffic scenario and return statistical summary."""

        trials: List[TrialResult] = []
        node_overload_count: Dict[str, int] = {}
        node_amp_sum: Dict[str, float] = {}

        for i in range(n_trials):
            mult = random.uniform(*mult_range)
            result = self.run_trial(mult)
            result.trial_id = i
            trials.append(result)

            for svc in result.overloaded_services:
                node_overload_count[svc] = node_overload_count.get(svc, 0) + 1

        costs = [t.total_cost for t in trials]
        amps = [t.amplification for t in trials]
        mults = [t.traffic_multiplier for t in trials]
        costs_sorted = sorted(costs)

        def perc(arr, p):
            idx = int(p * len(arr))
            return arr[min(idx, len(arr) - 1)]

        # Risk ranking
        risk_rank = sorted(
            [{"node": k, "overload_pct": round(v / n_trials * 100, 1)}
             for k, v in node_overload_count.items()],
            key=lambda x: x["overload_pct"],
            reverse=True,
        )[:10]

        most_overloaded = risk_rank[0]["node"] if risk_rank else ""
        overload_freq = risk_rank[0]["overload_pct"] / 100 if risk_rank else 0

        return MonteCarloDistribution(
            n_trials=n_trials,
            traffic_mult_mean=round(statistics.mean(mults), 3),
            traffic_mult_std=round(statistics.stdev(mults) if len(mults) > 1 else 0, 3),
            cost_mean=round(statistics.mean(costs), 2),
            cost_std=round(statistics.stdev(costs) if len(costs) > 1 else 0, 2),
            cost_p5=round(perc(costs_sorted, 0.05), 2),
            cost_p25=round(perc(costs_sorted, 0.25), 2),
            cost_median=round(perc(costs_sorted, 0.50), 2),
            cost_p75=round(perc(costs_sorted, 0.75), 2),
            cost_p95=round(perc(costs_sorted, 0.95), 2),
            cost_p99=round(perc(costs_sorted, 0.99), 2),
            cost_max=round(max(costs), 2),
            amp_mean=round(statistics.mean(amps), 4),
            amp_std=round(statistics.stdev(amps) if len(amps) > 1 else 0, 4),
            amp_p95=round(perc(sorted(amps), 0.95), 4),
            amp_max=round(max(amps), 4),
            prob_overload=round(sum(1 for t in trials if t.overloaded_count > 0) / n_trials, 3),
            prob_superlinear=round(sum(1 for t in trials if t.amplification > 1.15) / n_trials, 3),
            prob_explosive=round(sum(1 for t in trials if t.amplification > 1.8) / n_trials, 3),
            prob_cascade=round(sum(1 for t in trials if t.overloaded_count > 3) / n_trials, 3),
            prob_cost_2x=round(sum(1 for t in trials if t.cost_ratio > 2) / n_trials, 3),
            prob_cost_5x=round(sum(1 for t in trials if t.cost_ratio > 5) / n_trials, 3),
            most_overloaded_node=most_overloaded,
            overload_frequency=round(overload_freq, 3),
            risk_ranking=risk_rank,
        )

    def full_report(self, n_trials_per_scenario: int = 500,
                    include_raw: bool = False) -> MonteCarloReport:
        """Run all scenarios and produce a comprehensive risk report."""

        SCENARIOS = {
            "steady_state":    (0.9, 1.1),
            "moderate_growth": (1.2, 1.8),
            "high_traffic":    (2.0, 3.5),
            "spike":           (3.0, 5.0),
            "extreme":         (4.0, 6.0),
        }

        distributions = {}
        all_risk_nodes: Dict[str, List[float]] = {}

        for label, mult_range in SCENARIOS.items():
            dist = self.run_scenario(label, mult_range, n_trials_per_scenario)
            distributions[label] = dist

            for rn in dist.risk_ranking:
                all_risk_nodes.setdefault(rn["node"], []).append(rn["overload_pct"])

        # Overall assessment
        spike_dist = distributions.get("spike", distributions.get("high_traffic"))
        if spike_dist and spike_dist.prob_explosive > 0.3:
            overall_risk = "critical"
        elif spike_dist and spike_dist.prob_superlinear > 0.5:
            overall_risk = "high"
        elif spike_dist and spike_dist.prob_overload > 0.3:
            overall_risk = "moderate"
        else:
            overall_risk = "low"

        instability = 0.0
        if spike_dist:
            instability = min(1.0, (spike_dist.prob_explosive * 0.4 +
                                     spike_dist.prob_cascade * 0.3 +
                                     spike_dist.prob_cost_5x * 0.3))

        top_risk = sorted(
            [{"node": k, "avg_overload_pct": round(statistics.mean(v), 1)}
             for k, v in all_risk_nodes.items()],
            key=lambda x: x["avg_overload_pct"],
            reverse=True,
        )[:5]

        # Root cause via cascade analysis
        cascade = analyze_cascade(self.G, 3.0)
        rc_summary = cascade.root_cause_explanation

        return MonteCarloReport(
            architecture_name=self.meta["name"],
            architecture_pattern=self.meta["pattern"],
            baseline_cost=self.baseline_cost,
            n_services=len(self.data["services"]),
            n_dependencies=len(self.data["dependencies"]),
            scenario_distributions={k: asdict(v) for k, v in distributions.items()},
            overall_risk_class=overall_risk,
            overall_instability_score=round(instability, 3),
            top_risk_nodes=top_risk,
            root_cause_summary=rc_summary,
        )
