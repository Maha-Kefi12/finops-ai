"""
Context Enricher — enriches PatternMatches with graph RAG metrics.
=================================================================
For each pattern match, injects:
  - Dependency tree (which services depend on / are depended upon)
  - Blast radius (% of architecture affected)
  - SPOF detection and redundancy path analysis
  - Cross-AZ cost estimation
  - Traffic metrics (QPS, error rate, latency)
  - Cascading failure risk assessment
  - AWS-native language translation
"""

from typing import Dict, List, Any, Optional, Set
import logging

from .detectors import _parse_service, _parse_resource_name, _get_edges_for_node

logger = logging.getLogger(__name__)


def enrich_matches(matches: List[Dict], graph_data: dict) -> List[Dict]:
    """Enrich each PatternMatch with full graph RAG context.
    
    Returns enriched recommendations ready for LLM polishing or direct display.
    """
    raw_nodes = graph_data.get("services") or graph_data.get("nodes") or {}
    edges = graph_data.get("edges") or graph_data.get("dependencies") or []
    
    if isinstance(raw_nodes, dict):
        node_map = raw_nodes  # Already keyed by ID
        node_list = list(raw_nodes.values())
    else:
        node_list = raw_nodes
        node_map = {n.get("node_id") or n.get("id", ""): n for n in node_list}
    
    if isinstance(edges, dict):
        edges = list(edges.values())
    
    total_nodes = len(node_list)
    
    enriched = []
    for match in matches:
        resource_id = match["resource_id"]
        resource_name = match["resource_name"]
        
        # Find the node in graph
        node = node_map.get(resource_id) or _find_node_by_name(node_map, resource_name)
        if not node:
            # Even without node match, keep the match with basic enrichment
            match["enrichment"] = {"status": "node_not_found"}
            enriched.append(match)
            continue
        
        node_edges = _get_edges_for_node(node, edges)
        
        # ═══ 1. Dependency Analysis ═══
        deps_in, deps_out = _build_dependency_tree(node, edges, node_map)
        
        # ═══ 2. Traffic Metrics ═══
        traffic = _extract_traffic_metrics(node_edges)
        
        # ═══ 3. Cross-AZ Analysis ═══
        cross_az = _analyze_cross_az(node_edges)
        
        # ═══ 4. Redundancy Path Analysis ═══
        redundancy = _analyze_redundancy(node, edges, node_map, total_nodes)
        
        # ═══ 5. Build enrichment context ═══
        gm = match.get("graph_metrics", {})
        blast_pct = gm.get("blast_radius", 0) * 100
        centrality = gm.get("centrality", 0)
        in_degree = gm.get("in_degree", 0)
        out_degree = gm.get("out_degree", 0)
        spof = gm.get("single_point_of_failure", False)
        cascade_risk = gm.get("cascading_failure_risk", "low")
        
        enrichment = {
            "dependencies_in": deps_in,
            "dependencies_out": deps_out,
            "dependency_count": in_degree + out_degree,
            "services_powered": in_degree,
            "services_consumed": out_degree,
            "blast_radius_pct": round(blast_pct, 1),
            "centrality_score": round(centrality, 3),
            "is_spof": spof,
            "cascade_risk": cascade_risk,
            "traffic": traffic,
            "cross_az": cross_az,
            "redundancy": redundancy,
        }
        
        match["enrichment"] = enrichment
        
        # ═══ 6. Render into AWS-native recommendation text ═══
        match["rendered_recommendation"] = _render_aws_native(match, enrichment)
        match["rendered_why_it_matters"] = _render_why_it_matters(match, enrichment)
        match["rendered_implementation"] = _render_implementation(match)
        
        # ═══ 7. Fill template placeholders ═══
        match["title"] = _fill_template(
            match["recommendation_template"], match, enrichment
        )
        
        enriched.append(match)
    
    logger.info("Enriched %d recommendations with graph context", len(enriched))
    return enriched


# ═══════════════════════════════════════════════════════════════════════════
# DEPENDENCY ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def _build_dependency_tree(node: dict, edges: list, node_map: dict) -> tuple:
    """Build dependency tree: who depends on this node and what it depends on."""
    node_id = node.get("node_id") or node.get("id", "")
    
    deps_in = []   # Services that depend ON this node (this is a target)
    deps_out = []  # Services this node depends ON (this is a source)
    
    for edge in edges:
        source = edge.get("source", "")
        target = edge.get("target", "")
        
        if target == node_id:
            # Something depends on this node
            source_name = source.split("/")[-1] if "/" in source else source
            source_svc = source.split(":")[2] if "arn:aws:" in source else "unknown"
            deps_in.append({
                "resource": source_name,
                "service": source_svc.upper(),
                "qps": edge.get("traffic_properties", {}).get("queries_per_second", 0),
                "is_critical": edge.get("is_critical", False),
            })
        
        if source == node_id:
            # This node depends on something
            target_name = target.split("/")[-1] if "/" in target else target
            target_svc = target.split(":")[2] if "arn:aws:" in target else "unknown"
            deps_out.append({
                "resource": target_name,
                "service": target_svc.upper(),
                "qps": edge.get("traffic_properties", {}).get("queries_per_second", 0),
                "is_critical": edge.get("is_critical", False),
            })
    
    return deps_in, deps_out


# ═══════════════════════════════════════════════════════════════════════════
# TRAFFIC METRICS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_traffic_metrics(node_edges: list) -> dict:
    """Extract traffic metrics from edges."""
    if not node_edges:
        return {"total_qps": 0, "total_rps": 0, "avg_latency_ms": 0, "avg_error_rate": 0}
    
    total_qps = sum(e.get("traffic_properties", {}).get("queries_per_second", 0) for e in node_edges)
    total_rps = sum(e.get("traffic_properties", {}).get("requests_per_second", 0) for e in node_edges)
    
    latencies = [e.get("traffic_properties", {}).get("average_latency_ms", 0) for e in node_edges if e.get("traffic_properties", {}).get("average_latency_ms", 0) > 0]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    
    error_rates = [e.get("behavior_properties", {}).get("error_rate", 0) for e in node_edges if e.get("behavior_properties", {}).get("error_rate", 0) > 0]
    avg_error_rate = sum(error_rates) / len(error_rates) if error_rates else 0
    
    return {
        "total_qps": round(total_qps, 1),
        "total_rps": round(total_rps, 1),
        "avg_latency_ms": round(avg_latency, 1),
        "avg_error_rate": round(avg_error_rate, 4),
        "connection_patterns": list({e.get("behavior_properties", {}).get("connection_pattern", "unknown") for e in node_edges}),
    }


# ═══════════════════════════════════════════════════════════════════════════
# CROSS-AZ ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def _analyze_cross_az(node_edges: list) -> dict:
    """Analyze cross-AZ data transfer costs."""
    cross_az_edges = [e for e in node_edges
                      if e.get("network_properties", {}).get("cross_az", False)]
    
    if not cross_az_edges:
        return {"has_cross_az": False, "cross_az_count": 0, "estimated_monthly_cost": 0}
    
    # Estimate cross-AZ cost: $0.02/GB, assume 1GB/1000 requests
    total_rps = sum(e.get("traffic_properties", {}).get("requests_per_second", 0) for e in cross_az_edges)
    monthly_gb = (total_rps * 3600 * 24 * 30) / 1000 * 0.001  # rough estimate
    monthly_cost = monthly_gb * 0.02
    
    az_pairs = []
    for e in cross_az_edges:
        net = e.get("network_properties", {})
        source_az = net.get("source_az", "?")
        target_az = net.get("target_az", "?")
        az_pairs.append(f"{source_az}→{target_az}")
    
    return {
        "has_cross_az": True,
        "cross_az_count": len(cross_az_edges),
        "az_pairs": az_pairs,
        "estimated_monthly_cost": round(monthly_cost, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════
# REDUNDANCY ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def _analyze_redundancy(node: dict, edges: list, node_map: dict, total_nodes: int) -> dict:
    """Analyze if alternative paths exist (redundancy)."""
    node_id = node.get("node_id") or node.get("id", "")
    
    # Find all nodes that depend on this one
    dependents = set()
    for edge in edges:
        if edge.get("target") == node_id:
            dependents.add(edge.get("source", ""))
    
    # For each dependent, check if it has alternative paths (other edges not through this node)
    has_alternative = {}
    for dep_id in dependents:
        alt_targets = set()
        for edge in edges:
            if edge.get("source") == dep_id and edge.get("target") != node_id:
                alt_targets.add(edge.get("target", ""))
        dep_name = dep_id.split("/")[-1] if "/" in dep_id else dep_id
        has_alternative[dep_name] = len(alt_targets) > 0
    
    has_full_redundancy = all(has_alternative.values()) if has_alternative else True
    
    return {
        "dependent_count": len(dependents),
        "has_full_redundancy": has_full_redundancy,
        "alternative_paths": has_alternative,
        "risk_if_removed": "LOW" if has_full_redundancy else ("HIGH" if len(dependents) >= 3 else "MEDIUM"),
    }


# ═══════════════════════════════════════════════════════════════════════════
# AWS-NATIVE RENDERING
# ═══════════════════════════════════════════════════════════════════════════

def _render_aws_native(match: dict, enrichment: dict) -> str:
    """Render recommendation in full AWS-native language."""
    lines = []
    
    # Header
    lines.append(f"### Recommendation: {match.get('title', match['recommendation_template'][:80])}")
    lines.append("")
    
    # Resource details
    lines.append(f"**Resource ID:** `{match['resource_id']}`")
    lines.append(f"**Resource Name:** {match['resource_name']}")
    lines.append(f"**Service:** {match['aws_service']}")
    lines.append(f"**Environment:** {match['environment']}")
    lines.append(f"**Region:** {match['region']}")
    if match.get('current_instance_type'):
        lines.append(f"**Current Type:** {match['current_instance_type']}")
    lines.append(f"**Current Monthly Cost:** ${match['current_monthly_cost']:,.2f}")
    lines.append(f"**Priority:** {match['priority']} | **Risk:** {match['risk_level']}")
    lines.append("")
    
    # Why it matters
    lines.append(f"**Why This Matters:**")
    lines.append(match.get("rendered_why_it_matters", ""))
    lines.append("")
    
    # Best practice reference
    lines.append(f"**Best Practice:** {match['linked_best_practice']}")
    lines.append("")
    
    # Savings
    lines.append(f"**Savings:**")
    lines.append(f"  Monthly Savings: ${match['estimated_savings_monthly']:,.2f}/mo")
    lines.append(f"  Annual Impact: ${match['estimated_savings_annual']:,.2f}/yr")
    lines.append(f"  Savings Rate: {match['savings_percentage']}%")
    
    return "\n".join(lines)


def _render_why_it_matters(match: dict, enrichment: dict) -> str:
    """Render a rich business-impact narrative from graph analysis."""
    resource_name = match.get("resource_name", match.get("resource_id", "this resource"))
    aws_service = match.get("aws_service", "AWS service")
    category = match.get("category", "optimization")
    savings = match.get("estimated_savings_monthly", 0)
    cost = match.get("current_monthly_cost", 0)
    env = match.get("environment", "production")
    region = match.get("region", "us-east-1")

    in_deg = enrichment.get("services_powered", 0)
    blast = enrichment.get("blast_radius_pct", 0)
    spof = enrichment.get("is_spof", False)
    cascade = enrichment.get("cascade_risk", "low")
    traffic = enrichment.get("traffic", {})
    cross_az = enrichment.get("cross_az", {})
    redundancy = enrichment.get("redundancy", {})
    deps_in = enrichment.get("dependencies_in", [])

    sentences = []

    # Opening: resource context
    sentences.append(
        f"{resource_name} is a {aws_service} resource running in {env} ({region})"
        + (f", currently costing ${cost:,.2f}/month" if cost > 0 else "")
        + "."
    )

    # Dependency impact
    if in_deg > 0:
        dep_names = [d.get("resource", "") for d in deps_in[:4] if d.get("resource")]
        dep_str = ", ".join(dep_names) if dep_names else f"{in_deg} service(s)"
        sentences.append(
            f"It powers {in_deg} downstream service(s) ({dep_str}), "
            f"meaning any disruption here would ripple across the architecture."
        )

    # Blast radius
    if blast > 5:
        sentences.append(
            f"A failure or misconfiguration would impact approximately {blast:.0f}% "
            f"of the entire architecture, affecting service availability and user experience."
        )

    # SPOF
    if spof:
        sentences.append(
            f"This resource is a single point of failure with no redundancy path — "
            f"if it goes down, dependent services have no fallback."
        )

    # Cascade risk
    if cascade not in ("low", "none"):
        sentences.append(
            f"The cascading failure risk is {cascade.upper()}: a partial outage here "
            f"could trigger sequential failures in connected services."
        )

    # Traffic
    qps = traffic.get("total_qps", 0)
    latency = traffic.get("avg_latency_ms", 0)
    if qps > 0:
        traffic_str = f"It handles approximately {qps:.0f} queries/second"
        if latency > 0:
            traffic_str += f" with an average latency of {latency:.0f}ms"
        sentences.append(traffic_str + ".")

    # Cross-AZ
    if cross_az.get("has_cross_az"):
        xaz_count = cross_az.get("cross_az_count", 0)
        xaz_cost = cross_az.get("estimated_monthly_cost", 0)
        sentences.append(
            f"Cross-AZ data transfer is detected across {xaz_count} edge(s), "
            f"adding approximately ${xaz_cost:,.2f}/month in transfer costs."
        )

    # Redundancy
    if not redundancy.get("has_full_redundancy", True):
        dep_count = redundancy.get("dependent_count", 0)
        sentences.append(
            f"There is no alternative path for {dep_count} dependent service(s) — "
            f"adding a failover or replica is strongly recommended before making changes."
        )

    # Savings closing
    if savings > 0:
        sentences.append(
            f"Addressing this recommendation would save approximately ${savings:,.2f}/month "
            f"(${savings * 12:,.2f}/year), improving cost efficiency without sacrificing reliability."
        )

    if not sentences or len(sentences) == 1:
        sentences.append(
            f"While no critical graph dependencies were detected, optimizing {resource_name} "
            f"aligns with AWS Well-Architected best practices for {category.replace('_', ' ')} "
            f"and reduces operational overhead in the {env} environment."
        )

    return " ".join(sentences)


def _render_implementation(match: dict) -> str:
    """Render AWS CLI implementation steps."""
    template = match.get("implementation_template", "")
    resource_id = match.get("resource_id", "")
    resource_name = match.get("resource_name", "")
    recommended = match.get("recommended_instance_type", "")
    region = match.get("region", "us-east-1")
    
    cmd = template.replace("{resource_id}", resource_id)
    cmd = cmd.replace("{resource_name}", resource_name)
    cmd = cmd.replace("{recommended}", recommended)
    cmd = cmd.replace("{region}", region)
    cmd = cmd.replace("{vpc_id}", "vpc-XXXXXXXX")
    cmd = cmd.replace("{route_table_id}", "rtb-XXXXXXXX")
    
    return cmd


def _fill_template(template: str, match: dict, enrichment: dict) -> str:
    """Fill recommendation template with actual values."""
    gm = match.get("graph_metrics", {})
    traffic = enrichment.get("traffic", {})
    
    result = template
    result = result.replace("{resource}", match.get("resource_name", "unknown"))
    result = result.replace("{current}", match.get("current_instance_type", "current"))
    result = result.replace("{recommended}", match.get("recommended_instance_type", "optimized"))
    result = result.replace("{savings_pct}", str(match.get("savings_percentage", 0)))
    result = result.replace("{util}", str(gm.get("utilization_score", 0)))
    result = result.replace("{in_degree}", str(gm.get("in_degree", 0)))
    result = result.replace("{blast_pct}", f"{gm.get('blast_radius', 0) * 100:.0f}")
    result = result.replace("{qps}", f"{traffic.get('total_qps', 0):.0f}")
    result = result.replace("{cascade_risk}", gm.get("cascading_failure_risk", "low"))
    result = result.replace("{centrality}", f"{gm.get('centrality', 0):.3f}")
    
    return result


def _find_node_by_name(node_map: dict, name: str) -> Optional[dict]:
    """Find a node by resource name in the node map."""
    for key, node in node_map.items():
        if name in key or name in str(node.get("node_name", "")):
            return node
    return None


__all__ = ["enrich_matches"]
