"""
Graph retrieval and management API handlers.
"""
import json
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import networkx as nx

from src.storage.database import get_db
from src.graph.models import Architecture, Service, Dependency
from src.graph.engine import GraphEngine, SERVICE_TYPE_COLORS

router = APIRouter(prefix="/api", tags=["graphs"])


@router.get("/graphs")
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


@router.get("/graphs/{arch_id}")
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


@router.delete("/graphs/{arch_id}")
def delete_graph(arch_id: str, db: Session = Depends(get_db)):
    """Delete an architecture and all its services/dependencies."""
    arch = db.query(Architecture).filter(Architecture.id == arch_id).first()
    if not arch:
        raise HTTPException(status_code=404, detail="Architecture not found")

    db.delete(arch)
    db.commit()
    return {"message": f"Architecture '{arch.name}' deleted"}


# ──────────────────────────────────────────────────────────────────────
#  Graph Metrics — computes centrality, pagerank, clustering from DB
# ──────────────────────────────────────────────────────────────────────
def _strip_prefix(sid: str, arch_id: str) -> str:
    prefix = f"{arch_id}::"
    return sid[len(prefix):] if sid.startswith(prefix) else sid


@router.get("/graph-metrics/{arch_id}")
def get_graph_metrics(arch_id: str, db: Session = Depends(get_db)):
    """Compute full graph metrics (centrality, pagerank, clustering) for an architecture."""
    arch = db.query(Architecture).filter(Architecture.id == arch_id).first()
    if not arch:
        raise HTTPException(status_code=404, detail="Architecture not found")

    services = db.query(Service).filter(Service.architecture_id == arch_id).all()
    deps = db.query(Dependency).filter(Dependency.architecture_id == arch_id).all()

    # Build NetworkX graph
    G = nx.DiGraph()
    for svc in services:
        short_id = _strip_prefix(svc.id, arch_id)
        G.add_node(short_id, name=svc.name, type=svc.service_type,
                   cost=svc.cost_monthly or 0.0, owner=svc.owner or "unknown")
    for dep in deps:
        src = _strip_prefix(dep.source, arch_id)
        tgt = _strip_prefix(dep.target, arch_id)
        if G.has_node(src) and G.has_node(tgt):
            G.add_edge(src, tgt, type=dep.dep_type, weight=dep.weight or 1.0)

    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()

    # Centrality
    degree_cent = nx.degree_centrality(G) if n_nodes > 0 else {}
    betweenness_cent = nx.betweenness_centrality(G, weight="weight") if n_nodes > 0 else {}
    top_bottlenecks = sorted(betweenness_cent.items(), key=lambda x: x[1], reverse=True)[:10]

    # PageRank
    try:
        pagerank = nx.pagerank(G) if n_nodes > 0 else {}
    except Exception:
        pagerank = {n: 1.0 / max(1, n_nodes) for n in G.nodes()}
    top_important = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:10]

    # Clustering (on undirected version)
    try:
        clustering = nx.clustering(G.to_undirected()) if n_nodes > 0 else {}
    except Exception:
        clustering = {}
    avg_clustering = sum(clustering.values()) / max(1, len(clustering))

    # Density & components
    density = nx.density(G) if n_nodes > 0 else 0
    is_dag = nx.is_directed_acyclic_graph(G) if n_nodes > 0 else True
    components = nx.number_weakly_connected_components(G) if n_nodes > 0 else 0

    # Cycles
    try:
        cycles = list(nx.simple_cycles(G))[:20]
    except Exception:
        cycles = []

    return {
        "architecture_id": arch_id,
        "architecture_name": arch.name,
        "metrics": {
            "summary": {
                "total_nodes": n_nodes,
                "total_edges": n_edges,
                "density": round(density, 4),
                "is_dag": is_dag,
                "components": components,
                "num_cycles": len(cycles),
                "avg_clustering": round(avg_clustering, 4),
            },
            "centrality": {
                "betweenness": {k: round(v, 6) for k, v in betweenness_cent.items()},
                "degree": {k: round(v, 6) for k, v in degree_cent.items()},
                "top_bottlenecks": top_bottlenecks,
            },
            "pagerank": {
                "scores": {k: round(v, 6) for k, v in pagerank.items()},
                "top_important": top_important,
            },
            "clustering": {
                "coefficients": {k: round(v, 6) for k, v in clustering.items()},
                "average": round(avg_clustering, 4),
            },
            "cycles": cycles[:10],
        },
    }
