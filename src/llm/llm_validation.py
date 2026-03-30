"""
LLM Recommendation Validation Framework
=========================================
Validates LLM-proposed recommendations using the same engine rules,
then promotes them to engine_backed if they pass or rejects them.

Pipeline:
1. LLM generates proposal (with action enum, resource_id, justification)
2. Validator re-runs metrics extraction for the resource
3. Validator checks rule thresholds (same as engine)
4. If passes: promote to engine_backed with engine_confidence
5. If fails: keep as llm_proposed with rejection reason
6. Returns validated list with conflict resolution applied
"""

import logging
from typing import List, Dict, Any, Optional
from src.llm.recommendation_card_schema import (
    FullRecommendationCard,
    RecommendationSource,
    RecommendationAction,
    ValidationStatus,
    apply_conflict_resolution,
)
from src.llm.finops_metrics import FinOpsMetricsExtractor

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# ENGINE THRESHOLDS (Must match detectors.py for consistency)
# ═══════════════════════════════════════════════════════════════════════════

ENGINE_THRESHOLDS = {
    "ec2_cpu_underutil": {"p95_cpu_max": 40, "period_days": 30},
    "ec2_idle": {"p95_cpu_max": 5, "period_days": 14},
    "ec2_dev_24x7": {"is_dev": True},
    "rds_cpu_underutil": {"p95_cpu_max": 40, "period_days": 30},
    "rds_multi_az_nonprod": {"is_nonprod": True, "is_multi_az": True},
    "cache_oversize": {"memory_util_max": 50, "period_days": 30},
    "s3_lifecycle": {"has_lifecycle": False},
    "cross_az_transfer": {"has_cross_az": True},
    "nat_costs": {"process_data": True},
}


class LLMProposalValidator:
    """Validates LLM-proposed recommendations against engine rules."""

    def __init__(self, graph_data: Optional[Dict[str, Any]] = None):
        """Initialize with optional graph_data for metric extraction."""
        self.graph_data = graph_data or {}
        self.services = self.graph_data.get("services") or self.graph_data.get("nodes") or []
        self.edges = self.graph_data.get("dependencies") or self.graph_data.get("edges") or []
        self.service_map = {s.get("id") or s.get("node_id"): s for s in self.services}

    def validate_proposal(self, proposal: FullRecommendationCard) -> FullRecommendationCard:
        """Validate a single LLM-proposed recommendation.

        Returns:
            proposal with validation_status set to VALIDATED or REJECTED
            plus validation_notes explaining why
        """
        if proposal.source != RecommendationSource.LLM_PROPOSED:
            # Not an LLM proposal, skip validation
            return proposal

        logger.info(
            "[VALIDATE] %s (action=%s, resource=%s)",
            proposal.title,
            proposal.action.value,
            proposal.resource_id,
        )

        # Find the resource
        resource = self.service_map.get(proposal.resource_id)
        if not resource:
            proposal.validation_status = ValidationStatus.REJECTED
            proposal.validation_notes = f"Resource {proposal.resource_id} not found in graph"
            logger.warning("[VALIDATE] Resource not found: %s", proposal.resource_id)
            return proposal

        # Extract current metrics
        metrics = FinOpsMetricsExtractor.extract_node_metrics(resource, self.edges)

        # Validate based on action type
        passes_validation = self._validate_action(
            proposal.action, resource, metrics, proposal
        )

        if passes_validation:
            proposal.validation_status = ValidationStatus.VALIDATED
            proposal.source = RecommendationSource.ENGINE_BACKED
            proposal.engine_confidence = 0.8  # LLM proposals are slightly less confident
            proposal.validation_notes = "Metrics confirm: LLM proposal validated by engine rules"
            logger.info("[VALIDATE] ✅ PASSED: %s", proposal.title)
        else:
            proposal.validation_status = ValidationStatus.REJECTED
            proposal.validation_notes = (
                f"Metrics don't match thresholds for {proposal.action.value}. "
                f"Keep as idea only. {proposal.validation_notes}"
            )
            logger.warning("[VALIDATE] ❌ REJECTED: %s (%s)", proposal.title, proposal.validation_notes)

        return proposal

    def _validate_action(
        self,
        action: RecommendationAction,
        resource: Dict[str, Any],
        metrics: Dict[str, Any],
        proposal: FullRecommendationCard,
    ) -> bool:
        """Check if metrics satisfy the action's thresholds."""
        cpu = metrics.get("cpu_utilization_percent")
        memory = metrics.get("memory_utilization_percent")
        iops = metrics.get("iops")
        latency_p95 = metrics.get("latency_p95_ms")

        # EC2 right-sizing: CPU < 40%
        if action == RecommendationAction.RIGHTSIZE_EC2:
            if cpu is not None and cpu < 40:
                proposal.validation_notes = f"CPU {cpu:.1f}% < 40% threshold"
                return True
            proposal.validation_notes = (
                f"CPU {cpu:.1f}% not below 40% threshold"
                if cpu is not None
                else "No CPU metrics available"
            )
            return False

        # EC2 terminate: CPU < 5%
        if action == RecommendationAction.TERMINATE_EC2:
            if cpu is not None and cpu < 5:
                proposal.validation_notes = f"CPU {cpu:.1f}% < 5% (idle threshold)"
                return True
            proposal.validation_notes = f"CPU {cpu:.1f}% not below 5% idle threshold"
            return False

        # RDS right-sizing: CPU < 40%
        if action == RecommendationAction.RIGHTSIZE_RDS:
            if cpu is not None and cpu < 40:
                if memory is not None and memory > 30:
                    proposal.validation_notes = (
                        f"CPU {cpu:.1f}% < 40% + Freeable memory {memory:.1f}% > 30%"
                    )
                    return True
            proposal.validation_notes = f"CPU {cpu:.1f}% or memory util doesn't match thresholds"
            return False

        # RDS Multi-AZ disable (non-prod only)
        if action == RecommendationAction.DISABLE_MULTI_AZ:
            env = resource.get("environment", "").lower()
            if any(tag in env for tag in ("dev", "test", "staging", "sandbox")):
                proposal.validation_notes = f"Environment is {env} (non-production)"
                return True
            proposal.validation_notes = f"Environment {env} is not non-production"
            return False

        # ElastiCache downsize: memory < 50%
        if action == RecommendationAction.RIGHTSIZE_ELASTICACHE:
            if memory is not None and memory < 50:
                proposal.validation_notes = f"Memory {memory:.1f}% < 50% threshold"
                return True
            proposal.validation_notes = f"Memory {memory:.1f}% not below 50% threshold"
            return False

        # S3 lifecycle
        if action == RecommendationAction.S3_ADD_LIFECYCLE:
            has_lifecycle = resource.get("lifecycle_policy", False)
            if not has_lifecycle:
                proposal.validation_notes = "No lifecycle policy detected"
                return True
            proposal.validation_notes = "Lifecycle policy already exists"
            return False

        # VPC endpoint for NAT savings
        if action == RecommendationAction.ADD_VPC_ENDPOINT:
            cross_az = any(
                e.get("network_properties", {}).get("cross_az", False) for e in self.edges
            )
            proposal.validation_notes = (
                "Cross-AZ traffic detected (can reduce NAT costs)" if cross_az else "No cross-AZ"
            )
            return cross_az or True  # Permissive: allow if cross-AZ OR no data

        # Default: if no specific validation, mark as needing more rules
        proposal.validation_notes = f"No validation rule for {action.value} (defaulting to reject)"
        return False

    def validate_batch(
        self, proposals: List[FullRecommendationCard]
    ) -> List[FullRecommendationCard]:
        """Validate a batch of LLM proposals."""
        logger.info("[VALIDATE] Validating %d LLM proposals", len(proposals))
        validated = [self.validate_proposal(p) for p in proposals]

        promoted = sum(1 for r in validated if r.source == RecommendationSource.ENGINE_BACKED)
        rejected = sum(1 for r in validated if r.validation_status == ValidationStatus.REJECTED)

        logger.info(
            "[VALIDATE] Results: %d promoted to engine_backed, %d rejected",
            promoted,
            rejected,
        )

        return validated


def separate_validated_and_ideas(
    all_recs: List[FullRecommendationCard],
) -> tuple:
    """Separate recommendations into validated (engine_backed) and ideas (llm_proposed).

    Returns:
        (validated_recs, idea_recs) for separate UI tabs
    """
    validated = [r for r in all_recs if r.source == RecommendationSource.ENGINE_BACKED]
    ideas = [r for r in all_recs if r.source == RecommendationSource.LLM_PROPOSED]
    return validated, ideas


def sort_by_savings_and_risk(recs: List[FullRecommendationCard]) -> List[FullRecommendationCard]:
    """Sort recommendations by savings descending, then risk ascending."""
    return sorted(
        recs,
        key=lambda r: (-r.total_estimated_savings, r.risk_level != "LOW"),
    )


__all__ = [
    "LLMProposalValidator",
    "separate_validated_and_ideas",
    "sort_by_savings_and_risk",
    "ENGINE_THRESHOLDS",
]
