"""
Amplification & Cascade Analyzer — detects structural risk patterns in
architecture graphs that cause nonlinear cost growth under pressure.

The four structural patterns:
1. Centralization  — many services depend on one hub node
2. Depth           — long dependency chains amplify latency & uncertainty
3. Feedback loops  — cycles create recursive amplification
4. Asymmetric scaling — horizontal/vertical mismatch creates bottlenecks
"""

from __future__ import annotations

import networkx as nx
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .behavior_models import get_model, ScaleStrategy


@dataclass
class AmplificationResult:
    node_id: str
    node_name: str
    node_type: str
    pressure_received: float
    cost_amplification: float   # cost_growth / pressure_growth
    latency_amplification: float
    is_bottleneck: bool
    root_cause_chain: List[str]  # path from entry → this node


@dataclass
class CascadeAnalysis:
    """Full cascade analysis for an architecture under a given traffic mult."""
    architecture_name: str
    traffic_multiplier: float
    total_baseline_cost: float
    total_stressed_cost: float
    global_amplification: float
    risk_class: str  # linear | superlinear | explosive

    # Pattern detections
    centralization_score: float
    centralization_hub: Optional[str]
    max_chain_depth: int
    longest_chain: List[str]
    cycle_count: int
    cycles: List[List[str]]
    asymmetric_bottlenecks: List[Dict[str, str]]
    dominant_pattern: str

    # Per-node amplification
    node_amplifications: List[AmplificationResult]
    bottleneck_nodes: List[str]

    # Root-cause analysis
    root_cause_path: List[str]
    root_cause_explanation: str


def analyze_cascade(G: nx.DiGraph, traffic_mult: float) -> CascadeAnalysis:
    """Full cascade + amplification analysis on a NetworkX DiGraph."""

    nodes = list(G.nodes(data=True))
    n = len(nodes)

    # ── Pressure propagation ──────────────────────────────────────────
    pressure: Dict[str, float] = {}
    entry_nodes = [n_id for n_id in G.nodes if G.in_degree(n_id) == 0]
    if not entry_nodes:
        entry_nodes = [list(G.nodes)[0]]

    # Topological or BFS order
    if nx.is_directed_acyclic_graph(G):
        order = list(nx.topological_sort(G))
    else:
        from collections import deque
        visited = set()
        order = []
        queue = deque(entry_nodes)
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            order.append(node)
            for succ in G.successors(node):
                if succ not in visited:
                    queue.append(succ)
        for nd in G.nodes:
            if nd not in visited:
                order.append(nd)

    for n_id in entry_nodes:
        pressure[n_id] = traffic_mult

    for n_id in order:
        if n_id not in pressure:
            preds = list(G.predecessors(n_id))
            if preds:
                pressure[n_id] = max(
                    pressure.get(p, 1.0) * G[p][n_id].get("weight", 1.0)
                    for p in preds
                )
            else:
                pressure[n_id] = 1.0

    # ── Per-node amplification ────────────────────────────────────────
    total_baseline = 0.0
    total_stressed = 0.0
    amplifications: List[AmplificationResult] = []

    for n_id, data in nodes:
        svc_type = data.get("type", "service")
        model = get_model(svc_type)
        base_cost = data.get("cost", 0)
        p = pressure.get(n_id, 1.0)

        stressed = model.stressed_cost(base_cost, p)
        total_baseline += base_cost
        total_stressed += stressed

        cost_amp = (stressed / max(base_cost, 1)) / max(p, 0.01)
        lat_amp = model.latency(p) / max(model.latency(1.0), 0.01)

        # Trace root cause chain (shortest path from any entry)
        chain = []
        for entry in entry_nodes:
            try:
                path = nx.shortest_path(G, entry, n_id)
                if not chain or len(path) < len(chain):
                    chain = path
            except nx.NetworkXNoPath:
                pass

        amplifications.append(AmplificationResult(
            node_id=n_id,
            node_name=data.get("name", n_id),
            node_type=svc_type,
            pressure_received=round(p, 4),
            cost_amplification=round(cost_amp, 4),
            latency_amplification=round(lat_amp, 4),
            is_bottleneck=model.is_overloaded(p),
            root_cause_chain=[G.nodes[x].get("name", x) for x in chain],
        ))

    # ── Structural patterns ───────────────────────────────────────────
    # Centralization
    in_deg = dict(G.in_degree())
    max_in = max(in_deg.values()) if in_deg else 0
    cent_score = 0.0
    cent_hub = None
    if n > 1 and max_in > 0:
        cent_score = sum(max_in - d for d in in_deg.values()) / ((n - 1) * max(n - 2, 1))
        cent_score = min(cent_score, 1.0)
        cent_hub = max(in_deg, key=in_deg.get)

    # Depth
    if nx.is_directed_acyclic_graph(G):
        longest = nx.dag_longest_path(G)
    else:
        longest = []
        for src in entry_nodes:
            for tgt in G.nodes:
                if src != tgt:
                    try:
                        for p in nx.all_simple_paths(G, src, tgt, cutoff=12):
                            if len(p) > len(longest):
                                longest = p
                    except nx.NetworkXError:
                        pass

    # Cycles
    cycles = [c for c in nx.simple_cycles(G) if len(c) <= 8]

    # Asymmetry
    asym = []
    for u, v in G.edges:
        u_strat = get_model(G.nodes[u].get("type", "service")).strategy
        v_strat = get_model(G.nodes[v].get("type", "service")).strategy
        if u_strat != v_strat:
            asym.append({
                "horizontal": G.nodes[u].get("name", u) if u_strat == ScaleStrategy.HORIZONTAL else G.nodes[v].get("name", v),
                "vertical": G.nodes[u].get("name", u) if u_strat == ScaleStrategy.VERTICAL else G.nodes[v].get("name", v),
            })

    # Dominant
    scores = {
        "centralization": cent_score,
        "depth": len(longest) / max(n, 1),
        "cycle": 1.0 if cycles else 0.0,
        "asymmetry": min(len(asym) / max(n, 1), 1.0),
    }
    dominant = max(scores, key=scores.get)
    if max(scores.values()) < 0.1:
        dominant = "balanced"

    # ── Global metrics ────────────────────────────────────────────────
    global_amp = (total_stressed / max(total_baseline, 1)) / max(traffic_mult, 0.01)
    if global_amp < 1.15:
        risk = "linear"
    elif global_amp < 1.8:
        risk = "superlinear"
    else:
        risk = "explosive"

    bottlenecks = [a for a in amplifications if a.is_bottleneck]
    bottleneck_names = [b.node_name for b in bottlenecks]

    # Root cause: the highest-amplification bottleneck
    if bottlenecks:
        worst = max(bottlenecks, key=lambda b: b.cost_amplification)
        rc_path = worst.root_cause_chain
        rc_explain = (
            f"Root cause: '{worst.node_name}' ({worst.node_type}) receives {worst.pressure_received:.1f}× pressure "
            f"and amplifies cost by {worst.cost_amplification:.2f}× due to {get_model(worst.node_type).strategy.value} "
            f"scaling. The pressure propagates through: {' → '.join(rc_path)}."
        )
    else:
        rc_path = []
        rc_explain = "No overloaded services detected at this traffic level."

    return CascadeAnalysis(
        architecture_name="",
        traffic_multiplier=traffic_mult,
        total_baseline_cost=round(total_baseline, 2),
        total_stressed_cost=round(total_stressed, 2),
        global_amplification=round(global_amp, 4),
        risk_class=risk,
        centralization_score=round(cent_score, 4),
        centralization_hub=G.nodes[cent_hub].get("name") if cent_hub else None,
        max_chain_depth=len(longest),
        longest_chain=[G.nodes[x].get("name", x) for x in longest],
        cycle_count=len(cycles),
        cycles=[[G.nodes[x].get("name", x) for x in c] for c in cycles[:5]],
        asymmetric_bottlenecks=asym[:10],
        dominant_pattern=dominant,
        node_amplifications=amplifications,
        bottleneck_nodes=bottleneck_names,
        root_cause_path=rc_path,
        root_cause_explanation=rc_explain,
    )
