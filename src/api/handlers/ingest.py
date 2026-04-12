"""
FastAPI route handlers for architecture ingestion.
Supports: built-in synthetic files, uploaded JSON, real AWS discovery,
          and CUR-based ingestion with CloudWatch metrics + Neo4j graph storage.
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
from src.graph.models import IngestionSnapshot
from src.api.schemas.persistence import GraphDataSchema, LLMReportPayloadSchema, model_to_dict
from src.graph.engine import GraphEngine
from src.graph.builder import GraphBuilder
from src.graph.metrics import MetricsCalculator
from src.graph.neo4j_store import Neo4jGraphStore
import logging

logger = logging.getLogger(__name__)
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


class IngestCurRequest(BaseModel):
    region: str = "us-east-1"
    cur_bucket: Optional[str] = None
    cur_prefix: Optional[str] = None
    collect_cloudwatch: bool = True


def _build_neo4j_graph_payload(data: dict) -> dict:
    """Build a transformed graph payload (nodes/edges/metadata) from services/dependencies."""
    engine = GraphEngine(data)
    graph = engine.get_graph_json()

    return {
        "metadata": {
            **(data.get("metadata", {}) or {}),
            "total_services": graph.get("metrics", {}).get("total_services", len(graph.get("nodes", []))),
            "total_cost_monthly": graph.get("metrics", {}).get("total_cost_monthly", 0.0),
        },
        "nodes": graph.get("nodes", []),
        "edges": [
            {
                "source": e.get("source"),
                "target": e.get("target"),
                "type": e.get("type", "depends_on"),
                "weight": e.get("weight", 1.0),
            }
            for e in graph.get("links", [])
        ],
        "services": data.get("services", []),
        "dependencies": data.get("dependencies", []),
    }


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
    """Common ingestion logic: transform graph and persist topology in Neo4j."""
    graph_payload = _build_neo4j_graph_payload(data)
    meta = graph_payload.get("metadata", {})
    arch_id = str(uuid.uuid4())

    neo4j = Neo4jGraphStore()
    try:
        neo4j.store_graph(graph_payload, arch_id)
    finally:
        neo4j.close()

    # File/manual ingestion still writes a completed snapshot for history.
    snap = IngestionSnapshot(
        architecture_id=arch_id,
        source="file",
        status="completed",
        pipeline_stage="completed",
        pipeline_detail=f"File ingestion complete for {source_file}",
        region=meta.get("region", "us-east-1"),
        total_services=len(graph_payload.get("nodes", [])),
        total_cost_monthly=float(meta.get("total_cost_monthly", 0.0) or 0.0),
        raw_data=model_to_dict(GraphDataSchema, graph_payload),
        duration_seconds=0.0,
    )
    db.add(snap)
    db.commit()

    return {
        "id": arch_id,
        "name": meta.get("name", source_file),
        "pattern": meta.get("pattern", "unknown"),
        "total_services": len(graph_payload.get("nodes", [])),
        "total_cost_monthly": float(meta.get("total_cost_monthly", 0.0) or 0.0),
    }


# ──────────────────────────────────────────────────────────────────────
#  LLM Report Generation
# ──────────────────────────────────────────────────────────────────────
def _generate_ingestion_report(arch_data, arch_id, arch_name):
    """Generate an LLM report focused on security, reliability, and performance."""
    import httpx, networkx as nx

    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model_name = os.getenv("FINOPS_MODEL", "qwen2.5:7b")

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

    # Identify SPOFs: nodes with high in-degree and no redundancy
    spof_nodes = []
    for node_id in G.nodes():
        in_deg = G.in_degree(node_id)
        node_data = G.nodes[node_id]
        svc_type = str(node_data.get("type", "")).lower()
        if in_deg >= 3 and ("rds" in svc_type or "database" in svc_type or "dynamo" in svc_type or "elasticache" in svc_type):
            spof_nodes.append(f"  SPOF: {node_data.get('name', node_id)} ({svc_type}) - {in_deg} services depend on it")

    # Security context from metadata
    security_ctx = meta.get("security_context", {})
    sec_summary = security_ctx.get("summary", {})
    sec_lines = []
    if sec_summary:
        sec_lines.append(f"  Security findings: {sec_summary.get('total_security_findings', 0)}")
        sec_lines.append(f"  Compliance issues: {sec_summary.get('total_compliance_issues', 0)}")
        sec_lines.append(f"  Data sources enabled: {sec_summary.get('data_sources_enabled', 0)}")

    system = (
        "You are a Principal AWS Security and Reliability Architect. "
        "Analyze the architecture for SECURITY VULNERABILITIES, RELIABILITY RISKS, "
        "and PERFORMANCE BOTTLENECKS. Do NOT focus on cost optimization. "
        "Respond with valid JSON only. No markdown, no emoji.\n\n"
        "Respond with:\n"
        "{\n"
        '  "health_score": 0-100,\n'
        '  "assessment": "2-3 sentence overall security/reliability assessment",\n'
        '  "security_findings": [\n'
        '    {"severity": "critical|high|medium", "resource": "resource_name", "finding": "description", "remediation": "fix"}\n'
        "  ],\n"
        '  "reliability_risks": [\n'
        '    {"severity": "critical|high|medium", "resource": "resource_name", "risk": "description", "mitigation": "fix"}\n'
        "  ],\n"
        '  "performance_issues": [\n'
        '    {"severity": "high|medium", "resource": "resource_name", "issue": "description", "optimization": "fix"}\n'
        "  ],\n"
        '  "recommendations": [\n'
        '    {"priority": "critical|high|medium", "category": "security|reliability|performance", "action": "specific action", "resource": "target_resource"}\n'
        "  ]\n"
        "}"
    )

    # Build detailed service inventory
    svc_lines = []
    for s in arch_data.get("services", []):
        config_info = ""
        config = s.get("config", {})
        if config:
            parts = []
            if config.get("multi_az") is not None:
                parts.append(f"multi_az={config['multi_az']}")
            if config.get("encrypted") is not None:
                parts.append(f"encrypted={config['encrypted']}")
            if config.get("publicly_accessible") is not None:
                parts.append(f"public={config['publicly_accessible']}")
            if config.get("backup_retention_period") is not None:
                parts.append(f"backup_days={config['backup_retention_period']}")
            if parts:
                config_info = f" [{', '.join(parts)}]"
        deps_in = G.in_degree(s["id"]) if s["id"] in G else 0
        deps_out = G.out_degree(s["id"]) if s["id"] in G else 0
        svc_lines.append(
            f"  {s['name']} ({s['type']}) deps_in={deps_in} deps_out={deps_out}{config_info}"
        )

    user_prompt = (
        f"Analyze this AWS architecture for SECURITY, RELIABILITY, and PERFORMANCE issues:\n\n"
        f"Architecture: {arch_name}\n"
        f"Region: {meta.get('region', 'unknown')}\n"
        f"Services: {n_services}, Dependencies: {n_deps}\n"
        f"Graph density: {density:.4f}\n\n"
        f"ALL SERVICES (with dependency counts and config):\n" + "\n".join(svc_lines) + "\n\n"
    )
    if spof_nodes:
        user_prompt += "DETECTED SINGLE POINTS OF FAILURE:\n" + "\n".join(spof_nodes) + "\n\n"
    if sec_lines:
        user_prompt += "SECURITY SCAN RESULTS:\n" + "\n".join(sec_lines) + "\n\n"

    # Include security findings detail if available
    for source_key in ["security_hub", "guardduty", "config_compliance", "iam_credential_report", "trusted_advisor"]:
        source_data = security_ctx.get(source_key, {})
        if isinstance(source_data, dict):
            findings = source_data.get("findings", source_data.get("checks", []))
            if findings and isinstance(findings, list):
                user_prompt += f"\n{source_key.upper()} FINDINGS:\n"
                for f in findings[:10]:
                    if isinstance(f, dict):
                        title = f.get("title", f.get("name", f.get("finding", str(f)[:100])))
                        sev = f.get("severity", f.get("level", ""))
                        user_prompt += f"  [{sev}] {title}\n"

    user_prompt += (
        "\nFocus on:\n"
        "1. Security: public exposure, missing encryption, overly permissive access, missing MFA\n"
        "2. Reliability: SPOFs, missing backups, no multi-AZ, no failover, missing health checks\n"
        "3. Performance: bottlenecks, missing caches, synchronous chains, connection pooling\n"
        "4. DO NOT recommend cost optimization or savings. Focus only on security/reliability/performance.\n"
        "5. Generate 5-12 specific, actionable recommendations with exact resource names.\n"
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
                "options": {"temperature": 0.3, "num_predict": 4000},
            },
            timeout=120,
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
#  Background LLM Worker (fire-and-forget after ingestion completes)
# ──────────────────────────────────────────────────────────────────────
def _run_llm_work_background(snap_id: str, arch_id: str, arch_data: dict, arch_name: str):
    """Generate LLM report + recommendation cards in a background thread.

    Uses its own DB session so it never blocks or interferes with the
    ingestion pipeline.  If Ollama is slow or unavailable the ingestion
    snapshot stays 'completed' — only the llm_report / recommendation
    fields are updated when the work finishes.
    """
    import threading
    def _worker():
        db = SessionLocal()
        try:
            # ── 1. LLM Report (security / reliability / performance) ──
            report = None
            try:
                report = _generate_ingestion_report(arch_data, arch_id, arch_name)
                logger.info("[LLM-BG] Report generated for %s", arch_id)
            except Exception as e:
                report = {"error": str(e)}
                logger.warning("[LLM-BG] Report failed: %s", e)

            # Persist report to snapshot
            try:
                snap = db.query(IngestionSnapshot).filter(
                    IngestionSnapshot.id == snap_id
                ).first()
                if snap:
                    snap.llm_report = model_to_dict(LLMReportPayloadSchema, report or {})
                    db.commit()
            except Exception:
                db.rollback()

            # ── 2. Recommendation Cards (engine + LLM parallel pipeline) ──
            try:
                from src.analysis.graph_analyzer import GraphAnalyzer
                from src.analysis.context_assembler import ContextAssembler
                from src.llm.client import generate_recommendations
                from src.graph.models import RecommendationResult
                from src.api.schemas.persistence import RecommendationPayloadSchema
                from dataclasses import asdict as _asdict

                analyzer = GraphAnalyzer(arch_data)
                analysis_report = analyzer.analyze()
                assembler = ContextAssembler(arch_data, analysis_report)
                ctx_pkg = assembler.assemble()

                rec_result = generate_recommendations(
                    context_package=ctx_pkg,
                    architecture_name=arch_name,
                    raw_graph_data=arch_data,
                )

                rec_cards = rec_result.cards or []
                if rec_cards:
                    rec_payload = model_to_dict(RecommendationPayloadSchema, {
                        "recommendations": rec_cards,
                        "total_estimated_savings": rec_result.total_estimated_savings,
                        "llm_used": rec_result.llm_used,
                        "generation_time_ms": rec_result.generation_time_ms,
                        "context_package": _asdict(ctx_pkg),
                        "architecture_name": rec_result.architecture_name or arch_name,
                        "deduplicated_existing_count": 0,
                    })
                    rec_row = RecommendationResult(
                        architecture_id=arch_id,
                        architecture_file=None,
                        status="completed",
                        payload=rec_payload,
                        generation_time_ms=rec_payload.get("generation_time_ms"),
                        total_estimated_savings=rec_payload.get("total_estimated_savings"),
                        card_count=len(rec_cards),
                    )
                    db.add(rec_row)
                    db.commit()
                logger.info("[LLM-BG] %d recommendation cards for %s", len(rec_cards), arch_id)
            except Exception as rec_err:
                logger.warning("[LLM-BG] Recommendation generation failed: %s", rec_err, exc_info=True)
        except Exception as outer_err:
            logger.error("[LLM-BG] Unexpected error: %s", outer_err, exc_info=True)
        finally:
            db.close()

    t = threading.Thread(target=_worker, daemon=True, name=f"llm-bg-{arch_id[:8]}")
    t.start()
    logger.info("[LLM-BG] Launched background LLM thread for %s", arch_id)


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

        # ── Stage 3: Security & Compliance Scan ────────────────────────
        _update_pipeline_stage(snap_id, "security_scan",
                               "Collecting security data (Config, SecurityHub, GuardDuty, IAM, Inspector, VPC Flow Logs)...")
        security_context = {}
        try:
            from src.ingestion.aws_security_collector import AWSSecurityCollector
            sec_collector = AWSSecurityCollector(region=region)
            security_context = sec_collector.collect_all()
            summary = security_context.get("summary", {})
            _update_pipeline_stage(snap_id, "security_done",
                                   f"Security: {summary.get('data_sources_enabled', 0)} sources, "
                                   f"{summary.get('total_security_findings', 0)} findings, "
                                   f"{summary.get('total_compliance_issues', 0)} compliance issues")
        except Exception as sec_err:
            logger.warning(f"Security scan failed (non-fatal): {sec_err}")
            _update_pipeline_stage(snap_id, "security_done",
                                   f"Security scan skipped: {sec_err}")

        # Attach security context to arch_data metadata for LLM consumption
        if security_context:
            arch_data.setdefault("metadata", {})["security_context"] = security_context

        # ── Stage 4: Neo4j Storage ────────────────────────────────────
        _update_pipeline_stage(snap_id, "neo4j_store", "Persisting graph to Neo4j...")
        arch_id = str(uuid.uuid4())
        neo4j_graph = _build_neo4j_graph_payload(arch_data)
        neo4j = Neo4jGraphStore()
        try:
            neo4j.store_graph(neo4j_graph, arch_id)
        finally:
            neo4j.close()
        _update_pipeline_stage(snap_id, "neo4j_done", "Graph persisted to Neo4j")

        meta = arch_data.get("metadata", {})

        # ── Stage 5: Launch async LLM work (non-blocking) ────────────
        _update_pipeline_stage(snap_id, "llm_report", "LLM analysis queued (runs in background)...")
        arch_display_name = meta.get("name", f"aws:{region}")
        _run_llm_work_background(snap_id, arch_id, arch_data, arch_display_name)
        _update_pipeline_stage(snap_id, "llm_done", "LLM analysis running in background")

        # ── Stage 6: Finalize ─────────────────────────────────────────
        elapsed = _time.time() - t0
        total_cost = meta.get(
            "total_cost_monthly",
            sum(s.get("cost_monthly", 0) for s in arch_data.get("services", [])),
        )

        snap = db.query(IngestionSnapshot).filter(IngestionSnapshot.id == snap_id).first()
        if snap:
            snap.status = "completed"
            snap.pipeline_stage = "completed"
            snap.pipeline_detail = f"Ingested {n_services} resources in {elapsed:.1f}s (LLM analysis in background)"
            snap.architecture_id = arch_id
            snap.total_services = G.number_of_nodes()
            snap.total_cost_monthly = total_cost
            snap.raw_data = model_to_dict(GraphDataSchema, arch_data)
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


# ──────────────────────────────────────────────────────────────────────
#  CUR Pipeline — Background Worker
# ──────────────────────────────────────────────────────────────────────
def _run_cur_ingestion_background(
    snap_id: str,
    region: str,
    cur_bucket: Optional[str],
    cur_prefix: Optional[str],
    collect_cloudwatch: bool,
):
    """Run the full CUR ingestion pipeline in a background thread.

    Pipeline stages:
        queued → cur_fetch → cur_parse → cloudwatch_collect →
        transform → neo4j_store → completed
    """
    db = SessionLocal()
    t0 = _time.time()

    try:
        # ── Stage 1: CUR Fetch ────────────────────────────────────────
        _update_pipeline_stage(snap_id, "cur_fetch",
                               f"Fetching CUR data for {region}...")
        from src.ingestion.cur_parser import CURLoader
        loader = CURLoader(region=region)

        raw_rows = []
        if cur_bucket and cur_prefix:
            # Try S3 manifest-based CUR
            manifests = loader.list_cur_manifests(cur_bucket, cur_prefix)
            if manifests:
                raw_rows = loader.load_from_s3(cur_bucket, manifests[0]["key"])
            else:
                raw_rows = loader.generate_sample_cur()
        else:
            # Check for local CUR files
            local_dir = os.getenv("CUR_DATA_DIR", "/app/data/cur_exports")
            local_files = sorted(Path(local_dir).glob("*.csv")) if Path(local_dir).exists() else []
            if local_files:
                raw_rows = loader.load_from_local(str(local_files[-1]))
            else:
                # Fall back to generating sample from live AWS discovery
                raw_rows = loader.generate_sample_cur()

        _update_pipeline_stage(snap_id, "cur_fetch_done",
                               f"Fetched {len(raw_rows)} CUR line items")

        # ── Stage 2: CUR Parse ────────────────────────────────────────
        _update_pipeline_stage(snap_id, "cur_parse",
                               "Parsing CUR line items into resources...")
        from src.ingestion.cur_parser import CURParser
        parser = CURParser(raw_rows)
        parsed = parser.parse()

        n_resources = len(parsed.get("resources", []))
        total_cost = parsed.get("summary", {}).get("total_unblended_cost", 0)
        _update_pipeline_stage(snap_id, "cur_parse_done",
                               f"Parsed {n_resources} resources, "
                               f"${total_cost:,.2f} total cost")

        # ── Stage 3: CloudWatch Metrics ───────────────────────────────
        cw_metrics = {}
        if collect_cloudwatch:
            _update_pipeline_stage(snap_id, "cloudwatch_collect",
                                   "Collecting CloudWatch performance metrics...")
            try:
                from src.ingestion.cloudwatch_collector import CloudWatchCollector
                cw = CloudWatchCollector(region=region)
                resources = parsed.get("resources", [])
                cw_metrics = cw.collect_metrics(resources=resources)
                n_metrics = sum(len(v.get("metrics", {}) if isinstance(v, dict) else {}) for v in cw_metrics.values())
                _update_pipeline_stage(snap_id, "cloudwatch_done",
                                       f"Collected metrics for "
                                       f"{len(cw_metrics)} resources "
                                       f"({n_metrics} metric series)")
            except Exception as cw_err:
                logger.warning(f"CloudWatch collection failed: {cw_err}")
                _update_pipeline_stage(snap_id, "cloudwatch_done",
                                       f"CloudWatch skipped: {cw_err}")

        # ── Stage 3.5: Security & Compliance Data ─────────────────────
        security_data = {}
        _update_pipeline_stage(snap_id, "security_collect",
                               "Collecting security & compliance data (Config, SecurityHub, GuardDuty, IAM, etc.)...")
        try:
            from src.ingestion.aws_security_collector import AWSSecurityCollector
            sec_collector = AWSSecurityCollector(region=region)
            security_data = sec_collector.collect_all()
            
            summary = security_data.get("summary", {})
            _update_pipeline_stage(snap_id, "security_done",
                                   f"Security data: {summary.get('data_sources_enabled', 0)} sources, "
                                   f"{summary.get('total_security_findings', 0)} findings, "
                                   f"{summary.get('total_compliance_issues', 0)} compliance issues")
        except Exception as sec_err:
            logger.warning(f"Security data collection failed: {sec_err}")
            _update_pipeline_stage(snap_id, "security_done",
                                   f"Security collection skipped: {sec_err}")

        # ── Stage 4: Transform ────────────────────────────────────────
        _update_pipeline_stage(snap_id, "transform",
                               "Transforming CUR + metrics into graph...")
        from src.ingestion.cur_transformer import CURTransformer
        transformer = CURTransformer(
            parsed_cur=parsed,
            cloudwatch_metrics=cw_metrics,
            region=region,
        )
        graph_data = transformer.transform()
        
        # Enrich graph metadata with security & compliance data
        if security_data:
            graph_data["metadata"]["security_context"] = security_data
        
        n_nodes = len(graph_data.get("nodes", []))
        n_edges = len(graph_data.get("edges", []))
        _update_pipeline_stage(snap_id, "transform_done",
                               f"Graph: {n_nodes} nodes, {n_edges} edges")

        # ── Stage 5: Neo4j Storage ────────────────────────────────────
        _update_pipeline_stage(snap_id, "neo4j_store",
                               "Storing graph in Neo4j...")
        arch_id = str(uuid.uuid4())
        neo4j_result = {"nodes_created": 0, "edges_created": 0}
        try:
            from src.graph.neo4j_store import Neo4jGraphStore
            neo4j = Neo4jGraphStore()
            neo4j_result = neo4j.store_graph(graph_data, arch_id)
            neo4j.close()
            _update_pipeline_stage(snap_id, "neo4j_done",
                                   f"Neo4j: {neo4j_result['nodes_created']} nodes, "
                                   f"{neo4j_result['edges_created']} edges stored")
        except Exception as neo4j_err:
            logger.warning(f"Neo4j storage failed: {neo4j_err}")
            _update_pipeline_stage(snap_id, "neo4j_done",
                                   f"Neo4j skipped: {neo4j_err}")

        _update_pipeline_stage(snap_id, "neo4j_done", "Neo4j storage complete")

        # ── Stage 6: Launch async LLM work (non-blocking) ────────────
        cur_arch_data = {
            "services": graph_data.get("nodes", graph_data.get("services", [])),
            "dependencies": graph_data.get("edges", graph_data.get("dependencies", [])),
            "metadata": graph_data.get("metadata", {}),
        }
        cur_arch_name = cur_arch_data.get("metadata", {}).get("name", f"cur:{region}")
        _run_llm_work_background(snap_id, arch_id, cur_arch_data, cur_arch_name)

        # ── Stage 7: Finalize ─────────────────────────────────────────
        elapsed = _time.time() - t0

        snap = db.query(IngestionSnapshot).filter(
            IngestionSnapshot.id == snap_id
        ).first()
        if snap:
            validated_graph = model_to_dict(GraphDataSchema, graph_data)
            snap.status = "completed"
            snap.pipeline_stage = "completed"
            snap.pipeline_detail = (
                f"CUR pipeline complete: {n_nodes} resources, "
                f"{n_edges} dependencies, ${total_cost:,.2f}/mo in {elapsed:.1f}s "
                f"(LLM analysis in background)"
            )
            snap.architecture_id = arch_id
            snap.total_services = n_nodes
            snap.total_cost_monthly = round(total_cost, 2)
            snap.raw_data = validated_graph
            snap.duration_seconds = round(elapsed, 2)
            db.commit()

    except Exception as e:
        import traceback
        logger.error(f"CUR pipeline failed: {e}\n{traceback.format_exc()}")
        elapsed = _time.time() - t0
        try:
            snap = db.query(IngestionSnapshot).filter(
                IngestionSnapshot.id == snap_id
            ).first()
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
#  CUR Ingestion Endpoints
# ──────────────────────────────────────────────────────────────────────
@router.post("/ingest/cur")
def ingest_from_cur(req: IngestCurRequest, db: Session = Depends(get_db)):
    """Start CUR-based ingestion pipeline. Returns snapshot_id for polling.

    Pipeline: CUR Fetch → Parse → CloudWatch → Transform → Neo4j (graph) → PostgreSQL snapshot
    """
    import threading
    import datetime

    # Clean up stale running snapshots
    stale_cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=5)
    stale = db.query(IngestionSnapshot).filter(
        IngestionSnapshot.status == "running",
        IngestionSnapshot.source == "cur",
        IngestionSnapshot.created_at < stale_cutoff,
    ).all()
    for s in stale:
        s.status = "failed"
        s.pipeline_stage = "failed"
        s.pipeline_detail = "Expired — superseded by new CUR ingestion"
        s.error_message = "Superseded"
    if stale:
        db.commit()

    snap = IngestionSnapshot(
        source="cur",
        status="running",
        pipeline_stage="queued",
        pipeline_detail="Preparing CUR ingestion pipeline...",
        region=req.region,
    )
    db.add(snap)
    db.commit()
    snap_id = snap.id

    thread = threading.Thread(
        target=_run_cur_ingestion_background,
        args=(snap_id, req.region, req.cur_bucket, req.cur_prefix,
              req.collect_cloudwatch),
        daemon=True,
    )
    thread.start()

    return {
        "snapshot_id": snap_id,
        "status": "running",
        "pipeline_stage": "queued",
        "message": f"CUR ingestion pipeline started for {req.region}",
    }


@router.get("/ingest/cur/status/{snapshot_id}")
def get_cur_pipeline_status(snapshot_id: str, db: Session = Depends(get_db)):
    """Poll CUR pipeline status. Same format as AWS pipeline status."""
    import datetime
    db.expire_all()

    snap = db.query(IngestionSnapshot).filter(
        IngestionSnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(404, "Snapshot not found")

    # Auto-expire stale
    if snap.status == "running" and snap.created_at:
        age = (datetime.datetime.utcnow() - snap.created_at).total_seconds()
        if age > 600:  # 10 min for CUR pipeline
            snap.status = "failed"
            snap.pipeline_stage = "failed"
            snap.pipeline_detail = f"Pipeline timed out after {age:.0f}s"
            snap.error_message = "Pipeline timed out — background worker may have crashed."
            snap.duration_seconds = round(age, 2)
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
        # Include the transformed graph data for frontend display
        if snap.raw_data:
            result["graph_data"] = {
                "metadata": snap.raw_data.get("metadata", {}),
                "nodes": snap.raw_data.get("nodes", []),
                "edges": snap.raw_data.get("edges", []),
                "services_breakdown": snap.raw_data.get("services_breakdown", []),
                "daily_costs": snap.raw_data.get("daily_costs", []),
                "performance_summary": snap.raw_data.get("performance_summary", {}),
            }

    return result


# ──────────────────────────────────────────────────────────────────────
#  Security Scan Pipeline — Config + SecurityHub + GuardDuty + IAM …
# ──────────────────────────────────────────────────────────────────────

class IngestSecurityScanRequest(BaseModel):
    region: str = "us-east-1"


def _run_security_scan_background(snap_id: str, region: str):
    """Ingest AWS Config + Security Hub + GuardDuty + IAM + Trusted Advisor
    + Inspector + VPC Flow Logs, transform into an architecture graph
    enriched with security findings, and store for LLM analysis."""
    db = SessionLocal()
    t0 = _time.time()

    try:
        # ── Stage 1: AWS Resource Discovery (via Config) ───────────────
        _update_pipeline_stage(snap_id, "discovery",
                               f"Discovering resources via AWS Config in {region}...")
        from src.ingestion.aws_security_collector import AWSSecurityCollector
        collector = AWSSecurityCollector(region=region)

        # Config snapshots give us the resource inventory
        config_data = collector.collect_aws_config()
        n_resources = config_data.get("total_resources", 0)
        _update_pipeline_stage(snap_id, "discovery_done",
                               f"Config: {n_resources} resources tracked, "
                               f"{config_data.get('compliance_summary', {}).get('non_compliant', 0)} non-compliant")

        # ── Stage 2: Security Hub Findings ─────────────────────────────
        _update_pipeline_stage(snap_id, "security_hub",
                               "Fetching Security Hub findings (CRITICAL/HIGH/MEDIUM)...")
        securityhub_data = collector.collect_security_hub()
        _update_pipeline_stage(snap_id, "security_hub_done",
                               f"SecurityHub: {securityhub_data.get('total_findings', 0)} findings "
                               f"({securityhub_data.get('by_severity', {}).get('CRITICAL', 0)} critical)")

        # ── Stage 3: GuardDuty Threats ─────────────────────────────────
        _update_pipeline_stage(snap_id, "guardduty",
                               "Fetching GuardDuty threat detections (last 30 days)...")
        guardduty_data = collector.collect_guardduty()
        _update_pipeline_stage(snap_id, "guardduty_done",
                               f"GuardDuty: {guardduty_data.get('total_findings', 0)} threats")

        # ── Stage 4: IAM Credential Report ─────────────────────────────
        _update_pipeline_stage(snap_id, "iam_scan",
                               "Generating IAM credential report (MFA, key age, passwords)...")
        iam_data = collector.collect_iam_credentials()
        iam_issues = len(iam_data.get("issues", []))
        _update_pipeline_stage(snap_id, "iam_done",
                               f"IAM: {iam_issues} issues "
                               f"({iam_data.get('statistics', {}).get('total_users', 0)} users)")

        # ── Stage 5: Trusted Advisor + Compute Optimizer + Inspector ───
        _update_pipeline_stage(snap_id, "advisors",
                               "Fetching Trusted Advisor, Compute Optimizer, Inspector...")
        ta_data = collector.collect_trusted_advisor()
        co_data = collector.collect_compute_optimizer()
        inspector_data = collector.collect_inspector()
        _update_pipeline_stage(snap_id, "advisors_done",
                               f"TA: {ta_data.get('checks_with_issues', 0)} issues, "
                               f"CO: {co_data.get('total_recommendations', 0)} recs, "
                               f"Inspector: {inspector_data.get('total_findings', 0)} vulns")

        # ── Stage 6: VPC Flow Logs ─────────────────────────────────────
        _update_pipeline_stage(snap_id, "vpc_flowlogs",
                               "Analyzing VPC Flow Logs for traffic patterns...")
        vpc_data = collector.collect_vpc_flow_logs()
        _update_pipeline_stage(snap_id, "vpc_done",
                               f"VPC: {vpc_data.get('vpcs_with_flow_logs', 0)} VPCs with flow logs")

        # ── Stage 7: Build architecture graph from Config snapshots ────
        _update_pipeline_stage(snap_id, "graph_build",
                               "Building architecture graph from Config snapshots...")

        # Transform Config snapshots into services + dependencies
        services = []
        dependencies = []
        seen_ids = set()
        critical_resources = config_data.get("critical_resources", [])

        for item in critical_resources:
            rid = item.get("resource_id", "")
            rtype = item.get("resource_type", "")
            rname = item.get("resource_name") or rid
            config = item.get("configuration", {})
            tags = item.get("tags", {})

            if rid in seen_ids:
                continue
            seen_ids.add(rid)

            # Map AWS Config resource type to service type
            svc_type_map = {
                "AWS::EC2::Instance": "EC2",
                "AWS::RDS::DBInstance": "RDS",
                "AWS::S3::Bucket": "S3",
                "AWS::Lambda::Function": "Lambda",
                "AWS::EC2::SecurityGroup": "SecurityGroup",
                "AWS::IAM::Role": "IAM",
                "AWS::ElastiCache::CacheCluster": "ElastiCache",
                "AWS::ECS::Service": "ECS",
                "AWS::DynamoDB::Table": "DynamoDB",
            }
            svc_type = svc_type_map.get(rtype, rtype.split("::")[-1] if "::" in rtype else "Unknown")

            # Attach security findings to the resource
            resource_findings = []
            for f in securityhub_data.get("findings", []):
                if f.get("resource_id") and rid in str(f.get("resource_id", "")):
                    resource_findings.append({
                        "severity": f.get("severity"),
                        "title": f.get("title"),
                    })

            svc = {
                "id": rid,
                "name": rname,
                "type": svc_type,
                "aws_service": rtype,
                "region": region,
                "environment": tags.get("Environment", tags.get("env", "unknown")),
                "cost_monthly": 0,
                "tags": tags,
                "configuration": config,
                "security_findings": resource_findings,
            }
            services.append(svc)

        # Build dependency edges from security group rules and Config relationships
        for svc in services:
            config = svc.get("configuration", {})
            # RDS → SecurityGroup dependencies
            if svc.get("aws_service") == "AWS::RDS::DBInstance":
                for sg in config.get("vpcSecurityGroups", []):
                    sg_id = sg.get("vpcSecurityGroupId", "")
                    if sg_id and sg_id in seen_ids:
                        dependencies.append({
                            "source": svc["id"],
                            "target": sg_id,
                            "type": "secured_by",
                        })
            # EC2 → SecurityGroup
            if svc.get("aws_service") == "AWS::EC2::Instance":
                for sg in config.get("securityGroups", []):
                    sg_id = sg.get("groupId", "")
                    if sg_id and sg_id in seen_ids:
                        dependencies.append({
                            "source": svc["id"],
                            "target": sg_id,
                            "type": "secured_by",
                        })

        # Assemble the full security context
        security_context = {
            "summary": collector._generate_summary({
                "aws_config": config_data,
                "security_hub": securityhub_data,
                "guardduty": guardduty_data,
                "vpc_flow_logs": vpc_data,
                "iam_credentials": iam_data,
                "trusted_advisor": ta_data,
                "compute_optimizer": co_data,
                "inspector": inspector_data,
            }),
            "aws_config": config_data,
            "security_hub": securityhub_data,
            "guardduty": guardduty_data,
            "vpc_flow_logs": vpc_data,
            "iam_credentials": iam_data,
            "trusted_advisor": ta_data,
            "compute_optimizer": co_data,
            "inspector": inspector_data,
        }

        graph_data = {
            "metadata": {
                "name": f"Security Scan ({region})",
                "pattern": "security-scan",
                "region": region,
                "total_services": len(services),
                "total_cost_monthly": 0,
                "security_context": security_context,
            },
            "services": services,
            "dependencies": dependencies,
            "nodes": [
                {
                    "id": s["id"],
                    "label": s["name"],
                    "type": s["type"],
                    "cost_monthly": s.get("cost_monthly", 0),
                    "metadata": {
                        "aws_service": s.get("aws_service"),
                        "environment": s.get("environment"),
                        "security_findings": s.get("security_findings", []),
                        "tags": s.get("tags", {}),
                    },
                }
                for s in services
            ],
            "edges": [
                {
                    "source": d["source"],
                    "target": d["target"],
                    "type": d.get("type", "depends_on"),
                    "weight": 1.0,
                }
                for d in dependencies
            ],
        }

        n_nodes = len(graph_data["nodes"])
        n_edges = len(graph_data["edges"])
        _update_pipeline_stage(snap_id, "graph_done",
                               f"Graph: {n_nodes} nodes, {n_edges} edges")

        # ── Stage 8: Neo4j Storage ─────────────────────────────────────
        _update_pipeline_stage(snap_id, "storing", "Storing graph in Neo4j...")
        arch_id = str(uuid.uuid4())
        try:
            neo4j_payload = _build_neo4j_graph_payload({
                "metadata": graph_data["metadata"],
                "services": services,
                "dependencies": dependencies,
            })
            neo4j = Neo4jGraphStore()
            neo4j.store_graph(neo4j_payload, arch_id)
            neo4j.close()
        except Exception as neo4j_err:
            logger.warning(f"Neo4j storage failed: {neo4j_err}")
        _update_pipeline_stage(snap_id, "stored", "Graph stored")

        # ── Stage 9: Finalize ──────────────────────────────────────────
        elapsed = _time.time() - t0
        snap = db.query(IngestionSnapshot).filter(
            IngestionSnapshot.id == snap_id
        ).first()
        if snap:
            validated_graph = model_to_dict(GraphDataSchema, graph_data)
            snap.status = "completed"
            snap.pipeline_stage = "completed"
            snap.pipeline_detail = (
                f"Security scan complete: {n_nodes} resources, "
                f"{security_context['summary']['total_security_findings']} security findings, "
                f"{security_context['summary']['total_compliance_issues']} compliance issues "
                f"in {elapsed:.1f}s"
            )
            snap.architecture_id = arch_id
            snap.total_services = n_nodes
            snap.total_cost_monthly = 0
            snap.raw_data = validated_graph
            snap.duration_seconds = round(elapsed, 2)
            db.commit()

    except Exception as e:
        import traceback
        logger.error(f"Security scan pipeline failed: {e}\n{traceback.format_exc()}")
        elapsed = _time.time() - t0
        try:
            snap = db.query(IngestionSnapshot).filter(
                IngestionSnapshot.id == snap_id
            ).first()
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


@router.post("/ingest/security-scan")
def ingest_security_scan(req: IngestSecurityScanRequest, db: Session = Depends(get_db)):
    """Start AWS security scan pipeline.

    Ingests: AWS Config + Security Hub + GuardDuty + IAM Credentials
    + Trusted Advisor + Compute Optimizer + Inspector + VPC Flow Logs.
    Returns snapshot_id for polling via /ingest/security-scan/status/{id}.
    """
    import threading
    import datetime

    # Clean up stale
    stale_cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    stale = db.query(IngestionSnapshot).filter(
        IngestionSnapshot.status == "running",
        IngestionSnapshot.source == "security_scan",
        IngestionSnapshot.created_at < stale_cutoff,
    ).all()
    for s in stale:
        s.status = "failed"
        s.pipeline_stage = "failed"
        s.pipeline_detail = "Expired — superseded by new security scan"
        s.error_message = "Superseded"
    if stale:
        db.commit()

    snap = IngestionSnapshot(
        source="security_scan",
        status="running",
        pipeline_stage="queued",
        pipeline_detail="Preparing AWS security scan pipeline...",
        region=req.region,
    )
    db.add(snap)
    db.commit()
    snap_id = snap.id

    thread = threading.Thread(
        target=_run_security_scan_background,
        args=(snap_id, req.region),
        daemon=True,
    )
    thread.start()

    return {
        "snapshot_id": snap_id,
        "status": "running",
        "pipeline_stage": "queued",
        "message": f"Security scan pipeline started for {req.region}",
    }


@router.get("/ingest/security-scan/status/{snapshot_id}")
def get_security_scan_status(snapshot_id: str, db: Session = Depends(get_db)):
    """Poll security scan pipeline status."""
    import datetime
    db.expire_all()

    snap = db.query(IngestionSnapshot).filter(
        IngestionSnapshot.id == snapshot_id
    ).first()
    if not snap:
        raise HTTPException(404, "Snapshot not found")

    if snap.status == "running" and snap.created_at:
        age = (datetime.datetime.utcnow() - snap.created_at).total_seconds()
        if age > 600:
            snap.status = "failed"
            snap.pipeline_stage = "failed"
            snap.pipeline_detail = f"Pipeline timed out after {age:.0f}s"
            snap.error_message = "Pipeline timed out"
            snap.duration_seconds = round(age, 2)
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

    return result


# ──────────────────────────────────────────────────────────────────────
#  Neo4j Status Endpoint
# ──────────────────────────────────────────────────────────────────────
@router.get("/neo4j/status")
def neo4j_status():
    """Check Neo4j connectivity and return basic stats."""
    try:
        from src.graph.neo4j_store import Neo4jGraphStore
        store = Neo4jGraphStore()
        health = store.health_check()
        store.close()
        return health
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/neo4j/graph/{architecture_id}")
def get_neo4j_graph(architecture_id: str):
    """Get the full graph from Neo4j for an architecture."""
    try:
        from src.graph.neo4j_store import Neo4jGraphStore
        store = Neo4jGraphStore()
        graph = store.get_graph(architecture_id)
        store.close()
        return graph
    except Exception as e:
        raise HTTPException(500, f"Neo4j error: {e}")
