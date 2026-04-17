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
    """Render a rich, resource-type-specific business-impact narrative.

    Uses ALL available match data (pattern, best practice, instance types,
    config) plus graph enrichment to produce a unique paragraph per card.
    """
    resource_name = match.get("resource_name", match.get("resource_id", "this resource"))
    aws_service = match.get("aws_service", "AWS service").upper()
    category = match.get("category", "optimization")
    savings = match.get("estimated_savings_monthly", 0)
    cost = match.get("current_monthly_cost", 0)
    env = match.get("environment", "production")
    region = match.get("region", "us-east-1")
    current_type = match.get("current_instance_type", "")
    recommended_type = match.get("recommended_instance_type", "")
    best_practice = match.get("linked_best_practice", "")
    pattern_id = match.get("pattern_id", "")
    risk_level = match.get("risk_level", "LOW")
    savings_pct = match.get("savings_percentage", 0)

    in_deg = enrichment.get("services_powered", 0)
    blast = enrichment.get("blast_radius_pct", 0)
    spof = enrichment.get("is_spof", False)
    cascade = enrichment.get("cascade_risk", "low")
    traffic = enrichment.get("traffic", {})
    cross_az = enrichment.get("cross_az", {})
    redundancy = enrichment.get("redundancy", {})
    deps_in = enrichment.get("dependencies_in", [])
    deps_out = enrichment.get("dependencies_out", [])

    sentences = []

    # ── Opening: category-specific context about what was detected ──
    cat_lower = category.lower().replace("_", "-")
    if "right-sizing" in cat_lower or "right_sizing" in cat_lower:
        if current_type and recommended_type:
            sentences.append(
                f"{resource_name} is currently running on a {current_type} instance in {env} ({region}), "
                f"but utilization analysis indicates it is over-provisioned. "
                f"Migrating to {recommended_type} would right-size this {aws_service} resource, "
                f"reducing waste while maintaining the same performance headroom."
            )
        else:
            sentences.append(
                f"{resource_name} is an over-provisioned {aws_service} resource in {env} ({region}). "
                f"Current utilization patterns show significant headroom that can be reclaimed "
                f"through right-sizing without impacting workload performance."
            )
    elif "waste" in cat_lower:
        sentences.append(
            f"{resource_name} is a {aws_service} resource in {env} ({region}) that shows signs of "
            f"underutilization or idle capacity. "
            + (f"At ${cost:,.2f}/month, " if cost > 0 else "")
            + f"this resource is consuming budget without delivering proportional value. "
            f"Consolidating or eliminating idle resources is a core FinOps practice that "
            f"directly improves cloud unit economics."
        )
    elif "network" in cat_lower:
        sentences.append(
            f"{resource_name} is a {aws_service} networking resource in {env} ({region}) "
            + (f"costing ${cost:,.2f}/month. " if cost > 0 else ". ")
            + f"Network-layer optimizations such as VPC endpoint adoption, NAT Gateway "
            f"consolidation, or traffic routing improvements can significantly reduce "
            f"data transfer costs and improve latency for services that route through this resource."
        )
    elif "storage" in cat_lower:
        sentences.append(
            f"{resource_name} is a {aws_service} storage resource in {env} ({region}) "
            + (f"with a current spend of ${cost:,.2f}/month. " if cost > 0 else ". ")
            + f"Storage optimization — such as migrating from gp2 to gp3, enabling lifecycle "
            f"policies, or tiering infrequently accessed data — reduces costs while often "
            f"improving throughput and IOPS performance."
        )
    elif "config" in cat_lower:
        sentences.append(
            f"{resource_name} is a {aws_service} resource in {env} ({region}) with a "
            f"configuration that does not match its workload requirements. "
            + (f"At ${cost:,.2f}/month, " if cost > 0 else "")
            + f"adjusting settings such as Multi-AZ, backup retention, or instance class "
            f"to align with the {env} tier can yield meaningful savings without risk."
        )
    elif "caching" in cat_lower:
        sentences.append(
            f"{resource_name} is a {aws_service} resource in {env} ({region}). "
            f"Introducing or tuning a caching layer reduces repeated queries to "
            f"origin services, lowering latency and backend load while cutting costs."
        )
    elif "reserved" in cat_lower:
        sentences.append(
            f"{resource_name} is a {aws_service} resource in {env} ({region}) "
            + (f"running at ${cost:,.2f}/month on-demand pricing. " if cost > 0 else ". ")
            + f"Committing to a Reserved Instance or Savings Plan for stable workloads "
            f"typically reduces compute spend by 30-60% with no performance change."
        )
    else:
        sentences.append(
            f"{resource_name} is a {aws_service} resource in {env} ({region})"
            + (f", currently costing ${cost:,.2f}/month" if cost > 0 else "")
            + f". This {category.replace('_', ' ')} opportunity was detected through "
            f"pattern analysis of the architecture graph."
        )

    # ── Dependent services — always name them ──
    dep_names = [d.get("resource", "") for d in deps_in if d.get("resource")]
    if dep_names:
        named = ", ".join(dep_names[:6])
        extra = f" and {len(dep_names) - 6} more" if len(dep_names) > 6 else ""
        sentences.append(
            f"This resource directly powers {len(dep_names)} downstream service(s): "
            f"{named}{extra}. Any changes must account for these dependencies to avoid "
            f"disrupting production traffic."
        )

    # ── Upstream deps (what it depends on) ──
    up_names = [d.get("resource", "") for d in deps_out if d.get("resource")]
    if up_names:
        sentences.append(
            f"It also depends on {len(up_names)} upstream service(s) "
            f"({', '.join(up_names[:4])}), forming a critical path in the architecture."
        )

    # ── Blast radius / SPOF / cascade ──
    if blast > 5:
        sentences.append(
            f"The blast radius is approximately {blast:.0f}% of the architecture — "
            f"a misconfiguration or outage would cascade to a significant portion of "
            f"the service mesh."
        )
    if spof:
        sentences.append(
            f"This resource is a single point of failure with no redundancy path. "
            f"Any downtime here leaves dependent services with zero fallback."
        )
    if cascade not in ("low", "none", ""):
        sentences.append(
            f"Cascading failure risk is rated {cascade.upper()}, meaning a partial "
            f"outage could propagate through connected services."
        )

    # ── Traffic metrics ──
    qps = traffic.get("total_qps", 0)
    latency = traffic.get("avg_latency_ms", 0)
    error_rate = traffic.get("avg_error_rate", 0)
    if qps > 0:
        t = f"Current traffic: ~{qps:.0f} queries/sec"
        if latency > 0:
            t += f", {latency:.0f}ms avg latency"
        if error_rate > 0.01:
            t += f", {error_rate:.2f}% error rate"
        sentences.append(t + ".")

    # ── Cross-AZ costs ──
    if cross_az.get("has_cross_az"):
        sentences.append(
            f"Cross-AZ data transfer detected ({cross_az.get('cross_az_count', 0)} edges), "
            f"adding ~${cross_az.get('estimated_monthly_cost', 0):,.2f}/month in transfer costs."
        )

    # ── Redundancy ──
    if not redundancy.get("has_full_redundancy", True):
        sentences.append(
            f"No alternative path exists for {redundancy.get('dependent_count', 0)} "
            f"dependent service(s) — add a failover or replica before making changes."
        )

    # ── Financial impact ──
    if savings > 0:
        sentences.append(
            f"Implementing this change saves ${savings:,.2f}/month (${savings * 12:,.2f}/year"
            + (f", a {savings_pct}% reduction" if savings_pct > 0 else "")
            + f"). Risk level: {risk_level}."
        )

    # ── Best practice reference ──
    if best_practice:
        sentences.append(f"This aligns with: {best_practice}.")

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
