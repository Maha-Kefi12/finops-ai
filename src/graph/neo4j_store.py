"""
Neo4j Graph Store
=================
Stores and retrieves the infrastructure graph (nodes, edges, dependencies)
in Neo4j.  CUR cost data stays in PostgreSQL; the graph topology + metrics
live here.

Node labels:  :Resource {id, name, type, region, cost_monthly, ...}
Edge types:   :DEPENDS_ON, :ROUTES_TO, :QUERIES, :CACHES_VIA, etc.
Architecture: :Architecture {id, name, pattern, ...}

Cypher patterns:
  MERGE (n:Resource {id: $id}) SET n += $props
  MERGE (a)-[:DEPENDS_ON {type: $type, weight: $w}]->(b)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_driver():
    """Create a Neo4j driver from environment variables."""
    from neo4j import GraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "finops_neo4j")

    return GraphDatabase.driver(uri, auth=(user, password))


class Neo4jGraphStore:
    """Persist and query infrastructure graphs in Neo4j."""

    def __init__(self, driver=None):
        self._driver = driver or _get_driver()
        self._ensure_indices()

    def close(self):
        if self._driver:
            self._driver.close()

    # ──────────────────────────────────────────────────────────────────
    #  Schema / Constraints
    # ──────────────────────────────────────────────────────────────────
    def _ensure_indices(self):
        """Create uniqueness constraints and indexes (idempotent)."""
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Resource) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Architecture) REQUIRE a.id IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (r:Resource) ON (r.type)",
            "CREATE INDEX IF NOT EXISTS FOR (r:Resource) ON (r.architecture_id)",
        ]
        try:
            with self._driver.session() as session:
                for q in queries:
                    session.run(q)
        except Exception as e:
            logger.warning(f"Neo4j index creation notice: {e}")

    # ──────────────────────────────────────────────────────────────────
    #  Write: store a full transformed graph
    # ──────────────────────────────────────────────────────────────────
    def store_graph(self, graph_data: Dict[str, Any], architecture_id: str) -> Dict[str, Any]:
        """Store the entire graph (nodes + edges) for one architecture.

        Parameters
        ----------
        graph_data : dict
            Output of CURTransformer.transform() — contains ``nodes`` and ``edges``.
        architecture_id : str
            Architecture UUID (matches the PostgreSQL record).

        Returns
        -------
        dict  {"nodes_created", "edges_created", "architecture_id"}
        """
        metadata = graph_data.get("metadata", {})
        nodes = graph_data.get("nodes", [])
        edges = graph_data.get("edges", [])

        nodes_created = 0
        edges_created = 0

        with self._driver.session() as session:
            # 1. Upsert Architecture node
            session.run(
                """
                MERGE (a:Architecture {id: $id})
                SET a.name            = $name,
                    a.pattern         = $pattern,
                    a.complexity      = $complexity,
                    a.region          = $region,
                    a.environment     = $environment,
                    a.total_services  = $total_services,
                    a.total_cost      = $total_cost,
                    a.updated_at      = datetime()
                """,
                id=architecture_id,
                name=metadata.get("name", ""),
                pattern=metadata.get("pattern", "unknown"),
                complexity=metadata.get("complexity", "medium"),
                region=metadata.get("region", "us-east-1"),
                environment=metadata.get("environment", "production"),
                total_services=metadata.get("total_services", len(nodes)),
                total_cost=metadata.get("total_cost_monthly", 0),
            )

            # 2. Upsert Resource nodes (batched for performance)
            for batch_start in range(0, len(nodes), 50):
                batch = nodes[batch_start:batch_start + 50]
                for node in batch:
                    props = self._node_to_props(node, architecture_id)
                    session.run(
                        """
                        MERGE (r:Resource {id: $id})
                        SET r += $props
                        WITH r
                        MATCH (a:Architecture {id: $arch_id})
                        MERGE (r)-[:BELONGS_TO]->(a)
                        """,
                        id=node["id"],
                        props=props,
                        arch_id=architecture_id,
                    )
                    nodes_created += 1

            # 3. Create edges
            for edge in edges:
                rel_type = edge.get("type", "DEPENDS_ON").upper().replace(" ", "_")
                # Cypher does not support parameterised relationship types,
                # so we use DEPENDS_ON as the label and store the sub-type as a property.
                session.run(
                    """
                    MATCH (a:Resource {id: $source})
                    MATCH (b:Resource {id: $target})
                    MERGE (a)-[r:DEPENDS_ON {type: $dep_type}]->(b)
                    SET r.weight     = $weight,
                        r.updated_at = datetime()
                    """,
                    source=edge["source"],
                    target=edge["target"],
                    dep_type=edge.get("type", "depends_on"),
                    weight=edge.get("weight", 1.0),
                )
                edges_created += 1

        logger.info(
            f"Neo4j: stored {nodes_created} nodes, {edges_created} edges "
            f"for architecture {architecture_id}"
        )

        return {
            "nodes_created": nodes_created,
            "edges_created": edges_created,
            "architecture_id": architecture_id,
        }

    # ──────────────────────────────────────────────────────────────────
    #  Read: full graph for an architecture
    # ──────────────────────────────────────────────────────────────────
    def get_graph(self, architecture_id: str) -> Dict[str, Any]:
        """Return all nodes and edges for a given architecture as JSON-ready dict."""
        with self._driver.session() as session:
            # Fetch nodes
            node_result = session.run(
                """
                MATCH (r:Resource)-[:BELONGS_TO]->(a:Architecture {id: $arch_id})
                RETURN r
                """,
                arch_id=architecture_id,
            )
            nodes = []
            for record in node_result:
                props = dict(record["r"])
                # Convert Neo4j temporal types if present
                for k, v in list(props.items()):
                    if hasattr(v, "iso_format"):
                        props[k] = v.iso_format()
                nodes.append(props)

            # Fetch edges
            edge_result = session.run(
                """
                MATCH (a:Resource)-[r:DEPENDS_ON]->(b:Resource)
                WHERE a.architecture_id = $arch_id
                RETURN a.id AS source, b.id AS target,
                       r.type AS dep_type, r.weight AS weight
                """,
                arch_id=architecture_id,
            )
            edges = []
            for record in edge_result:
                edges.append({
                    "source": record["source"],
                    "target": record["target"],
                    "type": record["dep_type"] or "depends_on",
                    "weight": record["weight"] or 1.0,
                })

        return {
            "architecture_id": architecture_id,
            "nodes": nodes,
            "edges": edges,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
        }

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get a single node by ID."""
        with self._driver.session() as session:
            result = session.run(
                "MATCH (r:Resource {id: $id}) RETURN r",
                id=node_id,
            )
            record = result.single()
            if record:
                props = dict(record["r"])
                for k, v in list(props.items()):
                    if hasattr(v, "iso_format"):
                        props[k] = v.iso_format()
                return props
        return None

    def get_neighbors(self, node_id: str, direction: str = "both") -> Dict[str, Any]:
        """Get a node's neighbors and the connecting edges."""
        with self._driver.session() as session:
            if direction == "outgoing":
                q = """
                    MATCH (a:Resource {id: $id})-[r:DEPENDS_ON]->(b:Resource)
                    RETURN a, r, b
                """
            elif direction == "incoming":
                q = """
                    MATCH (b:Resource)-[r:DEPENDS_ON]->(a:Resource {id: $id})
                    RETURN a, r, b
                """
            else:
                q = """
                    MATCH (a:Resource {id: $id})-[r:DEPENDS_ON]-(b:Resource)
                    RETURN a, r, b
                """
            result = session.run(q, id=node_id)
            neighbors = []
            edges = []
            seen = set()
            for record in result:
                b_props = dict(record["b"])
                b_id = b_props.get("id", "")
                if b_id not in seen:
                    seen.add(b_id)
                    neighbors.append(b_props)
                edges.append({
                    "source": record["a"]["id"],
                    "target": record["b"]["id"],
                    "type": record["r"].get("type", "depends_on"),
                    "weight": record["r"].get("weight", 1.0),
                })

        return {"node_id": node_id, "neighbors": neighbors, "edges": edges}

    # ──────────────────────────────────────────────────────────────────
    #  Read: aggregated stats
    # ──────────────────────────────────────────────────────────────────
    def get_graph_stats(self, architecture_id: str) -> Dict[str, Any]:
        """Return summary stats for a graph."""
        with self._driver.session() as session:
            # Node count + cost by type
            type_result = session.run(
                """
                MATCH (r:Resource)-[:BELONGS_TO]->(a:Architecture {id: $arch_id})
                RETURN r.type AS type, count(r) AS cnt,
                       sum(r.cost_monthly) AS total_cost
                ORDER BY total_cost DESC
                """,
                arch_id=architecture_id,
            )
            by_type = []
            total_nodes = 0
            total_cost = 0
            for rec in type_result:
                by_type.append({
                    "type": rec["type"],
                    "count": rec["cnt"],
                    "total_cost": round(rec["total_cost"] or 0, 2),
                })
                total_nodes += rec["cnt"]
                total_cost += rec["total_cost"] or 0

            # Edge count
            edge_result = session.run(
                """
                MATCH (a:Resource {architecture_id: $arch_id})-[r:DEPENDS_ON]->()
                RETURN count(r) AS edge_count
                """,
                arch_id=architecture_id,
            )
            total_edges = edge_result.single()["edge_count"]

            # Risk distribution
            risk_result = session.run(
                """
                MATCH (r:Resource)-[:BELONGS_TO]->(a:Architecture {id: $arch_id})
                RETURN r.risk_level AS risk, count(r) AS cnt
                """,
                arch_id=architecture_id,
            )
            risk_dist = {}
            for rec in risk_result:
                risk_dist[rec["risk"] or "low"] = rec["cnt"]

        return {
            "architecture_id": architecture_id,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "total_cost_monthly": round(total_cost, 2),
            "by_type": by_type,
            "risk_distribution": risk_dist,
        }

    # ──────────────────────────────────────────────────────────────────
    #  Delete
    # ──────────────────────────────────────────────────────────────────
    def delete_graph(self, architecture_id: str) -> int:
        """Delete all nodes and edges for an architecture. Returns nodes deleted."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (r:Resource)-[:BELONGS_TO]->(a:Architecture {id: $arch_id})
                DETACH DELETE r
                WITH a
                DETACH DELETE a
                RETURN count(*) AS deleted
                """,
                arch_id=architecture_id,
            )
            return result.single()["deleted"]

    def list_architectures(self) -> List[Dict]:
        """List all stored architectures in Neo4j."""
        with self._driver.session() as session:
            result = session.run(
                """
                MATCH (a:Architecture)
                OPTIONAL MATCH (r:Resource)-[:BELONGS_TO]->(a)
                RETURN a, count(r) AS node_count
                ORDER BY a.updated_at DESC
                """
            )
            archs = []
            for rec in result:
                props = dict(rec["a"])
                props["node_count"] = rec["node_count"]
                for k, v in list(props.items()):
                    if hasattr(v, "iso_format"):
                        props[k] = v.iso_format()
                archs.append(props)
        return archs

    # ──────────────────────────────────────────────────────────────────
    #  Path queries
    # ──────────────────────────────────────────────────────────────────
    def find_path(self, source_id: str, target_id: str, max_hops: int = 5) -> List[Dict]:
        """Find shortest path between two resources."""
        with self._driver.session() as session:
            result = session.run(
                f"""
                MATCH p = shortestPath(
                    (a:Resource {{id: $source}})-[:DEPENDS_ON*1..{max_hops}]-(b:Resource {{id: $target}})
                )
                RETURN [n IN nodes(p) | n.id] AS path,
                       length(p) AS hops
                """,
                source=source_id,
                target=target_id,
            )
            paths = []
            for rec in result:
                paths.append({"path": rec["path"], "hops": rec["hops"]})
        return paths

    def find_clusters(self, architecture_id: str) -> List[Dict]:
        """Find weakly connected components (clusters) in the graph."""
        with self._driver.session() as session:
            # Get all nodes for this architecture
            result = session.run(
                """
                MATCH (r:Resource)-[:BELONGS_TO]->(a:Architecture {id: $arch_id})
                OPTIONAL MATCH (r)-[:DEPENDS_ON]-(other:Resource)
                WHERE other.architecture_id = $arch_id
                RETURN r.id AS node_id, r.type AS node_type,
                       r.cost_monthly AS cost,
                       collect(DISTINCT other.id) AS connected_to
                """,
                arch_id=architecture_id,
            )

            # Build adjacency and find components via BFS
            adjacency = {}
            node_info = {}
            for rec in result:
                nid = rec["node_id"]
                adjacency[nid] = set(rec["connected_to"]) if rec["connected_to"] else set()
                node_info[nid] = {
                    "id": nid,
                    "type": rec["node_type"],
                    "cost": rec["cost"] or 0,
                }

            # Simple BFS component detection
            visited = set()
            components = []
            for nid in adjacency:
                if nid in visited:
                    continue
                component = []
                queue = [nid]
                while queue:
                    current = queue.pop(0)
                    if current in visited:
                        continue
                    visited.add(current)
                    component.append(current)
                    for neighbor in adjacency.get(current, set()):
                        if neighbor not in visited:
                            queue.append(neighbor)
                components.append({
                    "nodes": component,
                    "size": len(component),
                    "total_cost": sum(node_info.get(n, {}).get("cost", 0) for n in component),
                    "types": list(set(node_info.get(n, {}).get("type", "") for n in component)),
                })

            components.sort(key=lambda c: c["size"], reverse=True)
            return components

    # ──────────────────────────────────────────────────────────────────
    #  Helpers
    # ──────────────────────────────────────────────────────────────────
    def _node_to_props(self, node: Dict, architecture_id: str) -> Dict[str, Any]:
        """Convert a transformer node dict to flat Neo4j properties.

        Neo4j doesn't support nested dicts/lists as property values, so we
        flatten or serialise complex fields.
        """
        import json

        props = {
            "id": node["id"],
            "architecture_id": architecture_id,
            "name": node.get("name", node["id"]),
            "type": node.get("type", "service"),
            "product_code": node.get("product_code", ""),
            "instance_type": node.get("instance_type", ""),
            "region": node.get("region", "us-east-1"),
            "cost_monthly": node.get("cost_monthly", 0),
            "cost_daily_avg": node.get("cost_daily_avg", 0),
            "usage_amount": node.get("usage_amount", 0),
            "line_item_count": node.get("line_item_count", 0),
            "health_score": node.get("health_score", 100),
            "risk_level": node.get("risk_level", "low"),
            "environment": node.get("environment", "production"),
            "owner": node.get("owner", ""),
            "in_degree": node.get("in_degree", 0),
            "out_degree": node.get("out_degree", 0),
            "degree_centrality": node.get("degree_centrality", 0),
            "cost_share": node.get("cost_share", 0),
            "updated_at": "datetime()",
        }

        # Optional performance metrics (flatten)
        if node.get("cpu_utilization") is not None:
            props["cpu_utilization"] = node["cpu_utilization"]
        if node.get("memory_utilization") is not None:
            props["memory_utilization"] = node["memory_utilization"]
        if node.get("error_count") is not None:
            props["error_count"] = node["error_count"]

        # Serialise complex fields to JSON strings
        if node.get("performance_metrics"):
            props["performance_metrics_json"] = json.dumps(node["performance_metrics"])
        if node.get("attributes"):
            props["attributes_json"] = json.dumps(node["attributes"])
        if node.get("daily_costs"):
            props["daily_costs_json"] = json.dumps(node["daily_costs"])

        return props

    def health_check(self) -> Dict[str, Any]:
        """Check Neo4j connectivity and return basic stats."""
        try:
            with self._driver.session() as session:
                result = session.run(
                    "MATCH (n) RETURN count(n) AS node_count"
                )
                nc = result.single()["node_count"]
                result2 = session.run(
                    "MATCH ()-[r]->() RETURN count(r) AS rel_count"
                )
                rc = result2.single()["rel_count"]
                return {
                    "status": "connected",
                    "node_count": nc,
                    "relationship_count": rc,
                }
        except Exception as e:
            return {"status": "error", "error": str(e)}
