"""
Graph retrieval and management API handlers.
"""
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.storage.database import get_db
from src.graph.models import Architecture, Service, Dependency
from src.graph.engine import GraphEngine, SERVICE_TYPE_COLORS

router = APIRouter(prefix="/api/graphs", tags=["graphs"])


@router.get("")
def list_graphs(db: Session = Depends(get_db)):
    """List all ingested architectures."""
    archs = db.query(Architecture).order_by(Architecture.created_at.desc()).all()
    return {
        "architectures": [
            {
                "id": a.id,
                "name": a.name,
                "pattern": a.pattern,
                "complexity": a.complexity,
                "total_services": a.total_services,
                "total_cost_monthly": a.total_cost_monthly,
                "source_file": a.source_file,
                "created_at": a.created_at.isoformat(),
            }
            for a in archs
        ]
    }


@router.get("/{arch_id}")
def get_graph(arch_id: str, db: Session = Depends(get_db)):
    """Get the full graph with nodes, links, and metrics for a given architecture."""
    arch = db.query(Architecture).filter(Architecture.id == arch_id).first()
    if not arch:
        raise HTTPException(status_code=404, detail="Architecture not found")

    services = db.query(Service).filter(Service.architecture_id == arch_id).all()
    deps = db.query(Dependency).filter(Dependency.architecture_id == arch_id).all()

    # Map service DB ids back to short IDs for the graph
    nodes = []
    for svc in services:
        short_id = svc.id.split("::", 1)[-1]
        nodes.append({
            "id": svc.id,
            "short_id": short_id,
            "name": svc.name,
            "type": svc.service_type,
            "owner": svc.owner,
            "cost_monthly": svc.cost_monthly,
            "environment": svc.environment,
            "attributes": svc.attributes or {},
            "color": SERVICE_TYPE_COLORS.get(svc.service_type, "#6b7280"),
            "degree_centrality": svc.degree_centrality,
            "betweenness_centrality": svc.betweenness_centrality,
            "in_degree": svc.in_degree,
            "out_degree": svc.out_degree,
            "val": max(4, svc.degree_centrality * 30 + 4),
            "cost_share": round(
                (svc.cost_monthly / max(0.01, arch.total_cost_monthly)) * 100, 2
            ),
        })

    links = [
        {
            "source": d.source,
            "target": d.target,
            "type": d.dep_type,
            "weight": d.weight,
        }
        for d in deps
    ]

    critical_nodes = sorted(nodes, key=lambda n: n["betweenness_centrality"], reverse=True)[:3]
    cost_hotspots = sorted(nodes, key=lambda n: n["cost_monthly"], reverse=True)[:3]

    return {
        "architecture": {
            "id": arch.id,
            "name": arch.name,
            "pattern": arch.pattern,
            "complexity": arch.complexity,
            "total_services": arch.total_services,
            "total_cost_monthly": arch.total_cost_monthly,
            "source_file": arch.source_file,
            "created_at": arch.created_at.isoformat(),
        },
        "nodes": nodes,
        "links": links,
        "metrics": {
            "total_services": len(nodes),
            "total_dependencies": len(links),
            "total_cost_monthly": arch.total_cost_monthly,
            "critical_nodes": [n["id"] for n in critical_nodes],
            "cost_hotspots": [n["id"] for n in cost_hotspots],
        },
    }


@router.delete("/{arch_id}")
def delete_graph(arch_id: str, db: Session = Depends(get_db)):
    """Delete an architecture and all its services/dependencies."""
    arch = db.query(Architecture).filter(Architecture.id == arch_id).first()
    if not arch:
        raise HTTPException(status_code=404, detail="Architecture not found")

    db.delete(arch)
    db.commit()
    return {"message": f"Architecture '{arch.name}' deleted"}
