"""Neo4j bridge helpers for loading/storing architecture graph data.

This module provides a single normalised shape for graph reads so API handlers
and background tasks can treat Neo4j as the source of truth for architecture,
services, and dependencies.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.graph.neo4j_store import Neo4jGraphStore


def _normalise_dependency_type(value: Optional[str]) -> str:
    if not value:
        return "depends_on"
    return str(value).strip().lower() or "depends_on"


def _normalise_weight(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 1.0


def list_architectures_neo4j() -> List[Dict[str, Any]]:
    """List architecture metadata stored in Neo4j."""
    store = Neo4jGraphStore()
    try:
        return store.list_architectures()
    finally:
        store.close()


def load_graph_from_neo4j(architecture_id: str) -> Optional[Dict[str, Any]]:
    """Return full graph payload from Neo4j for one architecture id."""
    store = Neo4jGraphStore()
    try:
        graph = store.get_graph(architecture_id)
        if not graph or not graph.get("nodes"):
            return None

        arch_meta = None
        for arch in store.list_architectures():
            if arch.get("id") == architecture_id:
                arch_meta = arch
                break

        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])

        services = []
        for n in nodes:
            services.append(
                {
                    "id": n.get("id", ""),
                    "name": n.get("name") or n.get("id", ""),
                    "type": n.get("type", "service"),
                    "environment": n.get("environment", "production"),
                    "owner": n.get("owner", ""),
                    "cost_monthly": float(n.get("cost_monthly", 0.0) or 0.0),
                    "attributes": {},
                }
            )

        dependencies = []
        for e in edges:
            dependencies.append(
                {
                    "source": e.get("source", ""),
                    "target": e.get("target", ""),
                    "type": _normalise_dependency_type(e.get("type")),
                    "weight": _normalise_weight(e.get("weight")),
                }
            )

        metadata = {
            "name": (arch_meta or {}).get("name") or f"arch:{architecture_id[:8]}",
            "pattern": (arch_meta or {}).get("pattern", "unknown"),
            "complexity": (arch_meta or {}).get("complexity", "medium"),
            "environment": (arch_meta or {}).get("environment", "production"),
            "region": (arch_meta or {}).get("region", "us-east-1"),
            "total_services": len(nodes),
            "total_cost_monthly": float((arch_meta or {}).get("total_cost", 0.0) or 0.0),
            "source": "neo4j",
        }

        return {
            "architecture_id": architecture_id,
            "metadata": metadata,
            "services": services,
            "dependencies": dependencies,
            "nodes": nodes,
            "edges": edges,
        }
    finally:
        store.close()
