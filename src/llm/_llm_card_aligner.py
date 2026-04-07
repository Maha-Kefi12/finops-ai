"""
LLM Card → Engine Shape Alignment
===================================
Post-enrichment step that fills engine-specific fields on LLM-proposed cards
so they render identically to engine-backed cards in the frontend.

Rules:
  - Only called on LLM cards, NEVER on engine cards.
  - Uses setdefault / empty-check everywhere — never overwrites existing data.
  - Does NOT import or modify any recommendation_engine module.
"""

from typing import Any, Dict, List

# Maps canonical action enum → engine pattern_id prefix
_ACTION_TO_PATTERN: Dict[str, str] = {
    "DOWNSIZE":             "cpu_underutil",
    "TERMINATE":            "resource_waste",
    "STOP":                 "schedule_stop",
    "MOVE_TO_GRAVITON":     "graviton_migration",
    "CHANGE_STORAGE_CLASS": "storage_class_migration",
    "ADD_LIFECYCLE":        "s3_lifecycle",
    "ADD_VPC_ENDPOINT":     "nat_gateway_cost",
    "ELIMINATE_CROSS_AZ":   "cross_az_traffic",
    "DISABLE_MULTI_AZ":     "rds_multi_az",
    "ADD_READ_REPLICA":     "rds_read_replica",
    "ADD_CACHE":            "database_caching",
    "TUNE_MEMORY":          "lambda_memory",
    "PURCHASE_RESERVED":    "reserved_instance",
    "REVIEW_ARCHITECTURE":  "architecture_review",
}


def align_llm_cards_to_engine_shape(
    cards: List[Dict[str, Any]],
    graph_data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Fill missing engine-format fields on every LLM-proposed card.

    Assumes _enrich_cards() has already run (graph_context is populated).
    """
    services = graph_data.get("services") or graph_data.get("nodes") or []
    svc_map: Dict[str, Dict] = {}
    for s in services:
        for key in (s.get("id", ""), s.get("name", "")):
            if key:
                svc_map[key] = s

    for card in cards:
        rid_block  = card.get("resource_identification") or {}
        resource_id = rid_block.get("resource_id", "")
        svc        = svc_map.get(resource_id) or {}

        action          = card.get("action", "")
        service_type    = rid_block.get("service_type") or card.get("service_type") or svc.get("aws_service", "")
        current_type    = rid_block.get("current_instance_type") or svc.get("attributes", {}).get("instance_type", "")
        recommended_type = rid_block.get("recommended_instance_type", "")
        env             = rid_block.get("environment") or svc.get("environment", "production")
        region          = rid_block.get("region") or svc.get("region", "us-east-1")

        cb       = card.setdefault("cost_breakdown", {})
        savings  = float(card.get("total_estimated_savings") or cb.get("savings") or 0)
        current  = float(cb.get("current_monthly") or card.get("current_monthly_cost") or svc.get("cost_monthly", 0))
        if savings <= 0:
            savings = float(card.get("estimated_savings_monthly") or 0)
        savings_pct = round(savings / current * 100, 1) if current > 0 else 0
        annual      = round(savings * 12, 2)

        graph_ctx  = card.get("graph_context") or {}
        dep_names  = graph_ctx.get("dependent_services") or []
        narrative  = graph_ctx.get("narrative", "")
        is_spof    = graph_ctx.get("is_spof", False)
        risk_level = str(card.get("risk_level") or "LOW").upper()

        # ── 1. pattern_id ────────────────────────────────────────────────────
        card.setdefault("pattern_id", _ACTION_TO_PATTERN.get(action, "optimization"))

        # ── 2. resource_identification completeness ───────────────────────────
        if current_type and not rid_block.get("current_instance_type"):
            rid_block["current_instance_type"] = current_type
        if not rid_block.get("current_config"):
            parts = [f"Instance Type: {current_type}"] if current_type else []
            parts += [f"Service: {service_type}", f"Region: {region}", f"Environment: {env}"]
            rid_block["current_config"] = " | ".join(p for p in parts if p)

        # ── 3. cost_breakdown completeness ────────────────────────────────────
        if not cb.get("line_items"):
            aws_svc = svc.get("aws_service", service_type) or service_type
            cb["line_items"] = [{
                "item": f"{aws_svc} Instance/Service Cost",
                "usage": f"{env} ({region})",
                "cost": round(current, 2),
            }]
        if not cb.get("savings_percentage") and savings_pct > 0:
            cb["savings_percentage"] = savings_pct
        if not cb.get("annual_impact") and annual > 0:
            cb["annual_impact"] = annual
        if not cb.get("projected_monthly") and current > 0 and savings > 0:
            cb["projected_monthly"] = round(max(0.0, current - savings), 2)

        # ── 4. why_it_matters (build from LLM output fields) ────────────────
        if not card.get("why_it_matters") or len(str(card.get("why_it_matters", ""))) < 40:
            # Try to build from justification, summary, or description
            _why_parts = []
            _just = card.get("justification") or []
            if isinstance(_just, list) and _just:
                _why_parts.extend(str(j).strip("- ").strip() for j in _just[:2] if j)
            _summary = card.get("summary") or card.get("title") or ""
            _desc = card.get("description") or ""
            if _desc and len(_desc) > 30:
                _why_parts.append(str(_desc)[:200])
            elif _summary and len(_summary) > 20:
                _why_parts.append(str(_summary)[:200])
            if dep_names:
                _why_parts.append(f"Impacts {len(dep_names)} dependent service(s): {', '.join(dep_names[:3])}")
            if _why_parts:
                card["why_it_matters"] = ". ".join(_why_parts[:3])
            elif narrative:
                card["why_it_matters"] = narrative[:200]

        # ── 5. recommendations[0] — full_analysis, performance_impact,
        #        risk_mitigation in engine format ──────────────────────────────
        recs = card.get("recommendations") or [{}]
        rec0 = recs[0] if recs else {}

        linked_bp = card.get("linked_best_practice", "")

        # full_analysis — only overwrite if empty / very short
        if len(str(rec0.get("full_analysis") or "")) < 60:
            parts = [f"Pattern Detected: {card.get('pattern_id', '')}"]
            if linked_bp:
                parts.append(f"Best Practice: {linked_bp}")
            parts.append("")
            if current_type:
                parts.append(f"Current State: {current_type} in {region} ({env} environment)")
            if recommended_type:
                parts.append(f"Recommended: Migrate to {recommended_type}")
            if savings > 0:
                parts.append(f"Estimated Savings: ${savings:.2f}/month (${annual:.2f}/year)")
            parts.append("")
            if dep_names:
                parts.append(f"Impact Analysis: depended on by: {', '.join(dep_names[:3])}.")
            if is_spof:
                parts.append("CRITICAL: This is a Single Point of Failure. Add redundancy before making changes.")
            rec0["full_analysis"] = "\n".join(parts)

        # performance_impact — always rebuild to match engine format exactly
        if savings > 0:
            rec0["performance_impact"] = (
                f"Savings: ${savings:.2f}/mo ({savings_pct}% reduction). "
                f"Annual impact: ${annual:.2f}/yr"
            )

        # risk_mitigation — rebuild with actual dependent services
        risk_parts = [f"Risk Level: {risk_level}"]
        if dep_names:
            risk_parts.append(
                f"Impact: {len(dep_names)} dependent service(s) - {', '.join(dep_names[:3])}"
            )
        if is_spof:
            risk_parts.append("SPOF: Add Multi-AZ or replica BEFORE making changes")
        risk_parts.append("Always test in staging/dev environment first")
        rec0["risk_mitigation"] = ". ".join(risk_parts)

        # estimated_monthly_savings — keep consistent
        if savings > 0:
            rec0["estimated_monthly_savings"] = savings

        card["recommendations"] = [rec0] + list(recs[1:])

    return cards
