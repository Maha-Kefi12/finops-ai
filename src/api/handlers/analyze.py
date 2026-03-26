"""
Analyze endpoint — runs the 5-agent pipeline on an architecture
and returns the full risk report with LLM-generated recommendations.
Supports both synthetic files and DB-stored architectures.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional
import json
import os
import hashlib
from pathlib import Path
from sqlalchemy.orm import Session

from src.storage.database import get_db
from src.graph.models import IngestionSnapshot, RecommendationResult, LLMReport
from src.graph.neo4j_bridge import load_graph_from_neo4j, list_architectures_neo4j
from src.api.schemas.persistence import LLMReportPayloadSchema, RecommendationPayloadSchema, model_to_dict

router = APIRouter(prefix="/api", tags=["analyze"])

SYNTHETIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "synthetic"


class AnalyzeRequest(BaseModel):
    architecture_file: Optional[str] = None  # filename in data/synthetic/
    architecture_id: Optional[str] = None    # UUID from database
    scenario: Optional[str] = "spike"


class RecommendationRequest(BaseModel):
    architecture_file: Optional[str] = None
    architecture_id: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
#  Helper: strip arch_id:: prefix from service IDs
# ──────────────────────────────────────────────────────────────────────
def _strip_prefix(sid: str, arch_id: str) -> str:
    prefix = f"{arch_id}::"
    return sid[len(prefix):] if sid.startswith(prefix) else sid


def _recommendation_fingerprint(card: Dict[str, Any]) -> str:
    """Build a deterministic fingerprint for recommendation dedupe."""
    resource = (card.get("resource_identification") or {}).get("resource_id", "")
    title = card.get("title", "")
    action = ""
    recs = card.get("recommendations") or []
    if recs and isinstance(recs[0], dict):
        action = recs[0].get("action", "")
    savings = round(float(card.get("total_estimated_savings", 0) or 0), 2)
    key = f"{resource.strip().lower()}|{title.strip().lower()}|{action.strip().lower()}|{savings:.2f}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _existing_fingerprints(
    db: Session,
    architecture_id: Optional[str],
    architecture_file: Optional[str],
) -> set[str]:
    """Load recommendation fingerprints already persisted for the same architecture."""
    query = db.query(RecommendationResult).filter(RecommendationResult.status == "completed")
    if architecture_id:
        query = query.filter(RecommendationResult.architecture_id == architecture_id)
    elif architecture_file:
        query = query.filter(RecommendationResult.architecture_file == architecture_file)
    else:
        return set()

    seen: set[str] = set()
    rows = query.all()
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else (json.loads(row.payload) if row.payload else {})
        for card in payload.get("recommendations", []):
            seen.add(_recommendation_fingerprint(card))
    return seen


def _filter_new_cards(cards: List[Dict[str, Any]], seen_fingerprints: set[str]) -> tuple[List[Dict[str, Any]], int]:
    """Keep only recommendations that are not already stored in DB."""
    fresh: List[Dict[str, Any]] = []
    skipped = 0
    for card in cards:
        fp = _recommendation_fingerprint(card)
        if fp in seen_fingerprints:
            skipped += 1
            continue
        seen_fingerprints.add(fp)
        fresh.append(card)
    return fresh, skipped


def _prune_recommendation_history_keep_latest(
    db: Session,
    architecture_id: Optional[str],
    architecture_file: Optional[str],
) -> int:
    """Keep only latest completed non-empty recommendation row for one architecture selector."""
    if not architecture_id and not architecture_file:
        return 0

    query = db.query(RecommendationResult).filter(
        RecommendationResult.status == "completed",
        RecommendationResult.card_count > 0,
    )

    if architecture_id:
        query = query.filter(RecommendationResult.architecture_id == architecture_id)
    else:
        query = query.filter(RecommendationResult.architecture_file == architecture_file)

    latest = query.order_by(RecommendationResult.created_at.desc()).first()
    if not latest:
        return 0

    old_query = db.query(RecommendationResult).filter(
        RecommendationResult.status == "completed",
        RecommendationResult.card_count > 0,
        RecommendationResult.id != latest.id,
    )

    if architecture_id:
        old_query = old_query.filter(RecommendationResult.architecture_id == architecture_id)
    else:
        old_query = old_query.filter(RecommendationResult.architecture_file == architecture_file)

    old_rows = old_query.all()
    for row in old_rows:
        db.delete(row)

    if old_rows:
        db.commit()

    return len(old_rows)


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
        arch_data = load_graph_from_neo4j(req.architecture_id)
        if not arch_data:
            # Recovery fallback: try latest completed snapshot raw graph.
            snap = (
                db.query(IngestionSnapshot)
                .filter(
                    IngestionSnapshot.architecture_id == req.architecture_id,
                    IngestionSnapshot.status == "completed",
                )
                .order_by(IngestionSnapshot.created_at.desc())
                .first()
            )
            if snap and snap.raw_data:
                raw = snap.raw_data if isinstance(snap.raw_data, dict) else json.loads(snap.raw_data)
                arch_data = {
                    "metadata": raw.get("metadata", {}),
                    "services": raw.get("services") or raw.get("nodes") or [],
                    "dependencies": raw.get("dependencies") or raw.get("edges") or [],
                }
            else:
                raise HTTPException(404, f"Architecture not found in Neo4j: {req.architecture_id}")

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

    # Persist LLM report from the same successful pipeline run so history is reliable.
    try:
        validated_report = model_to_dict(LLMReportPayloadSchema, result or {})
        run_time_ms = result.get("timings", {}).get("total_ms")
        if not isinstance(run_time_ms, int):
            run_time_ms = None

        report_row = LLMReport(
            architecture_id=req.architecture_id or "",
            architecture_file=req.architecture_file,
            agent_names=",".join((result.get("agents") or {}).keys()),
            status="completed",
            payload=validated_report,
            generation_time_ms=run_time_ms,
        )
        db.add(report_row)
        db.commit()
    except Exception:
        db.rollback()

    return result


# ──────────────────────────────────────────────────────────────────────
#  List architectures (synthetic + database)
# ──────────────────────────────────────────────────────────────────────
@router.get("/analyze/architectures")
async def list_architectures(db: Session = Depends(get_db)):
    """List available architecture files for analysis, including DB entries."""
    files = []
    seen_names = set()
    seen_arch_ids = set()

    # ── Neo4j architectures first ────────────────────────────────────
    try:
        neo4j_archs = list_architectures_neo4j()
        for a in neo4j_archs:
            name = a.get("name") or f"arch:{str(a.get('id', ''))[:8]}"
            seen_names.add(name)
            seen_arch_ids.add(a.get("id"))
            files.append({
                "filename": None,
                "architecture_id": a.get("id"),
                "name": name,
                "pattern": a.get("pattern", "unknown"),
                "complexity": a.get("complexity", "medium"),
                "services": a.get("total_services") or a.get("node_count") or 0,
                "cost": a.get("total_cost") or 0.0,
                "source": "neo4j",
            })
    except Exception:
        pass

    # ── Snapshot-backed architectures (recovery path) ───────────────
    try:
        snaps = (
            db.query(IngestionSnapshot)
            .filter(IngestionSnapshot.status == "completed")
            .order_by(IngestionSnapshot.created_at.desc())
            .all()
        )
        for s in snaps:
            if not s.raw_data:
                continue
            if s.architecture_id and s.architecture_id in seen_arch_ids:
                continue

            raw = s.raw_data if isinstance(s.raw_data, dict) else json.loads(s.raw_data)
            meta = raw.get("metadata", {})
            services = raw.get("services") or raw.get("nodes") or []
            name = meta.get("name") or f"snapshot:{(s.architecture_id or s.id)[:8]}"
            if name in seen_names:
                continue

            files.append({
                "filename": None,
                "architecture_id": s.architecture_id or s.id,
                "name": name,
                "pattern": meta.get("pattern", "unknown"),
                "complexity": meta.get("complexity", "medium"),
                "services": s.total_services or len(services),
                "cost": s.total_cost_monthly or meta.get("total_cost_monthly", 0.0),
                "source": f"snapshot:{s.source}",
            })
            seen_names.add(name)
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
                display_name = name
                # Keep all synthetic variants selectable, even if names overlap with
                # Neo4j/snapshot entries or other synthetic versions.
                if display_name in seen_names:
                    display_name = f"{name} [{f.stem}]"
                files.append({
                    "filename": f.name,
                    "architecture_id": None,
                    "name": display_name,
                    "pattern": meta.get("pattern", "unknown"),
                    "complexity": meta.get("complexity", "medium"),
                    "services": meta.get("total_services", len(data.get("services", []))),
                    "cost": meta.get("total_cost_monthly", sum(s.get("cost_monthly", 0) for s in data.get("services", []))),
                    "source": "synthetic",
                })
                seen_names.add(display_name)
            except Exception:
                pass

    return {"architectures": files}


# ──────────────────────────────────────────────────────────────────────
#  Deep Graph Analysis — per-node metrics + interesting node narratives
# ──────────────────────────────────────────────────────────────────────
class DeepAnalysisRequest(BaseModel):
    architecture_id: Optional[str] = None
    architecture_file: Optional[str] = None


@router.post("/analyze/deep")
async def deep_graph_analysis(req: DeepAnalysisRequest, db: Session = Depends(get_db)):
    """Run the deep graph analyzer: compute per-node metrics, identify
    interesting nodes, build context + narratives."""
    import asyncio
    from dataclasses import asdict
    from src.analysis.graph_analyzer import GraphAnalyzer

    graph_data = None

    # ── Try loading from Neo4j (CUR pipeline result) ─────────────────
    if req.architecture_id:
        # First try: load raw_data from IngestionSnapshot (full CUR graph)
        from src.graph.models import IngestionSnapshot
        snap = (
            db.query(IngestionSnapshot)
            .filter(
                IngestionSnapshot.architecture_id == req.architecture_id,
                IngestionSnapshot.status == "completed",
            )
            .order_by(IngestionSnapshot.created_at.desc())
            .first()
        )
        if snap and snap.raw_data:
            graph_data = snap.raw_data if isinstance(snap.raw_data, dict) else json.loads(snap.raw_data)

        # Fallback: load from Neo4j (architecture/services/dependencies)
        if not graph_data:
            neo4j_graph = load_graph_from_neo4j(req.architecture_id)
            if not neo4j_graph:
                raise HTTPException(404, f"Architecture not found in Neo4j: {req.architecture_id}")
            graph_data = {
                "metadata": neo4j_graph.get("metadata", {}),
                "services": neo4j_graph.get("services", []),
                "dependencies": neo4j_graph.get("dependencies", []),
            }

    # ── Load from synthetic file ─────────────────────────────────────
    elif req.architecture_file:
        arch_path = SYNTHETIC_DIR / req.architecture_file
        if not arch_path.exists():
            raise HTTPException(404, f"Architecture file not found: {req.architecture_file}")
        with open(arch_path) as f:
            graph_data = json.load(f)
    else:
        raise HTTPException(400, "Provide architecture_id or architecture_file")

    # ── Run analysis in thread ───────────────────────────────────────
    def _run():
        analyzer = GraphAnalyzer(graph_data)
        return analyzer.analyze()

    report = await asyncio.to_thread(_run)
    return asdict(report)


# ──────────────────────────────────────────────────────────────────────
#  Full Recommendation Engine — Context Package → LLM → Cards
# ──────────────────────────────────────────────────────────────────────
class RecommendationRequest(BaseModel):
    architecture_id: Optional[str] = None
    architecture_file: Optional[str] = None


@router.post("/analyze/recommendations")
async def generate_recommendations(req: RecommendationRequest, db: Session = Depends(get_db)):
    """Run the full pipeline: deep analysis → 8-section context package
    → LLM → structured recommendation cards with CUR cost breakdowns."""
    import asyncio
    from dataclasses import asdict
    from src.analysis.graph_analyzer import GraphAnalyzer
    from src.analysis.context_assembler import ContextAssembler
    from src.llm.client import generate_recommendations as gen_recs

    graph_data = None

    # ── Load graph data (same logic as /analyze/deep) ────────────────
    if req.architecture_id:
        from src.graph.models import IngestionSnapshot
        snap = (
            db.query(IngestionSnapshot)
            .filter(
                IngestionSnapshot.architecture_id == req.architecture_id,
                IngestionSnapshot.status == "completed",
            )
            .order_by(IngestionSnapshot.created_at.desc())
            .first()
        )
        if snap and snap.raw_data:
            graph_data = snap.raw_data if isinstance(snap.raw_data, dict) else json.loads(snap.raw_data)

        if not graph_data:
            neo4j_graph = load_graph_from_neo4j(req.architecture_id)
            if not neo4j_graph:
                raise HTTPException(404, f"Architecture not found in Neo4j: {req.architecture_id}")
            graph_data = {
                "metadata": neo4j_graph.get("metadata", {}),
                "services": neo4j_graph.get("services", []),
                "dependencies": neo4j_graph.get("dependencies", []),
            }

    elif req.architecture_file:
        arch_path = SYNTHETIC_DIR / req.architecture_file
        if not arch_path.exists():
            raise HTTPException(404, f"Architecture file not found: {req.architecture_file}")
        with open(arch_path) as f:
            graph_data = json.load(f)
    else:
        raise HTTPException(400, "Provide architecture_id or architecture_file")

    # ── Full pipeline in thread ──────────────────────────────────────
    def _run():
        import traceback as tb
        try:
            # Step 1: Deep analysis
            analyzer = GraphAnalyzer(graph_data)
            report = analyzer.analyze()

            # Step 2: Assemble 8-section context package
            assembler = ContextAssembler(graph_data, report)
            ctx_pkg = assembler.assemble()

            # Step 3: Generate recommendations via LLM
            arch_name = graph_data.get("metadata", {}).get("name", "")
            rec_result = gen_recs(
                context_package=ctx_pkg,
                architecture_name=arch_name,
                raw_graph_data=graph_data,
            )

            return {
                "recommendations": rec_result.cards,
                "total_estimated_savings": rec_result.total_estimated_savings,
                "llm_used": rec_result.llm_used,
                "generation_time_ms": rec_result.generation_time_ms,
                "context_package": asdict(ctx_pkg),
                "architecture_name": rec_result.architecture_name or arch_name,
            }
        except Exception as e:
            error_tb = tb.format_exc()
            print(f"❌ Recommendation pipeline error:\n{error_tb}")
            raise HTTPException(500, detail=f"Recommendation pipeline failed: {str(e)}")

    try:
        result = await asyncio.to_thread(_run)
        # Live response must reflect full fresh LLM output for this run.
        # Keep per-run dedupe/filtering in src/llm/client.py, but do not suppress
        # cards just because they existed in prior runs.
        fresh_cards = result.get("recommendations", [])
        result["recommendations"] = fresh_cards
        result["total_estimated_savings"] = sum(float(c.get("total_estimated_savings", 0) or 0) for c in fresh_cards)
        result["deduplicated_existing_count"] = 0

        validated_payload = model_to_dict(RecommendationPayloadSchema, result)

        # Store successful result in PostgreSQL for retry / history
        row = RecommendationResult(
            architecture_id=req.architecture_id or "",
            architecture_file=req.architecture_file,
            status="completed",
            payload=validated_payload,
            generation_time_ms=validated_payload.get("generation_time_ms"),
            total_estimated_savings=validated_payload.get("total_estimated_savings"),
            card_count=len(validated_payload.get("recommendations", [])),
        )
        db.add(row)
        db.commit()
        _prune_recommendation_history_keep_latest(
            db,
            architecture_id=req.architecture_id,
            architecture_file=req.architecture_file,
        )
        return validated_payload
    except HTTPException as e:
        # Store failed run so user can retry or inspect
        err_msg = e.detail if isinstance(e.detail, str) else str(e.detail) if e.detail else str(e)
        row = RecommendationResult(
            architecture_id=req.architecture_id or "",
            architecture_file=req.architecture_file,
            status="failed",
            error_message=err_msg[:4096] if err_msg else None,
        )
        try:
            db.add(row)
            db.commit()
        except Exception:
            db.rollback()
        raise


@router.get("/analyze/recommendations/last")
async def get_last_recommendation(
    architecture_id: Optional[str] = None,
    architecture_file: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Fetch the most recent recommendation result from the database.
    
    Filters by architecture_id or architecture_file if provided.
    Returns full recommendation data ready for display.
    """
    query = db.query(RecommendationResult).filter(
        RecommendationResult.status == "completed",
        RecommendationResult.card_count > 0,
    )
    
    if architecture_id:
        query = query.filter(RecommendationResult.architecture_id == architecture_id)
    elif architecture_file:
        query = query.filter(RecommendationResult.architecture_file == architecture_file)
    
    last = query.order_by(RecommendationResult.created_at.desc()).first()
    
    if not last:
        return {
            "status": "none", 
            "message": "No recommendations found in history",
            "recommendations": []
        }
    
    payload = last.payload if isinstance(last.payload, dict) else (json.loads(last.payload) if last.payload else {})
    
    return {
        "id": str(last.id),
        "status": last.status,
        "created_at": last.created_at.isoformat() if last.created_at else None,
        "recommendations": payload.get("recommendations", []),
        "total_estimated_savings": payload.get("total_estimated_savings", 0),
        "llm_used": payload.get("llm_used", False),
        "generation_time_ms": last.generation_time_ms,
        "card_count": last.card_count,
        "architecture_name": payload.get("architecture_name", ""),
        "error": last.error_message if last.status == "failed" else None
    }


@router.get("/analyze/recommendations/history")
async def get_recommendations_history(
    architecture_id: Optional[str] = None,
    architecture_file: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Fetch recommendation history for an architecture.
    
    Returns multiple recommendation results ordered by most recent first.
    """
    query = db.query(RecommendationResult).filter(
        RecommendationResult.status == "completed",
        RecommendationResult.card_count > 0,
    )
    
    if architecture_id:
        query = query.filter(RecommendationResult.architecture_id == architecture_id)
    elif architecture_file:
        query = query.filter(RecommendationResult.architecture_file == architecture_file)
    
    # Order by most recent first and limit
    results = query.order_by(RecommendationResult.created_at.desc()).limit(limit).all()
    
    history = []
    for result in results:
        payload = result.payload if isinstance(result.payload, dict) else (json.loads(result.payload) if result.payload else {})
        history.append({
            "id": str(result.id),
            "status": result.status,
            "created_at": result.created_at.isoformat() if result.created_at else None,
            "recommendations": payload.get("recommendations", []),
            "total_estimated_savings": payload.get("total_estimated_savings", 0),
            "llm_used": payload.get("llm_used", False),
            "generation_time_ms": result.generation_time_ms,
            "card_count": result.card_count,
            "architecture_name": payload.get("architecture_name", ""),
            "error": result.error_message if result.status == "failed" else None
        })
    
    return {
        "history": history,
        "total_count": len(history)
    }


@router.post("/analyze/llm-report/save")
async def save_llm_report(
    architecture_id: Optional[str] = None,
    architecture_file: Optional[str] = None,
    agent_names: Optional[str] = None,
    report_data: Optional[dict] = None,
    generation_time_ms: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Save LLM report from 5-agent pipeline to database."""
    if not architecture_id and not architecture_file:
        raise HTTPException(400, "Provide architecture_id or architecture_file")

    validated_report = model_to_dict(LLMReportPayloadSchema, report_data or {})
    if generation_time_ms is None:
        total_ms = (report_data or {}).get("timings", {}).get("total_ms")
        generation_time_ms = total_ms if isinstance(total_ms, int) else None

    resolved_agent_names = agent_names
    if not resolved_agent_names:
        resolved_agent_names = ",".join((validated_report.get("agents") or {}).keys())

    report = LLMReport(
        architecture_id=architecture_id or "",
        architecture_file=architecture_file,
        agent_names=resolved_agent_names,
        status="completed",
        payload=validated_report,
        generation_time_ms=generation_time_ms
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    
    return {
        "id": str(report.id),
        "status": report.status,
        "created_at": report.created_at.isoformat()
    }


@router.get("/analyze/llm-report/latest")
async def get_latest_llm_report(
    architecture_id: Optional[str] = None,
    architecture_file: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Fetch the most recent LLM report for an architecture."""
    query = db.query(LLMReport).filter(
        LLMReport.status == "completed"
    )
    
    if architecture_id:
        query = query.filter(LLMReport.architecture_id == architecture_id)
    elif architecture_file:
        query = query.filter(LLMReport.architecture_file == architecture_file)
    
    latest = query.order_by(LLMReport.created_at.desc()).first()
    
    if not latest:
        return {
            "status": "none",
            "message": "No LLM reports found",
            "agents": {}
        }
    
    payload = latest.payload if isinstance(latest.payload, dict) else (json.loads(latest.payload) if latest.payload else {})
    
    return {
        "id": str(latest.id),
        "status": latest.status,
        "created_at": latest.created_at.isoformat() if latest.created_at else None,
        "agents": payload.get("agents", {}),
        "all_findings": payload.get("all_findings", []),
        "interesting_nodes": payload.get("interesting_nodes", []),
        "generation_time_ms": latest.generation_time_ms,
        "agent_names": latest.agent_names,
        "error": latest.error_message if latest.status == "failed" else None
    }


@router.get("/analyze/llm-report/history")
async def get_llm_report_history(
    architecture_id: Optional[str] = None,
    architecture_file: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Fetch LLM report history for an architecture."""
    query = db.query(LLMReport).filter(
        LLMReport.status == "completed"
    )
    
    if architecture_id:
        query = query.filter(LLMReport.architecture_id == architecture_id)
    elif architecture_file:
        query = query.filter(LLMReport.architecture_file == architecture_file)
    
    results = query.order_by(LLMReport.created_at.desc()).limit(limit).all()
    
    history = []
    for result in results:
        payload = result.payload if isinstance(result.payload, dict) else (json.loads(result.payload) if result.payload else {})
        history.append({
            "id": str(result.id),
            "status": result.status,
            "created_at": result.created_at.isoformat() if result.created_at else None,
            "agents": payload.get("agents", {}),
            "all_findings": payload.get("all_findings", []),
            "interesting_nodes": payload.get("interesting_nodes", []),
            "generation_time_ms": result.generation_time_ms,
            "agent_names": result.agent_names,
            "error": result.error_message if result.status == "failed" else None
        })
    
    return {
        "history": history,
        "total_count": len(history)
    }
