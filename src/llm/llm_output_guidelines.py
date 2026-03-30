"""
LLM Output Schema & Guidelines
================================
Instructions for the LLM on what format to output for recommendations.

When generating LLM-proposed recommendations, the LLM must output JSON
following a strict schema that forces it to pick from known actions,
include confidence, and justify with real metrics.

The key constraint: LLM cannot invent actions or make up confidence numbers.
It must pick from the known enum and properly justify proposals.
"""

LLM_OUTPUT_SCHEMA = """
When you propose a recommendation, output it as structured JSON following this EXACT format:

{
  "recommendations": [
    {
      "resource_id": "ec2-prod-api-1",                    // REQUIRED: must match graph node ID
      "action": "rightsize_ec2",                          // REQUIRED: must be from this enum
      "source": "llm_proposed",                           // REQUIRED: always "llm_proposed"
      "title": "Right-size EC2 from m5.xlarge to m6g.large",  // Human-readable title
      "priority": "HIGH",                                 // HIGH, MEDIUM, LOW
      "severity": "high",                                 // high, medium, low
      "category": "right-sizing",                         // Category of optimization
      "estimated_savings_approx": 125.50,                 // OPTIONAL: approximate, LLM's estimate
      "llm_confidence": 0.85,                             // 0-1.0: YOUR confidence in this idea
      "implementation_complexity": "low",                 // low, medium, high
      "risk_level": "LOW",                                // LOW, MEDIUM, HIGH
      "justification": "Resource shows CPU utilization of 35%, averaging well below the 40% threshold for 30+ days. Memory is also underutilized at 28%. Migrating from m5.xlarge to m6g.large (Graviton3) would reduce costs by ~50% while maintaining capacity.",
      "metrics_referenced": {
        "cpu_utilization_percent": 35.0,
        "p95_latency_ms": 67.5,
        "iops": 1500.0,
        "cost_monthly": 250.0
      }
    }
  ]
}

ALLOWED ACTIONS (enum values):
================================

EC2:
  - rightsize_ec2              // Downsize underutilized instance
  - terminate_ec2              // Remove idle instance (CPU <5%)
  - migrate_ec2_graviton       // Migrate old-gen to Graviton ARM
  - schedule_ec2_stop          // Schedule stop for dev/test

RDS:
  - rightsize_rds              // Downsize underutilized DB
  - disable_multi_az           // Disable Multi-AZ for non-prod
  - migrate_rds_gp2_to_gp3     // Upgrade storage type
  - add_read_replica           // Add read replica for high traffic

ElastiCache:
  - rightsize_elasticache      // Downsize underutilized cache
  - migrate_cache_graviton     // Migrate to Graviton r7g nodes

Storage:
  - s3_add_lifecycle           // Add lifecycle transition policy
  - s3_enable_intelligent_tiering  // Enable auto-tiering
  - ebs_migrate_gp2_to_gp3     // Upgrade EBS volume type

Network/VPC:
  - add_vpc_endpoint           // Add VPC endpoint (eliminate NAT)
  - eliminate_cross_az         // Co-locate in same AZ
  - replace_nat_with_endpoints // Replace NAT Gateway

Other:
  - lambda_tune_memory         // Optimize Lambda memory allocation
  - lambda_migrate_arm64       // Migrate to ARM64 (Graviton)
  - cloudfront_restrict_price_class  // Restrict to cheaper price class
  - redshift_pause_schedule    // Schedule pause for off-hours

IMPORTANT RULES:
================

1. ONLY use actions from the enum above. Do NOT invent new actions like
   "upgrade-cache" or "consolidate-databases". The engine only recognizes
   the actions listed above.

2. resource_id MUST match a node in the graph (ec2-*, rds-*, s3-*, etc.).
   Do NOT make up IDs.

3. llm_confidence is YOUR confidence (0-1.0), separate from engine confidence.
   Be honest: if you're guessing, use 0.5-0.7. If you're confident based on
   strong metrics, use 0.8-0.95.

4. justification MUST reference real metrics or observations. Examples:
   ✅ "CPU has averaged 32% over 30 days, well below the 40% target"
   ❌ "This might be overconfigured"
   ✅ "Cross-AZ traffic costs $45/mo; VPC endpoint would eliminate this"
   ❌ "Could save money"

5. estimated_savings_approx is OPTIONAL and should be conservative or omitted.
   The engine will validate it. Do NOT invent a number if unsure.

6. category helps group recs. Choose from:
   - right-sizing, waste-elimination, scheduling, storage-optimization,
     network-optimization, capacity-planning, configuration, performance

VALIDATION FLOW:
=================

After you output LLM proposals:

1. Engine extracts your JSON
2. For each proposal:
   a) Looks up resource in graph
   b) Re-extracts metrics (CPU, IOPS, P95 latency, cost, etc.)
   c) Checks if metrics meet thresholds for the action
   d) If YES: promotes to engine_backed, validation_status=validated
   e) If NO: keeps as llm_proposed, validation_status=rejected (becomes "idea only")

3. If your proposal conflicts with an engine-backed rec on the same resource:
   Engine always wins. Your proposal gets marked downgraded=true

Example Validation:
  Your proposal: rightsize_ec2 on resource X with llm_confidence=0.8
  Engine re-checks: CPU=38%, which is <40% threshold ✅
  Result: VALIDATED → promoted to engine_backed ✅

  Your proposal: add_vpc_endpoint on resource Y with justification
  Engine re-checks: No cross-AZ traffic detected ❌
  Result: REJECTED → stays as idea_only (can be shown in "AI Ideas" tab)

CLUSTERING & GROUPING:
=======================

When you propose multiple recs, you can group them by theme:

"All dev EC2 instances idle clean-up campaign" →
  - terminate_ec2 on dev-app-1
  - terminate_ec2 on dev-app-2
  - terminate_ec2 on dev-worker-3

"RDS multi-AZ cleanup (non-prod)" →
  - disable_multi_az on staging-db-1
  - disable_multi_az on staging-db-2

"Storage optimization wave" →
  - ebs_migrate_gp2_to_gp3 on ebs-volume-1
  - s3_add_lifecycle on s3-bucket-main
  - s3_enable_intelligent_tiering on s3-bucket-archive

When grouped, the engine treats them as a cohesive campaign and can
prioritize/bundle them for the user.

UI PRESENTATION:
=================

Frontend will show two tabs:

  TAB 1: Validated Recommendations (engine_backed=true)
    - Show with engine_confidence
    - Action/savings are engine-verified
    - Ready to implement

  TAB 2: AI-Suggested Ideas (llm_proposed, not yet validated)
    - Show with llm_confidence
    - Why it was rejected (validation_notes)
    - User can review and potentially implement anyway
    - Helps catch blind spots the engine might miss

Good luck! You have 20 allowed actions and finops metrics. Be specific, cite metrics, and let the engine do the validation.
"""

# Quick reference table for thresholds
ENGINE_THRESHOLDS_REFERENCE = {
    "rightsize_ec2": {
        "threshold": "P95 CPU < 40%",
        "period": "30 days",
        "confidence": "Very high - tight constraint"
    },
    "terminate_ec2": {
        "threshold": "P95 CPU < 5%, low network I/O",
        "period": "14 days",
        "confidence": "Very high - strong idle signal"
    },
    "rightsize_rds": {
        "threshold": "P95 CPU < 40%, Freeable memory > 30%",
        "period": "30 days",
        "confidence": "Very high"
    },
    "disable_multi_az": {
        "threshold": "Non-production environment",
        "period": "Any",
        "confidence": "High - RTO/RPO lower in non-prod"
    },
    "rightsize_elasticache": {
        "threshold": "Memory utilization < 50%",
        "period": "30 days",
        "confidence": "High"
    },
    "s3_add_lifecycle": {
        "threshold": "No lifecycle policy exists",
        "period": "One-time",
        "confidence": "High - standard practice"
    },
    "add_vpc_endpoint": {
        "threshold": "Cross-AZ traffic detected",
        "period": "Ongoing",
        "confidence": "Medium - depends on access patterns"
    },
}

print(__doc__)

__all__ = [
    "LLM_OUTPUT_SCHEMA",
    "ENGINE_THRESHOLDS_REFERENCE",
]
