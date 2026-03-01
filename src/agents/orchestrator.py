"""
Agent Orchestrator — runs the 5-agent pipeline sequentially.

Pipeline flow:
  1. Topology Analyst    → reads graph                     → structural patterns
  2. Behavior Scientist  → reads MC report                 → behavioral anomalies
  3. Cost Economist      → reads MC + cascade              → cost amplification
  4. Risk Detective      → reads agents 1+2+3 + cascade    → root-of-root-cause
  5. Executive Synthesizer → reads agents 1+2+3+4          → final verdict

Each agent's output feeds into the next.  The final output is a complete
risk assessment with structural root causes, behavioral probabilities,
cost projections, and prioritised action items.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_agent import AgentOutput
from .architect_agent import TopologyAnalystAgent
from .behavior_agent import BehaviorScientistAgent
from .economist_agent import CostEconomistAgent
from .detective_agent import RiskDetectiveAgent
from .synthesizer_agent import ExecutiveSynthesizerAgent


class AgentOrchestrator:
    """Sequential 5-agent pipeline for architecture risk analysis."""

    def __init__(self):
        self.agents = [
            TopologyAnalystAgent(),
            BehaviorScientistAgent(),
            CostEconomistAgent(),
            RiskDetectiveAgent(),
            ExecutiveSynthesizerAgent(),
        ]

    def run(self, arch_data: Dict[str, Any],
            cascade_analysis: Dict[str, Any],
            mc_report: Dict[str, Any],
            progress_callback=None) -> Dict[str, Any]:
        """Run the full pipeline.

        Parameters
        ----------
        arch_data : dict
            Raw architecture JSON (services, dependencies, metadata)
        cascade_analysis : dict
            Output from amplification.analyze_cascade()
        mc_report : dict
            Output from MonteCarloSimulator.full_report()
        progress_callback : callable, optional
            Called with (agent_index, agent_name, status) for progress updates

        Returns
        -------
        dict with keys: verdict, agents, findings, recommendations, timings
        """

        arch_name = arch_data.get("metadata", {}).get("name", "Unknown")
        baseline_cost = sum(s["cost_monthly"] for s in arch_data.get("services", []))

        context = {
            "architecture_name": arch_name,
            "architecture_pattern": arch_data.get("metadata", {}).get("pattern", ""),
            "n_services": len(arch_data.get("services", [])),
            "n_dependencies": len(arch_data.get("dependencies", [])),
            "baseline_cost": baseline_cost,
            "graph_metrics": {},
            "cascade_analysis": cascade_analysis,
            "monte_carlo_report": mc_report,
        }

        outputs: Dict[str, Dict] = {}
        timings: Dict[str, int] = {}
        total_start = time.time()

        for i, agent in enumerate(self.agents):
            label = agent.role

            if progress_callback:
                progress_callback(i, agent.name, "running")

            # Inject previous agents' outputs into context
            if label == "risk_detective":
                context["topology_output"] = outputs.get("topology_analyst", {})
                context["behavior_output"] = outputs.get("behavior_scientist", {})
                context["cost_output"] = outputs.get("cost_economist", {})

            if label == "executive_synthesizer":
                context["topology_output"] = outputs.get("topology_analyst", {})
                context["behavior_output"] = outputs.get("behavior_scientist", {})
                context["cost_output"] = outputs.get("cost_economist", {})
                context["detective_output"] = outputs.get("risk_detective", {})

            result: AgentOutput = agent.analyze(context)
            outputs[label] = asdict(result)
            timings[label] = result.execution_time_ms

            if progress_callback:
                progress_callback(i, agent.name, "done")

        total_elapsed = int((time.time() - total_start) * 1000)

        # ── Build final report ────────────────────────────────────────
        synth = outputs.get("executive_synthesizer", {})
        det = outputs.get("risk_detective", {})

        return {
            "architecture": arch_name,
            "pattern": arch_data.get("metadata", {}).get("pattern", ""),
            "baseline_cost_monthly": baseline_cost,
            "n_services": len(arch_data.get("services", [])),
            "n_dependencies": len(arch_data.get("dependencies", [])),
            "verdict": synth.get("findings", [{}])[0].get("description", "Analysis complete"),
            "risk_score": synth.get("risk_score", 0),
            "agents": outputs,
            "all_findings": self._aggregate_findings(outputs),
            "recommendations": synth.get("recommendations", []),
            "root_cause": det.get("findings", [{}])[0].get("description", "") if det.get("findings") else "",
            "timings": {**timings, "total_ms": total_elapsed},
        }

    def _aggregate_findings(self, outputs: Dict[str, Dict]) -> List[Dict]:
        """Collect all findings from all agents, sorted by severity."""
        all_f = []
        severity_rank = {"critical": 4, "high": 3, "moderate": 2, "low": 1}
        for label, output in outputs.items():
            for f in output.get("findings", []):
                f["source_agent"] = label
                all_f.append(f)
        all_f.sort(key=lambda f: severity_rank.get(f.get("severity", "low"), 0), reverse=True)
        return all_f

    def run_from_file(self, arch_path: str,
                      progress_callback=None) -> Dict[str, Any]:
        """Convenience: load an architecture JSON, run Monte Carlo + cascade,
        then run the agent pipeline."""

        import networkx as nx
        from ..simulation.amplification import analyze_cascade
        from ..simulation.simulator import MonteCarloSimulator

        with open(arch_path) as f:
            arch_data = json.load(f)

        # Build graph
        G = nx.DiGraph()
        for svc in arch_data["services"]:
            G.add_node(svc["id"], name=svc["name"], type=svc["type"],
                       cost=svc["cost_monthly"], owner=svc.get("owner", "unknown"))
        for dep in arch_data["dependencies"]:
            G.add_edge(dep["source"], dep["target"],
                       type=dep["type"], weight=dep.get("weight", 1.0))

        # Cascade analysis at 3× traffic
        cascade = analyze_cascade(G, 3.0)

        # Monte Carlo report
        sim = MonteCarloSimulator(arch_data)
        mc = sim.full_report(n_trials_per_scenario=500)

        return self.run(arch_data, asdict(cascade), asdict(mc), progress_callback)
