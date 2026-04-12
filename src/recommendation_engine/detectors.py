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
            ("athena", "athena"),
            ("emr", "emr"),
            ("sagemaker", "sagemaker"),
            ("step-function", "states"),
            ("stepfunction", "states"),
            ("state-machine", "states"),
            ("api-gateway", "apigateway"),
            ("apigateway", "apigateway"),
            ("api_gateway", "apigateway"),
            ("eventbridge", "eventbridge"),
            ("eks", "eks"),
            ("ecs", "ecs"),
            ("fargate", "ecs"),
            ("ec2", "ec2"),
            ("rds", "rds"),
            ("aurora", "rds"),
            ("s3", "s3"),
            ("alb", "alb"),
            ("load-balancer", "alb"),
            ("load_balancer", "alb"),
            ("nat", "vpc"),
            ("vpc", "vpc"),
            ("sqs", "sqs"),
            ("sns", "sns"),
            ("ebs", "ebs"),
            ("cloudwatch", "cloudwatch"),
            ("waf", "waf"),
            ("guardduty", "guardduty"),
            ("config", "config"),
            ("route53", "route53"),
            ("kms", "kms"),
            ("secrets", "secretsmanager"),
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
    "alb": 65.0, "service": 80.0, "apigateway": 35.0, "kinesis": 55.0,
    "states": 30.0, "cloudwatch": 60.0, "glue": 80.0, "athena": 40.0,
    "emr": 250.0, "sagemaker": 350.0, "eventbridge": 10.0,
    "waf": 20.0, "guardduty": 15.0, "config": 10.0, "route53": 10.0,
    "kms": 5.0, "secretsmanager": 8.0,
}

INSTANCE_TYPES = {
    "ec2": ("m5.xlarge", "m6g.large"),        # current → recommended
    "rds": ("db.m5.xlarge", "db.m6g.large"),
    "elasticache": ("cache.r6g.large", "cache.r6g.medium"),
    "opensearch": ("m5.large.search", "m5.medium.search"),
    "redshift": ("ra3.xlarge", "ra3.large"),
    "ecs": ("Fargate-1vCPU-2GB", "Fargate-0.5vCPU-1GB"),
    "eks": ("m5.xlarge", "m7g.xlarge"),
    "dynamodb": ("On-Demand", "Provisioned"),
    "apigateway": ("REST-API", "HTTP-API"),
    "kinesis": ("4-shards", "2-shards"),
    "emr": ("m5.xlarge", "m7g.xlarge"),
    "sagemaker": ("ml.m5.xlarge", "ml.m7g.xlarge"),
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
# ECS DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_ecs_fargate_spot(node, edges, all_nodes):
    """ECS Fargate task in dev/test → use Fargate Spot (70% savings)."""
    svc = _parse_service(node)
    if svc not in ("ecs", "fargate"):
        return False
    name = _parse_resource_name(node).lower()
    return any(tag in name for tag in ("dev", "test", "staging", "sandbox", "qa"))

def _detect_ecs_idle_service(node, edges, all_nodes):
    """ECS service with 0 traffic → candidate for deletion."""
    svc = _parse_service(node)
    if svc not in ("ecs", "fargate"):
        return False
    node_edges = _get_edges_for_node(node, edges)
    total_qps = sum(e.get("traffic_properties", {}).get("queries_per_second", 0) for e in node_edges)
    return total_qps < 1 and node.get("utilization_score", 0) < 5

def _detect_ecs_graviton(node, edges, all_nodes):
    """ECS task not on Graviton → migrate for 20% savings."""
    svc = _parse_service(node)
    return svc in ("ecs", "fargate")

def _detect_ecs_overprovisioned(node, edges, all_nodes):
    """ECS task/service with low CPU/memory utilization → right-size."""
    svc = _parse_service(node)
    if svc not in ("ecs", "fargate"):
        return False
    return node.get("utilization_score", 0) < 40


# ═══════════════════════════════════════════════════════════════════════════
# EKS DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_eks_node_underutil(node, edges, all_nodes):
    """EKS node group with <50% utilization → downsize or consolidate."""
    if _parse_service(node) != "eks":
        return False
    return node.get("utilization_score", 0) < 50

def _detect_eks_idle_cluster(node, edges, all_nodes):
    """EKS cluster with minimal workload → consolidate or delete ($73/mo control plane)."""
    if _parse_service(node) != "eks":
        return False
    node_edges = _get_edges_for_node(node, edges)
    return len(node_edges) < 2

def _detect_eks_no_spot(node, edges, all_nodes):
    """EKS worker nodes all On-Demand → use Spot for stateless workloads (70% savings)."""
    if _parse_service(node) != "eks":
        return False
    return True  # Always recommend Spot review for EKS

def _detect_eks_dev_scheduling(node, edges, all_nodes):
    """EKS dev/staging cluster running 24x7 → schedule scale-down (65% savings)."""
    if _parse_service(node) != "eks":
        return False
    name = _parse_resource_name(node).lower()
    return any(tag in name for tag in ("dev", "test", "staging", "sandbox", "qa"))


# ═══════════════════════════════════════════════════════════════════════════
# DYNAMODB DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_dynamodb_on_demand(node, edges, all_nodes):
    """DynamoDB in On-Demand mode for steady traffic → switch to Provisioned (60-85% cheaper)."""
    if _parse_service(node) != "dynamodb":
        return False
    return True  # Always recommend capacity mode review

def _detect_dynamodb_no_ttl(node, edges, all_nodes):
    """DynamoDB table without TTL → enable to auto-delete expired items."""
    if _parse_service(node) != "dynamodb":
        return False
    return True  # Always recommend TTL review

def _detect_dynamodb_no_ia(node, edges, all_nodes):
    """DynamoDB table without Standard-IA storage class → 60% cheaper storage."""
    if _parse_service(node) != "dynamodb":
        return False
    return True


# ═══════════════════════════════════════════════════════════════════════════
# API GATEWAY DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_apigw_rest_to_http(node, edges, all_nodes):
    """API Gateway REST API → migrate to HTTP API (71% cheaper)."""
    svc = _parse_service(node)
    name = _parse_resource_name(node).lower()
    return svc == "apigateway" or "api-gateway" in name or "apigateway" in name or "api_gateway" in name

def _detect_apigw_no_cache(node, edges, all_nodes):
    """API Gateway without caching → enable for read-heavy endpoints."""
    svc = _parse_service(node)
    name = _parse_resource_name(node).lower()
    if svc != "apigateway" and "api-gateway" not in name and "apigateway" not in name:
        return False
    node_edges = _get_edges_for_node(node, edges)
    read_qps = sum(e.get("traffic_properties", {}).get("queries_per_second", 0)
                   for e in node_edges if e.get("target") == (node.get("node_id") or node.get("id", "")))
    return read_qps > 50


# ═══════════════════════════════════════════════════════════════════════════
# KINESIS / CLOUDWATCH / STEP FUNCTIONS DETECTORS
# ═══════════════════════════════════════════════════════════════════════════

def _detect_kinesis_over_sharded(node, edges, all_nodes):
    """Kinesis stream with too many shards → reduce ($11/shard/month)."""
    svc = _parse_service(node)
    return svc == "kinesis"

def _detect_cloudwatch_log_retention(node, edges, all_nodes):
    """CloudWatch log groups without retention → set retention (biggest CW cost driver)."""
    svc = _parse_service(node)
    return svc == "cloudwatch"

def _detect_step_functions_standard(node, edges, all_nodes):
    """Step Functions Standard workflows for high-volume → migrate to Express (90% savings)."""
    svc = _parse_service(node)
    name = _parse_resource_name(node).lower()
    return svc == "states" or "step-function" in name or "stepfunction" in name or "state-machine" in name


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
    # ────── ECS/Fargate ──────
    {
        "pattern_id": "ecs_fargate_spot",
        "service": "ecs",
        "category": "purchasing",
        "priority": "MEDIUM",
        "detector": _detect_ecs_fargate_spot,
        "threshold": {"env": "non-production"},
        "linked_best_practice": "AWS FinOps - ECS Fargate Spot: 70% discount for fault-tolerant/dev workloads. Use Spot capacity providers for non-critical tasks",
        "recommendation_template": "Switch {resource} to Fargate Spot — 70% savings for dev/test ECS tasks. Configure capacity provider with Spot base",
        "savings_estimator": lambda n: _node_cost(n) * 0.70,
        "risk_level": "LOW",
        "implementation_template": "aws ecs put-cluster-capacity-providers --cluster {resource_name} --capacity-providers FARGATE_SPOT --default-capacity-provider-strategy capacityProvider=FARGATE_SPOT,weight=1",
    },
    {
        "pattern_id": "ecs_idle_service",
        "service": "ecs",
        "category": "waste_elimination",
        "priority": "HIGH",
        "detector": _detect_ecs_idle_service,
        "threshold": {"traffic_min_qps": 1, "util_max": 5},
        "linked_best_practice": "AWS FinOps - ECS Waste: Services with 0 traffic and <5% utilization for 14+ days should be deleted or scaled to 0",
        "recommendation_template": "Delete idle ECS service {resource} — 0 traffic and <5% utilization. Scale desiredCount to 0 or delete entirely",
        "savings_estimator": lambda n: _node_cost(n) * 0.95,
        "risk_level": "MEDIUM",
        "implementation_template": "aws ecs update-service --cluster {cluster} --service {resource_name} --desired-count 0",
    },
    {
        "pattern_id": "ecs_graviton_migration",
        "service": "ecs",
        "category": "right_sizing",
        "priority": "MEDIUM",
        "detector": _detect_ecs_graviton,
        "threshold": {"savings_pct": 20},
        "linked_best_practice": "AWS FinOps - ECS Graviton: ARM-based Fargate/EC2 tasks are 20% cheaper. Use Graviton for all new ECS task definitions",
        "recommendation_template": "Migrate {resource} to Graviton (ARM64) — 20% cheaper compute. Update task definition CPU architecture to ARM64",
        "savings_estimator": lambda n: _node_cost(n) * 0.20,
        "risk_level": "LOW",
        "implementation_template": "aws ecs register-task-definition --family {resource_name} --runtime-platform cpuArchitecture=ARM64,operatingSystemFamily=LINUX",
    },
    {
        "pattern_id": "ecs_overprovisioned",
        "service": "ecs",
        "category": "right_sizing",
        "priority": "HIGH",
        "detector": _detect_ecs_overprovisioned,
        "threshold": {"util_max": 40},
        "linked_best_practice": "AWS FinOps - ECS Right-Sizing: Monitor CPU/memory via Container Insights. Target 60-70% utilization. Below 40% = over-provisioned",
        "recommendation_template": "Right-size {resource} task CPU/memory — utilization below 40%. Reduce task definition CPU/memory allocation to match actual usage",
        "savings_estimator": lambda n: _node_cost(n) * 0.40,
        "risk_level": "LOW",
        "implementation_template": "aws ecs register-task-definition --family {resource_name} --cpu {recommended_cpu} --memory {recommended_memory}",
    },
    # ────── EKS ──────
    {
        "pattern_id": "eks_node_underutil",
        "service": "eks",
        "category": "right_sizing",
        "priority": "HIGH",
        "detector": _detect_eks_node_underutil,
        "threshold": {"util_max": 50},
        "linked_best_practice": "AWS FinOps - EKS Node Sizing: Target 65-80% CPU/memory allocation. Below 50% = over-provisioned. Use Karpenter for automatic right-sizing",
        "recommendation_template": "Consolidate {resource} EKS nodes — utilization below 50%. Use Karpenter for automatic bin-packing or downsize node group instance type",
        "savings_estimator": lambda n: _node_cost(n) * 0.35,
        "risk_level": "MEDIUM",
        "implementation_template": "aws eks update-nodegroup-config --cluster-name {cluster} --nodegroup-name {resource_name} --scaling-config minSize=1,maxSize=3,desiredSize=2",
    },
    {
        "pattern_id": "eks_idle_cluster",
        "service": "eks",
        "category": "waste_elimination",
        "priority": "HIGH",
        "detector": _detect_eks_idle_cluster,
        "threshold": {"min_workload_edges": 2},
        "linked_best_practice": "AWS FinOps - EKS Waste: Each cluster costs $73/month control plane minimum. Consolidate workloads to fewer clusters",
        "recommendation_template": "Consolidate or delete idle EKS cluster {resource} — $73/month control plane with minimal workloads. Merge into another cluster",
        "savings_estimator": lambda n: 73.0 + _node_cost(n) * 0.50,
        "risk_level": "HIGH",
        "implementation_template": "aws eks delete-cluster --name {resource_name}  # After migrating workloads",
    },
    {
        "pattern_id": "eks_spot_nodes",
        "service": "eks",
        "category": "purchasing",
        "priority": "MEDIUM",
        "detector": _detect_eks_no_spot,
        "threshold": {"savings_pct": 70},
        "linked_best_practice": "AWS FinOps - EKS Spot: Use Spot for stateless workloads (70% savings). Diversify across 10+ instance types. Use Karpenter for automatic Spot management",
        "recommendation_template": "Add Spot instances to {resource} node groups — 70% savings for stateless workloads. Configure pod disruption budgets and diversify instance types",
        "savings_estimator": lambda n: _node_cost(n) * 0.40,
        "risk_level": "MEDIUM",
        "implementation_template": "aws eks create-nodegroup --cluster-name {cluster} --nodegroup-name {resource_name}-spot --capacity-type SPOT --instance-types m7g.xlarge m6i.xlarge c7g.xlarge",
    },
    {
        "pattern_id": "eks_dev_scheduling",
        "service": "eks",
        "category": "scheduling",
        "priority": "MEDIUM",
        "detector": _detect_eks_dev_scheduling,
        "threshold": {"schedule": "Scale down after hours"},
        "linked_best_practice": "AWS FinOps - EKS Scheduling: Dev/staging clusters running 24x7 waste 65% of compute. Schedule node scale-down after business hours",
        "recommendation_template": "Schedule {resource} EKS dev/staging to scale down after hours — 65% savings. Use Karpenter or CronJob to scale nodes to 0 off-hours",
        "savings_estimator": lambda n: _node_cost(n) * 0.65,
        "risk_level": "LOW",
        "implementation_template": "kubectl apply -f cronjob-scale-down.yaml  # Scale node group to 0 at 7PM, back up at 7AM",
    },
    # ────── DynamoDB ──────
    {
        "pattern_id": "dynamodb_capacity_mode",
        "service": "dynamodb",
        "category": "configuration",
        "priority": "HIGH",
        "detector": _detect_dynamodb_on_demand,
        "threshold": {"steady_state_days": 30},
        "linked_best_practice": "AWS FinOps - DynamoDB Capacity: On-Demand is 5-7x more expensive for steady workloads. Switch to Provisioned after 30 days of stable traffic",
        "recommendation_template": "Switch {resource} from On-Demand to Provisioned capacity — 60-85% savings for steady-state workloads. Monitor ConsumedReadCapacityUnits first",
        "savings_estimator": lambda n: _node_cost(n) * 0.60,
        "risk_level": "MEDIUM",
        "implementation_template": "aws dynamodb update-table --table-name {resource_name} --billing-mode PROVISIONED --provisioned-throughput ReadCapacityUnits=100,WriteCapacityUnits=50",
    },
    {
        "pattern_id": "dynamodb_ttl",
        "service": "dynamodb",
        "category": "waste_elimination",
        "priority": "MEDIUM",
        "detector": _detect_dynamodb_no_ttl,
        "threshold": {},
        "linked_best_practice": "AWS FinOps - DynamoDB TTL: Auto-delete expired items (sessions, logs, temp data) at no cost. Reduces storage and RCU/WCU consumption",
        "recommendation_template": "Enable TTL on {resource} — auto-delete expired items at no cost. Reduces storage ($0.25/GB) and capacity consumption",
        "savings_estimator": lambda n: _node_cost(n) * 0.15,
        "risk_level": "LOW",
        "implementation_template": "aws dynamodb update-time-to-live --table-name {resource_name} --time-to-live-specification Enabled=true,AttributeName=ttl",
    },
    {
        "pattern_id": "dynamodb_standard_ia",
        "service": "dynamodb",
        "category": "storage_optimization",
        "priority": "MEDIUM",
        "detector": _detect_dynamodb_no_ia,
        "threshold": {"cold_data_pct": 80},
        "linked_best_practice": "AWS FinOps - DynamoDB Standard-IA: 60% cheaper storage ($0.10 vs $0.25/GB). Enable for tables with >80% cold data",
        "recommendation_template": "Enable Standard-IA storage class on {resource} — 60% cheaper storage for infrequently accessed data. Items auto-move after 30 days inactivity",
        "savings_estimator": lambda n: _node_cost(n) * 0.25,
        "risk_level": "LOW",
        "implementation_template": "aws dynamodb update-table --table-name {resource_name} --table-class STANDARD_INFREQUENT_ACCESS",
    },
    # ────── API Gateway ──────
    {
        "pattern_id": "apigw_rest_to_http",
        "service": "apigateway",
        "category": "configuration",
        "priority": "MEDIUM",
        "detector": _detect_apigw_rest_to_http,
        "threshold": {"savings_pct": 71},
        "linked_best_practice": "AWS FinOps - API Gateway: HTTP API is 71% cheaper than REST API ($1 vs $3.50/million). Migrate unless you need REST-only features (WAF, caching, usage plans)",
        "recommendation_template": "Migrate {resource} from REST API to HTTP API — 71% cheaper ($1 vs $3.50/million requests). HTTP API supports Lambda proxy, JWT auth, CORS",
        "savings_estimator": lambda n: _node_cost(n) * 0.50,
        "risk_level": "MEDIUM",
        "implementation_template": "aws apigatewayv2 create-api --name {resource_name}-http --protocol-type HTTP --target {lambda_arn}",
    },
    {
        "pattern_id": "apigw_caching",
        "service": "apigateway",
        "category": "performance",
        "priority": "LOW",
        "detector": _detect_apigw_no_cache,
        "threshold": {"min_read_qps": 50},
        "linked_best_practice": "AWS FinOps - API Gateway Caching: Enable cache for GET endpoints to reduce Lambda invocations by 80-95%. 0.5GB cache = $14/month",
        "recommendation_template": "Enable API cache for {resource} — high read traffic ({qps} QPS). 0.5GB cache ($14/month) reduces backend invocations by 80-95%",
        "savings_estimator": lambda n: _node_cost(n) * 0.30,
        "risk_level": "LOW",
        "implementation_template": "aws apigateway update-stage --rest-api-id {api_id} --stage-name prod --patch-operations op=replace,path=/cacheClusterEnabled,value=true",
    },
    # ────── Kinesis ──────
    {
        "pattern_id": "kinesis_shard_rightsizing",
        "service": "kinesis",
        "category": "right_sizing",
        "priority": "MEDIUM",
        "detector": _detect_kinesis_over_sharded,
        "threshold": {"util_target": "60-80"},
        "linked_best_practice": "AWS FinOps - Kinesis: Each shard costs $11/month. Monitor IncomingBytes/IncomingRecords to right-size. Consider SQS for <1MB/s throughput",
        "recommendation_template": "Right-size {resource} Kinesis shards — each unused shard costs $11/month. Monitor IncomingBytes to find optimal shard count. Consider SQS if <1MB/s",
        "savings_estimator": lambda n: _node_cost(n) * 0.40,
        "risk_level": "MEDIUM",
        "implementation_template": "aws kinesis update-shard-count --stream-name {resource_name} --target-shard-count {optimal_count} --scaling-type UNIFORM_SCALING",
    },
    # ────── CloudWatch ──────
    {
        "pattern_id": "cloudwatch_log_retention",
        "service": "cloudwatch",
        "category": "waste_elimination",
        "priority": "HIGH",
        "detector": _detect_cloudwatch_log_retention,
        "threshold": {"retention_days": {"dev": 7, "staging": 30, "prod": 90}},
        "linked_best_practice": "AWS FinOps - CloudWatch Logs: Set retention policies (default is NEVER expire = infinite cost). $0.50/GB ingestion + $0.03/GB storage. Biggest CW cost driver",
        "recommendation_template": "Set log retention on {resource} — default 'never expire' accumulates infinite cost ($0.03/GB/month storage). Set 7d dev, 30d staging, 90d prod",
        "savings_estimator": lambda n: _node_cost(n) * 0.60,
        "risk_level": "LOW",
        "implementation_template": "aws logs put-retention-policy --log-group-name {resource_name} --retention-in-days 30",
    },
    # ────── Step Functions ──────
    {
        "pattern_id": "step_functions_express",
        "service": "stepfunctions",
        "category": "configuration",
        "priority": "MEDIUM",
        "detector": _detect_step_functions_standard,
        "threshold": {"daily_executions_min": 10000},
        "linked_best_practice": "AWS FinOps - Step Functions: Express Workflows are 80-90% cheaper than Standard for high-volume (<5min duration). $0.000001/request vs $0.025/1000 transitions",
        "recommendation_template": "Migrate {resource} from Standard to Express Workflow — 80-90% savings for high-volume, short-duration executions (<5 min)",
        "savings_estimator": lambda n: _node_cost(n) * 0.80,
        "risk_level": "MEDIUM",
        "implementation_template": "aws stepfunctions create-state-machine --name {resource_name}-express --type EXPRESS --definition file://state-machine.json --role-arn {role_arn}",
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
