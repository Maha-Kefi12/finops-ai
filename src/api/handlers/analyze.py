"""
Analyze endpoint — runs the 5-agent pipeline on an architecture
and returns the full risk report with LLM-generated recommendations.
Supports both synthetic files and DB-stored architectures.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
import os
from pathlib import Path
from sqlalchemy.orm import Session

from src.storage.database import get_db
from src.graph.models import Architecture, Service, Dependency

router = APIRouter(prefix="/api", tags=["analyze"])

SYNTHETIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "synthetic"


class AnalyzeRequest(BaseModel):
    architecture_file: Optional[str] = None  # filename in data/synthetic/
    architecture_id: Optional[str] = None    # UUID from database
    scenario: Optional[str] = "spike"


# ──────────────────────────────────────────────────────────────────────
#  Helper: strip arch_id:: prefix from service IDs
# ──────────────────────────────────────────────────────────────────────
def _strip_prefix(sid: str, arch_id: str) -> str:
    prefix = f"{arch_id}::"
    return sid[len(prefix):] if sid.startswith(prefix) else sid


# ──────────────────────────────────────────────────────────────────────
#  Analyze endpoint
# ──────────────────────────────────────────────────────────────────────
@router.post("/analyze")
async def analyze_architecture(req: AnalyzeRequest, db: Session = Depends(get_db)):
    """Run the 5-agent pipeline on an architecture file or DB record."""
    import asyncio
    import networkx as nx
    from dataclasses import asdict
    from src.simulation.amplification import analyze_cascade
    from src.simulation.simulator import MonteCarloSimulator
    from src.agents.orchestrator import AgentOrchestrator

    arch_data = None

    # ── Load from database if architecture_id is provided ────────────
    if req.architecture_id:
        arch = db.query(Architecture).filter(Architecture.id == req.architecture_id).first()
        if not arch:
            raise HTTPException(404, f"Architecture not found: {req.architecture_id}")

        services = db.query(Service).filter(Service.architecture_id == req.architecture_id).all()
        deps = db.query(Dependency).filter(Dependency.architecture_id == req.architecture_id).all()

        arch_data = {
            "metadata": {
                "name": arch.name,
                "pattern": arch.pattern,
                "complexity": arch.complexity or "medium",
                "environment": arch.environment or "production",
                "region": arch.region or "us-east-1",
                "total_services": arch.total_services,
                "total_cost_monthly": arch.total_cost_monthly,
            },
            "services": [
                {
                    "id": _strip_prefix(s.id, req.architecture_id),
                    "name": s.name,
                    "type": s.service_type or "service",
                    "environment": s.environment or "production",
                    "owner": s.owner or "",
                    "cost_monthly": s.cost_monthly or 0.0,
                    "attributes": s.attributes or {},
                }
                for s in services
            ],
            "dependencies": [
                {
                    "source": _strip_prefix(d.source, req.architecture_id),
                    "target": _strip_prefix(d.target, req.architecture_id),
                    "type": d.dep_type or "calls",
                    "weight": d.weight or 1.0,
                }
                for d in deps
            ],
        }

    # ── Load from synthetic file ─────────────────────────────────────
    elif req.architecture_file:
        arch_path = SYNTHETIC_DIR / req.architecture_file
        if not arch_path.exists():
            raise HTTPException(404, f"Architecture file not found: {req.architecture_file}")
        with open(arch_path) as f:
            arch_data = json.load(f)
    else:
        raise HTTPException(400, "Provide either architecture_file or architecture_id")

    # ── Build graph ──────────────────────────────────────────────────
    G = nx.DiGraph()
    for svc in arch_data["services"]:
        G.add_node(svc["id"], name=svc["name"], type=svc["type"],
                   cost=svc.get("cost_monthly", 0), owner=svc.get("owner", "unknown"))
    for dep in arch_data["dependencies"]:
        G.add_edge(dep["source"], dep["target"],
                   type=dep["type"], weight=dep.get("weight", 1.0))

    # ── Cascade analysis ─────────────────────────────────────────────
    cascade = analyze_cascade(G, 3.0)

    # ── Monte Carlo ──────────────────────────────────────────────────
    sim = MonteCarloSimulator(arch_data)
    mc_report = sim.full_report(n_trials_per_scenario=200)

    # ── Agent pipeline (run in thread to avoid blocking event loop) ────
    orch = AgentOrchestrator()
    result = await asyncio.to_thread(orch.run, arch_data, asdict(cascade), asdict(mc_report))

    return result


# ──────────────────────────────────────────────────────────────────────
#  List architectures (synthetic + database)
# ──────────────────────────────────────────────────────────────────────
@router.get("/analyze/architectures")
async def list_architectures(db: Session = Depends(get_db)):
    """List available architecture files for analysis, including DB entries."""
    files = []
    seen_names = set()

    # ── DB architectures first ───────────────────────────────────────
    try:
        db_archs = db.query(Architecture).order_by(Architecture.name).all()
        for a in db_archs:
            seen_names.add(a.name)
            files.append({
                "filename": None,
                "architecture_id": a.id,
                "name": a.name,
                "pattern": a.pattern or "unknown",
                "complexity": a.complexity or "medium",
                "services": a.total_services or 0,
                "cost": a.total_cost_monthly or 0.0,
                "source": a.source_file or "db",
            })
    except Exception:
        pass

    # ── Synthetic files ──────────────────────────────────────────────
    if SYNTHETIC_DIR.exists():
        for f in sorted(SYNTHETIC_DIR.glob("*.json")):
            if f.name in ("architecture_summary.json",) or f.name.startswith("architecture."):
                continue
            try:
                with open(f) as fh:
                    data = json.load(fh)
                meta = data.get("metadata", {})
                name = meta.get("name", f.stem)
                if name in seen_names:
                    continue
                files.append({
                    "filename": f.name,
                    "architecture_id": None,
                    "name": name,
                    "pattern": meta.get("pattern", "unknown"),
                    "complexity": meta.get("complexity", "medium"),
                    "services": meta.get("total_services", len(data.get("services", []))),
                    "cost": meta.get("total_cost_monthly", sum(s.get("cost_monthly", 0) for s in data.get("services", []))),
                    "source": "synthetic",
                })
            except Exception:
                pass

    return {"architectures": files}
