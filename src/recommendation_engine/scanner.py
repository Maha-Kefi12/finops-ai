"""
Architecture Scanner — scans graph nodes + edges against all detector patterns.
=================================================================================
For each node in the architecture graph, runs ALL registered detectors.
Produces PatternMatch objects with resource metadata and savings estimates.
"""

from typing import Dict, List, Any, Optional
import logging

from .detectors import (
    get_all_patterns,
    _parse_service,
    _parse_resource_name,
    _node_cost,
    INSTANCE_TYPES,
    BASELINE_COSTS,
)

logger = logging.getLogger(__name__)


def scan_architecture(graph_data: dict) -> List[Dict[str, Any]]:
    """Scan architecture graph against ALL detector patterns.
    
    Args:
        graph_data: Graph JSON with 'nodes' (dict or list) and 'edges' (list).
        
    Returns:
        List of PatternMatch dicts, sorted by estimated savings (descending).
    """
    raw_nodes = graph_data.get("services") or graph_data.get("nodes") or {}
    edges = graph_data.get("edges") or graph_data.get("dependencies") or []
    
    # Normalize nodes into a list
    if isinstance(raw_nodes, dict):
        node_list = list(raw_nodes.values())
    elif isinstance(raw_nodes, list):
        node_list = raw_nodes
    else:
        logger.warning("No nodes found in graph data")
        return []
    
    if isinstance(edges, dict):
        edges = list(edges.values())
    
    patterns = get_all_patterns()
    all_matches: List[Dict[str, Any]] = []
    seen_pattern_resource = set()  # Deduplicate pattern+resource combinations
    
    logger.info("Scanning %d nodes against %d patterns (%d edges)",
               len(node_list), len(patterns), len(edges))
    
    for node in node_list:
        node_id = node.get("node_id") or node.get("id", "unknown")
        resource_name = _parse_resource_name(node)
        aws_service = _parse_service(node)
        
        for pattern in patterns:
            dedup_key = f"{pattern['pattern_id']}:{resource_name}"
            if dedup_key in seen_pattern_resource:
                continue
            
            try:
                if pattern["detector"](node, edges, node_list):
                    seen_pattern_resource.add(dedup_key)
                    
                    # Build PatternMatch
                    cost = _node_cost(node)
                    savings = pattern["savings_estimator"](node)
                    current_type, recommended_type = INSTANCE_TYPES.get(
                        aws_service, (f"{aws_service}-current", f"{aws_service}-optimized")
                    )
                    
                    # Infer environment
                    name_lower = resource_name.lower()
                    env = "production"
                    for tag in ("dev", "test", "staging", "sandbox", "qa"):
                        if tag in name_lower:
                            env = "development" if tag == "dev" else tag
                            break
                    
                    # Infer region from ARN
                    region = "us-east-1"
                    if "arn:aws:" in node_id:
                        parts = node_id.split(":")
                        if len(parts) > 3:
                            region = parts[3]
                    
                    match = {
                        "pattern_id": pattern["pattern_id"],
                        "resource_id": node_id,
                        "resource_name": resource_name,
                        "aws_service": aws_service.upper(),
                        "category": pattern["category"],
                        "priority": pattern["priority"],
                        "severity": pattern["priority"].lower(),
                        "risk_level": pattern["risk_level"],
                        "environment": env,
                        "region": region,
                        "current_instance_type": current_type,
                        "recommended_instance_type": recommended_type,
                        "current_monthly_cost": round(cost, 2),
                        "estimated_savings_monthly": round(savings, 2),
                        "estimated_savings_annual": round(savings * 12, 2),
                        "savings_percentage": round((savings / cost * 100) if cost > 0 else 0, 1),
                        "linked_best_practice": pattern["linked_best_practice"],
                        "recommendation_template": pattern["recommendation_template"],
                        "implementation_template": pattern["implementation_template"],
                        "threshold": pattern["threshold"],
                        # Graph metrics
                        "graph_metrics": {
                            "centrality": node.get("centrality", 0),
                            "betweenness_centrality": node.get("betweenness_centrality", 0),
                            "pagerank": node.get("pagerank", 0),
                            "blast_radius": node.get("blast_radius", 0),
                            "in_degree": node.get("in_degree", 0),
                            "out_degree": node.get("out_degree", 0),
                            "single_point_of_failure": node.get("single_point_of_failure", False),
                            "cascading_failure_risk": node.get("cascading_failure_risk", "low"),
                            "utilization_score": node.get("utilization_score", 0),
                            "clustering_coefficient": node.get("clustering_coefficient", 0),
                        },
                    }
                    
                    all_matches.append(match)
                    
            except Exception as e:
                logger.debug("Detector %s failed on %s: %s",
                           pattern["pattern_id"], resource_name, e)
    
    # Sort by savings (highest first), then by priority
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    all_matches.sort(key=lambda m: (
        priority_order.get(m["priority"], 3),
        -m["estimated_savings_monthly"],
    ))
    
    # Deduplicate: max 2 patterns per resource and max 2 per service family
    final = _apply_diversity_limits(all_matches)
    
    logger.info("Scanner: %d raw matches → %d after diversity limits", len(all_matches), len(final))
    return final


def _apply_diversity_limits(matches: List[Dict]) -> List[Dict]:
    """Apply diversity: max 2 per resource, max 3 per service family."""
    resource_count: Dict[str, int] = {}
    service_count: Dict[str, int] = {}
    result = []
    
    for m in matches:
        rname = m["resource_name"]
        svc = m["aws_service"]
        
        rc = resource_count.get(rname, 0)
        sc = service_count.get(svc, 0)
        
        if rc < 2 and sc < 3:
            result.append(m)
            resource_count[rname] = rc + 1
            service_count[svc] = sc + 1
    
    return result


__all__ = ["scan_architecture"]
