"""
GraphRAG Traversal API — exposes the 4 traversal strategies.

Endpoints:
    POST /api/graphrag/ego-network
    POST /api/graphrag/path-based
    POST /api/graphrag/cluster-based
    POST /api/graphrag/temporal
    POST /api/graphrag/combined
    GET  /api/graphrag/strategies
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.orm import Session

from src.storage.database import get_db
from src.graph.models import Architecture, Service, Dependency
from src.graph.engine import GraphEngine
from src.rag.traversal import GraphRAGTraversalEngine

router = APIRouter(prefix="/api/graphrag", tags=["graphrag"])


# ── Request schemas ──────────────────────────────────────────────────

class EgoNetworkRequest(BaseModel):
    arch_id: str
    seed_node: str
    hops: int = Field(default=2, ge=1, le=5)
    max_nodes: int = Field(default=50, ge=1, le=200)
    type_filter: Optional[List[str]] = None

class PathBasedRequest(BaseModel):
    arch_id: str
    source: str
    target: str
    max_paths: int = Field(default=5, ge=1, le=20)
    include_neighborhood: bool = True

class ClusterBasedRequest(BaseModel):
    arch_id: str
    min_cluster_size: int = Field(default=2, ge=1, le=20)
    resolution: float = Field(default=1.0, ge=0.1, le=5.0)
    focus_node: Optional[str] = None

class TemporalRequest(BaseModel):
    arch_id: str
    window_hours: int = Field(default=24, ge=1, le=8760)
    reference_time: Optional[str] = None
    sort_by: str = Field(default="newest")

class CombinedRequest(BaseModel):
    arch_id: str
    seed_node: Optional[str] = None
    target_node: Optional[str] = None
    hops: int = Field(default=2, ge=1, le=5)
    window_hours: int = Field(default=24, ge=1, le=8760)
    strategies: Optional[List[str]] = None


# ── Helper: rebuild graph from DB ────────────────────────────────────

def _build_engine(arch_id: str, db: Session) -> GraphRAGTraversalEngine:
    """Load architecture from DB, build graph, return traversal engine."""
    arch = db.query(Architecture).filter(Architecture.id == arch_id).first()
    if not arch:
        raise HTTPException(status_code=404, detail=f"Architecture '{arch_id}' not found")

    services = db.query(Service).filter(Service.architecture_id == arch_id).all()
    deps = db.query(Dependency).filter(Dependency.architecture_id == arch_id).all()

    # Reconstruct architecture JSON
    arch_data = {
        "metadata": {
            "name": arch.name,
            "pattern": arch.pattern,
            "complexity": arch.complexity,
        },
        "services": [
            {
                "id": svc.id.split("::", 1)[-1],
                "name": svc.name,
                "type": svc.service_type,
                "owner": svc.owner,
                "cost_monthly": svc.cost_monthly,
                "environment": svc.environment,
                "attributes": svc.attributes or {},
            }
            for svc in services
        ],
        "dependencies": [
            {
                "source": d.source.split("::", 1)[-1],
                "target": d.target.split("::", 1)[-1],
                "type": d.dep_type,
                "weight": d.weight,
            }
            for d in deps
        ],
    }

    engine = GraphEngine(arch_data)
    return GraphRAGTraversalEngine(engine.G)


# ── Helper: normalise node id ────────────────────────────────────────

def _strip_prefix(node_id: Optional[str]) -> Optional[str]:
    """Strip the optional '{arch_id}::' prefix so the id matches the graph."""
    if node_id and "::" in node_id:
        return node_id.split("::", 1)[-1]
    return node_id


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("/strategies")
def list_strategies():
    """List available traversal strategies."""
    return {
        "strategies": [
            {
                "id": "ego_network",
                "name": "Ego Network Expansion",
                "description": "BFS/DFS from a seed node to k-hop neighbors. "
                               "Shows the local neighborhood and influence zone.",
                "parameters": ["seed_node", "hops", "max_nodes", "type_filter"],
            },
            {
                "id": "path_based",
                "name": "Path-Based Expansion",
                "description": "Finds shortest and alternative paths between two nodes. "
                               "Reveals critical infrastructure paths and bottlenecks.",
                "parameters": ["source", "target", "max_paths", "include_neighborhood"],
            },
            {
                "id": "cluster_based",
                "name": "Cluster-Based Expansion",
                "description": "Community detection using modularity optimization. "
                               "Identifies logical infrastructure clusters.",
                "parameters": ["min_cluster_size", "resolution", "focus_node"],
            },
            {
                "id": "temporal",
                "name": "Temporal Expansion",
                "description": "Time-based traversal using discovery timestamps. "
                               "Identifies deployment waves and stale resources.",
                "parameters": ["window_hours", "reference_time", "sort_by"],
            },
        ]
    }


@router.post("/ego-network")
def ego_network(req: EgoNetworkRequest, db: Session = Depends(get_db)):
    """Execute ego network traversal from a seed node."""
    engine = _build_engine(req.arch_id, db)
    result = engine.ego_network(
        seed_node=_strip_prefix(req.seed_node),
        hops=req.hops,
        max_nodes=req.max_nodes,
        include_type_filter=req.type_filter,
    )
    return result.to_dict()


@router.post("/path-based")
def path_based(req: PathBasedRequest, db: Session = Depends(get_db)):
    """Execute path-based traversal between two nodes."""
    engine = _build_engine(req.arch_id, db)
    result = engine.path_based(
        source=_strip_prefix(req.source),
        target=_strip_prefix(req.target),
        max_paths=req.max_paths,
        include_neighborhood=req.include_neighborhood,
    )
    return result.to_dict()


@router.post("/cluster-based")
def cluster_based(req: ClusterBasedRequest, db: Session = Depends(get_db)):
    """Execute cluster-based community detection."""
    engine = _build_engine(req.arch_id, db)
    result = engine.cluster_based(
        min_cluster_size=req.min_cluster_size,
        resolution=req.resolution,
        focus_node=_strip_prefix(req.focus_node),
    )
    return result.to_dict()


@router.post("/temporal")
def temporal(req: TemporalRequest, db: Session = Depends(get_db)):
    """Execute temporal traversal analysis."""
    engine = _build_engine(req.arch_id, db)
    result = engine.temporal(
        window_hours=req.window_hours,
        reference_time=req.reference_time,
        sort_by=req.sort_by,
    )
    return result.to_dict()


@router.post("/combined")
def combined(req: CombinedRequest, db: Session = Depends(get_db)):
    """Execute combined multi-strategy traversal."""
    engine = _build_engine(req.arch_id, db)
    result = engine.combined_traversal(
        seed_node=_strip_prefix(req.seed_node),
        target_node=_strip_prefix(req.target_node),
        hops=req.hops,
        window_hours=req.window_hours,
        strategies=req.strategies,
    )
    return result.to_dict()
