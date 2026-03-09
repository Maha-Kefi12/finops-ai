"""
GraphStorage — persists architecture graph data to PostgreSQL via SQLAlchemy.
"""
import uuid
from typing import Dict, Any, Optional

import networkx as nx
from sqlalchemy.orm import Session

from src.graph.models import Architecture, Service, Dependency


class GraphStorage:
    """Persist graph + metrics into the Architecture/Service/Dependency tables."""

    def __init__(self, db: Session):
        self.db = db

    def persist(
        self,
        raw_data: Dict[str, Any],
        graph: nx.DiGraph,
        metrics: Dict[str, Dict[str, Any]],
        source_file: str = "unknown",
    ) -> str:
        """Store graph in DB. Returns the architecture ID."""
        meta = raw_data.get("metadata", {})
        arch_id = str(uuid.uuid4())

        total_cost = meta.get(
            "total_cost_monthly",
            sum(s.get("cost_monthly", 0) for s in raw_data.get("services", [])),
        )

        arch = Architecture(
            id=arch_id,
            name=meta.get("name", source_file),
            pattern=meta.get("pattern", "unknown"),
            complexity=meta.get("complexity", "medium"),
            environment=meta.get("environment", "production"),
            region=meta.get("region", "us-east-1"),
            total_services=graph.number_of_nodes(),
            total_cost_monthly=total_cost,
            source_file=source_file,
            metadata_json=meta,
        )
        self.db.add(arch)
        self.db.flush()

        for svc in raw_data.get("services", []):
            m = metrics.get(svc["id"], {})
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
            self.db.add(service)

        self.db.flush()

        for dep in raw_data.get("dependencies", []):
            dependency = Dependency(
                id=str(uuid.uuid4()),
                architecture_id=arch_id,
                source=f"{arch_id}::{dep['source']}",
                target=f"{arch_id}::{dep['target']}",
                dep_type=dep.get("type", "calls"),
                weight=dep.get("weight", 1.0),
            )
            self.db.add(dependency)

        self.db.commit()
        return arch_id

    def save_snapshot(self, arch_id: str, raw_data: dict, source: str = "file",
                      llm_report: Optional[dict] = None, duration_seconds: float = 0.0):
        """Optionally save an ingestion snapshot record. No-op if table missing."""
        try:
            from src.api.handlers.ingest import IngestionSnapshot

            snap = IngestionSnapshot(
                architecture_id=arch_id,
                source=source,
                status="completed",
                pipeline_stage="completed",
                raw_data=raw_data,
                llm_report=llm_report,
                duration_seconds=round(duration_seconds, 2),
                total_services=len(raw_data.get("services", [])),
                total_cost_monthly=sum(
                    s.get("cost_monthly", 0) for s in raw_data.get("services", [])
                ),
            )
            self.db.add(snap)
            self.db.commit()
        except Exception:
            self.db.rollback()
