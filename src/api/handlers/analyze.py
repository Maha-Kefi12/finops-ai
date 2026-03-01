"""
Analyze endpoint — runs the 5-agent pipeline on an architecture
and returns the full risk report with LLM-generated recommendations.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
import os
from pathlib import Path

router = APIRouter(prefix="/api", tags=["analyze"])

SYNTHETIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "synthetic"


class AnalyzeRequest(BaseModel):
    architecture_file: str  # filename in data/synthetic/
    scenario: Optional[str] = "spike"


@router.post("/analyze")
async def analyze_architecture(req: AnalyzeRequest):
    """Run the 5-agent pipeline on an architecture file."""
    import networkx as nx
    from dataclasses import asdict
    from src.simulation.amplification import analyze_cascade
    from src.simulation.simulator import MonteCarloSimulator
    from src.agents.orchestrator import AgentOrchestrator

    arch_path = SYNTHETIC_DIR / req.architecture_file
    if not arch_path.exists():
        raise HTTPException(404, f"Architecture file not found: {req.architecture_file}")

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

    # Cascade analysis
    cascade = analyze_cascade(G, 3.0)

    # Monte Carlo
    sim = MonteCarloSimulator(arch_data)
    mc_report = sim.full_report(n_trials_per_scenario=200)

    # Agent pipeline
    orch = AgentOrchestrator()
    result = orch.run(arch_data, asdict(cascade), asdict(mc_report))

    return result


@router.get("/analyze/architectures")
async def list_architectures():
    """List available architecture files for analysis."""
    files = []
    for f in sorted(SYNTHETIC_DIR.glob("*.json")):
        if f.name in ("architecture_summary.json",) or f.name.startswith("architecture."):
            continue
        try:
            with open(f) as fh:
                data = json.load(fh)
            meta = data.get("metadata", {})
            files.append({
                "filename": f.name,
                "name": meta.get("name", f.stem),
                "pattern": meta.get("pattern", "unknown"),
                "complexity": meta.get("complexity", "medium"),
                "services": meta.get("total_services", len(data.get("services", []))),
                "cost": meta.get("total_cost_monthly", sum(s.get("cost_monthly", 0) for s in data.get("services", []))),
            })
        except Exception:
            pass
    return {"architectures": files}
