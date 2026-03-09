"""
FastAPI route handlers for architecture ingestion.
Supports: built-in synthetic files, uploaded JSON, and real AWS discovery.
"""
import json
import os
import re
import uuid
import time as _time
from typing import List, Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.storage.database import get_db, SessionLocal
from src.graph.models import Architecture, Service, Dependency
from src.graph.engine import GraphEngine
from src.graph.builder import GraphBuilder
from src.graph.metrics import MetricsCalculator
from src.graph.storage import GraphStorage

router = APIRouter(prefix="/api", tags=["ingestion"])


# ──────────────────────────────────────────────────────────────────────
#  Models
# ──────────────────────────────────────────────────────────────────────
class IngestResponse(BaseModel):
    id: str
    name: str
    pattern: str
    total_services: int
    total_cost_monthly: float


class IngestAwsRequest(BaseModel):
    region: str = "us-east-1"
    account_id: Optional[str] = None


# ──────────────────────────────────────────────────────────────────────
#  Ingestion snapshot model (for pipeline tracking)
# ──────────────────────────────────────────────────────────────────────
try:
    from src.graph.models import IngestionSnapshot
except ImportError:
    from sqlalchemy import Column, String, Float, Integer, DateTime, JSON
    from src.storage.database import Base
    import datetime

    class IngestionSnapshot(Base):
        __tablename__ = "ingestion_snapshots"
        __table_args__ = {"extend_existing": True}

        id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
        account_id = Column(String, nullable=True)
        architecture_id = Column(String, nullable=True)
        source = Column(String, nullable=False, default="file")
        status = Column(String, nullable=False, default="pending")
        pipeline_stage = Column(String, nullable=True)
        pipeline_detail = Column(String, nullable=True)
        region = Column(String, nullable=True)
        total_services = Column(Integer, nullable=True, default=0)
        total_cost_monthly = Column(Float, nullable=True, default=0.0)
        duration_seconds = Column(Float, nullable=True, default=0.0)
        error_message = Column(String, nullable=True)
        raw_data = Column(JSON, nullable=True)
        llm_report = Column(JSON, nullable=True)
        created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ──────────────────────────────────────────────────────────────────────
#  Synthetic file listing
# ──────────────────────────────────────────────────────────────────────
@router.get("/synthetic-files")
def list_synthetic_files():
    """List available built-in synthetic JSON files."""
    data_dir = os.getenv("DATA_DIR", "/app/data/synthetic")
    files = []
    if os.path.exists(data_dir):
        for f in sorted(os.listdir(data_dir)):
            if f.endswith(".json") and f != "architecture_summary.json":
                full_path = os.path.join(data_dir, f)
                try:
                    with open(full_path, "r") as fh:
                        data = json.load(fh)
                    meta = data.get("metadata", {})
                    size = os.path.getsize(full_path)
                    files.append({
                        "filename": f,
                        "size_bytes": size,
                        "name": meta.get("name", f.replace(".json", "")),
                        "pattern": meta.get("pattern", "unknown"),
                        "complexity": meta.get("complexity", "medium"),
                        "total_services": meta.get("total_services", 0),
                        "total_cost_monthly": meta.get("total_cost_monthly", 0),
                    })
                except Exception:
                    files.append({"filename": f, "size_bytes": 0})
    return {"files": files}


# ──────────────────────────────────────────────────────────────────────
#  File-based ingestion
# ──────────────────────────────────────────────────────────────────────
@router.post("/ingest/file/{filename}", response_model=IngestResponse)
def ingest_builtin_file(filename: str, db: Session = Depends(get_db)):
    """Ingest one of the built-in synthetic JSON files by filename."""
    data_dir = os.getenv("DATA_DIR", "/app/data/synthetic")
    file_path = os.path.join(data_dir, filename)

    if not os.path.exists(file_path) or not filename.endswith(".json"):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

    with open(file_path, "r") as f:
        data = json.load(f)

    return _ingest_architecture(data, source_file=filename, db=db)


@router.post("/ingest/upload", response_model=IngestResponse)
async def ingest_uploaded_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload and ingest a custom JSON architecture file."""
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only JSON files are supported")

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    return _ingest_architecture(data, source_file=file.filename, db=db)


def _ingest_architecture(data: dict, source_file: str, db: Session) -> dict:
    """Common ingestion logic: build graph, compute metrics, persist."""
    engine = GraphEngine(data)
    graph_data = engine.get_graph_json()
    metrics_map = engine.compute_metrics()

    meta = data.get("metadata", {})
    arch_id = str(uuid.uuid4())

    arch = Architecture(
        id=arch_id,
        name=meta.get("name", source_file),
        pattern=meta.get("pattern", "unknown"),
        complexity=meta.get("complexity", "medium"),
        environment=meta.get("environment", "production"),
        region=meta.get("region", "us-east-1"),
        total_services=len(data.get("services", [])),
        total_cost_monthly=meta.get("total_cost_monthly", graph_data["metrics"]["total_cost_monthly"]),
        source_file=source_file,
        metadata_json=meta,
    )
    db.add(arch)
    db.flush()

    for svc in data.get("services", []):
        m = metrics_map.get(svc["id"], {})
        service = Service(
            id=f"{arch_id}::{svc['id']}",
            architecture_id=arch_id,
            name=svc.get("name", svc["id"]),
            service_type=svc.get("type", "service"),
            environment=svc.get("environment", "production"),
            owner=svc.get("owner", ""),
            cost_monthly=svc.get("cost_monthly", 0.0),
            attributes=svc.get("attributes", {}),
            degree_centrality=m.get("degree_centrality", 0.0),
            betweenness_centrality=m.get("betweenness_centrality", 0.0),
            in_degree=m.get("in_degree", 0),
            out_degree=m.get("out_degree", 0),
        )
        db.add(service)

    db.flush()

    for dep in data.get("dependencies", []):
        dependency = Dependency(
            id=str(uuid.uuid4()),
            architecture_id=arch_id,
            source=f"{arch_id}::{dep['source']}",
            target=f"{arch_id}::{dep['target']}",
            dep_type=dep.get("type", "calls"),
            weight=dep.get("weight", 1.0),
        )
        db.add(dependency)

    db.commit()

    return {
        "id": arch_id,
        "name": arch.name,
        "pattern": arch.pattern,
        "total_services": arch.total_services,
        "total_cost_monthly": arch.total_cost_monthly,
    }


# ──────────────────────────────────────────────────────────────────────
#  LLM Report Generation
# ──────────────────────────────────────────────────────────────────────
def _generate_ingestion_report(arch_data, arch_id, arch_name):
    """Generate an LLM report for an ingested architecture."""
    import httpx, networkx as nx

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model_name = os.getenv("FINOPS_MODEL", "finops-aws")

    G = nx.DiGraph()
    for svc in arch_data.get("services", []):
        G.add_node(svc["id"], **svc)
    for dep in arch_data.get("dependencies", []):
        G.add_edge(dep["source"], dep["target"], type=dep["type"])

    meta = arch_data.get("metadata", {})
    n_services = len(arch_data.get("services", []))
    n_deps = len(arch_data.get("dependencies", []))
    total_cost = sum(s.get("cost_monthly", 0) for s in arch_data.get("services", []))
    density = nx.density(G) if G.number_of_nodes() > 0 else 0

    # GraphRAG grounding
    rag_context = ""
    try:
        from src.rag.retrieval import GraphRAGRetriever
        retriever = GraphRAGRetriever()
        if retriever.load():
            rag_result = retriever.query(
                f"{arch_name} {meta.get('pattern', '')} {meta.get('region', '')} cost ${total_cost:,.0f} services {n_services}",
                top_k=5,
            )
            rag_context = rag_result.get("context", "")
    except Exception:
        pass

    system = (
        "You are a senior AWS Solutions Architect. Respond with valid JSON only. "
        "No emoji or special characters. Plain text only.\n\n"
        "Respond with: {\"health_score\": 0-100, \"assessment\": \"...\", "
        "\"cost_optimization\": [\"tip1\", ...], \"reliability_risks\": [\"risk1\", ...], "
        "\"recommendations\": [{\"priority\": \"high|medium|low\", \"action\": \"...\", "
        "\"estimated_savings\": \"$X/mo\"}]}"
    )

    top_services = sorted(arch_data.get("services", []), key=lambda s: s.get("cost_monthly", 0), reverse=True)[:10]
    svc_lines = [f"  {s['name']} ({s['type']}): ${s.get('cost_monthly', 0):,.0f}/mo" for s in top_services]

    user_prompt = (
        f"Analyze this AWS architecture:\n\n"
        f"Architecture: {arch_name}\n"
        f"Pattern: {meta.get('pattern', 'unknown')}\n"
        f"Services: {n_services}, Dependencies: {n_deps}\n"
        f"Total monthly cost: ${total_cost:,.0f}\n"
        f"Graph density: {density:.4f}\n\n"
        f"TOP SERVICES BY COST:\n" + "\n".join(svc_lines) + "\n\n"
        + (f"{rag_context}\n\n" if rag_context else "")
        + "Assess: health, cost optimization, risks, and recommendations."
    )

    try:
        resp = httpx.post(
            f"{ollama_url}/api/chat",
            json={
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 2000},
            },
            timeout=300,
        )
        if resp.status_code == 200:
            llm_text = resp.json().get("message", {}).get("content", "")
            try:
                from src.common.formatting import strip_symbols
                llm_text = strip_symbols(llm_text)
            except ImportError:
                pass
            # Try to parse as JSON
            try:
                m = re.search(r'\{.*\}', llm_text, re.DOTALL)
                if m:
                    return json.loads(m.group())
            except (json.JSONDecodeError, AttributeError):
                pass
            return {"raw_llm_response": llm_text}
        return {"error": f"LLM returned status {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


# ──────────────────────────────────────────────────────────────────────
#  AWS Pipeline Helpers
# ──────────────────────────────────────────────────────────────────────
def _update_pipeline_stage(snap_id: str, stage: str, detail: str):
    """Update pipeline stage on the snapshot (uses a fresh DB session)."""
    db = SessionLocal()
    try:
        snap = db.query(IngestionSnapshot).filter(IngestionSnapshot.id == snap_id).first()
        if snap:
            snap.pipeline_stage = stage
            snap.pipeline_detail = detail
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _run_aws_ingestion_background(snap_id: str, region: str, account_id: Optional[str]):
    """Run the full AWS ingestion pipeline in a background thread."""
    db = SessionLocal()
    t0 = _time.time()

    try:
        # ── Stage 1: Discovery ────────────────────────────────────────
        _update_pipeline_stage(snap_id, "discovery", f"Scanning AWS resources in {region}...")
        from src.ingestion.aws_client import RealAWSCollector
        collector = RealAWSCollector(region=region)
        arch_data = collector.discover_architecture()

        n_services = len(arch_data.get("services", []))
        n_deps = len(arch_data.get("dependencies", []))
        _update_pipeline_stage(snap_id, "discovery_done",
                               f"Found {n_services} resources, {n_deps} relationships")

        if account_id:
            arch_data["metadata"]["account_id"] = account_id

        # ── Stage 2: Graph Build ──────────────────────────────────────
        _update_pipeline_stage(snap_id, "graph_build", "Building NetworkX graph & computing metrics...")
        builder = GraphBuilder(arch_data)
        G = builder.build()

        calculator = MetricsCalculator(G)
        metrics_result = calculator.calculate()
        _update_pipeline_stage(snap_id, "graph_done",
                               f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

        # ── Stage 3: Database Storage ─────────────────────────────────
        _update_pipeline_stage(snap_id, "storing", "Persisting to PostgreSQL...")
        storage = GraphStorage(db)
        arch_id = storage.persist(
            raw_data=arch_data, graph=G,
            metrics=metrics_result,
            source_file=f"aws:{region}",
        )
        _update_pipeline_stage(snap_id, "stored", "Graph persisted to database")

        meta = arch_data.get("metadata", {})

        # ── Stage 4: LLM Report ──────────────────────────────────────
        report = None
        _update_pipeline_stage(snap_id, "llm_report", "Generating LLM architecture report...")
        try:
            report = _generate_ingestion_report(arch_data, arch_id, meta.get("name", f"aws:{region}"))
        except Exception as e:
            report = {"error": str(e)}
        _update_pipeline_stage(snap_id, "llm_done", "LLM report generated")

        # ── Stage 5: Finalize ─────────────────────────────────────────
        elapsed = _time.time() - t0
        total_cost = meta.get(
            "total_cost_monthly",
            sum(s.get("cost_monthly", 0) for s in arch_data.get("services", [])),
        )

        try:
            storage.save_snapshot(
                arch_id=arch_id, raw_data=arch_data, source="aws",
                llm_report=report, duration_seconds=elapsed,
            )
        except Exception:
            pass

        snap = db.query(IngestionSnapshot).filter(IngestionSnapshot.id == snap_id).first()
        if snap:
            snap.status = "completed"
            snap.pipeline_stage = "completed"
            snap.pipeline_detail = f"Ingested {n_services} resources in {elapsed:.1f}s"
            snap.architecture_id = arch_id
            snap.total_services = G.number_of_nodes()
            snap.total_cost_monthly = total_cost
            snap.raw_data = arch_data
            snap.llm_report = report
            snap.duration_seconds = round(elapsed, 2)
            db.commit()

    except Exception as e:
        elapsed = _time.time() - t0
        try:
            snap = db.query(IngestionSnapshot).filter(IngestionSnapshot.id == snap_id).first()
            if snap:
                snap.status = "failed"
                snap.pipeline_stage = "failed"
                snap.pipeline_detail = str(e)
                snap.error_message = str(e)
                snap.duration_seconds = round(elapsed, 2)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────
#  AWS Ingestion Endpoints
# ──────────────────────────────────────────────────────────────────────
@router.post("/ingest/aws")
def ingest_from_aws(req: IngestAwsRequest, db: Session = Depends(get_db)):
    """Start AWS discovery pipeline. Returns immediately with snapshot_id for polling."""
    import threading
    import datetime

    # ── Clean up stale running snapshots before starting a new one ─
    stale_cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
    stale = db.query(IngestionSnapshot).filter(
        IngestionSnapshot.status == "running",
        IngestionSnapshot.created_at < stale_cutoff,
    ).all()
    for s in stale:
        s.status = "failed"
        s.pipeline_stage = "failed"
        s.pipeline_detail = "Expired — superseded by new ingestion request"
        s.error_message = "Superseded by new ingestion request"
    if stale:
        db.commit()

    snap = IngestionSnapshot(
        account_id=req.account_id,
        source="aws",
        status="running",
        pipeline_stage="queued",
        pipeline_detail="Preparing AWS discovery...",
        region=req.region,
    )
    db.add(snap)
    db.commit()
    snap_id = snap.id

    thread = threading.Thread(
        target=_run_aws_ingestion_background,
        args=(snap_id, req.region, req.account_id),
        daemon=True,
    )
    thread.start()

    return {
        "snapshot_id": snap_id,
        "status": "running",
        "pipeline_stage": "queued",
        "message": f"AWS discovery pipeline started for {req.region}",
    }


@router.get("/ingest/aws/status/{snapshot_id}")
def get_aws_pipeline_status(snapshot_id: str, db: Session = Depends(get_db)):
    """Poll pipeline status for a running AWS ingestion."""
    import datetime
    db.expire_all()

    snap = db.query(IngestionSnapshot).filter(
        IngestionSnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(404, "Snapshot not found")

    # ── Auto-expire stale running snapshots (>5 min) ──────────────
    if snap.status == "running" and snap.created_at:
        age_seconds = (datetime.datetime.utcnow() - snap.created_at).total_seconds()
        if age_seconds > 300:  # 5 minutes
            snap.status = "failed"
            snap.pipeline_stage = "failed"
            snap.pipeline_detail = f"Pipeline timed out after {age_seconds:.0f}s (stale snapshot)"
            snap.error_message = "Pipeline timed out — the background worker may have crashed. Please retry."
            snap.duration_seconds = round(age_seconds, 2)
            db.commit()
            db.refresh(snap)

    result = {
        "snapshot_id": snap.id,
        "status": snap.status,
        "pipeline_stage": snap.pipeline_stage or "unknown",
        "pipeline_detail": snap.pipeline_detail or "",
        "region": snap.region,
        "total_services": snap.total_services,
        "total_cost_monthly": snap.total_cost_monthly,
        "duration_seconds": snap.duration_seconds,
        "error_message": snap.error_message,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
    }

    if snap.status == "completed":
        result["architecture_id"] = snap.architecture_id
        result["llm_report"] = snap.llm_report

    return result


# ──────────────────────────────────────────────────────────────────────
#  Ingestion snapshots listing
# ──────────────────────────────────────────────────────────────────────
@router.get("/ingest/snapshots")
def list_snapshots(db: Session = Depends(get_db)):
    """List all ingestion snapshots sorted by newest first."""
    snaps = db.query(IngestionSnapshot).order_by(
        IngestionSnapshot.created_at.desc()
    ).limit(100).all()
    return {
        "snapshots": [
            {
                "id": s.id,
                "account_id": s.account_id,
                "architecture_id": s.architecture_id,
                "source": s.source,
                "status": s.status,
                "pipeline_stage": getattr(s, 'pipeline_stage', None),
                "pipeline_detail": getattr(s, 'pipeline_detail', None),
                "region": s.region,
                "total_services": s.total_services,
                "total_cost_monthly": s.total_cost_monthly,
                "duration_seconds": s.duration_seconds,
                "error_message": s.error_message,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in snaps
        ]
    }
