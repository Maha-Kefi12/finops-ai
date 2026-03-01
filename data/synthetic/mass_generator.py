"""
Mass Architecture Generator — produces 2000+ unique AWS architectures.

Combines parametric dimensions:
  - 20 industry patterns
  - 4 complexity levels (small/medium/large/xlarge)
  - 5 AWS regions
  - 3 cost tiers (startup/growth/enterprise)
  - Random variation seeds for uniqueness

Each architecture is a realistic AWS topology with services, dependencies,
costs, and metadata — ready for graph engine analysis and RAG indexing.
"""

import json
import random
import hashlib
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Any

# ─── Parametric Dimensions ───────────────────────────────────────────────

PATTERNS = [
    "ecommerce", "saas", "gaming", "data_pipeline", "microservices",
    "serverless", "ml_platform", "media_streaming", "iot", "monolith",
    "fintech", "healthcare", "edtech", "logistics", "social_media",
    "adtech", "devops_platform", "analytics", "crm", "erp",
]

COMPLEXITIES = {
    "small":  {"services": (3, 7),   "deps_ratio": (1.0, 1.5)},
    "medium": {"services": (8, 16),  "deps_ratio": (1.2, 2.0)},
    "large":  {"services": (17, 30), "deps_ratio": (1.5, 2.5)},
    "xlarge": {"services": (31, 50), "deps_ratio": (1.8, 3.0)},
}

REGIONS = [
    {"id": "us-east-1",      "name": "US East (N. Virginia)",     "cost_mult": 1.0},
    {"id": "eu-west-1",      "name": "EU (Ireland)",              "cost_mult": 1.08},
    {"id": "ap-southeast-1", "name": "Asia Pacific (Singapore)",  "cost_mult": 1.15},
    {"id": "us-west-2",      "name": "US West (Oregon)",          "cost_mult": 0.98},
    {"id": "eu-central-1",   "name": "EU (Frankfurt)",            "cost_mult": 1.12},
]

COST_TIERS = {
    "startup":    {"base_range": (500, 5000),    "label": "Startup"},
    "growth":     {"base_range": (5000, 50000),  "label": "Growth"},
    "enterprise": {"base_range": (50000, 500000),"label": "Enterprise"},
}

TEAMS = [
    "platform-team", "backend-squad", "frontend-guild", "data-eng",
    "ml-ops", "devops", "security", "infra-core", "payments",
    "search-team", "mobile-backend", "analytics-team", "streaming-team",
    "identity-team", "billing-team", "notifications", "content-team",
    "growth-eng", "reliability-eng", "api-gateway-team",
]

ENVIRONMENTS = ["production", "staging", "production", "production", "dr"]

# ─── AWS Service Catalog ─────────────────────────────────────────────────

SERVICE_CATALOG = {
    "api_gateway":    {"type": "service",       "aws": "Amazon API Gateway",      "base_cost": (50, 500)},
    "alb":            {"type": "load_balancer",  "aws": "Application Load Balancer","base_cost": (20, 200)},
    "nlb":            {"type": "load_balancer",  "aws": "Network Load Balancer",   "base_cost": (20, 150)},
    "ec2_web":        {"type": "service",       "aws": "Amazon EC2 (Web)",        "base_cost": (100, 2000)},
    "ec2_app":        {"type": "service",       "aws": "Amazon EC2 (App)",        "base_cost": (200, 4000)},
    "ec2_worker":     {"type": "batch",         "aws": "Amazon EC2 (Worker)",     "base_cost": (100, 1500)},
    "ecs_fargate":    {"type": "service",       "aws": "Amazon ECS Fargate",      "base_cost": (150, 3000)},
    "eks":            {"type": "service",       "aws": "Amazon EKS",              "base_cost": (300, 5000)},
    "lambda":         {"type": "serverless",    "aws": "AWS Lambda",              "base_cost": (5, 500)},
    "step_functions": {"type": "serverless",    "aws": "AWS Step Functions",      "base_cost": (10, 200)},
    "rds_mysql":      {"type": "database",      "aws": "Amazon RDS MySQL",        "base_cost": (200, 5000)},
    "rds_postgres":   {"type": "database",      "aws": "Amazon RDS PostgreSQL",   "base_cost": (200, 5000)},
    "aurora":         {"type": "database",      "aws": "Amazon Aurora",           "base_cost": (400, 8000)},
    "dynamodb":       {"type": "database",      "aws": "Amazon DynamoDB",         "base_cost": (50, 2000)},
    "elasticache":    {"type": "cache",         "aws": "Amazon ElastiCache Redis","base_cost": (100, 2000)},
    "memcached":      {"type": "cache",         "aws": "Amazon ElastiCache Memcached","base_cost": (80, 1500)},
    "s3":             {"type": "storage",       "aws": "Amazon S3",               "base_cost": (10, 1000)},
    "efs":            {"type": "storage",       "aws": "Amazon EFS",              "base_cost": (30, 500)},
    "cloudfront":     {"type": "cdn",           "aws": "Amazon CloudFront",       "base_cost": (50, 3000)},
    "sqs":            {"type": "queue",         "aws": "Amazon SQS",              "base_cost": (5, 200)},
    "sns":            {"type": "queue",         "aws": "Amazon SNS",              "base_cost": (5, 100)},
    "kinesis":        {"type": "queue",         "aws": "Amazon Kinesis",          "base_cost": (50, 1000)},
    "kafka_msk":      {"type": "queue",         "aws": "Amazon MSK",              "base_cost": (200, 3000)},
    "opensearch":     {"type": "search",        "aws": "Amazon OpenSearch",       "base_cost": (150, 3000)},
    "sagemaker":      {"type": "service",       "aws": "Amazon SageMaker",        "base_cost": (500, 10000)},
    "redshift":       {"type": "database",      "aws": "Amazon Redshift",         "base_cost": (300, 8000)},
    "glue":           {"type": "batch",         "aws": "AWS Glue",                "base_cost": (50, 1000)},
    "emr":            {"type": "batch",         "aws": "Amazon EMR",              "base_cost": (200, 5000)},
    "cognito":        {"type": "service",       "aws": "Amazon Cognito",          "base_cost": (10, 300)},
    "waf":            {"type": "service",       "aws": "AWS WAF",                 "base_cost": (20, 200)},
    "cloudwatch":     {"type": "service",       "aws": "Amazon CloudWatch",       "base_cost": (10, 500)},
    "iot_core":       {"type": "service",       "aws": "AWS IoT Core",            "base_cost": (50, 1000)},
    "mediaconvert":   {"type": "batch",         "aws": "AWS Elemental MediaConvert","base_cost": (100, 2000)},
    "eventbridge":    {"type": "serverless",    "aws": "Amazon EventBridge",      "base_cost": (5, 100)},
    "secrets_mgr":    {"type": "service",       "aws": "AWS Secrets Manager",     "base_cost": (5, 50)},
    "route53":        {"type": "service",       "aws": "Amazon Route 53",         "base_cost": (5, 50)},
}

# ─── Pattern → Service Blueprints ────────────────────────────────────────

PATTERN_BLUEPRINTS = {
    "ecommerce": {
        "core":  ["alb", "ec2_web", "ec2_app", "rds_postgres", "elasticache"],
        "extra": ["cloudfront", "s3", "sqs", "lambda", "opensearch", "dynamodb", "sns", "cognito", "waf", "cloudwatch"],
    },
    "saas": {
        "core":  ["api_gateway", "ecs_fargate", "aurora", "elasticache", "cognito"],
        "extra": ["cloudfront", "s3", "sqs", "lambda", "sns", "dynamodb", "opensearch", "cloudwatch", "waf", "route53"],
    },
    "gaming": {
        "core":  ["nlb", "ec2_app", "dynamodb", "elasticache", "kinesis"],
        "extra": ["lambda", "s3", "cloudfront", "sqs", "sns", "ec2_worker", "opensearch", "cloudwatch", "cognito"],
    },
    "data_pipeline": {
        "core":  ["kinesis", "lambda", "s3", "glue", "redshift"],
        "extra": ["emr", "step_functions", "sqs", "dynamodb", "opensearch", "sns", "cloudwatch", "eventbridge"],
    },
    "microservices": {
        "core":  ["alb", "ecs_fargate", "rds_postgres", "elasticache", "sqs"],
        "extra": ["api_gateway", "lambda", "dynamodb", "s3", "sns", "kafka_msk", "opensearch", "cloudwatch", "cognito", "waf"],
    },
    "serverless": {
        "core":  ["api_gateway", "lambda", "dynamodb", "s3"],
        "extra": ["step_functions", "sqs", "sns", "cognito", "eventbridge", "cloudfront", "cloudwatch", "secrets_mgr"],
    },
    "ml_platform": {
        "core":  ["sagemaker", "s3", "glue", "redshift", "ec2_app"],
        "extra": ["lambda", "step_functions", "kinesis", "emr", "dynamodb", "opensearch", "cloudwatch", "ecs_fargate"],
    },
    "media_streaming": {
        "core":  ["cloudfront", "s3", "mediaconvert", "ec2_app", "dynamodb"],
        "extra": ["alb", "lambda", "elasticache", "sqs", "sns", "kinesis", "cloudwatch", "waf", "cognito"],
    },
    "iot": {
        "core":  ["iot_core", "kinesis", "lambda", "dynamodb", "s3"],
        "extra": ["step_functions", "sqs", "sns", "opensearch", "ec2_worker", "glue", "cloudwatch", "eventbridge"],
    },
    "monolith": {
        "core":  ["alb", "ec2_app", "rds_mysql", "s3"],
        "extra": ["elasticache", "cloudfront", "cloudwatch", "route53", "waf", "sns"],
    },
    "fintech": {
        "core":  ["api_gateway", "eks", "aurora", "elasticache", "dynamodb", "waf"],
        "extra": ["lambda", "sqs", "sns", "s3", "kinesis", "opensearch", "cognito", "secrets_mgr", "cloudwatch", "kms"],
    },
    "healthcare": {
        "core":  ["alb", "ecs_fargate", "aurora", "s3", "cognito", "waf"],
        "extra": ["lambda", "sqs", "dynamodb", "opensearch", "sns", "step_functions", "cloudwatch", "secrets_mgr"],
    },
    "edtech": {
        "core":  ["cloudfront", "ec2_web", "rds_postgres", "s3", "elasticache"],
        "extra": ["lambda", "sqs", "cognito", "sns", "dynamodb", "mediaconvert", "cloudwatch"],
    },
    "logistics": {
        "core":  ["api_gateway", "ecs_fargate", "rds_postgres", "dynamodb", "sqs"],
        "extra": ["lambda", "kinesis", "s3", "sns", "opensearch", "eventbridge", "cloudwatch", "iot_core"],
    },
    "social_media": {
        "core":  ["alb", "eks", "aurora", "elasticache", "cloudfront", "s3"],
        "extra": ["lambda", "dynamodb", "kinesis", "opensearch", "sqs", "sns", "cognito", "waf", "cloudwatch"],
    },
    "adtech": {
        "core":  ["alb", "ec2_app", "dynamodb", "elasticache", "kinesis", "redshift"],
        "extra": ["lambda", "s3", "emr", "opensearch", "sqs", "cloudwatch", "glue"],
    },
    "devops_platform": {
        "core":  ["alb", "eks", "rds_postgres", "s3", "elasticache"],
        "extra": ["lambda", "ecr", "sqs", "sns", "dynamodb", "opensearch", "cloudwatch", "secrets_mgr", "eventbridge"],
    },
    "analytics": {
        "core":  ["kinesis", "s3", "glue", "redshift", "opensearch"],
        "extra": ["lambda", "step_functions", "emr", "dynamodb", "cloudwatch", "eventbridge", "sagemaker"],
    },
    "crm": {
        "core":  ["alb", "ecs_fargate", "aurora", "elasticache", "opensearch"],
        "extra": ["lambda", "sqs", "s3", "sns", "cognito", "cloudwatch", "dynamodb", "ses"],
    },
    "erp": {
        "core":  ["alb", "ec2_app", "aurora", "s3", "elasticache", "sqs"],
        "extra": ["lambda", "dynamodb", "opensearch", "sns", "cloudwatch", "cognito", "waf", "step_functions"],
    },
}

DEP_TYPES = ["calls", "reads", "writes", "subscribes", "triggers", "caches", "queries"]

# ─── Name Generators ─────────────────────────────────────────────────────

ADJECTIVES = [
    "core", "primary", "shared", "central", "edge", "internal", "public",
    "private", "staging", "main", "secondary", "backup", "hot", "cold",
    "fast", "async", "realtime", "batch", "global", "regional",
]

NOUNS = {
    "ecommerce": ["storefront", "cart", "checkout", "inventory", "pricing", "catalog", "reviews", "shipping", "returns", "promotions"],
    "saas": ["tenant", "auth", "billing", "workspace", "notification", "audit", "config", "integrations", "analytics", "onboarding"],
    "gaming": ["matchmaker", "leaderboard", "inventory", "sessions", "lobby", "rewards", "chat", "telemetry", "anticheat", "store"],
    "data_pipeline": ["ingestion", "transform", "enrichment", "dedup", "validation", "routing", "aggregation", "archive", "replay", "schema"],
    "microservices": ["gateway", "user-svc", "order-svc", "payment-svc", "notification-svc", "search-svc", "report-svc", "config-svc", "audit-svc", "webhook-svc"],
    "serverless": ["handler", "processor", "validator", "transformer", "notifier", "scheduler", "aggregator", "router", "authorizer", "formatter"],
    "ml_platform": ["training", "inference", "features", "registry", "pipeline", "labeling", "monitoring", "serving", "experiment", "datasets"],
    "media_streaming": ["encoder", "transcoder", "player", "manifest", "drm", "thumbnail", "metadata", "cdn-origin", "analytics", "ads"],
    "iot": ["device-mgr", "telemetry", "commands", "rules-engine", "firmware", "shadow", "alerts", "digital-twin", "fleet", "provisioning"],
    "monolith": ["app-server", "web-tier", "batch-jobs", "reports", "admin", "mailer", "scheduler", "file-store", "sessions", "audit"],
    "fintech": ["ledger", "payments", "risk-engine", "kyc", "compliance", "transactions", "settlements", "fraud-detection", "accounts", "treasury"],
    "healthcare": ["patient-portal", "ehr", "scheduling", "labs", "imaging", "prescriptions", "claims", "telemedicine", "vitals", "consent"],
    "edtech": ["courses", "assessments", "gradebook", "video-lessons", "forums", "certificates", "enrollment", "progress", "content-mgr", "proctoring"],
    "logistics": ["routing", "tracking", "fleet-mgmt", "warehouse", "dispatch", "delivery", "returns", "manifest", "customs", "rates"],
    "social_media": ["feed", "profiles", "messaging", "media-upload", "notifications", "search", "moderation", "stories", "reactions", "follows"],
    "adtech": ["bidder", "ad-server", "targeting", "attribution", "campaign-mgr", "creative-store", "reports", "audience", "frequency-cap", "pacing"],
    "devops_platform": ["ci-runner", "artifact-store", "deploy-agent", "monitoring", "log-aggregator", "secret-vault", "registry", "scanner", "orchestrator", "dashboard"],
    "analytics": ["collector", "warehouse", "dashboards", "scheduler", "transforms", "exports", "alerts", "segments", "funnels", "cohorts"],
    "crm": ["contacts", "deals", "activities", "emails", "reports", "workflows", "forms", "scoring", "segments", "integrations"],
    "erp": ["procurement", "inventory", "finance", "hr", "manufacturing", "sales", "quality", "logistics", "maintenance", "compliance"],
}


def _make_service_name(pattern: str, svc_type: str, idx: int, seed: int) -> str:
    """Generate a unique service name."""
    rng = random.Random(seed + idx * 7)
    nouns = NOUNS.get(pattern, NOUNS["microservices"])
    noun = rng.choice(nouns)
    adj = rng.choice(ADJECTIVES)
    return f"{noun}-{svc_type.split('_')[0]}" if idx < 5 else f"{adj}-{noun}"


def generate_architecture(
    pattern: str,
    complexity: str,
    region: Dict,
    cost_tier: str,
    variation_seed: int,
) -> Dict[str, Any]:
    """Generate a single unique architecture."""
    rng = random.Random(variation_seed)

    comp = COMPLEXITIES[complexity]
    n_services = rng.randint(*comp["services"])
    deps_ratio = rng.uniform(*comp["deps_ratio"])
    n_deps = int(n_services * deps_ratio)

    tier = COST_TIERS[cost_tier]
    total_budget = rng.uniform(*tier["base_range"]) * region["cost_mult"]

    bp = PATTERN_BLUEPRINTS.get(pattern, PATTERN_BLUEPRINTS["microservices"])
    core = list(bp["core"])
    extra = list(bp["extra"])
    rng.shuffle(extra)

    # Select services
    selected = core[:min(len(core), n_services)]
    remaining = n_services - len(selected)
    if remaining > 0:
        selected += extra[:remaining]
    # If still need more, repeat with variations
    while len(selected) < n_services:
        selected.append(rng.choice(list(SERVICE_CATALOG.keys())))

    # Build services
    services = []
    cost_per_svc = total_budget / max(len(selected), 1)

    for i, svc_key in enumerate(selected):
        cat = SERVICE_CATALOG.get(svc_key, SERVICE_CATALOG["ec2_app"])
        base_lo, base_hi = cat["base_cost"]
        cost = rng.uniform(base_lo, min(base_hi, cost_per_svc * 2)) * region["cost_mult"]
        cost = round(cost, 2)

        svc_name = _make_service_name(pattern, svc_key, i, variation_seed)
        svc_id = f"{svc_name}-{str(i).zfill(3)}"

        services.append({
            "id": svc_id,
            "name": svc_name,
            "type": cat["type"],
            "aws_service": cat["aws"],
            "cost_monthly": cost,
            "owner": rng.choice(TEAMS),
            "environment": rng.choice(ENVIRONMENTS),
            "region": region["id"],
            "attributes": {
                "instance_type": rng.choice(["t3.micro", "t3.small", "t3.medium", "t3.large",
                                              "m5.large", "m5.xlarge", "r5.large", "c5.large"]),
                "auto_scaling": rng.choice([True, False]),
                "multi_az": rng.choice([True, False]),
                "encryption": rng.choice([True, True, True, False]),
            },
        })

    # Build dependencies — ensure connected graph
    dependencies = []
    svc_ids = [s["id"] for s in services]

    # Chain first to ensure connectivity
    for i in range(len(svc_ids) - 1):
        dependencies.append({
            "source": svc_ids[i],
            "target": svc_ids[i + 1],
            "type": rng.choice(DEP_TYPES),
            "weight": round(rng.uniform(0.3, 1.0), 2),
        })

    # Add extra random edges
    extra_deps = max(0, n_deps - len(dependencies))
    for _ in range(extra_deps):
        src = rng.choice(svc_ids)
        tgt = rng.choice(svc_ids)
        if src != tgt and not any(d["source"] == src and d["target"] == tgt for d in dependencies):
            dependencies.append({
                "source": src,
                "target": tgt,
                "type": rng.choice(DEP_TYPES),
                "weight": round(rng.uniform(0.1, 1.0), 2),
            })

    total_cost = round(sum(s["cost_monthly"] for s in services), 2)

    # Unique hash for this architecture
    arch_hash = hashlib.md5(f"{pattern}-{complexity}-{region['id']}-{cost_tier}-{variation_seed}".encode()).hexdigest()[:8]

    arch_name = f"{pattern.replace('_', ' ').title()} ({tier['label']}, {region['id']})"

    return {
        "metadata": {
            "name": arch_name,
            "id": arch_hash,
            "pattern": pattern,
            "complexity": complexity,
            "region": region["id"],
            "region_name": region["name"],
            "cost_tier": cost_tier,
            "cost_tier_label": tier["label"],
            "total_services": len(services),
            "total_dependencies": len(dependencies),
            "total_cost_monthly": total_cost,
            "generated_at": datetime.now().isoformat(),
            "variation_seed": variation_seed,
        },
        "services": services,
        "dependencies": dependencies,
    }


def generate_mass(output_dir: str = ".", target_count: int = 2000) -> List[Dict]:
    """Generate target_count+ unique architectures."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    architectures = []
    seed_base = 42
    count = 0

    # Calculate variations needed per combo
    total_combos = len(PATTERNS) * len(COMPLEXITIES) * len(REGIONS) * len(COST_TIERS)
    variations_per_combo = max(1, (target_count // total_combos) + 1)

    print(f"🏗️  Generating {target_count}+ architectures...")
    print(f"   {len(PATTERNS)} patterns × {len(COMPLEXITIES)} complexities × {len(REGIONS)} regions × {len(COST_TIERS)} cost tiers")
    print(f"   {total_combos} base combos × {variations_per_combo} variations = {total_combos * variations_per_combo} total")
    print()

    for pattern in PATTERNS:
        pattern_count = 0
        for complexity in COMPLEXITIES:
            for region in REGIONS:
                for cost_tier in COST_TIERS:
                    for v in range(variations_per_combo):
                        seed = seed_base + count * 31 + v * 7
                        arch = generate_architecture(pattern, complexity, region, cost_tier, seed)

                        filename = f"{pattern}_{complexity}_{region['id']}_{cost_tier}_v{v}.json"
                        filepath = output_path / filename

                        with open(filepath, "w") as f:
                            json.dump(arch, f, indent=2)

                        architectures.append({
                            "filename": filename,
                            "name": arch["metadata"]["name"],
                            "pattern": pattern,
                            "complexity": complexity,
                            "region": region["id"],
                            "cost_tier": cost_tier,
                            "services": arch["metadata"]["total_services"],
                            "cost": arch["metadata"]["total_cost_monthly"],
                        })

                        count += 1
                        pattern_count += 1

                        if count >= target_count:
                            break
                    if count >= target_count:
                        break
                if count >= target_count:
                    break
            if count >= target_count:
                break

        print(f"   ✅ {pattern:20s} → {pattern_count:4d} architectures")

        if count >= target_count:
            break

    # Save summary
    summary_path = output_path / "architecture_summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "total_architectures": len(architectures),
            "patterns": list(set(a["pattern"] for a in architectures)),
            "regions": list(set(a["region"] for a in architectures)),
            "cost_tiers": list(set(a["cost_tier"] for a in architectures)),
            "generated_at": datetime.now().isoformat(),
            "architectures": architectures,
        }, f, indent=2)

    print(f"\n🎉 Generated {len(architectures)} architectures in {output_path}")
    print(f"📄 Summary: {summary_path}")

    return architectures


if __name__ == "__main__":
    import sys
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    output = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).parent)
    generate_mass(output, target)
