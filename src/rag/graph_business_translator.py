"""Translate graph metrics into business-readable AWS context.

This is an internal GraphRAG helper layer and is not user-facing. It converts
centrality, dependency counts, and blast-radius style metrics into plain
business language that can be consumed by recommendation LLM prompts.
"""

from __future__ import annotations

from typing import Any, Dict, List


def translate_to_aws_language(graph_insight: Dict[str, Any]) -> Dict[str, str]:
    """Translate low-level graph values into business phrasing.

    Expected graph_insight keys include:
      - centrality (0..1)
      - in_degree (int)
      - blast_radius (0..1)
      - rank (int)
      - critical_dependents (list[str])
    """
    centrality = float(graph_insight.get("centrality", 0.0) or 0.0)
    in_degree = int(graph_insight.get("in_degree", 0) or 0)
    blast_radius = float(graph_insight.get("blast_radius", 0.0) or 0.0)
    rank = int(graph_insight.get("rank", 0) or 0)
    dependents = list(graph_insight.get("critical_dependents", []) or [])

    if rank > 0 and rank <= 5:
        criticality = f"This is one of your top {rank} most important services by traffic and dependency flow"
    elif centrality >= 0.8:
        criticality = "This service is a high-importance hub in your architecture"
    elif centrality >= 0.5:
        criticality = "This service has medium-high importance in your architecture"
    else:
        criticality = "This service has lower centrality and a smaller blast area"

    if dependents:
        sample = ", ".join(dependents[:3])
        dependencies_text = f"{in_degree} services rely on this, including {sample}"
    else:
        dependencies_text = f"{in_degree} direct downstream services rely on this"

    failure_impact = (
        f"If this fails, up to {int(round(blast_radius * 100))}% of the application path may be impacted"
        if blast_radius > 0
        else "Failure impact is expected to be limited to a narrow service boundary"
    )

    return {
        "criticality": criticality,
        "dependencies": dependencies_text,
        "failure_impact": failure_impact,
    }


def build_business_context_for_resources(graph_data: Dict[str, Any], top_n: int = 15) -> List[Dict[str, Any]]:
    """Build business-readable context entries for top resources by criticality.

    Output entries are designed for LLM prompt grounding and include both raw
    numbers and translated business text.
    """
    services = list(graph_data.get("services") or graph_data.get("nodes") or [])
    dependencies = list(graph_data.get("dependencies") or graph_data.get("edges") or [])
    if not services:
        return []

    ids = [s.get("id", "") for s in services if s.get("id")]
    total = max(1, len(ids))

    inbound: Dict[str, List[str]] = {sid: [] for sid in ids}
    for dep in dependencies:
        src = dep.get("source")
        tgt = dep.get("target")
        if tgt in inbound and src:
            inbound[tgt].append(src)

    # Sort by in-degree then cost to prioritise critical upstream services.
    ranked = sorted(
        services,
        key=lambda s: (
            len(inbound.get(s.get("id", ""), [])),
            float(s.get("cost_monthly", 0.0) or 0.0),
            float(s.get("degree_centrality", 0.0) or 0.0),
        ),
        reverse=True,
    )

    top = ranked[: max(1, top_n)]
    output: List[Dict[str, Any]] = []
    for idx, svc in enumerate(top, start=1):
        sid = svc.get("id", "")
        dependents = inbound.get(sid, [])
        in_degree = len(dependents)
        centrality = float(svc.get("degree_centrality", 0.0) or 0.0)
        if centrality <= 0:
            centrality = min(1.0, in_degree / total)
        blast_radius = min(1.0, (in_degree + 1) / total)

        translated = translate_to_aws_language(
            {
                "centrality": centrality,
                "in_degree": in_degree,
                "blast_radius": blast_radius,
                "rank": idx,
                "critical_dependents": dependents,
            }
        )

        output.append(
            {
                "resource_id": sid,
                "resource_name": svc.get("name", sid),
                "resource_type": svc.get("type", svc.get("aws_service", "service")),
                "cost_monthly": float(svc.get("cost_monthly", 0.0) or 0.0),
                "centrality": round(centrality, 4),
                "in_degree": in_degree,
                "blast_radius": round(blast_radius, 4),
                "business_insight": translated,
            }
        )

    return output
