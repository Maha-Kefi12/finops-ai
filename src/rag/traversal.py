"""
GraphRAG Traversal Engine — 4 advanced traversal strategies for
retrieving contextual sub-graphs from infrastructure knowledge graphs.

Strategies:
    1. Ego Network Expansion   — BFS/DFS from seed node to k-hop neighbors
    2. Path-Based Expansion    — shortest paths, critical path analysis
    3. Cluster-Based Expansion — community detection, cluster context
    4. Temporal Expansion      — time-based traversal using discovery timestamps

Each strategy produces a TraversalResult containing:
    - subgraph:  NetworkX DiGraph (the extracted subgraph)
    - nodes:     list of node dicts
    - edges:     list of edge dicts
    - context:   formatted text for LLM grounding
    - metadata:  strategy-specific analytics
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

logger = logging.getLogger(__name__)


# ===================================================================== #
#  Data Structures                                                        #
# ===================================================================== #

@dataclass
class TraversalResult:
    """Result from any traversal strategy."""
    strategy: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    context: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    subgraph: Optional[nx.DiGraph] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "nodes": self.nodes,
            "edges": self.edges,
            "context": self.context,
            "metadata": self.metadata,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
        }


@dataclass
class CombinedTraversalResult:
    """Result from combining multiple traversal strategies."""
    results: Dict[str, TraversalResult]
    merged_context: str
    total_nodes: int
    total_edges: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategies": {k: v.to_dict() for k, v in self.results.items()},
            "merged_context": self.merged_context,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
        }


# ===================================================================== #
#  Traversal Engine                                                       #
# ===================================================================== #

class GraphRAGTraversalEngine:
    """
    Executes 4 traversal strategies on a NetworkX graph and produces
    grounded context for LLM reasoning.

    Usage::

        engine = GraphRAGTraversalEngine(nx_graph)
        result = engine.ego_network("ecs-svc-api", hops=2)
        result = engine.path_based("alb-main", "rds-postgres")
        result = engine.cluster_based(min_cluster_size=3)
        result = engine.temporal(window_hours=24)
        combined = engine.combined_traversal(
            seed_node="ecs-svc-api", target_node="rds-postgres", hops=2
        )
    """

    def __init__(self, graph: nx.DiGraph):
        self.G = graph
        self._pagerank_cache: Optional[Dict[str, float]] = None
        self._betweenness_cache: Optional[Dict[str, float]] = None

    # ------------------------------------------------------------------ #
    #  Lazy metric caches                                                  #
    # ------------------------------------------------------------------ #
    @property
    def pagerank(self) -> Dict[str, float]:
        if self._pagerank_cache is None:
            try:
                self._pagerank_cache = nx.pagerank(self.G, alpha=0.85)
            except Exception:
                self._pagerank_cache = {n: 1.0 / max(1, len(self.G)) for n in self.G}
        return self._pagerank_cache

    @property
    def betweenness(self) -> Dict[str, float]:
        if self._betweenness_cache is None:
            try:
                self._betweenness_cache = nx.betweenness_centrality(self.G)
            except Exception:
                self._betweenness_cache = {n: 0.0 for n in self.G}
        return self._betweenness_cache

    # ================================================================== #
    #  STRATEGY 1: Ego Network Expansion                                   #
    # ================================================================== #
    def ego_network(
        self,
        seed_node: str,
        hops: int = 2,
        max_nodes: int = 50,
        include_type_filter: Optional[List[str]] = None,
        weight_by_centrality: bool = True,
    ) -> TraversalResult:
        """
        BFS expansion from a seed node to k-hop neighbors.

        Collects the ego network — subgraph of nodes reachable within
        ``hops`` edges from ``seed_node``. Optionally filters by node type
        and weights results by centrality for relevance ranking.

        Parameters:
            seed_node: Starting node ID (e.g. "ecs-svc-api")
            hops: Number of hops for BFS expansion (default 2)
            max_nodes: Maximum nodes to return (default 50)
            include_type_filter: Only include specific node types (e.g. ["service", "database"])
            weight_by_centrality: Rank nodes by PageRank * closeness
        """
        if seed_node not in self.G:
            return TraversalResult(
                strategy="ego_network",
                nodes=[], edges=[],
                context=f"Seed node '{seed_node}' not found in graph.",
                metadata={"error": "seed_not_found", "seed": seed_node},
            )

        # BFS with hop tracking
        visited: Dict[str, int] = {seed_node: 0}
        queue = deque([(seed_node, 0)])

        while queue:
            node, depth = queue.popleft()
            if depth >= hops:
                continue
            # Explore both directions (predecessors + successors)
            neighbors = set(self.G.successors(node)) | set(self.G.predecessors(node))
            for nbr in neighbors:
                if nbr not in visited:
                    visited[nbr] = depth + 1
                    queue.append((nbr, depth + 1))

        # Filter by type
        if include_type_filter:
            visited = {
                n: d for n, d in visited.items()
                if self.G.nodes[n].get("service_type", "service") in include_type_filter
                or n == seed_node
            }

        # Rank by centrality and trim
        if weight_by_centrality and len(visited) > max_nodes:
            pr = self.pagerank
            ranked = sorted(
                visited.keys(),
                key=lambda n: pr.get(n, 0) * (1.0 / max(1, visited[n])),
                reverse=True,
            )
            keep = set(ranked[:max_nodes])
            keep.add(seed_node)
            visited = {n: d for n, d in visited.items() if n in keep}

        # Extract subgraph
        node_set = set(visited.keys())
        subgraph = self.G.subgraph(node_set).copy()

        nodes = self._extract_nodes(subgraph, extra={"hop_distance": visited})
        edges = self._extract_edges(subgraph)

        # Build context
        seed_data = self.G.nodes[seed_node]
        context_parts = [
            f"=== EGO NETWORK: {seed_data.get('name', seed_node)} ===",
            f"Seed: {seed_node} (type={seed_data.get('service_type', '?')})",
            f"Hops: {hops}, Nodes found: {len(nodes)}, Edges: {len(edges)}",
            "",
            "Nodes by hop distance:",
        ]
        for hop in range(hops + 1):
            hop_nodes = [n for n, d in visited.items() if d == hop]
            if hop_nodes:
                names = [self.G.nodes[n].get("name", n) for n in hop_nodes[:10]]
                context_parts.append(f"  Hop {hop}: {', '.join(names)}")

        context_parts.append("")
        context_parts.append(self._summarize_subgraph(subgraph))

        return TraversalResult(
            strategy="ego_network",
            nodes=nodes,
            edges=edges,
            context="\n".join(context_parts),
            metadata={
                "seed_node": seed_node,
                "hops": hops,
                "hop_distribution": {
                    h: len([n for n, d in visited.items() if d == h])
                    for h in range(hops + 1)
                },
            },
            subgraph=subgraph,
        )

    # ================================================================== #
    #  STRATEGY 2: Path-Based Expansion                                    #
    # ================================================================== #
    def path_based(
        self,
        source: str,
        target: str,
        max_paths: int = 5,
        max_path_length: int = 10,
        include_neighborhood: bool = True,
    ) -> TraversalResult:
        """
        Find shortest and alternative paths between two nodes.

        Discovers the critical infrastructure path connecting two resources
        and extracts the surrounding context.

        Parameters:
            source: Start node (e.g. "alb-main")
            target: End node (e.g. "rds-postgres")
            max_paths: Maximum number of alternative paths to find
            max_path_length: Skip paths longer than this
            include_neighborhood: Include 1-hop neighbors of path nodes
        """
        for n, label in [(source, "source"), (target, "target")]:
            if n not in self.G:
                return TraversalResult(
                    strategy="path_based", nodes=[], edges=[],
                    context=f"{label.capitalize()} node '{n}' not found.",
                    metadata={"error": f"{label}_not_found"},
                )

        # Work on undirected view for path finding (infrastructure is often bidirectional)
        UG = self.G.to_undirected()

        paths: List[List[str]] = []
        try:
            # All simple paths (limited)
            for path in nx.all_simple_paths(UG, source, target, cutoff=max_path_length):
                paths.append(path)
                if len(paths) >= max_paths:
                    break
        except nx.NetworkXNoPath:
            pass

        if not paths:
            # Try each direction separately
            try:
                sp = nx.shortest_path(self.G, source, target)
                paths.append(sp)
            except nx.NetworkXNoPath:
                pass
            try:
                sp = nx.shortest_path(self.G, target, source)
                paths.append(list(reversed(sp)))
            except nx.NetworkXNoPath:
                pass

        if not paths:
            return TraversalResult(
                strategy="path_based", nodes=[], edges=[],
                context=f"No path found between {source} and {target}.",
                metadata={"error": "no_path", "source": source, "target": target},
            )

        # Collect all nodes on paths
        path_nodes: Set[str] = set()
        for p in paths:
            path_nodes.update(p)

        # Include 1-hop neighborhood
        if include_neighborhood:
            expansion: Set[str] = set()
            for n in path_nodes:
                expansion.update(self.G.successors(n))
                expansion.update(self.G.predecessors(n))
            path_nodes.update(expansion)

        subgraph = self.G.subgraph(path_nodes).copy()
        nodes = self._extract_nodes(subgraph)
        edges = self._extract_edges(subgraph)

        # Critical path analysis
        path_criticality = []
        bt = self.betweenness
        for i, path in enumerate(paths):
            path_cost = sum(self.G.nodes[n].get("cost_monthly", 0) for n in path)
            path_bt = sum(bt.get(n, 0) for n in path) / len(path)
            path_criticality.append({
                "path_index": i,
                "path": path,
                "length": len(path),
                "total_cost": round(path_cost, 2),
                "avg_betweenness": round(path_bt, 4),
                "nodes": [self.G.nodes[n].get("name", n) for n in path],
            })

        # Sort by criticality (betweenness * cost)
        path_criticality.sort(key=lambda p: p["avg_betweenness"], reverse=True)

        # Build context
        src_name = self.G.nodes[source].get("name", source)
        tgt_name = self.G.nodes[target].get("name", target)
        context_parts = [
            f"=== PATH ANALYSIS: {src_name} → {tgt_name} ===",
            f"Found {len(paths)} path(s), {len(nodes)} nodes, {len(edges)} edges",
            "",
        ]
        for pc in path_criticality:
            context_parts.append(
                f"Path {pc['path_index'] + 1}: {' → '.join(pc['nodes'])} "
                f"(length={pc['length']}, cost=${pc['total_cost']:,.0f}, "
                f"criticality={pc['avg_betweenness']:.4f})"
            )
        context_parts.append("")
        context_parts.append(self._summarize_subgraph(subgraph))

        return TraversalResult(
            strategy="path_based",
            nodes=nodes,
            edges=edges,
            context="\n".join(context_parts),
            metadata={
                "source": source, "target": target,
                "paths_found": len(paths),
                "path_details": path_criticality,
                "shortest_path_length": min(len(p) for p in paths),
            },
            subgraph=subgraph,
        )

    # ================================================================== #
    #  STRATEGY 3: Cluster-Based Expansion                                 #
    # ================================================================== #
    def cluster_based(
        self,
        min_cluster_size: int = 2,
        resolution: float = 1.0,
        focus_node: Optional[str] = None,
    ) -> TraversalResult:
        """
        Community detection using label propagation and structural clustering.

        Identifies logical infrastructure clusters (e.g. "networking layer",
        "compute cluster", "data tier") using graph community algorithms.

        Parameters:
            min_cluster_size: Minimum nodes for a cluster to be included
            resolution: Modularity resolution (higher = smaller clusters)
            focus_node: If given, only return the cluster containing this node
        """
        # Use undirected for community detection
        UG = self.G.to_undirected()

        if len(UG) == 0:
            return TraversalResult(
                strategy="cluster_based", nodes=[], edges=[],
                context="Empty graph — no clusters to detect.",
                metadata={"error": "empty_graph"},
            )

        # Try label propagation (works on any connected graph)
        communities: List[Set[str]] = []
        try:
            from networkx.algorithms.community import (
                greedy_modularity_communities,
                label_propagation_communities,
            )
            try:
                # Greedy modularity gives more stable results
                comms = greedy_modularity_communities(UG, resolution=resolution)
                communities = [set(c) for c in comms]
            except Exception:
                # Fallback to label propagation
                communities = [set(c) for c in label_propagation_communities(UG)]
        except Exception:
            # Manual clustering by connected component + service type
            communities = self._type_based_clustering()

        # Filter by minimum size
        communities = [c for c in communities if len(c) >= min_cluster_size]

        if not communities:
            # Fallback: cluster by service type
            communities = self._type_based_clustering()
            communities = [c for c in communities if len(c) >= min_cluster_size]

        # Focus on specific node's cluster
        if focus_node and focus_node in self.G:
            matching = [c for c in communities if focus_node in c]
            if matching:
                communities = matching

        # Enrich clusters with metadata
        cluster_details = []
        all_cluster_nodes: Set[str] = set()
        pr = self.pagerank

        for i, cluster in enumerate(communities):
            # Infer cluster label from dominant service type
            type_counts = defaultdict(int)
            total_cost = 0.0
            for n in cluster:
                t = self.G.nodes[n].get("service_type", "service")
                type_counts[t] += 1
                total_cost += self.G.nodes[n].get("cost_monthly", 0)

            dominant_type = max(type_counts, key=type_counts.get)  # type: ignore
            label = self._cluster_label(dominant_type, i)

            # Cluster centrality = avg PageRank of members
            cluster_centrality = sum(pr.get(n, 0) for n in cluster) / len(cluster)

            # Inter-cluster edges
            inter_edges = 0
            intra_edges = 0
            for u, v in self.G.edges():
                if u in cluster and v in cluster:
                    intra_edges += 1
                elif u in cluster or v in cluster:
                    inter_edges += 1

            cluster_details.append({
                "cluster_id": i,
                "label": label,
                "nodes": sorted(cluster),
                "size": len(cluster),
                "dominant_type": dominant_type,
                "type_distribution": dict(type_counts),
                "total_cost": round(total_cost, 2),
                "avg_centrality": round(cluster_centrality, 4),
                "intra_edges": intra_edges,
                "inter_edges": inter_edges,
                "cohesion": round(intra_edges / max(1, intra_edges + inter_edges), 3),
            })

            all_cluster_nodes.update(cluster)

        subgraph = self.G.subgraph(all_cluster_nodes).copy()
        nodes = self._extract_nodes(subgraph, extra={
            "cluster_id": {
                n: i for i, c in enumerate(communities)
                for n in c
            }
        })
        edges = self._extract_edges(subgraph)

        # Build context
        context_parts = [
            f"=== CLUSTER ANALYSIS ===",
            f"Detected {len(cluster_details)} infrastructure clusters",
            f"Total nodes: {len(all_cluster_nodes)}, Total edges: {len(edges)}",
            "",
        ]
        for cd in sorted(cluster_details, key=lambda x: x["total_cost"], reverse=True):
            node_names = [self.G.nodes[n].get("name", n) for n in cd["nodes"][:8]]
            context_parts.append(
                f"Cluster '{cd['label']}' ({cd['size']} nodes): "
                f"{', '.join(node_names)}"
            )
            context_parts.append(
                f"  Type: {cd['dominant_type']}, Cost: ${cd['total_cost']:,.0f}/mo, "
                f"Cohesion: {cd['cohesion']:.0%}, Centrality: {cd['avg_centrality']:.4f}"
            )
            context_parts.append("")

        return TraversalResult(
            strategy="cluster_based",
            nodes=nodes,
            edges=edges,
            context="\n".join(context_parts),
            metadata={
                "n_clusters": len(cluster_details),
                "clusters": cluster_details,
                "focus_node": focus_node,
            },
            subgraph=subgraph,
        )

    # ================================================================== #
    #  STRATEGY 4: Temporal Expansion                                      #
    # ================================================================== #
    def temporal(
        self,
        window_hours: int = 24,
        reference_time: Optional[str] = None,
        sort_by: str = "newest",
    ) -> TraversalResult:
        """
        Time-based traversal using discovered_at / created_at timestamps.

        Groups infrastructure by deployment timeline and identifies
        co-deployed resources, stale resources, and deployment waves.

        Parameters:
            window_hours: Time window for grouping co-deployed resources
            reference_time: ISO timestamp to center the window on (default: now)
            sort_by: "newest" or "oldest" ordering
        """
        ref_dt = datetime.fromisoformat(reference_time) if reference_time else datetime.now()
        # Strip timezone info from ref_dt for comparison consistency
        if ref_dt.tzinfo is not None:
            ref_dt = ref_dt.replace(tzinfo=None)

        # Extract timestamps from node attributes
        timestamped_nodes: List[Tuple[str, datetime, Dict]] = []

        for n, data in self.G.nodes(data=True):
            ts = self._extract_timestamp(data)
            if ts:
                # Normalize to naive datetime for consistent comparison
                if ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)
                timestamped_nodes.append((n, ts, data))

        if not timestamped_nodes:
            # If no timestamps, return all nodes grouped by type
            return TraversalResult(
                strategy="temporal",
                nodes=self._extract_nodes(self.G),
                edges=self._extract_edges(self.G),
                context="No timestamps found in graph nodes. "
                        "Returning all nodes without temporal grouping.",
                metadata={"error": "no_timestamps", "total_nodes": len(self.G)},
                subgraph=self.G.copy(),
            )

        # Sort by time
        if sort_by == "newest":
            timestamped_nodes.sort(key=lambda x: x[1], reverse=True)
        else:
            timestamped_nodes.sort(key=lambda x: x[1])

        # Group into deployment waves (within window_hours of each other)
        waves: List[List[Tuple[str, datetime]]] = []
        current_wave: List[Tuple[str, datetime]] = []

        for n, ts, _ in timestamped_nodes:
            if not current_wave:
                current_wave.append((n, ts))
            else:
                last_ts = current_wave[-1][1]
                diff = abs((ts - last_ts).total_seconds()) / 3600
                if diff <= window_hours:
                    current_wave.append((n, ts))
                else:
                    waves.append(current_wave)
                    current_wave = [(n, ts)]
        if current_wave:
            waves.append(current_wave)

        # Identify stale resources (deployed > 30 days ago with no recent neighbors)
        stale_threshold = datetime.now()
        stale_nodes = []
        for n, ts, _ in timestamped_nodes:
            ts_naive = ts.replace(tzinfo=None) if ts.tzinfo is not None else ts
            age_days = (stale_threshold - ts_naive).total_seconds() / 86400
            if age_days > 30:
                stale_nodes.append({"node": n, "age_days": round(age_days, 1)})

        # Build subgraph from all timestamped nodes
        node_set = {n for n, _, _ in timestamped_nodes}
        subgraph = self.G.subgraph(node_set).copy()

        nodes = self._extract_nodes(subgraph, extra={
            "deployment_wave": {
                n: i for i, wave in enumerate(waves)
                for n, _ in wave
            },
            "discovered_at": {
                n: ts.isoformat() for n, ts, _ in timestamped_nodes
            },
        })
        edges = self._extract_edges(subgraph)

        # Build context
        context_parts = [
            f"=== TEMPORAL ANALYSIS ===",
            f"Analyzed {len(timestamped_nodes)} timestamped resources",
            f"Deployment waves: {len(waves)}, Window: {window_hours}h",
            "",
        ]
        for i, wave in enumerate(waves):
            node_names = [self.G.nodes[n].get("name", n) for n, _ in wave[:8]]
            earliest = min(ts for _, ts in wave).isoformat()
            context_parts.append(
                f"Wave {i + 1} ({len(wave)} resources, from {earliest}): "
                f"{', '.join(node_names)}"
            )

        if stale_nodes:
            context_parts.append(f"\nStale resources (>30 days):")
            for sn in stale_nodes[:10]:
                name = self.G.nodes[sn['node']].get("name", sn['node'])
                context_parts.append(f"  {name}: {sn['age_days']} days old")

        return TraversalResult(
            strategy="temporal",
            nodes=nodes,
            edges=edges,
            context="\n".join(context_parts),
            metadata={
                "n_waves": len(waves),
                "waves": [
                    {
                        "wave_id": i,
                        "nodes": [n for n, _ in wave],
                        "size": len(wave),
                        "earliest": min(ts for _, ts in wave).isoformat(),
                        "latest": max(ts for _, ts in wave).isoformat(),
                    }
                    for i, wave in enumerate(waves)
                ],
                "stale_resources": stale_nodes[:20],
                "total_timestamped": len(timestamped_nodes),
            },
            subgraph=subgraph,
        )

    # ================================================================== #
    #  COMBINED TRAVERSAL                                                  #
    # ================================================================== #
    def combined_traversal(
        self,
        seed_node: Optional[str] = None,
        target_node: Optional[str] = None,
        hops: int = 2,
        window_hours: int = 24,
        strategies: Optional[List[str]] = None,
    ) -> CombinedTraversalResult:
        """
        Execute multiple traversal strategies and merge results.

        Parameters:
            seed_node: For ego network and cluster focus
            target_node: For path-based (if None, auto-selects farthest node)
            hops: Hops for ego network
            window_hours: Window for temporal analysis
            strategies: List of strategies to run (default: all 4)
        """
        active = strategies or ["ego_network", "path_based", "cluster_based", "temporal"]
        results: Dict[str, TraversalResult] = {}

        # Auto-select seed if not given
        if not seed_node and self.G:
            pr = self.pagerank
            seed_node = max(pr, key=pr.get) if pr else list(self.G.nodes())[0]  # type: ignore

        # Auto-select target if not given
        if not target_node and seed_node and self.G:
            # Pick the farthest high-centrality node
            bt = self.betweenness
            candidates = [n for n in self.G if n != seed_node]
            if candidates:
                target_node = max(candidates, key=lambda n: bt.get(n, 0))

        # 1. Ego Network
        if "ego_network" in active and seed_node:
            results["ego_network"] = self.ego_network(seed_node, hops=hops)

        # 2. Path-Based
        if "path_based" in active and seed_node and target_node:
            results["path_based"] = self.path_based(seed_node, target_node)

        # 3. Cluster-Based
        if "cluster_based" in active:
            results["cluster_based"] = self.cluster_based(focus_node=seed_node)

        # 4. Temporal
        if "temporal" in active:
            results["temporal"] = self.temporal(window_hours=window_hours)

        # Merge contexts
        all_nodes: Set[str] = set()
        all_edges: Set[Tuple[str, str]] = set()
        context_parts = ["=== COMBINED GRAPHRAG TRAVERSAL ===\n"]

        for name, result in results.items():
            for n in result.nodes:
                all_nodes.add(n["id"])
            for e in result.edges:
                all_edges.add((e["source"], e["target"]))
            context_parts.append(result.context)
            context_parts.append("")

        context_parts.append(
            f"\n--- TOTALS: {len(all_nodes)} unique nodes, "
            f"{len(all_edges)} unique edges across {len(results)} strategies ---"
        )

        return CombinedTraversalResult(
            results=results,
            merged_context="\n".join(context_parts),
            total_nodes=len(all_nodes),
            total_edges=len(all_edges),
        )

    # ================================================================== #
    #  Internal helpers                                                     #
    # ================================================================== #
    def _extract_nodes(
        self,
        subgraph: nx.DiGraph,
        extra: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Extract node dicts from subgraph with enrichment."""
        pr = self.pagerank
        bt = self.betweenness
        nodes = []
        for n, data in subgraph.nodes(data=True):
            node = {
                "id": n,
                "name": data.get("name", n),
                "type": data.get("service_type", "service"),
                "cost_monthly": data.get("cost_monthly", 0),
                "owner": data.get("owner", "unknown"),
                "environment": data.get("environment", "production"),
                "color": data.get("color", "#6b7280"),
                "pagerank": round(pr.get(n, 0), 6),
                "betweenness": round(bt.get(n, 0), 6),
                "in_degree": subgraph.in_degree(n),
                "out_degree": subgraph.out_degree(n),
                "attributes": data.get("attributes", {}),
            }
            # Add extra fields
            if extra:
                for key, mapping in extra.items():
                    if isinstance(mapping, dict) and n in mapping:
                        node[key] = mapping[n]
            nodes.append(node)
        return nodes

    def _extract_edges(self, subgraph: nx.DiGraph) -> List[Dict[str, Any]]:
        """Extract edge dicts from subgraph."""
        return [
            {
                "source": u,
                "target": v,
                "type": data.get("dep_type", "calls"),
                "weight": data.get("weight", 1.0),
            }
            for u, v, data in subgraph.edges(data=True)
        ]

    def _summarize_subgraph(self, subgraph: nx.DiGraph) -> str:
        """Generate a text summary of a subgraph."""
        if len(subgraph) == 0:
            return "Empty subgraph."

        type_counts = defaultdict(int)
        total_cost = 0.0
        for _, data in subgraph.nodes(data=True):
            type_counts[data.get("service_type", "service")] += 1
            total_cost += data.get("cost_monthly", 0)

        lines = [
            f"Subgraph summary: {len(subgraph)} nodes, {subgraph.number_of_edges()} edges",
            f"Total cost: ${total_cost:,.0f}/mo",
            f"Types: {', '.join(f'{t}({c})' for t, c in sorted(type_counts.items(), key=lambda x: -x[1]))}",
        ]

        # Top nodes by cost
        cost_ranked = sorted(
            subgraph.nodes(data=True),
            key=lambda nd: nd[1].get("cost_monthly", 0),
            reverse=True,
        )
        if cost_ranked:
            lines.append("Top cost nodes:")
            for n, d in cost_ranked[:5]:
                c = d.get("cost_monthly", 0)
                if c > 0:
                    lines.append(f"  {d.get('name', n)}: ${c:,.0f}/mo")

        return "\n".join(lines)

    def _type_based_clustering(self) -> List[Set[str]]:
        """Fallback clustering by service type."""
        type_map: Dict[str, Set[str]] = defaultdict(set)
        for n, data in self.G.nodes(data=True):
            t = data.get("service_type", "service")
            type_map[t].add(n)
        return list(type_map.values())

    @staticmethod
    def _cluster_label(dominant_type: str, index: int) -> str:
        """Generate a human-readable cluster label."""
        labels = {
            "network": "Network Layer",
            "security": "Security & IAM",
            "service": "Compute Cluster",
            "database": "Data Tier",
            "storage": "Storage Layer",
            "load_balancer": "Load Balancing",
            "cache": "Caching / Config",
            "batch": "Monitoring / Batch",
            "serverless": "Serverless",
            "queue": "Message Queues",
        }
        return labels.get(dominant_type, f"Cluster {index}")

    @staticmethod
    def _extract_timestamp(data: Dict) -> Optional[datetime]:
        """Extract a datetime from node attributes."""
        attrs = data.get("attributes", {})

        for key in ["discovered_at", "created_at", "launch_time", "creation_date",
                     "create_date", "last_modified"]:
            val = attrs.get(key) or data.get(key)
            if val:
                try:
                    if isinstance(val, datetime):
                        return val
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
        return None
