"""
LLM Recommendation Validator
=============================
Validates LLM-proposed recommendations against the deterministic engine.

For each LLM-proposed rec:
1. Re-run metrics/Cost Explorer queries
2. Check against engine rules (same as engine-backed recs)
3. Validate estimated savings with real pricing
4. Promote to engine_backed if validation passes
5. Otherwise, mark as "idea only" (rejected or low confidence)

This ensures LLM creativity is constrained by real data.
"""

from typing import Dict, List, Any, Optional, Tuple
import logging
import re
from dataclasses import asdict

from .scanner import scan_architecture
from .enricher import enrich_matches
from ..llm.recommendation_card_schema import (
    FullRecommendationCard,
    RecommendationSource,
    RecommendationAction,
    ValidationStatus,
    recommendation_card_to_dict,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION THRESHOLDS (AWS-style constants)
# ═══════════════════════════════════════════════════════════════════════════

VALIDATION_THRESHOLDS = {
    # EC2 idle detection
    "ec2_idle_cpu_p95": 5.0,  # P95 CPU < 5%
    "ec2_idle_network_mbps": 1.0,  # Network I/O < 1 Mbps
    "ec2_idle_min_days": 14,  # Must be idle for 14+ days
    
    # RDS oversize detection
    "rds_oversize_cpu_p95": 40.0,  # P95 CPU < 40%
    "rds_oversize_memory_pct": 30.0,  # P95 freeable memory > 30%
    "rds_oversize_min_days": 30,  # 30+ days observation
    
    # ElastiCache oversize
    "cache_oversize_memory_pct": 50.0,  # Memory < 50%
    "cache_oversize_evictions": 10,  # Low evictions < 10/day
    "cache_oversize_min_days": 30,
    
    # S3 lifecycle eligibility
    "s3_lifecycle_min_age_days": 90,  # Objects older than 90 days
    "s3_lifecycle_min_size_gb": 100,  # At least 100 GB
    
    # NAT Gateway idle
    "nat_idle_bytes_per_hour": 1_000_000,  # < 1 MB/hour
    "nat_idle_min_days": 7,
    
    # Lambda optimization
    "lambda_memory_sweet_spot_min": 1024,  # 1024-1792 MB sweet spot
    "lambda_memory_sweet_spot_max": 1792,
    
    # Minimum savings threshold
    "min_monthly_savings": 50.0,  # Must save at least $50/month
    
    # Confidence thresholds
    "high_confidence_threshold": 0.85,
    "medium_confidence_threshold": 0.60,
}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN VALIDATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def validate_llm_recommendations(
    llm_recs: List[Dict[str, Any]],
    graph_data: dict,
    engine_recs: Optional[List[Dict[str, Any]]] = None
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Validate LLM-proposed recommendations against engine rules.
    
    Args:
        llm_recs: List of LLM-proposed recommendation dicts
        graph_data: Full architecture graph data
        engine_recs: Optional list of engine-backed recs (for conflict detection)
        
    Returns:
        Tuple of (validated_recs, rejected_recs)
        - validated_recs: Promoted to engine_backed
        - rejected_recs: Kept as llm_proposed with rejected status
    """
    validated = []
    rejected = []
    
    logger.info("Validating %d LLM-proposed recommendations", len(llm_recs))
    
    for llm_rec in llm_recs:
        validation_result = _validate_single_recommendation(llm_rec, graph_data)
        
        if validation_result["is_valid"]:
            # Promote to engine_backed
            llm_rec["source"] = RecommendationSource.ENGINE_BACKED.value
            llm_rec["validation_status"] = ValidationStatus.VALIDATED.value
            llm_rec["validation_notes"] = validation_result["notes"]
            llm_rec["engine_confidence"] = validation_result["confidence"]
            validated.append(llm_rec)
            logger.info("✓ VALIDATED: %s (confidence: %.2f)", 
                       llm_rec.get("title", "Unknown")[:60], 
                       validation_result["confidence"])
        else:
            # Keep as llm_proposed but mark as rejected
            llm_rec["source"] = RecommendationSource.LLM_PROPOSED.value
            llm_rec["validation_status"] = ValidationStatus.REJECTED.value
            llm_rec["validation_notes"] = validation_result["notes"]
            llm_rec["engine_confidence"] = None
            rejected.append(llm_rec)
            logger.warning("✗ REJECTED: %s - %s", 
                          llm_rec.get("title", "Unknown")[:60],
                          validation_result["notes"])
    
    # Check for conflicts with engine-backed recs
    if engine_recs:
        validated, conflicted = _resolve_conflicts(validated, engine_recs)
        rejected.extend(conflicted)
    
    logger.info("Validation complete: %d validated, %d rejected", 
               len(validated), len(rejected))
    
    return validated, rejected


# ═══════════════════════════════════════════════════════════════════════════
# SINGLE RECOMMENDATION VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def _validate_single_recommendation(
    rec: Dict[str, Any],
    graph_data: dict
) -> Dict[str, Any]:
    """Validate a single LLM-proposed recommendation.
    
    Returns dict with:
        - is_valid: bool
        - confidence: float (0-1)
        - notes: str (validation details)
    """
    resource_id = rec.get("resource_id", "")
    action = rec.get("action", "")
    estimated_savings = rec.get("total_estimated_savings", 0) or rec.get("estimated_savings_per_month", 0)
    service_type = rec.get("service_type", "").lower()
    
    # Find the resource in graph
    node = _find_resource_in_graph(resource_id, graph_data)
    if not node:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Resource {resource_id} not found in architecture graph"
        }
    
    # Validate based on action type
    if "rightsize" in action.lower() or "ec2" in action.lower():
        return _validate_ec2_rightsize(rec, node, graph_data)
    elif "rds" in action.lower() or "database" in service_type:
        return _validate_rds_optimization(rec, node, graph_data)
    elif "cache" in action.lower() or "elasticache" in service_type:
        return _validate_cache_optimization(rec, node, graph_data)
    elif "s3" in action.lower() or "lifecycle" in action.lower():
        return _validate_s3_lifecycle(rec, node, graph_data)
    elif "nat" in action.lower() or "vpc" in action.lower():
        return _validate_nat_optimization(rec, node, graph_data)
    elif "lambda" in action.lower():
        return _validate_lambda_optimization(rec, node, graph_data)
    else:
        # Generic validation
        return _validate_generic(rec, node, graph_data)


# ═══════════════════════════════════════════════════════════════════════════
# SERVICE-SPECIFIC VALIDATORS
# ═══════════════════════════════════════════════════════════════════════════

def _get_reference_cost(rec: Dict, node: Dict) -> float:
    """Resolve the authoritative current monthly cost for a recommendation.
    
    Priority order:
    1. LLM's own current_monthly_cost (from ENGINE_FACTS prompt injection)
    2. cost_breakdown.current_monthly (normalised card field)
    3. Node's cost_monthly from graph
    Returns 0.0 if none available (no cost cap applied).
    """
    # LLM-stated current cost (most reliable when LLM used ENGINE_FACTS)
    cost = rec.get("current_monthly_cost") or 0
    if not cost:
        cost = (rec.get("cost_breakdown") or {}).get("current_monthly") or 0
    if not cost:
        cost = node.get("cost_monthly") or 0
    try:
        return float(cost)
    except (TypeError, ValueError):
        return 0.0


def _has_real_metrics(metrics: dict) -> bool:
    """Return True only when at least one numeric metric is non-zero."""
    check_keys = [
        "cpu_utilization_p95", "cpu_utilization", "network_in_mbps",
        "network_out_mbps", "memory_utilization", "freeable_memory_percent",
        "storage_gb", "average_object_age_days", "bytes_processed_per_hour",
    ]
    return any(float(metrics.get(k) or 0) > 0 for k in check_keys)


def _validate_ec2_rightsize(rec: Dict, node: Dict, graph_data: dict) -> Dict:
    """Validate EC2 rightsizing recommendation."""
    metrics = node.get("metrics", {})
    cpu_util = metrics.get("cpu_utilization_p95", metrics.get("cpu_utilization", 0))
    network_in = metrics.get("network_in_mbps", 0)
    network_out = metrics.get("network_out_mbps", 0)

    # No metric data — pass with low confidence (can't disprove)
    if not _has_real_metrics(metrics):
        confidence = 0.50
        notes = "Validated (no metrics): LLM recommendation accepted at low confidence — no CloudWatch data to refute"
    # Check if truly idle or underutilized
    elif cpu_util < VALIDATION_THRESHOLDS["ec2_idle_cpu_p95"] and (network_in + network_out) < VALIDATION_THRESHOLDS["ec2_idle_network_mbps"]:
        confidence = 0.95
        notes = f"Validated: P95 CPU {cpu_util:.1f}% < 5%, network I/O {network_in + network_out:.1f} Mbps < 1 Mbps"
    elif cpu_util < 30.0:
        confidence = 0.75
        notes = f"Validated: P95 CPU {cpu_util:.1f}% indicates underutilization"
    else:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: P95 CPU {cpu_util:.1f}% does not indicate rightsizing opportunity"
        }
    
    estimated_savings = float(rec.get("total_estimated_savings") or 0)
    current_cost = _get_reference_cost(rec, node)
    
    if estimated_savings < VALIDATION_THRESHOLDS["min_monthly_savings"]:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: Estimated savings ${estimated_savings:.2f}/mo below minimum ${VALIDATION_THRESHOLDS['min_monthly_savings']}/mo"
        }
    
    # Only reject if savings exceed the verified current cost (impossible savings)
    if current_cost > 0 and estimated_savings > current_cost:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: Savings ${estimated_savings:.2f} exceeds verified current cost ${current_cost:.2f}"
        }
    
    return {"is_valid": True, "confidence": confidence, "notes": notes}


def _validate_rds_optimization(rec: Dict, node: Dict, graph_data: dict) -> Dict:
    """Validate RDS optimization recommendation."""
    metrics = node.get("metrics", {})
    cpu_util = metrics.get("cpu_utilization_p95", metrics.get("cpu_utilization", 0))
    freeable_memory_pct = metrics.get("freeable_memory_percent", 0)

    # No metric data — pass with low confidence (can't disprove)
    if not _has_real_metrics(metrics):
        confidence = 0.50
        notes = "Validated (no metrics): LLM RDS recommendation accepted at low confidence — no CloudWatch data to refute"
    elif (
        cpu_util < VALIDATION_THRESHOLDS["rds_oversize_cpu_p95"] and
        freeable_memory_pct > VALIDATION_THRESHOLDS["rds_oversize_memory_pct"]
    ):
        confidence = 0.85
        notes = f"Validated: P95 CPU {cpu_util:.1f}% < 40%, freeable memory {freeable_memory_pct:.1f}% > 30%"
    else:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: Metrics do not indicate oversizing (CPU: {cpu_util:.1f}%, Memory: {freeable_memory_pct:.1f}%)"
        }
    
    estimated_savings = float(rec.get("total_estimated_savings") or 0)
    current_cost = _get_reference_cost(rec, node)
    
    if estimated_savings < VALIDATION_THRESHOLDS["min_monthly_savings"]:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: Savings ${estimated_savings:.2f}/mo below minimum threshold"
        }
    
    if current_cost > 0 and estimated_savings > current_cost:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: Savings ${estimated_savings:.2f} exceeds verified current cost ${current_cost:.2f}"
        }
    
    return {"is_valid": True, "confidence": confidence, "notes": notes}


def _validate_cache_optimization(rec: Dict, node: Dict, graph_data: dict) -> Dict:
    """Validate ElastiCache optimization recommendation."""
    metrics = node.get("metrics", {})
    memory_util = metrics.get("memory_utilization", 0)
    evictions = metrics.get("evictions_per_day", 0)

    if not _has_real_metrics(metrics):
        confidence = 0.50
        notes = "Validated (no metrics): LLM cache recommendation accepted at low confidence"
    elif (
        memory_util < VALIDATION_THRESHOLDS["cache_oversize_memory_pct"] and
        evictions < VALIDATION_THRESHOLDS["cache_oversize_evictions"]
    ):
        confidence = 0.80
        notes = f"Validated: Memory {memory_util:.1f}% < 50%, evictions {evictions:.0f}/day < 10"
    else:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": "Rejected: Cache metrics do not indicate oversizing"
        }
    
    return {
        "is_valid": True,
        "confidence": confidence,
        "notes": notes
    }


def _validate_s3_lifecycle(rec: Dict, node: Dict, graph_data: dict) -> Dict:
    """Validate S3 lifecycle recommendation."""
    metrics = node.get("metrics", {})
    storage_gb = metrics.get("storage_gb", 0)
    avg_age_days = metrics.get("average_object_age_days", 0)

    if not _has_real_metrics(metrics):
        confidence = 0.55
        notes = "Validated (no metrics): LLM S3 lifecycle recommendation accepted at low confidence"
    elif (
        storage_gb >= VALIDATION_THRESHOLDS["s3_lifecycle_min_size_gb"] and
        avg_age_days >= VALIDATION_THRESHOLDS["s3_lifecycle_min_age_days"]
    ):
        confidence = 0.90
        notes = f"Validated: {storage_gb:.0f} GB, avg age {avg_age_days:.0f} days > 90 days"
    else:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: Storage {storage_gb:.0f} GB or age {avg_age_days:.0f} days below threshold"
        }
    
    return {
        "is_valid": True,
        "confidence": confidence,
        "notes": notes
    }


def _validate_nat_optimization(rec: Dict, node: Dict, graph_data: dict) -> Dict:
    """Validate NAT Gateway optimization recommendation."""
    metrics = node.get("metrics", {})
    bytes_per_hour = metrics.get("bytes_processed_per_hour", 0)

    if not _has_real_metrics(metrics):
        confidence = 0.55
        notes = "Validated (no metrics): LLM NAT recommendation accepted at low confidence"
    elif bytes_per_hour < VALIDATION_THRESHOLDS["nat_idle_bytes_per_hour"]:
        confidence = 0.85
        notes = f"Validated: NAT processing {bytes_per_hour:,.0f} bytes/hour < 1 MB/hour"
    else:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: NAT is actively used ({bytes_per_hour:,.0f} bytes/hour)"
        }
    
    return {
        "is_valid": True,
        "confidence": confidence,
        "notes": notes
    }


def _validate_lambda_optimization(rec: Dict, node: Dict, graph_data: dict) -> Dict:
    """Validate Lambda optimization recommendation."""
    metrics = node.get("metrics", {})
    current_memory = metrics.get("memory_mb", 0)

    if not _has_real_metrics(metrics) or current_memory == 0:
        confidence = 0.50
        notes = "Validated (no metrics): LLM Lambda recommendation accepted at low confidence"
    elif not (VALIDATION_THRESHOLDS["lambda_memory_sweet_spot_min"] <= current_memory <= VALIDATION_THRESHOLDS["lambda_memory_sweet_spot_max"]):
        confidence = 0.70
        notes = f"Validated: Current memory {current_memory} MB outside sweet spot (1024-1792 MB)"
    else:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: Memory {current_memory} MB already in sweet spot range"
        }
    
    return {
        "is_valid": True,
        "confidence": confidence,
        "notes": notes
    }


def _validate_generic(rec: Dict, node: Dict, graph_data: dict) -> Dict:
    """Generic validation for recommendations without specific rules."""
    estimated_savings = float(rec.get("total_estimated_savings") or 0)
    current_cost = _get_reference_cost(rec, node)
    
    if estimated_savings < VALIDATION_THRESHOLDS["min_monthly_savings"]:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: Savings ${estimated_savings:.2f}/mo below minimum threshold"
        }
    
    # Reject only if savings are physically impossible (> current cost)
    if current_cost > 0 and estimated_savings > current_cost:
        return {
            "is_valid": False,
            "confidence": 0.0,
            "notes": f"Rejected: Savings ${estimated_savings:.2f} exceeds verified current cost ${current_cost:.2f}"
        }
    
    return {
        "is_valid": True,
        "confidence": 0.60,
        "notes": "Validated: Passed basic sanity checks"
    }


# ═══════════════════════════════════════════════════════════════════════════
# CONFLICT RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_conflicts(
    validated_llm_recs: List[Dict],
    engine_recs: List[Dict]
) -> Tuple[List[Dict], List[Dict]]:
    """Resolve conflicts between validated LLM recs and engine-backed recs.
    
    Engine-backed always wins. Conflicting LLM recs are downgraded.
    
    Returns:
        Tuple of (non_conflicting_recs, conflicted_recs)
    """
    non_conflicting = []
    conflicted = []
    
    # Build resource_id -> engine_rec map
    engine_by_resource = {
        rec.get("resource_id", ""): rec 
        for rec in engine_recs
    }
    
    for llm_rec in validated_llm_recs:
        resource_id = llm_rec.get("resource_id", "")
        
        if resource_id in engine_by_resource:
            # Conflict detected
            engine_rec = engine_by_resource[resource_id]
            llm_rec["source"] = RecommendationSource.LLM_PROPOSED.value
            llm_rec["validation_status"] = ValidationStatus.CONFLICT.value
            llm_rec["is_downgraded_due_to_conflict"] = True
            llm_rec["alternative_to_engine_rec_id"] = resource_id
            llm_rec["validation_notes"] = (
                f"Conflicts with engine-backed recommendation on same resource. "
                f"Engine action: {engine_rec.get('action', 'unknown')}"
            )
            conflicted.append(llm_rec)
            logger.info("Conflict: LLM rec on %s downgraded (engine takes precedence)", resource_id)
        else:
            non_conflicting.append(llm_rec)
    
    return non_conflicting, conflicted


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _find_resource_in_graph(resource_id: str, graph_data: dict) -> Optional[Dict]:
    """Find a resource node in the graph by ID or name."""
    nodes = graph_data.get("services") or graph_data.get("nodes") or []
    
    if isinstance(nodes, dict):
        nodes = list(nodes.values())
    
    for node in nodes:
        node_id = node.get("node_id") or node.get("id", "")
        node_name = node.get("name", "")
        
        if resource_id == node_id or resource_id == node_name:
            return node
        
        # Partial match on name
        if resource_id in node_name or node_name in resource_id:
            return node
    
    return None


__all__ = [
    "validate_llm_recommendations",
    "VALIDATION_THRESHOLDS",
]
