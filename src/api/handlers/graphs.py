"""
Graph retrieval and management API handlers.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import networkx as nx

from src.storage.database import get_db
from src.graph.engine import SERVICE_TYPE_COLORS
from src.graph.neo4j_store import Neo4jGraphStore
from src.graph.neo4j_bridge import list_architectures_neo4j, load_graph_from_neo4j

router = APIRouter(prefix="/api", tags=["graphs"])


@router.get("/graphs")
def list_graphs(db: Session = Depends(get_db)):
    """List all ingested architectures."""
    _ = db
    archs = list_architectures_neo4j()
    return {
        "architectures": [
            {
                "id": a.get("id"),
                "name": a.get("name"),
                "pattern": a.get("pattern", "unknown"),
                "complexity": a.get("complexity", "medium"),
                "total_services": a.get("total_services") or a.get("node_count") or 0,
                "total_cost_monthly": a.get("total_cost") or 0.0,
                "source_file": "neo4j",
                "created_at": a.get("updated_at") or a.get("created_at"),
            }
            for a in archs
        ]
    }


@router.get("/graphs/{arch_id}")
def get_graph(arch_id: str, db: Session = Depends(get_db)):
    """Get the full graph with nodes, links, and metrics for a given architecture."""
    _ = db
    graph_data = load_graph_from_neo4j(arch_id)
    if not graph_data:
        raise HTTPException(status_code=404, detail="Architecture not found in Neo4j")

    meta = graph_data.get("metadata", {})
    total_cost = float(meta.get("total_cost_monthly", 0.0) or 0.0)

    nodes = []
    for svc in graph_data.get("services", []):
        degree = int(svc.get("in_degree", 0) or 0) + int(svc.get("out_degree", 0) or 0)
        degree_centrality = float(svc.get("degree_centrality", 0.0) or 0.0)
        betweenness = float(svc.get("betweenness_centrality", 0.0) or 0.0)
        cost = float(svc.get("cost_monthly", 0.0) or 0.0)
        nodes.append({
            "id": svc.get("id"),
            "short_id": svc.get("id"),
            "name": svc.get("name", svc.get("id")),
            "type": svc.get("type", "service"),
            "owner": svc.get("owner", ""),
            "cost_monthly": cost,
            "environment": svc.get("environment", "production"),
            "attributes": svc.get("attributes", {}),
            "color": SERVICE_TYPE_COLORS.get(svc.get("type", "service"), "#6b7280"),
            "degree_centrality": degree_centrality,
            "betweenness_centrality": betweenness,
            "in_degree": int(svc.get("in_degree", 0) or 0),
            "out_degree": int(svc.get("out_degree", 0) or 0),
            "val": max(4, degree * 2 + 4),
            "cost_share": round((cost / max(0.01, total_cost)) * 100, 2),
        })

    links = [
        {
            "source": d.get("source"),
            "target": d.get("target"),
            "type": d.get("type", "depends_on"),
            "weight": d.get("weight", 1.0),
        }
        for d in graph_data.get("dependencies", [])
    ]

    critical_nodes = sorted(nodes, key=lambda n: n["betweenness_centrality"], reverse=True)[:3]
    cost_hotspots = sorted(nodes, key=lambda n: n["cost_monthly"], reverse=True)[:3]

    return {
        "architecture": {
            "id": arch_id,
            "name": meta.get("name", f"arch:{arch_id[:8]}"),
            "pattern": meta.get("pattern", "unknown"),
            "complexity": meta.get("complexity", "medium"),
            "total_services": len(nodes),
            "total_cost_monthly": total_cost,
            "source_file": "neo4j",
            "created_at": None,
        },
        "nodes": nodes,
        "links": links,
        "metrics": {
            "total_services": len(nodes),
            "total_dependencies": len(links),
            "total_cost_monthly": total_cost,
            "critical_nodes": [n["id"] for n in critical_nodes],
            "cost_hotspots": [n["id"] for n in cost_hotspots],
        },
    }


@router.delete("/graphs/{arch_id}")
def delete_graph(arch_id: str, db: Session = Depends(get_db)):
    """Delete an architecture and all its services/dependencies."""
    _ = db
    store = Neo4jGraphStore()
    try:
        deleted = store.delete_graph(arch_id)
    finally:
        store.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Architecture not found")
    return {"message": f"Architecture '{arch_id}' deleted from Neo4j"}


# ──────────────────────────────────────────────────────────────────────
#  Graph Metrics — computes centrality, pagerank, clustering from DB
# ──────────────────────────────────────────────────────────────────────
def _strip_prefix(sid: str, arch_id: str) -> str:
    prefix = f"{arch_id}::"
    return sid[len(prefix):] if sid.startswith(prefix) else sid


@router.get("/graph-metrics/{arch_id}")
def get_graph_metrics(arch_id: str, db: Session = Depends(get_db)):
    """Compute full graph metrics (centrality, pagerank, clustering) for an architecture."""
    _ = db
    graph_data = load_graph_from_neo4j(arch_id)
    if not graph_data:
        raise HTTPException(status_code=404, detail="Architecture not found")

    # Build NetworkX graph
    G = nx.DiGraph()
    for svc in graph_data.get("services", []):
        sid = svc.get("id")
        G.add_node(sid, name=svc.get("name", sid), type=svc.get("type", "service"),
                   cost=svc.get("cost_monthly", 0.0), owner=svc.get("owner", "unknown"))
    for dep in graph_data.get("dependencies", []):
        src = dep.get("source")
        tgt = dep.get("target")
        if G.has_node(src) and G.has_node(tgt):
            G.add_edge(src, tgt, type=dep.get("type", "depends_on"), weight=dep.get("weight", 1.0) or 1.0)

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
        "architecture_name": graph_data.get("metadata", {}).get("name", f"arch:{arch_id[:8]}"),
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
