"""
FastAPI route handlers for architecture ingestion.
"""
import json
import os
import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.storage.database import get_db
from src.graph.models import Architecture, Service, Dependency
from src.graph.engine import GraphEngine

router = APIRouter(prefix="/api", tags=["ingestion"])


class IngestResponse(BaseModel):
    id: str
    name: str
    pattern: str
    total_services: int
    total_cost_monthly: float


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
    db.flush()  # Flush architecture first

    # Insert all services first and flush to satisfy FK constraints
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

    db.flush()  # Flush all services before inserting dependencies

    # Now insert dependencies (FK references will be satisfied)
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
