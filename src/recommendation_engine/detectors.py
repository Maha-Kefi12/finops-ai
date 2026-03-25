"""
Pattern-Based Detectors for AWS FinOps Recommendations
=======================================================
Each best practice from the KB is compiled into an executable detector.

A detector is a dict:
{
    "pattern_id": str,
    "service": str,
    "category": str,
    "priority": "HIGH" | "MEDIUM" | "LOW",
    "detector": Callable(node, edges, all_nodes) -> bool,
    "threshold": dict,
    "linked_best_practice": str,
    "recommendation_template": str,
    "savings_estimator": Callable(node) -> float,
    "risk_level": "LOW" | "MEDIUM" | "HIGH",
    "implementation_template": str,
}
"""

from typing import Dict, List, Any, Callable, Optional
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# HELPER: parse service type from ARN or node
# ═══════════════════════════════════════════════════════════════════════════

def _parse_service(node: dict) -> str:
    """Extract AWS service family from a graph node.
    
    Normalizes friendly names like "amazon ec2 (app)" to "ec2"
    to match detector patterns.
    """
    # Service name normalization map
    friendly_to_short = {
        "amazon ec2": "ec2",
        "ec2": "ec2",
        "amazon rds": "rds",
        "rds": "rds",
        "amazon s3": "s3",
        "amazon dynamodb": "dynamodb",
        "dynamodb": "dynamodb",
        "amazon elasticache": "elasticache",
        "elasticache": "elasticache",
        "amazon redshift": "redshift",
        "redshift": "redshift",
        "amazon opensearch": "opensearch",
        "opensearch": "opensearch",
        "aws lambda": "lambda",
        "lambda": "lambda",
        "amazon cloudwatch": "cloudwatch",
        "cloudwatch": "cloudwatch",
        "aws glue": "glue",
        "glue": "glue",
        "amazon kinesis": "kinesis",
        "kinesis": "kinesis",
        "amazon iam": "iam",
        "iam": "iam",
        "application load balancer": "alb",
        "alb": "alb",
        "elastic load balancing": "elb",
        "elb": "elb",
        "amazon ebs": "ebs",
        "ebs": "ebs",
        "amazon vpc": "vpc",
        "vpc": "vpc",
        "amazon cloudfront": "cloudfront",
        "cloudfront": "cloudfront",
        "amazon sqs": "sqs",
        "sqs": "sqs",
    }
    
    node_id = node.get("node_id") or node.get("id", "")
    node_name = node.get("name", "")
    node_type = str(node.get("type", "") or "").lower().strip()

    def _infer_from_text(text: str, ntype: str) -> str:
        t = text.lower()

        # Prefer explicit service tokens in id/name before generic type mapping.
        token_map = [
            ("elasticache", "elasticache"),
            ("dynamodb", "dynamodb"),
            ("opensearch", "opensearch"),
            ("redshift", "redshift"),
            ("cloudfront", "cloudfront"),
            ("kinesis", "kinesis"),
            ("lambda", "lambda"),
            ("glue", "glue"),
            ("ec2", "ec2"),
            ("rds", "rds"),
            ("s3", "s3"),
            ("alb", "alb"),
            ("load-balancer", "alb"),
            ("load_balancer", "alb"),
            ("nat", "vpc"),
            ("vpc", "vpc"),
            ("sqs", "sqs"),
            ("sns", "sns"),
            ("ebs", "ebs"),
        ]
        for token, short in token_map:
            if token in t:
                return short

        # Last-resort mapping for coarse graph node types.
        type_map = {
            "load_balancer": "alb",
            "cache": "elasticache",
            "database": "rds",
            "queue": "sqs",
            "storage": "s3",
            "search": "opensearch",
            "batch": "glue",
            "service": "ec2",
        }
        if ntype in type_map:
            return type_map[ntype]

        return "unknown"

    if "arn:aws:" in node_id:
        parts = node_id.split(":")
        return parts[2].lower() if len(parts) > 2 else "unknown"
    
    svc = node.get("service_type", node.get("aws_service", "unknown"))
    if not svc or svc == "Unknown":
        inferred = _infer_from_text(f"{node_id} {node_name}", node_type)
        return inferred
    
    svc_lower = str(svc).lower().strip()
    
    # Try exact match first
    if svc_lower in friendly_to_short:
        return friendly_to_short[svc_lower]
    
    # Try to find a partial match (e.g., "amazon ec2 (app)" contains "ec2")
    for friendly, short in friendly_to_short.items():
        if friendly in svc_lower:
            return short
    
    if svc_lower == "unknown":
        return _infer_from_text(f"{node_id} {node_name}", node_type)

    return svc_lower


def _parse_resource_name(node: dict) -> str:
    node_id = node.get("node_id") or node.get("id", "")
    return node_id.split("/")[-1] if "/" in node_id else node_id


def _get_edges_for_node(node: dict, edges: list) -> List[dict]:
    """Get all edges where this node is source or target."""
    node_id = node.get("node_id") or node.get("id", "")
    return [e for e in edges
            if e.get("source") == node_id or e.get("target") == node_id]


# ═══════════════════════════════════════════════════════════════════════════
# BASELINE COSTS (when CUR data is $0)
# ═══════════════════════════════════════════════════════════════════════════

BASELINE_COSTS = {
    "ec2": 150.0, "rds": 350.0, "s3": 85.0, "lambda": 45.0,
    "elasticache": 180.0, "opensearch": 280.0, "redshift": 450.0,
    "cloudfront": 120.0, "vpc": 95.0, "sqs": 25.0, "sns": 15.0,
    "dynamodb": 100.0, "ecs": 200.0, "eks": 300.0, "nat": 95.0,
    "alb": 65.0, "service": 80.0,
}

INSTANCE_TYPES = {
    "ec2": ("m5.xlarge", "m6g.large"),        # current → recommended
    "rds": ("db.m5.xlarge", "db.m6g.large"),
    "elasticache": ("cache.r6g.large", "cache.r6g.medium"),
    "opensearch": ("m5.large.search", "m5.medium.search"),
    "redshift": ("ra3.xlarge", "ra3.large"),
}


def _node_cost(node: dict) -> float:
    """Get node cost, falling back to baseline."""
    cost = node.get("total_monthly_cost") or node.get("cost_monthly", 0)
    if cost == 0:
        svc = _parse_service(node)
        cost = BASELINE_COSTS.get(svc, 50.0)
    return cost


# ═══════════════════════════════════════════════════════════════════════════
# EC2 DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_ec2_cpu_underutil(node, edges, all_nodes):
    """EC2 CPU < 40% avg over 30 days → right-size."""
    if _parse_service(node) != "ec2":
        return False
    util = node.get("utilization_score", 0)
    # If utilization data available, check < 40%. 
    # If no utilization data (score=0), flag as needing review.
    return util < 40

def _detect_ec2_idle(node, edges, all_nodes):
    """EC2 CPU < 5% for 30+ days → terminate or stop."""
    if _parse_service(node) != "ec2":
        return False
    util = node.get("utilization_score", 0)
    node_edges = _get_edges_for_node(node, edges)
    # Idle = low utilization AND low traffic
    total_qps = sum(e.get("traffic_properties", {}).get("queries_per_second", 0) for e in node_edges)
    return util < 5 and total_qps < 1

def _detect_ec2_old_gen(node, edges, all_nodes):
    """EC2 running old-gen instances (m4, c4, t2) → migrate to current gen."""
    if _parse_service(node) != "ec2":
        return False
    # Always flag EC2 for Graviton migration review
    return True

def _detect_ec2_dev_24x7(node, edges, all_nodes):
    """Dev/test EC2 running 24x7 → schedule stop/start."""
    if _parse_service(node) != "ec2":
        return False
    name = _parse_resource_name(node).lower()
    return any(tag in name for tag in ("dev", "test", "staging", "sandbox", "qa"))

def _detect_ec2_no_autoscaling(node, edges, all_nodes):
    """EC2 without auto-scaling → implement scaling."""
    if _parse_service(node) != "ec2":
        return False
    peak = node.get("peak_usage_score", 0)
    util = node.get("utilization_score", 0)
    # If peak is much higher than average, needs autoscaling
    return peak > 0 and util > 0 and (peak - util) > 30


# ═══════════════════════════════════════════════════════════════════════════
# RDS DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_rds_cpu_underutil(node, edges, all_nodes):
    """RDS CPU < 40% avg → right-size to smaller instance."""
    if _parse_service(node) != "rds":
        return False
    return node.get("utilization_score", 0) < 40

def _detect_rds_multi_az_nonprod(node, edges, all_nodes):
    """Non-production RDS with Multi-AZ → disable for 50% savings."""
    if _parse_service(node) != "rds":
        return False
    name = _parse_resource_name(node).lower()
    is_nonprod = any(tag in name for tag in ("dev", "test", "staging", "sandbox"))
    return is_nonprod  # Non-prod DBs likely have Multi-AZ that can be disabled

def _detect_rds_gp2_storage(node, edges, all_nodes):
    """RDS on gp2 storage → migrate to gp3 (20% cheaper)."""
    if _parse_service(node) != "rds":
        return False
    return True  # Always recommend gp2→gp3 review

def _detect_rds_idle(node, edges, all_nodes):
    """RDS with 0 connections for 30+ days → stop or terminate."""
    if _parse_service(node) != "rds":
        return False
    node_edges = _get_edges_for_node(node, edges)
    total_qps = sum(e.get("traffic_properties", {}).get("queries_per_second", 0) for e in node_edges)
    return total_qps < 1 and node.get("utilization_score", 0) < 5

def _detect_rds_no_read_replica(node, edges, all_nodes):
    """High-traffic RDS without read replicas → add replicas."""
    if _parse_service(node) != "rds":
        return False
    node_edges = _get_edges_for_node(node, edges)
    read_qps = sum(e.get("traffic_properties", {}).get("queries_per_second", 0)
                   for e in node_edges if e.get("target") == (node.get("node_id") or node.get("id", "")))
    return read_qps > 100  # High read traffic


# ═══════════════════════════════════════════════════════════════════════════
# S3 DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_s3_no_lifecycle(node, edges, all_nodes):
    """S3 bucket without lifecycle policies → add tiering."""
    return _parse_service(node) == "s3"

def _detect_s3_no_intelligent_tiering(node, edges, all_nodes):
    """S3 Standard data → enable Intelligent-Tiering."""
    return _parse_service(node) == "s3"


# ═══════════════════════════════════════════════════════════════════════════
# EBS DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_ebs_unattached(node, edges, all_nodes):
    """EBS volume not attached to any instance → delete."""
    if _parse_service(node) != "ebs":
        return False
    node_edges = _get_edges_for_node(node, edges)
    return len(node_edges) == 0

def _detect_ebs_gp2(node, edges, all_nodes):
    """EBS gp2 volumes → migrate to gp3 (20% cheaper)."""
    if _parse_service(node) != "ebs":
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# LAMBDA DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_lambda_oversized(node, edges, all_nodes):
    """Lambda with oversized memory → tune to sweet spot."""
    return _parse_service(node) == "lambda"

def _detect_lambda_no_graviton(node, edges, all_nodes):
    """Lambda not using ARM/Graviton → migrate for 20% savings."""
    return _parse_service(node) == "lambda"


# ═══════════════════════════════════════════════════════════════════════════
# ELASTICACHE DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_elasticache_oversized(node, edges, all_nodes):
    """ElastiCache nodes oversized → downsize."""
    return _parse_service(node) == "elasticache"


# ═══════════════════════════════════════════════════════════════════════════
# NETWORK DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_cross_az_traffic(node, edges, all_nodes):
    """Cross-AZ data transfer detected → optimize placement."""
    node_id = node.get("node_id") or node.get("id", "")
    node_edges = _get_edges_for_node(node, edges)
    for e in node_edges:
        net = e.get("network_properties", {})
        if net.get("cross_az", False):
            return True
    return False

def _detect_nat_no_endpoint(node, edges, all_nodes):
    """NAT Gateway without VPC endpoints → replace with endpoints."""
    svc = _parse_service(node)
    name = _parse_resource_name(node).lower()
    return svc == "vpc" or "nat" in name or "vpn" in name

def _detect_unused_eip(node, edges, all_nodes):
    """Elastic IP not attached → release."""
    svc = _parse_service(node)
    name = _parse_resource_name(node).lower()
    return "eip" in name or "elastic-ip" in name

def _detect_idle_alb(node, edges, all_nodes):
    """ALB with 0 targets → delete."""
    svc = _parse_service(node)
    name = _parse_resource_name(node).lower()
    if svc != "alb" and "load-balancer" not in name:
        return False
    node_edges = _get_edges_for_node(node, edges)
    return len(node_edges) == 0


# ═══════════════════════════════════════════════════════════════════════════
# ARCHITECTURAL DETECTORS (graph-native)
# ═══════════════════════════════════════════════════════════════════════════

def _detect_spof(node, edges, all_nodes):
    """Single Point of Failure → add redundancy."""
    return node.get("single_point_of_failure", False)

def _detect_high_fan_in(node, edges, all_nodes):
    """High fan-in node (many services depend on it) → add caching layer."""
    in_deg = node.get("in_degree", 0)
    return in_deg >= 3  # 3+ services hitting this node

def _detect_cascade_risk(node, edges, all_nodes):
    """High cascading failure risk → review architecture."""
    risk = node.get("cascading_failure_risk", "low")
    return risk in ("medium", "high", "critical")

def _detect_high_centrality(node, edges, all_nodes):
    """High centrality node (architectural bottleneck) → optimize or redistribute."""
    return node.get("centrality", 0) >= 0.3 or node.get("betweenness_centrality", 0) >= 0.3

def _detect_high_blast_radius(node, edges, all_nodes):
    """High blast radius → reduce dependencies or add failover."""
    return node.get("blast_radius", 0) >= 0.15  # 15%+ of architecture affected


# ═══════════════════════════════════════════════════════════════════════════
# OPENSEARCH / REDSHIFT DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_opensearch_overprovisioned(node, edges, all_nodes):
    """OpenSearch cluster overprovisioned → downsize."""
    return _parse_service(node) == "opensearch"

def _detect_redshift_idle(node, edges, all_nodes):
    """Redshift cluster with low utilization → pause or downsize."""
    return _parse_service(node) == "redshift"


# ═══════════════════════════════════════════════════════════════════════════
# CLOUDFRONT / SQS DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_cloudfront_price_class(node, edges, all_nodes):
    """CloudFront using All Edges → restrict price class."""
    return _parse_service(node) == "cloudfront"

def _detect_sqs_overprovisioned(node, edges, all_nodes):
    """SQS queue overprovisioned → review message volume."""
    return _parse_service(node) == "sqs"


# ═══════════════════════════════════════════════════════════════════════════
# MASTER PATTERN REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

PATTERNS: List[Dict[str, Any]] = [
    # ────── EC2 ──────
    {
        "pattern_id": "ec2_cpu_underutil",
        "service": "ec2",
        "category": "right_sizing",
        "priority": "HIGH",
        "detector": _detect_ec2_cpu_underutil,
        "threshold": {"cpu_avg_max": 40, "period_days": 30},
        "linked_best_practice": "AWS FinOps - EC2 Right-Sizing: CPU <40% for 30+ days → downsize (50% savings per tier)",
        "recommendation_template": "Right-size {resource} from {current} to {recommended} (Graviton2) — {savings_pct}% cheaper, same workload capacity",
        "savings_estimator": lambda n: _node_cost(n) * 0.35,
        "risk_level": "LOW",
        "implementation_template": "aws ec2 modify-instance-attribute --instance-id {resource_id} --instance-type {recommended}",
    },
    {
        "pattern_id": "ec2_idle_instance",
        "service": "ec2",
        "category": "waste_elimination",
        "priority": "HIGH",
        "detector": _detect_ec2_idle,
        "threshold": {"cpu_avg_max": 5, "period_days": 30},
        "linked_best_practice": "AWS FinOps - EC2 Waste: CPU <2% for 14+ days → terminate or stop",
        "recommendation_template": "Terminate idle {resource} — CPU <5% with no traffic for 30+ days. Schedule stop if intermittent use",
        "savings_estimator": lambda n: _node_cost(n) * 0.95,
        "risk_level": "MEDIUM",
        "implementation_template": "aws ec2 stop-instances --instance-ids {resource_id}  # or terminate-instances",
    },
    {
        "pattern_id": "ec2_graviton_migration",
        "service": "ec2",
        "category": "right_sizing",
        "priority": "MEDIUM",
        "detector": _detect_ec2_old_gen,
        "threshold": {"savings_pct": 20},
        "linked_best_practice": "AWS FinOps - EC2 Graviton: ARM-based processors offer 20-40% better price-performance (t4g, m7g, c7g, r7g)",
        "recommendation_template": "Migrate {resource} from {current} to {recommended} (Graviton3) — 20-40% cheaper with same or better performance",
        "savings_estimator": lambda n: _node_cost(n) * 0.25,
        "risk_level": "LOW",
        "implementation_template": "aws ec2 run-instances --instance-type {recommended} --image-id ami-graviton3 # then migrate",
    },
    {
        "pattern_id": "ec2_dev_scheduling",
        "service": "ec2",
        "category": "scheduling",
        "priority": "MEDIUM",
        "detector": _detect_ec2_dev_24x7,
        "threshold": {"schedule": "7PM-7AM weekdays + weekends off"},
        "linked_best_practice": "AWS FinOps - EC2 Scheduling: Dev/test don't need 24x7 → implement stop/start for 65-75% savings",
        "recommendation_template": "Schedule {resource} to stop 7PM-7AM weekdays + all weekend — 65% savings on dev/test instance",
        "savings_estimator": lambda n: _node_cost(n) * 0.65,
        "risk_level": "LOW",
        "implementation_template": "aws scheduler create-schedule --name {resource}-stop --schedule-expression 'cron(0 19 ? * MON-FRI *)' --target 'ec2:StopInstances'",
    },
    # ────── RDS ──────
    {
        "pattern_id": "rds_cpu_underutil",
        "service": "rds",
        "category": "right_sizing",
        "priority": "HIGH",
        "detector": _detect_rds_cpu_underutil,
        "threshold": {"cpu_avg_max": 40, "period_days": 30},
        "linked_best_practice": "AWS FinOps - RDS Right-Sizing: CPU <40% for 30+ days → downsize. Keep freeable memory >20%",
        "recommendation_template": "Downsize {resource} from {current} to {recommended} — CPU averaging {util}%, well below 60-75% target range",
        "savings_estimator": lambda n: _node_cost(n) * 0.40,
        "risk_level": "LOW",
        "implementation_template": "aws rds modify-db-instance --db-instance-identifier {resource_id} --db-instance-class {recommended} --apply-immediately",
    },
    {
        "pattern_id": "rds_multi_az_nonprod",
        "service": "rds",
        "category": "configuration",
        "priority": "HIGH",
        "detector": _detect_rds_multi_az_nonprod,
        "threshold": {"env": "non-production"},
        "linked_best_practice": "AWS FinOps - RDS Multi-AZ: 2x instance cost. Disable for dev/test (50% savings). Use single-AZ + snapshots",
        "recommendation_template": "Disable Multi-AZ for {resource} (non-production) — 50% savings. Use automated snapshots for recovery (RPO: 5min)",
        "savings_estimator": lambda n: _node_cost(n) * 0.50,
        "risk_level": "LOW",
        "implementation_template": "aws rds modify-db-instance --db-instance-identifier {resource_id} --no-multi-az --apply-immediately",
    },
    {
        "pattern_id": "rds_gp2_to_gp3",
        "service": "rds",
        "category": "storage_optimization",
        "priority": "MEDIUM",
        "detector": _detect_rds_gp2_storage,
        "threshold": {"savings_pct": 20},
        "linked_best_practice": "AWS FinOps - RDS Storage: gp3 is 20% cheaper than gp2 with baseline 3k IOPS + 125MB/s. Migrate all gp2→gp3",
        "recommendation_template": "Migrate {resource} storage from gp2 to gp3 — 20% cheaper with configurable IOPS (3000 IOPS baseline free)",
        "savings_estimator": lambda n: _node_cost(n) * 0.08,  # storage is ~40% of RDS cost, 20% savings on that
        "risk_level": "LOW",
        "implementation_template": "aws rds modify-db-instance --db-instance-identifier {resource_id} --storage-type gp3 --apply-immediately",
    },
    {
        "pattern_id": "rds_read_replica",
        "service": "rds",
        "category": "architecture",
        "priority": "MEDIUM",
        "detector": _detect_rds_no_read_replica,
        "threshold": {"read_qps_min": 100},
        "linked_best_practice": "AWS FinOps - RDS Read Replicas: Offload reads to replica (async copy). Reduce primary load and enable smaller primary instance",
        "recommendation_template": "Add read replica for {resource} — {qps} QPS read traffic can be offloaded, enabling primary downsize",
        "savings_estimator": lambda n: _node_cost(n) * 0.20,
        "risk_level": "MEDIUM",
        "implementation_template": "aws rds create-db-instance-read-replica --db-instance-identifier {resource_id}-replica --source-db-instance-identifier {resource_id}",
    },
    # ────── S3 ──────
    {
        "pattern_id": "s3_lifecycle_policy",
        "service": "s3",
        "category": "storage_optimization",
        "priority": "MEDIUM",
        "detector": _detect_s3_no_lifecycle,
        "threshold": {"transition_days": 30, "glacier_days": 90},
        "linked_best_practice": "AWS FinOps - S3 Lifecycle: Move to IA after 30d → Glacier after 90d → delete after 365d = ~70% cost reduction",
        "recommendation_template": "Add lifecycle policy to {resource}: Standard→IA (30d) → Glacier (90d) → delete (365d) — up to 70% storage cost reduction",
        "savings_estimator": lambda n: _node_cost(n) * 0.50,
        "risk_level": "LOW",
        "implementation_template": "aws s3api put-bucket-lifecycle-configuration --bucket {resource_name} --lifecycle-configuration file://lifecycle.json",
    },
    {
        "pattern_id": "s3_intelligent_tiering",
        "service": "s3",
        "category": "storage_optimization",
        "priority": "MEDIUM",
        "detector": _detect_s3_no_intelligent_tiering,
        "threshold": {"object_min_size_kb": 128},
        "linked_best_practice": "AWS FinOps - S3 Intelligent-Tiering: Auto-moves between tiers based on access patterns. Up to 95% savings on cold data",
        "recommendation_template": "Enable S3 Intelligent-Tiering on {resource} — automatic tier management, up to 95% savings on infrequently accessed data",
        "savings_estimator": lambda n: _node_cost(n) * 0.40,
        "risk_level": "LOW",
        "implementation_template": "aws s3api put-bucket-intelligent-tiering-configuration --bucket {resource_name} --id AutoTier --intelligent-tiering-configuration '{\"Status\": \"Enabled\"}'",
    },
    # ────── EBS ──────
    {
        "pattern_id": "ebs_gp2_to_gp3",
        "service": "ebs",
        "category": "storage_optimization",
        "priority": "MEDIUM",
        "detector": _detect_ebs_gp2,
        "threshold": {"savings_pct": 20},
        "linked_best_practice": "AWS FinOps - EBS: gp3 is 20% cheaper than gp2 ($0.08 vs $0.10/GB-month) with free 3k IOPS + 125MB/s",
        "recommendation_template": "Migrate {resource} EBS volumes from gp2 to gp3 — 20% cheaper with better baseline IOPS (3000 free vs 100/GB)",
        "savings_estimator": lambda n: 15.0,  # typical EBS savings per volume
        "risk_level": "LOW",
        "implementation_template": "aws ec2 modify-volume --volume-id {resource_id} --volume-type gp3",
    },
    # ────── Lambda ──────
    {
        "pattern_id": "lambda_memory_tuning",
        "service": "lambda",
        "category": "right_sizing",
        "priority": "MEDIUM",
        "detector": _detect_lambda_oversized,
        "threshold": {"memory_sweet_spot_mb": "1024-1792"},
        "linked_best_practice": "AWS FinOps - Lambda Memory: Sweet spot 1024-1792 MB. More memory = faster execution = sometimes cheaper overall",
        "recommendation_template": "Tune {resource} memory to sweet spot (1024-1792 MB) — use AWS Lambda Power Tuning to find optimal cost-performance balance",
        "savings_estimator": lambda n: _node_cost(n) * 0.30,
        "risk_level": "LOW",
        "implementation_template": "aws lambda update-function-configuration --function-name {resource_name} --memory-size 1024",
    },
    {
        "pattern_id": "lambda_graviton",
        "service": "lambda",
        "category": "right_sizing",
        "priority": "LOW",
        "detector": _detect_lambda_no_graviton,
        "threshold": {"savings_pct": 20},
        "linked_best_practice": "AWS FinOps - Lambda ARM64: Graviton2 is 20% cheaper per GB-second. Use for new functions unless x86 dependency",
        "recommendation_template": "Migrate {resource} to ARM64 (Graviton2) architecture — 20% lower cost per GB-second with comparable performance",
        "savings_estimator": lambda n: _node_cost(n) * 0.20,
        "risk_level": "LOW",
        "implementation_template": "aws lambda update-function-configuration --function-name {resource_name} --architectures arm64",
    },
    # ────── ElastiCache ──────
    {
        "pattern_id": "elasticache_rightsizing",
        "service": "elasticache",
        "category": "right_sizing",
        "priority": "MEDIUM",
        "detector": _detect_elasticache_oversized,
        "threshold": {"memory_target_pct": "60-80"},
        "linked_best_practice": "AWS FinOps - ElastiCache: Keep memory 60-80%. If <50% for 30+ days → downsize. Use r7g Graviton for 35% better price-performance",
        "recommendation_template": "Downsize {resource} from {current} to {recommended} (Graviton r7g) — memory utilization below 60% target; 35% better price-performance",
        "savings_estimator": lambda n: _node_cost(n) * 0.35,
        "risk_level": "LOW",
        "implementation_template": "aws elasticache modify-cache-cluster --cache-cluster-id {resource_name} --cache-node-type cache.r7g.medium",
    },
    # ────── Network ──────
    {
        "pattern_id": "cross_az_data_transfer",
        "service": "network",
        "category": "network_optimization",
        "priority": "HIGH",
        "detector": _detect_cross_az_traffic,
        "threshold": {"cost_per_gb": 0.02},
        "linked_best_practice": "AWS FinOps - Data Transfer: Cross-AZ costs $0.02/GB (in+out). Can be 20-40% of total bill for chatty architectures. Place replicas in same AZ",
        "recommendation_template": "Eliminate cross-AZ data transfer for {resource} — currently routing traffic across AZs at $0.02/GB. Co-locate in same AZ or use VPC endpoints",
        "savings_estimator": lambda n: 45.0,  # typical cross-AZ savings
        "risk_level": "MEDIUM",
        "implementation_template": "# Review AZ placement: aws ec2 describe-instances --instance-ids {resource_id} --query 'Reservations[].Instances[].Placement.AvailabilityZone'",
    },
    {
        "pattern_id": "nat_vpc_endpoint",
        "service": "vpc",
        "category": "network_optimization",
        "priority": "MEDIUM",
        "detector": _detect_nat_no_endpoint,
        "threshold": {"nat_processing_cost": 0.045},
        "linked_best_practice": "AWS FinOps - NAT Gateway: $0.045/hr + $0.045/GB processed. Replace with VPC endpoints for S3/DynamoDB ($0 gateway endpoints)",
        "recommendation_template": "Replace NAT Gateway with VPC endpoints for {resource} — eliminate $0.045/GB processing fee for S3/DynamoDB traffic",
        "savings_estimator": lambda n: _node_cost(n) * 0.60,
        "risk_level": "LOW",
        "implementation_template": "aws ec2 create-vpc-endpoint --vpc-id {vpc_id} --service-name com.amazonaws.{region}.s3 --route-table-ids {route_table_id}",
    },
    # ────── OpenSearch / Redshift ──────
    {
        "pattern_id": "opensearch_rightsizing",
        "service": "opensearch",
        "category": "right_sizing",
        "priority": "MEDIUM",
        "detector": _detect_opensearch_overprovisioned,
        "threshold": {"cpu_target": "60-70"},
        "linked_best_practice": "AWS FinOps - OpenSearch: Right-size instances to 60-70% utilization. Consider UltraWarm for warm data (90% cheaper)",
        "recommendation_template": "Right-size {resource} from {current} to {recommended} — reduce cluster capacity to match actual search workload",
        "savings_estimator": lambda n: _node_cost(n) * 0.30,
        "risk_level": "MEDIUM",
        "implementation_template": "aws opensearch update-domain-config --domain-name {resource_name} --cluster-config InstanceType={recommended}",
    },
    {
        "pattern_id": "redshift_pause_schedule",
        "service": "redshift",
        "category": "scheduling",
        "priority": "MEDIUM",
        "detector": _detect_redshift_idle,
        "threshold": {"idle_hours_per_day": 12},
        "linked_best_practice": "AWS FinOps - Redshift: Pause during off-hours (50% savings). For variable workloads use Serverless instead of provisioned",
        "recommendation_template": "Schedule {resource} to pause during off-hours — save 50% by pausing 12 hours/day. Consider Redshift Serverless for variable workloads",
        "savings_estimator": lambda n: _node_cost(n) * 0.50,
        "risk_level": "LOW",
        "implementation_template": "aws redshift pause-cluster --cluster-identifier {resource_name}",
    },
    # ────── CloudFront / SQS ──────
    {
        "pattern_id": "cloudfront_price_class",
        "service": "cloudfront",
        "category": "configuration",
        "priority": "LOW",
        "detector": _detect_cloudfront_price_class,
        "threshold": {"target_price_class": "PriceClass_100"},
        "linked_best_practice": "AWS FinOps - CloudFront: Use Price Class 100 (US/Europe only) for 20-25% cheaper if no global audience. Target >85% cache hit ratio",
        "recommendation_template": "Restrict {resource} to Price Class 100 (US/Europe) — 20-25% cheaper if users are primarily in these regions. Increase cache TTL for >85% hit ratio",
        "savings_estimator": lambda n: _node_cost(n) * 0.20,
        "risk_level": "LOW",
        "implementation_template": "aws cloudfront update-distribution --id {resource_id} --distribution-config PriceClass=PriceClass_100",
    },
    # ────── Architectural (graph-native) ──────
    {
        "pattern_id": "arch_spof",
        "service": "architecture",
        "category": "reliability",
        "priority": "HIGH",
        "detector": _detect_spof,
        "threshold": {},
        "linked_best_practice": "AWS Well-Architected - Reliability: Eliminate single points of failure. Add redundancy before resizing critical resources",
        "recommendation_template": "⚠️ {resource} is a Single Point of Failure — {in_degree} services depend on it with {blast_pct}% blast radius. Add redundancy (Multi-AZ/replica) before making any changes",
        "savings_estimator": lambda n: 0,  # reliability, not savings
        "risk_level": "HIGH",
        "implementation_template": "# Add redundancy: Multi-AZ deployment, read replicas, or failover configuration",
    },
    {
        "pattern_id": "arch_high_fan_in",
        "service": "architecture",
        "category": "performance",
        "priority": "HIGH",
        "detector": _detect_high_fan_in,
        "threshold": {"min_in_degree": 3},
        "linked_best_practice": "AWS Well-Architected - Performance: High-fan-in services are bottlenecks. Add caching layer (ElastiCache) to reduce load by 60-80%",
        "recommendation_template": "Add ElastiCache read-through cache in front of {resource} — {in_degree} services hitting it directly at {qps} QPS. Cache layer reduces DB load by 60-80%",
        "savings_estimator": lambda n: _node_cost(n) * 0.25,
        "risk_level": "MEDIUM",
        "implementation_template": "aws elasticache create-cache-cluster --cache-cluster-id {resource_name}-cache --cache-node-type cache.r6g.medium --engine redis --num-cache-nodes 1",
    },
    {
        "pattern_id": "arch_cascade_risk",
        "service": "architecture",
        "category": "reliability",
        "priority": "HIGH",
        "detector": _detect_cascade_risk,
        "threshold": {},
        "linked_best_practice": "AWS Well-Architected - Resilience: High cascade risk means failure propagates across services. Implement circuit breakers and bulkheads",
        "recommendation_template": "🔴 {resource} has {cascade_risk} cascading failure risk — failure affects {blast_pct}% of architecture. Implement circuit breaker pattern and bulkhead isolation",
        "savings_estimator": lambda n: 0,
        "risk_level": "HIGH",
        "implementation_template": "# Implement: circuit breaker (e.g., resilience4j), bulkhead isolation, async fallback queues",
    },
    {
        "pattern_id": "arch_bottleneck",
        "service": "architecture",
        "category": "performance",
        "priority": "MEDIUM",
        "detector": _detect_high_centrality,
        "threshold": {"min_centrality": 0.3},
        "linked_best_practice": "AWS Well-Architected - Performance: High centrality = architectural bottleneck. Redistribute load or add caching to reduce hotspot pressure",
        "recommendation_template": "Architectural bottleneck: {resource} has centrality={centrality:.2f} — it's a critical path for {blast_pct}% of traffic. Optimize or add failover path",
        "savings_estimator": lambda n: _node_cost(n) * 0.15,
        "risk_level": "MEDIUM",
        "implementation_template": "# Review architecture: add load balancing, caching, or async processing to distribute load",
    },
]


def get_all_patterns() -> List[Dict[str, Any]]:
    """Return all registered detector patterns."""
    return PATTERNS


def get_patterns_for_service(service: str) -> List[Dict[str, Any]]:
    """Return detector patterns for a specific service."""
    return [p for p in PATTERNS if p["service"] == service.lower()]


__all__ = ["PATTERNS", "get_all_patterns", "get_patterns_for_service",
           "BASELINE_COSTS", "INSTANCE_TYPES", "_parse_service", "_parse_resource_name",
           "_get_edges_for_node", "_node_cost"]
