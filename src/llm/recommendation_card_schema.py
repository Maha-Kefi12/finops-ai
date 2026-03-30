"""
Unified Recommendation Card Schema
===================================
Defines the complete structure for recommendation cards with strict
two-tier separation:

1. engine_backed: Deterministic rules + real metrics. Always correct.
2. llm_proposed: LLM-generated ideas needing engine validation.

Each rec tracks its source, confidence, and validation status.
Conflict resolution: engine_backed always wins over llm_proposed.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, is_dataclass, field
from enum import Enum
import dataclasses


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS FOR STRICT ACTION & SOURCE TRACKING
# ═══════════════════════════════════════════════════════════════════════════

class RecommendationSource(str, Enum):
    """Source of recommendation: deterministic engine or LLM proposed."""
    ENGINE_BACKED = "engine_backed"      # Real metrics + rules
    LLM_PROPOSED = "llm_proposed"        # LLM idea, needs validation


class RecommendationAction(str, Enum):
    """Allowed actions (no LLM can invent new ones)."""
    # EC2
    RIGHTSIZE_EC2 = "rightsize_ec2"
    TERMINATE_EC2 = "terminate_ec2"
    MIGRATE_EC2_GRAVITON = "migrate_ec2_graviton"
    SCHEDULE_EC2_STOP = "schedule_ec2_stop"

    # RDS
    RIGHTSIZE_RDS = "rightsize_rds"
    DISABLE_MULTI_AZ = "disable_multi_az"
    MIGRATE_RDS_GP2_TO_GP3 = "migrate_rds_gp2_to_gp3"
    ADD_READ_REPLICA = "add_read_replica"

    # ElastiCache
    RIGHTSIZE_ELASTICACHE = "rightsize_elasticache"
    MIGRATE_CACHE_GRAVITON = "migrate_cache_graviton"

    # Storage
    S3_ADD_LIFECYCLE = "s3_add_lifecycle"
    S3_ENABLE_INTELLIGENT_TIERING = "s3_enable_intelligent_tiering"
    EBS_MIGRATE_GP2_TO_GP3 = "ebs_migrate_gp2_to_gp3"

    # Network/VPC
    ADD_VPC_ENDPOINT = "add_vpc_endpoint"
    ELIMINATE_CROSS_AZ = "eliminate_cross_az"
    REPLACE_NAT_WITH_ENDPOINTS = "replace_nat_with_endpoints"

    # Other
    LAMBDA_TUNE_MEMORY = "lambda_tune_memory"
    LAMBDA_MIGRATE_ARM64 = "lambda_migrate_arm64"
    CLOUDFRONT_RESTRICT_PRICE_CLASS = "cloudfront_restrict_price_class"
    REDSHIFT_PAUSE_SCHEDULE = "redshift_pause_schedule"


class ValidationStatus(str, Enum):
    """LLM-proposed rec validation status."""
    PENDING = "pending"                 # Waiting for engine validation
    VALIDATED = "validated"             # Engine confirmed, promoted to backed
    REJECTED = "rejected"               # Engine rejected, keep as idea only
    CONFLICT = "conflict"               # Conflicts with engine rec, downgraded


class ConfidenceLevel(str, Enum):
    """Confidence in recommendation (distinct from engine confidence)."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class MetricsSummary:
    """Comprehensive finops metrics for a resource."""
    cpu_utilization_percent: Optional[float] = None
    memory_utilization_percent: Optional[float] = None
    iops: Optional[float] = None
    read_iops: Optional[float] = None
    write_iops: Optional[float] = None
    latency_p50_ms: Optional[float] = None
    latency_p95_ms: Optional[float] = None
    latency_p99_ms: Optional[float] = None
    error_rate_percent: Optional[float] = None
    throughput_qps: Optional[float] = None
    throughput_rps: Optional[float] = None
    network_in_mbps: Optional[float] = None
    network_out_mbps: Optional[float] = None
    cost_monthly: Optional[float] = None
    cost_p95_monthly: Optional[float] = None
    health_score: Optional[float] = None
    observation: str = "No metrics available"


@dataclass
class ResourceIdentification:
    """Resource identification and current configuration."""
    resource_id: str
    resource_name: str
    service_type: str
    environment: str
    region: str
    current_instance_type: Optional[str] = None
    recommended_instance_type: Optional[str] = None
    current_config: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class CostBreakdown:
    """Cost analysis and savings projection."""
    current_monthly: float
    projected_monthly: float
    savings_percentage: float
    annual_impact: float
    line_items: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GraphContext:
    """Architectural graph metrics and relationships."""
    blast_radius_pct: float
    blast_radius_services: int
    dependency_count: int
    depends_on_count: int
    dependent_services: List[str]
    cross_az_count: int
    cross_az_dependencies: List[str]
    is_spof: bool
    cascading_failure_risk: str  # low, medium, high
    centrality: float
    narrative: str
    severity_label: str
    total_qps: Optional[float] = None
    avg_latency_ms: Optional[float] = None
    avg_error_rate: Optional[float] = None
    has_redundancy: bool = True
    alternative_paths: Dict[str, bool] = field(default_factory=dict)


@dataclass
class Recommendation:
    """Single recommendation action."""
    title: str
    description: str
    full_analysis: str
    implementation_steps: List[str]
    performance_impact: str
    risk_mitigation: str
    estimated_monthly_savings: float
    confidence: str  # high, medium, low
    action: RecommendationAction = RecommendationAction.RIGHTSIZE_EC2  # Action enum


@dataclass
class FullRecommendationCard:
    """Complete recommendation card with two-tier source tracking."""
    # ── Core identification ──
    title: str
    service_type: str
    total_estimated_savings: float
    priority: str  # HIGH, MEDIUM, LOW
    severity: str  # high, medium, low
    category: str  # right-sizing, waste-elimination, etc.
    implementation_complexity: str  # low, medium, high
    risk_level: str  # LOW, MEDIUM, HIGH

    # ── TWO-TIER SOURCE TRACKING (Critical) ──
    source: RecommendationSource  # engine_backed OR llm_proposed
    action: RecommendationAction  # Must be from known enum

    # ── Confidence tracking (separate for engine vs LLM) ──
    engine_confidence: Optional[float] = None  # 0-1.0 for engine (deterministic)
    llm_confidence: float = 0.5  # 0-1.0 for LLM (always present for llm_proposed)

    # ── Validation state (for LLM-proposed recs) ──
    validation_status: ValidationStatus = ValidationStatus.PENDING
    validation_notes: Optional[str] = None  # Why rejected/conflicted

    # ── Conflict resolution ──
    is_downgraded_due_to_conflict: bool = False
    conflicting_rec_ids: List[str] = field(default_factory=list)  # IDs of engine-backed recs it conflicts with
    alternative_to_engine_rec_id: Optional[str] = None  # If downgraded, which engine rec it conflicts with

    # ── Pattern & metadata ──
    pattern_id: Optional[str] = None
    resource_id: str = ""

    # ── Detailed sections ──
    resource_identification: Optional[ResourceIdentification] = None
    cost_breakdown: Optional[CostBreakdown] = None
    graph_context: Optional[GraphContext] = None
    metrics_summary: Optional[MetricsSummary] = None

    # ── Recommendations (can have multiple) ──
    recommendations: List[Recommendation] = field(default_factory=list)

    # ── Best practice links ──
    finops_best_practice: Optional[str] = None
    linked_best_practice: Optional[str] = None
    why_it_matters: Optional[str] = None

    # ── Justification (especially for LLM-proposed) ──
    justification: Optional[str] = None  # Why LLM proposed this, references metrics


def recommendation_card_to_dict(card: FullRecommendationCard) -> Dict[str, Any]:
    """Convert dataclass to frontend-friendly dict with None-filtering."""
    def _filter_nones(obj: Any) -> Any:
        if is_dataclass(obj) and not isinstance(obj, type):
            d = asdict(obj)
            # Convert enums to strings for JSON serialization
            for k, v in d.items():
                if isinstance(v, Enum):
                    d[k] = v.value
            return _filter_nones(d)
        elif isinstance(obj, dict):
            return {k: _filter_nones(v) for k, v in obj.items() if v is not None}
        elif isinstance(obj, list):
            return [_filter_nones(item) for item in obj]
        elif isinstance(obj, Enum):
            return obj.value
        else:
            return obj

    return _filter_nones(asdict(card))


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION & CONFLICT RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════

def is_engine_backed(rec: FullRecommendationCard) -> bool:
    """Check if rec is engine-backed (deterministic)."""
    return rec.source == RecommendationSource.ENGINE_BACKED


def is_llm_proposed(rec: FullRecommendationCard) -> bool:
    """Check if rec is LLM-proposed (needs validation)."""
    return rec.source == RecommendationSource.LLM_PROPOSED


def get_recommendations_by_source(recs: List[FullRecommendationCard], source: RecommendationSource):
    """Filter recommendations by source."""
    return [r for r in recs if r.source == source]


def find_conflicting_recommendations(
    new_rec: FullRecommendationCard,
    existing_recs: List[FullRecommendationCard]
) -> List[FullRecommendationCard]:
    """Find recs that conflict with new_rec on the same resource."""
    conflicts = []
    for rec in existing_recs:
        if rec.resource_id == new_rec.resource_id:
            # Check if actions conflict
            if _actions_conflict(rec.action, new_rec.action):
                conflicts.append(rec)
    return conflicts


def _actions_conflict(action1: RecommendationAction, action2: RecommendationAction) -> bool:
    """Determine if two actions conflict on the same resource."""
    # Terminate conflicts with any optimization
    if action1 == RecommendationAction.TERMINATE_EC2 or action2 == RecommendationAction.TERMINATE_EC2:
        if action1 != action2:
            return True

    # Both are rightsizing but to different targets = conflict
    rightsize_actions = {
        RecommendationAction.RIGHTSIZE_EC2,
        RecommendationAction.RIGHTSIZE_RDS,
        RecommendationAction.RIGHTSIZE_ELASTICACHE,
    }
    if action1 in rightsize_actions and action2 in rightsize_actions and action1 != action2:
        return True

    return False


def apply_conflict_resolution(recs: List[FullRecommendationCard]) -> List[FullRecommendationCard]:
    """Resolve conflicts: engine-backed always wins, LLM-proposed get downgraded.

    Returns modified list with conflict markers set.
    """
    engine_backed_recs = get_recommendations_by_source(recs, RecommendationSource.ENGINE_BACKED)
    llm_proposed_recs = get_recommendations_by_source(recs, RecommendationSource.LLM_PROPOSED)

    for llm_rec in llm_proposed_recs:
        conflicts = find_conflicting_recommendations(llm_rec, engine_backed_recs)
        if conflicts:
            llm_rec.is_downgraded_due_to_conflict = True
            llm_rec.validation_status = ValidationStatus.CONFLICT
            llm_rec.conflicting_rec_ids = [c.resource_id for c in conflicts]
            if conflicts:
                llm_rec.alternative_to_engine_rec_id = conflicts[0].resource_id
            llm_rec.validation_notes = f"Conflicts with engine-backed rec on same resource. Engine takes precedence."

    return recs


__all__ = [
    "RecommendationSource",
    "RecommendationAction",
    "ValidationStatus",
    "ConfidenceLevel",
    "MetricsSummary",
    "ResourceIdentification",
    "CostBreakdown",
    "GraphContext",
    "Recommendation",
    "FullRecommendationCard",
    "recommendation_card_to_dict",
    "is_engine_backed",
    "is_llm_proposed",
    "get_recommendations_by_source",
    "find_conflicting_recommendations",
    "apply_conflict_resolution",
]
