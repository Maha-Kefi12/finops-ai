"""
LLM Client — handles communication with Ollama for recommendation generation.
Reuses the same LLM infrastructure as the agent pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from src.rag.indexing import get_knowledge_index
    HAS_RAG = True
except ImportError:
    HAS_RAG = False


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("FINOPS_MODEL", "finops-aws")


@dataclass
class RecommendationResult:
    """Result from the recommendation engine."""
    cards: List[Dict[str, Any]] = field(default_factory=list)
    total_estimated_savings: float = 0.0
    context_sections_used: int = 8
    llm_used: bool = False
    generation_time_ms: int = 0
    architecture_name: str = ""
    error: Optional[str] = None


def call_llm(system_prompt: str, user_prompt: str,
             temperature: float = 0.3, max_tokens: int = 4096,
             architecture_name: str = "") -> str:
    """
    Call the Ollama LLM with optional GraphRAG grounding.
    Falls back to empty string if unavailable.
    """
    # Check if Ollama is reachable first
    try:
        test_resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if test_resp.status_code != 200:
            logger.warning("Ollama at %s returned status %d in health check", OLLAMA_URL, test_resp.status_code)
    except requests.exceptions.RequestException as e:
        logger.error("Ollama health check failed: %s", e)
        raise RuntimeError(f"Ollama is not responding at {OLLAMA_URL}: {e}")
    
    grounding = ""
    if HAS_RAG and architecture_name:
        try:
            idx = get_knowledge_index()
            ctx = idx.retrieve_context(architecture_name)
            grounding = idx.format_grounding_prompt(ctx)
        except Exception:
            pass

    grounded_system = system_prompt
    if grounding:
        grounded_system = (
            system_prompt + "\n\n"
            "CRITICAL: You are grounded by factual data from a GraphRAG knowledge index. "
            "Only reference services and metrics that appear in the provided data.\n\n"
            + grounding
        )

    if not HAS_REQUESTS:
        logger.error("requests library not available — LLM calls are disabled")
        raise RuntimeError("requests library not available — cannot call LLM")

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": grounded_system},
                    {"role": "user",   "content": user_prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=300,
        )
        if resp.status_code == 200:
            return resp.json().get("message", {}).get("content", "")
        else:
            logger.error("Ollama returned status %d", resp.status_code)
            raise RuntimeError(f"LLM returned status {resp.status_code}")
    except requests.exceptions.Timeout as e:
        logger.error("Ollama request timed out after 60s: %s", e)
        raise RuntimeError(f"LLM request timed out: {e}")
    except requests.exceptions.ConnectionError as e:
        logger.error("Cannot connect to Ollama at %s: %s", OLLAMA_URL, e)
        raise RuntimeError(f"Cannot connect to Ollama at {OLLAMA_URL}: {e}")
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        raise RuntimeError(f"LLM call failed: {e}")


def extract_json_array(text: str) -> Optional[List]:
    """Extract a JSON array from LLM output text."""
    if not text:
        return None

    # Try code block
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    # Try raw array
    for start in range(len(text)):
        if text[start] == '[':
            for end in range(len(text), start, -1):
                if text[end - 1] == ']':
                    try:
                        parsed = json.loads(text[start:end])
                        if isinstance(parsed, list):
                            return parsed
                    except json.JSONDecodeError:
                        continue
    return None


def generate_recommendations(
    context_package,
    architecture_name: str = "",
    raw_graph_data: Optional[dict] = None,
) -> RecommendationResult:
    """
    Full pipeline: service inventory + graph context + Graph RAG docs
    → LLM → specific, actionable recommendation cards.
    """
    from src.llm.prompts import (
        RECOMMENDATION_SYSTEM_PROMPT,
        RECOMMENDATION_USER_PROMPT,
    )

    start = time.time()
    pkg = context_package
    pkg_dict = asdict(pkg) if hasattr(pkg, '__dataclass_fields__') else pkg

    # ── 1. Build detailed SERVICE INVENTORY from raw architecture data ──
    service_inventory = _build_service_inventory(raw_graph_data) if raw_graph_data else "(No raw service data available)"

    # ── 2. Context package summary ──
    context_text = _render_context_text_from_dict(pkg_dict)

    # ── 3. Graph theory analysis ──
    graph_theory_context = _get_graph_theory_context(pkg_dict)

    # ── 4. Monte Carlo risk predictions ──
    monte_carlo_context = _get_monte_carlo_context(pkg_dict)

    # ── 5. CUR cost & usage data ──
    cur_metrics = _extract_cur_metrics(pkg_dict)

    # ── 6. AWS best practices from Graph RAG docs ──
    aws_best_practices = _get_aws_best_practices_context(pkg_dict)

    # ── 7. Service-level narratives ──
    narratives = "\n\n".join(pkg_dict.get("interesting_node_narratives", [])[:10])
    if not narratives:
        narratives = "(No individual node narratives available)"

    user_prompt = RECOMMENDATION_USER_PROMPT.format(
        service_inventory=service_inventory,
        context_text=context_text,
        graph_theory_context=graph_theory_context,
        monte_carlo_context=monte_carlo_context,
        cur_metrics=cur_metrics,
        aws_best_practices=aws_best_practices,
        narratives=narratives,
    )

    # Call LLM — this is the ONLY source
    raw_response = call_llm(
        system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.3,
        max_tokens=8000,
        architecture_name=architecture_name,
    )

    elapsed = int((time.time() - start) * 1000)
    result = RecommendationResult(
        architecture_name=architecture_name,
        generation_time_ms=elapsed,
    )

    if not raw_response:
        raise RuntimeError("LLM returned empty response — Ollama unavailable or model error")

    # Save response for debugging
    try:
        with open("/tmp/llm_response.txt", "w") as f:
            f.write(f"=== RAW LLM RESPONSE ({len(raw_response)} chars) ===\n")
            f.write(raw_response[:5000])
    except Exception:
        pass

    cards = _parse_structured_recommendations(raw_response)
    logger.info("Parsed %d recommendation cards from LLM response", len(cards))

    if not cards:
        logger.error("No valid cards parsed. Response preview:\n%s", raw_response[:500])
        raise RuntimeError("LLM did not produce valid structured recommendation output")

    # ── Enrich cards with REAL architecture data ────────────────────
    if raw_graph_data:
        cards = _enrich_cards_from_architecture(cards, raw_graph_data)

    result.cards = cards
    result.llm_used = True
    result.total_estimated_savings = sum(
        c.get("total_estimated_savings", 0) for c in result.cards
    )
    logger.info(
        "LLM generated %d recommendations ($%.2f savings) in %dms",
        len(result.cards), result.total_estimated_savings, elapsed,
    )
    return result


def _parse_structured_recommendations(text: str) -> List[Dict]:
    """Parse recommendations from LLM output.

    Handles multiple formats the LLM might produce:
    - Markdown: ### Cost Optimization Recommendation #N
    - Plain:    COST OPTIMIZATION RECOMMENDATION #N
    - Simple:   Recommendation #N
    """

    if not text or not text.strip():
        logger.error("Empty text provided for parsing")
        return []

    cards = []

    # Try multiple header patterns (most specific first)
    patterns = [
        r"(?:^|\n)#{1,4}\s*Cost Optimization Recommendation\s*#(\d+)",
        r"COST OPTIMIZATION RECOMMENDATION\s*#(\d+)",
        r"(?:^|\n)#{1,4}\s*Recommendation\s*#(\d+)",
        r"Recommendation\s*#(\d+)",
    ]

    matches = []
    for pat in patterns:
        matches = list(re.finditer(pat, text, re.IGNORECASE | re.MULTILINE))
        if matches:
            logger.info("Matched %d recommendations with pattern: %s", len(matches), pat[:50])
            break

    if not matches:
        logger.warning("No recommendation sections found in LLM output")
        logger.debug("First 500 chars:\n%s", text[:500])
        return []

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        rec_text = text[start:end]

        card = _extract_recommendation_from_text(rec_text, i + 1)
        if card:
            cards.append(card)
        else:
            logger.warning("Could not extract recommendation #%d", i + 1)

    return cards


# ── Instance type downsize map ─────────────────────────────────────────────
_DOWNSIZE_MAP = {
    "m5.xlarge": ("m5.large", 0.50), "m5.2xlarge": ("m5.xlarge", 0.50),
    "m5.4xlarge": ("m5.2xlarge", 0.50), "m5.large": ("m5.medium", 0.50),
    "r5.xlarge": ("r5.large", 0.50), "r5.2xlarge": ("r5.xlarge", 0.50),
    "r5.large": ("t3.large", 0.60), "c5.xlarge": ("c5.large", 0.50),
    "c5.2xlarge": ("c5.xlarge", 0.50), "c5.large": ("t3.large", 0.55),
    "t3.xlarge": ("t3.large", 0.50), "t3.large": ("t3.medium", 0.50),
    "t3.2xlarge": ("t3.xlarge", 0.50),
}

_FINOPS_PRACTICES = {
    "database": "AWS Well-Architected Cost Pillar: Use Aurora Serverless v2 for variable workloads. Apply Reserved Instances for steady-state databases. Enable Performance Insights to right-size.",
    "load_balancer": "AWS FinOps: Review ALB idle connections and unused rules. Use connection draining. Consolidate ALBs where possible to reduce fixed hourly charges.",
    "service": "AWS FinOps: Use Compute Savings Plans (up to 66% savings). Enable auto-scaling based on CloudWatch metrics. Use Spot Instances for fault-tolerant workloads.",
    "storage": "AWS S3 Cost Optimization: Enable S3 Intelligent-Tiering for unknown access patterns. Use S3 Lifecycle rules to transition to Glacier for archives. Enable S3 Storage Lens.",
    "queue": "AWS SQS/SNS: Use long polling to reduce API calls. Set appropriate visibility timeout. Use SQS FIFO only when ordering is required (5x more expensive).",
    "cache": "ElastiCache: Use reserved nodes for 1yr+ workloads (40% savings). Right-size based on CloudWatch EngineCPUUtilization and DatabaseMemoryUsagePercentage.",
    "serverless": "AWS Lambda: Optimize memory allocation (use AWS Lambda Power Tuning). Use Graviton2 for 20% cost reduction. Set appropriate timeout values.",
    "cdn": "CloudFront: Use Origin Shield to reduce origin load. Enable caching for static content. Use CloudFront Functions instead of Lambda@Edge where possible.",
    "dns": "Route 53: Consolidate hosted zones. Use alias records instead of CNAME (no query charges). Minimize health check frequency for non-critical endpoints.",
}


def _enrich_cards_from_architecture(cards: list, graph_data: dict) -> list:
    """Enrich LLM-generated cards with REAL data from the architecture.

    For each card, look up the resource in the architecture by fuzzy matching
    the resource ID, then fill in: instance type, cost, environment, region,
    and generate specific implementation steps.
    """
    services = graph_data.get("services") or graph_data.get("nodes") or []
    if not services:
        return cards

    # Build lookup: id -> service, name -> service
    svc_by_id = {}
    svc_by_name = {}
    for svc in services:
        sid = svc.get("id", "")
        sname = svc.get("name", "")
        svc_by_id[sid] = svc
        svc_by_name[sname] = svc
        # Also index by id without numeric suffix (e.g. "consent-alb-000" -> "consent-alb")
        base = re.sub(r"-\d+$", "", sid)
        svc_by_name[base] = svc

    region = graph_data.get("metadata", {}).get("region", "us-east-1")

    for card in cards:
        res = card.get("resource_identification", {})
        rid = res.get("resource_id", "") or res.get("service_name", "")

        # ── Fuzzy match resource to architecture service ──
        matched_svc = svc_by_id.get(rid) or svc_by_name.get(rid)
        if not matched_svc:
            # Try partial matching
            rid_lower = rid.lower().strip()
            for key, svc in {**svc_by_id, **svc_by_name}.items():
                if rid_lower in key.lower() or key.lower() in rid_lower:
                    matched_svc = svc
                    break

        if not matched_svc:
            continue

        # ── Fill in real data ──
        attrs = matched_svc.get("attributes", matched_svc.get("properties", {}))
        inst_type = attrs.get("instance_type", "")
        aws_service = matched_svc.get("aws_service", matched_svc.get("type", ""))
        svc_type = matched_svc.get("type", "service")
        cost = matched_svc.get("cost_monthly", 0)
        env = matched_svc.get("environment", "production")
        auto_scale = attrs.get("auto_scaling", False)
        multi_az = attrs.get("multi_az", False)
        svc_id = matched_svc.get("id", rid)
        svc_name = matched_svc.get("name", rid)

        # Update resource_identification
        res["service_name"] = svc_name
        res["resource_id"] = svc_id
        res["service_type"] = aws_service
        res["region"] = region
        res["current_config"] = (
            f"{inst_type} | {env} | Multi-AZ: {'Yes' if multi_az else 'No'} | "
            f"Auto-Scale: {'Yes' if auto_scale else 'No'} | Cost: ${cost:,.2f}/mo"
        )

        # Update cost breakdown
        card["cost_breakdown"]["current_monthly"] = cost
        if not card["cost_breakdown"].get("line_items"):
            card["cost_breakdown"]["line_items"] = [
                {"item": f"{aws_service} ({inst_type})", "usage": f"{env}", "cost": cost}
            ]

        # ── Generate specific implementation steps ──
        impl_steps = []
        perf_impact = ""
        risk_mitigation = ""
        val_steps = []
        savings = 0

        # RIGHT-SIZING
        target_type = None
        savings_pct = 0
        if inst_type in _DOWNSIZE_MAP and env in ("staging", "dr", "development", "test"):
            target_type, savings_pct = _DOWNSIZE_MAP[inst_type]
            savings = cost * savings_pct
        elif inst_type in _DOWNSIZE_MAP:
            target_type, savings_pct = _DOWNSIZE_MAP[inst_type]
            savings = cost * 0.25  # conservative for production

        if target_type:
            card["title"] = f"Downsize {svc_id} from {inst_type} to {target_type}"

            if svc_type == "database":
                impl_steps = [
                    f"Create snapshot: aws rds create-db-cluster-snapshot --db-cluster-identifier {svc_id} --db-cluster-snapshot-identifier {svc_id}-pre-resize",
                    f"Modify instance: aws rds modify-db-instance --db-instance-identifier {svc_id} --db-instance-class db.{target_type} --apply-immediately",
                    f"Monitor CloudWatch: Check CPUUtilization, FreeableMemory, ReadIOPS for 48 hours after resize",
                ]
                perf_impact = f"Downsizing from {inst_type} to {target_type} reduces vCPUs and memory. For {env} workload this is typically sufficient. Monitor database performance metrics closely."
                risk_mitigation = f"Take RDS snapshot before resize. Schedule during {env} maintenance window. If performance degrades, revert: aws rds modify-db-instance --db-instance-identifier {svc_id} --db-instance-class db.{inst_type}"
            elif svc_type == "service" or svc_type == "serverless":
                impl_steps = [
                    f"Update ECS task definition: Change instance type from {inst_type} to {target_type} in task definition for {svc_id}",
                    f"Deploy with rolling update: aws ecs update-service --cluster {svc_name}-cluster --service {svc_id} --force-new-deployment",
                    f"Monitor: Watch CloudWatch CPUUtilization and MemoryUtilization for the service for 24 hours",
                ]
                perf_impact = f"Reduces compute from {inst_type} to {target_type}. {env.title()} workload should not be impacted. Risk: {'LOW' if env != 'production' else 'MEDIUM'}"
                risk_mitigation = f"Use rolling deployment with health checks. Set minimum healthy percent to 50%. If issues arise, roll back the ECS task definition."
            else:
                impl_steps = [
                    f"Change {svc_id} instance type from {inst_type} to {target_type} in the AWS Console or via CloudFormation/Terraform",
                    f"Schedule the change during {env} maintenance window to minimize impact",
                    f"Monitor CloudWatch metrics for 48 hours after the change",
                ]
                perf_impact = f"Reduces compute capacity. For {env} environment this is an acceptable trade-off. Risk: LOW"
                risk_mitigation = f"Create AMI/snapshot before change. Test in staging first if production."

            val_steps = [
                f"After 7 days, verify on CUR that {svc_id} line item shows ~${cost - savings:,.2f} instead of ${cost:,.2f}",
                f"Check CloudWatch alarms: no CPU > 80% sustained or memory pressure alerts",
                f"Confirm application health checks are passing for {svc_name}",
            ]
        else:
            # RI / Savings Plan recommendations for production
            if env == "production" and cost > 50:
                savings = cost * 0.30
                card["title"] = f"Apply Reserved Instance for {svc_id} ({aws_service})"
                impl_steps = [
                    f"Purchase 1-year No Upfront Reserved Instance for {aws_service} {inst_type} in {region}: saves ~30%",
                    f"Go to AWS Console → Cost Management → Reservations → Purchase Reserved Instances",
                    f"Select: Instance Type={inst_type}, Term=1 Year, Payment=No Upfront, Region={region}",
                ]
                perf_impact = "Zero performance impact — Reserved Instances are a billing construct, not a configuration change."
                risk_mitigation = "Start with 1-year No Upfront RI to minimize commitment risk. Review utilization after 6 months before considering 3-year terms."
                val_steps = [
                    f"After purchase, verify RI coverage in AWS Cost Explorer → Reservations → Utilization",
                    f"After 30 days, confirm {svc_id} shows RI pricing on CUR (should be ~${cost * 0.70:,.2f}/mo)",
                ]
            elif not auto_scale and cost > 30:
                savings = cost * 0.15
                card["title"] = f"Enable auto-scaling for {svc_id} to reduce idle costs"
                impl_steps = [
                    f"Enable auto-scaling for {svc_id}: set min=1, max=3, target CPU=70%",
                    f"aws application-autoscaling register-scalable-target --service-namespace ecs --resource-id service/{svc_name}-cluster/{svc_id} --scalable-dimension ecs:service:DesiredCount --min-capacity 1 --max-capacity 3",
                    f"Create scaling policy: aws application-autoscaling put-scaling-policy --policy-name {svc_id}-cpu-scaling --service-namespace ecs --resource-id service/{svc_name}-cluster/{svc_id} --scalable-dimension ecs:service:DesiredCount --policy-type TargetTrackingScaling --target-tracking-scaling-policy-configuration '{{\"TargetValue\":70,\"PredefinedMetricSpecification\":{{\"PredefinedMetricType\":\"ECSServiceAverageCPUUtilization\"}}}}'",
                ]
                perf_impact = "Auto-scaling adjusts capacity dynamically. During low-traffic periods, reduces to minimum instances. May add ~30s scale-up latency during traffic spikes."
                risk_mitigation = "Set conservative min capacity. Monitor scale-in events. Use CloudWatch alarms on high CPU to detect under-provisioning."
                val_steps = [
                    f"After 14 days, check avg instance count vs current fixed count",
                    f"Verify no increased latency from CloudWatch Application metrics",
                ]
            elif multi_az and env in ("staging", "dr", "development"):
                savings = cost * 0.30
                card["title"] = f"Disable Multi-AZ for {env} resource {svc_id}"
                impl_steps = [
                    f"Disable Multi-AZ for {svc_id}: This is a {env} resource and does not need cross-AZ redundancy",
                    f"aws rds modify-db-instance --db-instance-identifier {svc_id} --no-multi-az --apply-immediately" if svc_type == "database" else f"Update {svc_id} configuration to single-AZ deployment",
                    f"Update monitoring: Remove cross-AZ failover alerts for this {env} resource",
                ]
                perf_impact = f"Removes cross-AZ redundancy for {env} environment. Acceptable risk since this is not production."
                risk_mitigation = f"Only apply to {env} environments. Production resources MUST keep Multi-AZ enabled."
                val_steps = [
                    f"Verify {svc_id} is now single-AZ in AWS Console",
                    f"After 30 days, confirm ~${savings:,.2f}/mo savings on CUR",
                ]
            else:
                savings = cost * 0.10
                card["title"] = f"Optimize {svc_id} ({aws_service}) configuration"
                impl_steps = [
                    f"Review CloudWatch metrics for {svc_id}: CPUUtilization, MemoryUsage, NetworkIn/Out",
                    f"If avg CPU < 40%, consider downsizing {inst_type} to a smaller instance type",
                    f"Evaluate Savings Plans coverage for {aws_service} workloads in {region}",
                ]
                perf_impact = f"Depends on specific optimization chosen. Monitor for 48 hours after any change."
                risk_mitigation = f"Start with non-production changes. Use CloudWatch dashboards to track impact."
                val_steps = [f"Monitor CUR for {svc_id} cost trend over next 30 days"]

        # Update savings
        card["total_estimated_savings"] = round(savings, 2)

        # Update sub-recommendations
        if card.get("recommendations"):
            for rec in card["recommendations"]:
                rec["implementation_steps"] = impl_steps
                rec["validation_steps"] = val_steps
                rec["performance_impact"] = perf_impact
                rec["risk_mitigation"] = risk_mitigation
                rec["estimated_monthly_savings"] = round(savings, 2)
                rec["action"] = card["title"]
        else:
            card["recommendations"] = [{
                "action_number": 1,
                "action": card["title"],
                "estimated_monthly_savings": round(savings, 2),
                "confidence": "high" if env != "production" else "medium",
                "implementation_steps": impl_steps,
                "validation_steps": val_steps,
                "performance_impact": perf_impact,
                "risk_mitigation": risk_mitigation,
            }]

        # Add FinOps best practice
        card["finops_best_practice"] = _FINOPS_PRACTICES.get(svc_type, _FINOPS_PRACTICES.get("service", ""))

        # Update category
        if "downsize" in card["title"].lower() or "right" in card["title"].lower():
            card["category"] = "right-sizing"
        elif "reserved" in card["title"].lower() or "savings plan" in card["title"].lower():
            card["category"] = "reserved-capacity"
        elif "auto-scal" in card["title"].lower():
            card["category"] = "architecture"
        elif "multi-az" in card["title"].lower():
            card["category"] = "networking"
        elif "storage" in card["title"].lower() or "s3" in card["title"].lower():
            card["category"] = "caching"

        # Set severity based on enriched savings
        if savings > 200:
            card["severity"] = "critical"
        elif savings > 100:
            card["severity"] = "high"
        elif savings > 30:
            card["severity"] = "medium"
        else:
            card["severity"] = "low"

        # Set complexity from steps count
        if impl_steps:
            card["implementation_complexity"] = "low" if len(impl_steps) <= 2 else ("medium" if len(impl_steps) <= 4 else "high")

    return cards


def _extract_recommendation_from_text(text: str, rec_num: int) -> Optional[Dict]:
    """Extract a recommendation card from LLM output text.

    Handles the markdown format the LLM produces with **bold headers**.
    Extracts all fields the frontend FullRecommendationCard expects.
    """
    if not text or len(text) < 20:
        return None

    card = {
        "priority": rec_num,
        "recommendation_number": rec_num,
        "title": "",
        "severity": "high",
        "category": "right-sizing",
        "risk_level": "medium",
        "implementation_complexity": "medium",
        "resource_identification": {},
        "cost_breakdown": {"current_monthly": 0, "line_items": [], "cost_trend": ""},
        "inefficiencies": [],
        "recommendations": [],
        "total_estimated_savings": 0,
    }

    # Helper: extract markdown section content between **Header:** and next **Header:** or ---
    def _md_section(header: str) -> str:
        pat = rf"\*\*{re.escape(header)}:?\*\*\s*\n?(.*?)(?:\n\*\*[A-Z]|\n---|$)"
        m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        pat2 = rf"\*\*{re.escape(header)}:?\*\*\s*(.+?)(?:\n|$)"
        m2 = re.search(pat2, text, re.IGNORECASE)
        return m2.group(1).strip() if m2 else ""

    def _extract_bullets(section_text: str) -> list:
        bullets = []
        for line in section_text.split("\n"):
            line = line.strip()
            m = re.match(r"^(?:\d+[\.\)]\s*|[-•*]\s+)(.*)", line)
            if m:
                content = re.sub(r"\*\*", "", m.group(1)).strip()
                if content:
                    bullets.append(content)
        return bullets

    # ── 1. Resource Identification ──────────────────────────────────
    res_section = _extract_section(text, "RESOURCE IDENTIFICATION")
    if res_section:
        card["resource_identification"] = _parse_resource_id_section(res_section)
    else:
        # Try **Target Service:** or **Resource ID:** in bold markdown
        target_svc = re.search(
            r"\*\*(?:Target Service|Resource ID):?\*\*\s*[`\"]?([^`\"\n]+)[`\"]?",
            text, re.IGNORECASE,
        )
        if target_svc:
            svc_name = target_svc.group(1).strip()
            card["resource_identification"]["service_name"] = svc_name
            card["resource_identification"]["resource_id"] = svc_name
        else:
            rid = re.search(r"Resource ID:\s*([^\n]+)", text)
            svc = re.search(r"Service:\s*([^\n]+)", text)
            if rid:
                card["resource_identification"]["resource_id"] = rid.group(1).strip()
            if svc:
                card["resource_identification"]["service_name"] = svc.group(1).strip()

        # Also extract **AWS Service:**
        aws_svc = re.search(r"\*\*AWS Service:?\*\*\s*([^\n]+)", text, re.IGNORECASE)
        if aws_svc:
            card["resource_identification"]["service_type"] = aws_svc.group(1).strip()

        # Also extract **Current Config:**
        cur_cfg = re.search(r"\*\*Current Config:?\*\*\s*([^\n]+)", text, re.IGNORECASE)
        if cur_cfg:
            card["resource_identification"]["current_config"] = cur_cfg.group(1).strip()

        rgn = re.search(r"Region:\s*([^\n]+)", text)
        if rgn:
            card["resource_identification"]["region"] = rgn.group(1).strip()

    # ── 2. Cost Breakdown ──────────────────────────────────────────
    cost_section = _extract_section(text, "CURRENT COST BREAKDOWN")
    if cost_section:
        card["cost_breakdown"] = _parse_cost_breakdown_section(cost_section)
    else:
        cmc = re.search(r"\*\*Current Monthly Cost:?\*\*\s*\$([0-9,]+\.?\d*)", text, re.IGNORECASE)
        if cmc:
            try:
                card["cost_breakdown"]["current_monthly"] = float(cmc.group(1).replace(",", ""))
            except ValueError:
                pass
        if card["cost_breakdown"]["current_monthly"] == 0:
            alt = re.search(r"\$([0-9,]+\.?\d*)\s*/\s*month", text, re.IGNORECASE)
            if alt:
                try:
                    card["cost_breakdown"]["current_monthly"] = float(alt.group(1).replace(",", ""))
                except ValueError:
                    pass

    # ── 3. Estimated Savings (card-level) ──────────────────────────
    ems = re.search(r"\*\*Estimated Monthly Savings:?\*\*\s*\$([0-9,]+\.?\d*)", text, re.IGNORECASE)
    if ems:
        try:
            card["total_estimated_savings"] = float(ems.group(1).replace(",", ""))
        except ValueError:
            pass

    # ── 4. Inefficiencies / Reasoning ──────────────────────────────
    ineff_section = _extract_section(text, "INEFFICIENCIES DETECTED")
    if ineff_section:
        card["inefficiencies"] = _parse_inefficiencies_section(ineff_section)
    else:
        reasoning_text = _md_section("Reasoning")
        if reasoning_text:
            bullets = _extract_bullets(reasoning_text)
            for idx, b in enumerate(bullets):
                card["inefficiencies"].append({
                    "id": idx + 1,
                    "description": b,
                    "severity": "HIGH",
                })

    # ── 5. Implementation Steps ────────────────────────────────────
    impl_text = _md_section("Implementation Steps")
    impl_steps = _extract_bullets(impl_text) if impl_text else []

    # ── 6. Performance Impact ──────────────────────────────────────
    perf_text = _md_section("Performance Impact")
    perf_impact = re.sub(r"\*\*", "", perf_text).strip() if perf_text else ""

    # ── 7. Risk Mitigation ─────────────────────────────────────────
    risk_text = _md_section("Risk Mitigation")
    risk_mitigation = re.sub(r"\*\*", "", risk_text).strip() if risk_text else ""

    # ── 8. Validation Steps ────────────────────────────────────────
    val_text = _md_section("Validation")
    val_steps = _extract_bullets(val_text) if val_text else []

    # ── 9. FinOps Best Practice ────────────────────────────────────
    bp_text = _md_section("FinOps Best Practice")
    if bp_text:
        card["finops_best_practice"] = re.sub(r"\*\*", "", bp_text).strip()[:500]

    # ── 10. Recommendations (actions) ──────────────────────────────
    rec_section = _extract_section(text, "COMPREHENSIVE RECOMMENDATIONS")
    if rec_section:
        card["recommendations"] = _parse_recommendations_list(rec_section)
    else:
        rec_text_md = _md_section("Recommendation")
        if rec_text_md:
            bold_bullets = re.findall(r"[-•*]\s+\*\*(.+?)\*\*:?\s*(.*?)(?:\n|$)", rec_text_md)
            if bold_bullets:
                for idx, (action, detail) in enumerate(bold_bullets):
                    savings = 0
                    sav_m = re.search(r"\$([0-9,]+\.?\d*)", detail)
                    if sav_m:
                        try:
                            savings = float(sav_m.group(1).replace(",", ""))
                        except ValueError:
                            pass
                    card["recommendations"].append({
                        "action_number": idx + 1,
                        "action": f"{action}: {detail}".strip().rstrip(":") if detail else action.strip(),
                        "estimated_monthly_savings": savings,
                        "implementation_steps": impl_steps,
                        "validation_steps": val_steps,
                        "performance_impact": perf_impact,
                        "risk_mitigation": risk_mitigation,
                    })
            else:
                simple = _extract_bullets(rec_text_md)
                for idx, s in enumerate(simple):
                    card["recommendations"].append({
                        "action_number": idx + 1,
                        "action": s,
                        "estimated_monthly_savings": 0,
                        "implementation_steps": impl_steps,
                        "validation_steps": val_steps,
                        "performance_impact": perf_impact,
                        "risk_mitigation": risk_mitigation,
                    })

        if not card["recommendations"]:
            card["recommendations"] = _parse_recommendations_list(text)
            for r in card["recommendations"]:
                if not r.get("implementation_steps"):
                    r["implementation_steps"] = impl_steps
                if not r.get("validation_steps"):
                    r["validation_steps"] = val_steps
                if not r.get("performance_impact"):
                    r["performance_impact"] = perf_impact
                if not r.get("risk_mitigation"):
                    r["risk_mitigation"] = risk_mitigation

    # ── Title generation ───────────────────────────────────────────
    res = card["resource_identification"]
    svc_name = res.get("service_name") or res.get("resource_id", "")
    if card["recommendations"]:
        card["title"] = card["recommendations"][0].get("action", f"Optimize {svc_name}")[:120]
    elif svc_name:
        card["title"] = f"Optimize {svc_name}"
    else:
        first_line = text.split("\n")[0].strip()
        card["title"] = re.sub(
            r"(?:###?\s*)?(?:Cost Optimization )?Recommendation\s*#\d+\s*",
            "", first_line, flags=re.IGNORECASE,
        ).strip()[:120] or f"Recommendation #{rec_num}"

    # ── Category inference ─────────────────────────────────────────
    txt_lower = text.lower()
    if any(w in txt_lower for w in ["right-siz", "downsize", "instance type", "t3.", "m5."]):
        card["category"] = "right-sizing"
    elif any(w in txt_lower for w in ["idle", "unused", "waste", "decommission"]):
        card["category"] = "waste-elimination"
    elif any(w in txt_lower for w in ["reserved", "savings plan", "commitment"]):
        card["category"] = "reserved-capacity"
    elif any(w in txt_lower for w in ["cache", "elasticache", "redis"]):
        card["category"] = "caching"
    elif any(w in txt_lower for w in ["transfer", "nat ", "vpc ", "endpoint", "network"]):
        card["category"] = "networking"
    elif any(w in txt_lower for w in ["serverless", "lambda", "migrate"]):
        card["category"] = "architecture"
    elif any(w in txt_lower for w in ["security", "acl", "security group"]):
        card["category"] = "security"

    # ── Severity + savings ─────────────────────────────────────────
    total_savings = sum(r.get("estimated_monthly_savings", 0) for r in card["recommendations"])
    if total_savings > 0:
        card["total_estimated_savings"] = total_savings
    elif card["total_estimated_savings"] == 0:
        savings_match = re.search(r"\$([0-9,]+\.?\d*)", text)
        if savings_match:
            try:
                card["total_estimated_savings"] = float(savings_match.group(1).replace(",", ""))
            except ValueError:
                pass

    cost = card["cost_breakdown"]["current_monthly"]
    if card["total_estimated_savings"] > 500 or cost > 500:
        card["severity"] = "critical"
    elif card["total_estimated_savings"] > 200 or cost > 100:
        card["severity"] = "high"
    elif card["total_estimated_savings"] > 50 or cost > 20:
        card["severity"] = "medium"
    else:
        card["severity"] = "low"

    # ── Implementation complexity ──────────────────────────────────
    if impl_steps:
        card["implementation_complexity"] = "low" if len(impl_steps) <= 2 else ("medium" if len(impl_steps) <= 4 else "high")

    # ── Risk level from performance impact ─────────────────────────
    if perf_impact:
        pi_lower = perf_impact.lower()
        if any(w in pi_lower for w in ["zero", "none", "no impact", "minimal"]):
            card["risk_level"] = "low"
        elif "high" in pi_lower:
            card["risk_level"] = "high"
        else:
            card["risk_level"] = "medium"

    return card


def _extract_section(text: str, section_header: str) -> Optional[str]:
    """Extract a section from LLM output between ═══ delimiters.

    Looks for the section_header (e.g. 'RESOURCE IDENTIFICATION') and
    returns all text until the next ═══ delimiter or end.
    """
    # Try delimited format first (═══...HEADER...═══...content...═══)
    pattern = rf"{re.escape(section_header)}.*?═{{3,}}\s*\n(.*?)(?:═{{3,}}|$)"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    # Fallback: just find the header and grab text until next section header
    idx = text.upper().find(section_header.upper())
    if idx >= 0:
        rest = text[idx + len(section_header):]
        # Skip past any delimiter line
        rest = re.sub(r'^[═\s]+', '', rest)
        # Take until next known section header
        next_headers = [
            "RESOURCE IDENTIFICATION", "CURRENT COST BREAKDOWN",
            "INEFFICIENCIES DETECTED", "COMPREHENSIVE RECOMMENDATIONS",
            "COST OPTIMIZATION RECOMMENDATION",
        ]
        end = len(rest)
        for h in next_headers:
            if h.upper() == section_header.upper():
                continue
            pos = rest.upper().find(h.upper())
            if 0 < pos < end:
                end = pos
        return rest[:end].strip()

    return None


def _parse_resource_id_section(text: str) -> Dict:
    """Parse resource identification section.

    Returns keys that FullRecommendationCard expects:
    service_name, service_type, region, current_config, tags.
    """
    res = {}

    patterns = {
        "resource_id": r"Resource ID:\s*([^\n]+)",
        "full_arn": r"Full ARN:\s*([^\n]+)",
        "service_name": r"Service:\s*([^\n]+)",
        "service_type": r"Service Type:\s*([^\n]+)",
        "current_config": r"(?:Current Instance|Instance|Config|Configuration):\s*([^\n]+)",
        "region": r"Region:\s*([^\n]+)",
        "availability_zone": r"Availability Zone:\s*([^\n]+)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            res[key] = match.group(1).strip()

    # Extract tags (Key=Value pairs)
    tags_match = re.search(r"Tags:\s*([^\n]+)", text)
    if tags_match:
        tags_str = tags_match.group(1).strip()
        tags = {}
        for pair in re.findall(r"(\w+)\s*=\s*(\S+)", tags_str):
            tags[pair[0]] = pair[1]
        if tags:
            res["tags"] = tags

    # Build current_config from instance if not found
    if "current_config" not in res and "service_name" in res:
        res["current_config"] = res["service_name"]

    return res


def _parse_cost_breakdown_section(text: str) -> Dict:
    """Parse cost breakdown with CUR table and cost trend."""
    breakdown = {"current_monthly": 0, "line_items": [], "cost_trend": ""}

    # Extract table rows (between │ characters)
    table_rows = re.findall(r"│\s*(.+?)\s*│\s*(.+?)\s*│\s*\$?([0-9,\.]+)\s*│", text)

    for item_desc, usage, cost_str in table_rows:
        try:
            cost_val = float(cost_str.replace(",", ""))
        except ValueError:
            continue
        if "TOTAL" in item_desc.upper():
            breakdown["current_monthly"] = cost_val
        else:
            breakdown["line_items"].append({
                "item": item_desc.strip(),
                "usage": usage.strip(),
                "cost": cost_val,
            })

    # Sum line items if no total found
    if breakdown["current_monthly"] == 0 and breakdown["line_items"]:
        breakdown["current_monthly"] = sum(li["cost"] for li in breakdown["line_items"])

    # Extract cost trend text
    trend_match = re.search(r"Cost Trend.*?:\s*\n(.*?)(?:\n\n|$)", text, re.DOTALL)
    if trend_match:
        breakdown["cost_trend"] = trend_match.group(1).strip()[:300]
    else:
        # Look for Trend: line
        trend_line = re.search(r"Trend:\s*([^\n]+)", text)
        if trend_line:
            breakdown["cost_trend"] = trend_line.group(1).strip()

    return breakdown


def _parse_inefficiencies_section(text: str) -> List[Dict]:
    """Parse inefficiencies/issues section - flexible to handle various formats."""
    import re
    
    inefficiencies = []
    
    # First try structured format: ISSUE #N: description (severity)\nBody
    issue_pattern_formal = r"ISSUE #(\d+):\s*([^\n\(]+)\s*\(([^)]+)\)\s*\n(.*?)(?:ISSUE #|\nRECOMMENDATIONS|$)"
    matches = list(re.finditer(issue_pattern_formal, text, re.DOTALL))
    
    if matches:
        # Use formal pattern
        for match in matches:
            ineff = {
                "id": int(match.group(1)),
                "description": match.group(2).strip(),
                "severity": match.group(3).upper(),
            }
            inefficiencies.append(ineff)
    else:
        # Fallback: simple format with bullet points
        # • ISSUE #1: description OR - ISSUE #1: description
        bullet_pattern = r"[•\-]\s*ISSUE #(\d+):\s*([^\n]+)"
        bullet_matches = re.finditer(bullet_pattern, text)
        
        for match in bullet_matches:
            ineff = {
                "id": int(match.group(1)),
                "description": match.group(2).strip(),
                "severity": "HIGH",  # Default severity
            }
            inefficiencies.append(ineff)
    
    return inefficiencies


def _parse_recommendations_list(text: str) -> List[Dict]:
    """Parse list of sub-recommendations within a card.

    Extracts action, savings, implementation_steps, validation_steps,
    performance_impact, risk_mitigation, and confidence — all fields
    that FullRecommendationCard renders.
    """

    recommendations = []

    # Try formal format: RECOMMENDATION #N: action (IMPLEMENT FIRST/SECOND)
    formal_pattern = r"RECOMMENDATION #(\d+):\s*([^\n]+)\n(.*?)(?=RECOMMENDATION #|\Z)"
    matches = list(re.finditer(formal_pattern, text, re.DOTALL))

    if matches:
        for match in matches:
            rec = {
                "action_number": int(match.group(1)),
                "action": match.group(2).strip(),
                "estimated_monthly_savings": 0,
                "implementation_steps": [],
                "validation_steps": [],
                "performance_impact": "",
                "risk_mitigation": "",
                "confidence": "",
            }

            body = match.group(3)

            # ── Savings ──
            savings_patts = [
                r"Monthly savings:\s*\$?([0-9,]+\.?\d*)",
                r"save[s ]?\s*\$?([0-9,]+\.?\d*)",
                r"Savings Calculation.*?Monthly savings:\s*\$?([0-9,]+\.?\d*)",
                r"Compute savings:\s*\$?([0-9,]+\.?\d*)",
            ]
            for patt in savings_patts:
                m = re.search(patt, body, re.IGNORECASE | re.DOTALL)
                if m:
                    try:
                        rec["estimated_monthly_savings"] = float(m.group(1).replace(",", ""))
                        break
                    except ValueError:
                        continue

            # ── Confidence ──
            conf_match = re.search(r"(?:confidence|risk):\s*(ZERO|LOW|MEDIUM|HIGH|VERY HIGH)", body, re.IGNORECASE)
            if conf_match:
                rec["confidence"] = conf_match.group(1).strip()

            # ── Implementation steps ──
            impl_section = re.search(r"Implementation:\s*\n(.*?)(?:\n\n|Validation|Performance|Risk|$)", body, re.DOTALL)
            if impl_section:
                steps = re.findall(r"\d+\.\s*(.+)", impl_section.group(1))
                rec["implementation_steps"] = [s.strip() for s in steps if s.strip()]

            # ── Validation steps ──
            val_section = re.search(r"Validation:\s*\n(.*?)(?:\n\n|Implementation|Performance|Risk|$)", body, re.DOTALL)
            if val_section:
                steps = re.findall(r"[-•]\s*(.+)", val_section.group(1))
                if not steps:
                    steps = re.findall(r"\d+\.\s*(.+)", val_section.group(1))
                rec["validation_steps"] = [s.strip() for s in steps if s.strip()]

            # ── Performance impact ──
            perf_match = re.search(r"Performance Impact:\s*\n(.*?)(?:\n\n|Implementation|Validation|Risk|$)", body, re.DOTALL)
            if perf_match:
                rec["performance_impact"] = perf_match.group(1).strip()[:300]
            else:
                perf_line = re.search(r"Performance Impact:\s*([^\n]+)", body)
                if perf_line:
                    rec["performance_impact"] = perf_line.group(1).strip()

            # ── Risk mitigation ──
            risk_match = re.search(r"Risk(?:\s+Mitigation)?:\s*\n?(.*?)(?:\n\n|Implementation|Validation|Performance|$)", body, re.DOTALL)
            if risk_match:
                risk_text = risk_match.group(1).strip()[:300]
                if risk_text and not risk_text.upper() in ("ZERO", "LOW", "MEDIUM", "HIGH"):
                    rec["risk_mitigation"] = risk_text

            recommendations.append(rec)

    else:
        # Fallback: bullet points
        bullet_pattern = r"[-•]\s*(?:Action|Recommendation)?\s*:?\s*([^\n$]+?)(?:\(?\s*save\s*\$?([0-9,]+\.?\d*)/month\)?|$)"
        bullet_matches = list(re.finditer(bullet_pattern, text, re.IGNORECASE))

        for idx, match in enumerate(bullet_matches):
            rec = {
                "action_number": idx + 1,
                "action": match.group(1).strip() if match.group(1) else "",
                "estimated_monthly_savings": 0,
                "implementation_steps": [],
                "validation_steps": [],
            }

            if match.group(2):
                try:
                    rec["estimated_monthly_savings"] = float(match.group(2).replace(",", ""))
                except ValueError:
                    pass

            if rec["action"]:
                recommendations.append(rec)

    return recommendations


def _get_aws_best_practices_context(pkg_dict: Optional[dict] = None) -> str:
    """Get AWS FinOps best practices from Graph RAG document index.

    Queries the DocIndexer with architecture-relevant terms.  Falls back
    to a hardcoded summary if the index is unavailable.
    """
    try:
        from src.rag.doc_indexer import get_doc_index
        idx = get_doc_index()

        # Build query terms from the architecture
        query_terms = ["AWS cost optimization best practices reserved instances"]
        if pkg_dict:
            # Add service types from the architecture
            for svc in (pkg_dict.get("top_expensive") or [])[:3]:
                name = svc.get("name", "")
                stype = svc.get("type", "")
                if stype:
                    query_terms.append(f"{stype} cost optimization")
                elif name:
                    query_terms.append(f"{name} cost optimization")

        context = idx.get_best_practices_context(query_terms, top_k=6)
        if context and len(context) > 100:
            logger.info("Graph RAG docs: retrieved %d chars of best practices", len(context))
            return context
    except Exception as e:
        logger.warning("DocIndexer unavailable, using fallback: %s", e)

    # Fallback
    return """AWS Cost Optimization Best Practices:
- Right-sizing: Match instance types to actual utilization (target 60-80% CPU)
- Reserved Capacity: Use RI or Savings Plans for predictable workloads (20-40% discount)
- Managed Services: RDS vs self-hosted, Lambda vs EC2 for variable loads
- Storage Optimization: Use appropriate storage classes (S3 Standard → Glacier/Archive)
- Data Transfer: Minimize cross-AZ and cross-region transfers
- Compute Consolidation: Consolidate workloads to reduce overhead
- Monitoring: Use Cost Anomaly Detection and Trusted Advisor
"""


def _build_service_inventory(graph_data: dict) -> str:
    """Build a detailed, per-resource inventory from the raw architecture JSON.

    This gives the LLM the exact resource IDs, instance types, costs,
    and configuration it needs to make specific recommendations.
    """
    services = graph_data.get("services") or graph_data.get("nodes") or []
    if not services:
        return "(No service inventory available)"

    region = graph_data.get("metadata", {}).get("region", "unknown")
    total_cost = graph_data.get("metadata", {}).get("total_cost_monthly", 0)

    lines = [
        f"TOTAL ARCHITECTURE COST: ${total_cost:,.2f}/month | Region: {region}",
        "",
        "RESOURCE ID               | AWS SERVICE                  | INSTANCE TYPE | COST/MO   | ENV        | AUTO-SCALE | MULTI-AZ",
        "--------------------------|------------------------------|---------------|-----------|------------|------------|--------",
    ]

    # Sort by cost descending so top spenders come first
    sorted_svcs = sorted(services, key=lambda s: s.get("cost_monthly", 0), reverse=True)

    for svc in sorted_svcs:
        rid = svc.get("id", "?")
        aws_svc = svc.get("aws_service", svc.get("type", "?"))
        attrs = svc.get("attributes", svc.get("properties", {}))
        inst_type = attrs.get("instance_type", svc.get("instance_type", "-"))
        cost = svc.get("cost_monthly", 0)
        env = svc.get("environment", "-")
        auto_scale = "Yes" if attrs.get("auto_scaling") else "No"
        multi_az = "Yes" if attrs.get("multi_az") else "No"

        lines.append(
            f"{rid:<26}| {aws_svc:<29}| {inst_type:<14}| ${cost:<9,.2f}| {env:<11}| {auto_scale:<11}| {multi_az}"
        )

    # Add dependencies summary
    deps = graph_data.get("dependencies", graph_data.get("edges", []))
    if deps:
        lines.append("")
        lines.append(f"DEPENDENCIES ({len(deps)} total):")
        for d in deps[:15]:
            src = d.get("source", d.get("from", "?"))
            tgt = d.get("target", d.get("to", "?"))
            dtype = d.get("type", d.get("dep_type", "calls"))
            lines.append(f"  {src} → {tgt} ({dtype})")
        if len(deps) > 15:
            lines.append(f"  ... and {len(deps) - 15} more")

    return "\n".join(lines)


def _extract_cur_metrics(pkg: dict) -> str:
    """Extract CUR metrics from context package."""
    lines = ["CUR Metrics Available:"]
    
    # Top expensive services
    if pkg.get("top_expensive"):
        lines.append("Top Expensive Services (from CUR):")
        for item in pkg["top_expensive"][:5]:
            lines.append(f"  - {item.get('name')}: ${item.get('cost_monthly'):,.2f}/mo")
    
    # Cost outliers
    if pkg.get("cost_outliers"):
        lines.append("\nCost Outliers (>2x expected):")
        for item in pkg["cost_outliers"][:5]:
            lines.append(f"  - {item.get('name')}: ${item.get('actual_cost'):,.2f} (expected ${item.get('expected_cost'):,.2f})")
    
    # Waste
    if pkg.get("waste_detected"):
        lines.append(f"\nWaste Detected: ${pkg.get('total_waste_monthly', 0):,.2f}/month")
    
    return "\n".join(lines)


def _get_graph_theory_context(pkg: dict) -> str:
    """Extract graph theory analysis from context package.

    Formats centrality rankings, PageRank, clustering coefficients,
    SPOFs, cascade risks, and articulation points for the LLM.
    """
    lines = []

    # ── Bottlenecks (highest betweenness centrality) ──
    bottlenecks = pkg.get("bottleneck_nodes") or []
    if bottlenecks:
        lines.append("TOP BOTTLENECKS (by betweenness centrality):")
        for i, b in enumerate(bottlenecks[:8], 1):
            name = b.get("name", b.get("node_id", "?"))
            cent = b.get("centrality", b.get("betweenness_centrality", 0))
            pr = b.get("pagerank", 0)
            cost = b.get("cost_monthly", 0)
            lines.append(
                f"  {i}. {name}: centrality={cent:.4f}, "
                f"PageRank={pr:.4f}, cost=${cost:,.2f}/mo"
            )

    # ── Critical services (high risk) ──
    critical = pkg.get("critical_services") or []
    if critical:
        lines.append("\nCRITICAL SERVICES (high-risk nodes):")
        for svc in critical[:8]:
            name = svc.get("name", "?")
            risk = svc.get("risk_level", "unknown")
            deps = svc.get("dependent_count", svc.get("in_degree", 0))
            cost = svc.get("cost_monthly", 0)
            lines.append(
                f"  - {name}: risk={risk}, dependents={deps}, "
                f"cost=${cost:,.2f}/mo"
            )

    # ── SPOFs (Single Points of Failure) ──
    spofs = pkg.get("single_points_of_failure") or pkg.get("spof_nodes") or []
    if spofs:
        lines.append(f"\nSINGLE POINTS OF FAILURE ({len(spofs)} detected):")
        for s in spofs[:5]:
            if isinstance(s, dict):
                lines.append(f"  - {s.get('name', '?')}: {s.get('in_degree', 0)} dependents")
            else:
                lines.append(f"  - {s}")

    # ── Cascade risks ──
    cascades = pkg.get("cascade_risks") or []
    if cascades:
        lines.append("\nCASCADE FAILURE RISKS:")
        for c in cascades[:5]:
            name = c.get("name", "?")
            risk = c.get("risk", c.get("cascade_risk", "unknown"))
            deps = c.get("dependents", 0)
            lines.append(f"  - {name}: cascade_risk={risk}, affects {deps} services")

    # ── Graph metrics ──
    density = pkg.get("graph_density", 0)
    components = pkg.get("connected_components", pkg.get("components", 0))
    is_dag = pkg.get("is_dag", None)
    if density or components:
        lines.append(f"\nGRAPH METRICS: density={density}, "
                     f"components={components}, DAG={is_dag}")

    # ── Anti-patterns from graph analysis ──
    anti_patterns = pkg.get("anti_patterns") or []
    if anti_patterns:
        lines.append("\nARCHITECTURAL ANTI-PATTERNS (from graph topology):")
        for ap in anti_patterns[:5]:
            if isinstance(ap, dict):
                lines.append(f"  - {ap.get('pattern', '?')}: {ap.get('description', '')}")
            else:
                lines.append(f"  - {ap}")

    return "\n".join(lines) if lines else "(No graph theory data available)"


def _get_monte_carlo_context(pkg: dict) -> str:
    """Extract Monte Carlo simulation predictions from context package.

    Formats cost overrun probabilities, p50/p95/p99 projections,
    and risk scenarios for the LLM.
    """
    lines = []

    sim = pkg.get("monte_carlo") or pkg.get("simulation_results") or {}
    if not sim:
        # Try to find simulation data nested in other sections
        risk = pkg.get("risk_assessment") or {}
        sim = risk.get("monte_carlo") or {}

    if not sim:
        return "(No Monte Carlo simulation data available)"

    lines.append("MONTE CARLO COST SIMULATION RESULTS:")

    # Cost projections
    projections = sim.get("cost_projections") or sim.get("projections") or {}
    if projections:
        lines.append("Cost Projections (next 90 days):")
        for label in ["p50", "p75", "p90", "p95", "p99"]:
            val = projections.get(label)
            if val is not None:
                lines.append(f"  - {label.upper()}: ${val:,.2f}/month")

    # Overrun probability
    overrun = sim.get("overrun_probability") or sim.get("budget_overrun_prob")
    if overrun is not None:
        lines.append(f"\nBudget Overrun Probability: {overrun:.1%}")

    # Risk scenarios
    scenarios = sim.get("risk_scenarios") or sim.get("scenarios") or []
    if scenarios:
        lines.append("\nRisk Scenarios:")
        for s in scenarios[:5]:
            if isinstance(s, dict):
                name = s.get("name", s.get("scenario", "?"))
                impact = s.get("cost_impact", s.get("impact", 0))
                prob = s.get("probability", 0)
                lines.append(f"  - {name}: +${impact:,.2f}/mo ({prob:.0%} probability)")
            else:
                lines.append(f"  - {s}")

    # Iterations
    iters = sim.get("iterations") or sim.get("num_simulations")
    if iters:
        lines.append(f"\nSimulation: {iters} iterations")

    return "\n".join(lines) if lines else "(No Monte Carlo simulation data available)"


def _render_context_text_from_dict(pkg: dict) -> str:
    """Render context package dict to text (mirrors ContextAssembler.render_context_text)."""
    lines = []

    # Section 1
    lines.append("=" * 55)
    lines.append("SECTION 1: ARCHITECTURE OVERVIEW")
    lines.append("=" * 55)
    lines.append(f"Architecture: {pkg.get('architecture_name', 'Unknown')}")
    lines.append(f"Total Services: {pkg.get('total_services', 0)}")
    lines.append(f"Total Monthly Cost: ${pkg.get('total_cost_monthly', 0):,.2f}")
    lines.append(f"Total Dependencies: {pkg.get('total_dependencies', 0)} edges")
    lines.append(f"Average Centrality: {pkg.get('avg_centrality', 0):.4f}")
    lines.append(f"Architecture Type: {pkg.get('architecture_type', 'microservices')}")
    lines.append("")
    lines.append("Service Breakdown by Type:")
    for t, info in pkg.get("service_breakdown", {}).items():
        cnt = info.get("count", 0) if isinstance(info, dict) else 0
        cost = info.get("cost", 0) if isinstance(info, dict) else 0
        lines.append(f"  - {t}: {cnt} services, ${cost:,.2f} total")
    cross_az = pkg.get("cross_az_dependency_count", 0)
    if cross_az > 0:
        lines.append(f"\nCross-AZ dependencies: {cross_az}")
    lines.append("")

    # Section 2
    lines.append("=" * 55)
    lines.append("SECTION 2: CRITICAL SERVICES (Top 5 by Centrality)")
    lines.append("=" * 55)
    for i, svc in enumerate(pkg.get("critical_services", []), 1):
        lines.append(f"\n{i}. {svc.get('name', '?')} (centrality {svc.get('centrality', 0):.4f})")
        lines.append(f"   Type: {svc.get('type', '?')}, Cost: ${svc.get('cost_monthly', 0):,.2f}/mo ({svc.get('cost_share', 0):.1f}%)")
        lines.append(f"   In-degree: {svc.get('in_degree', 0)}, Out-degree: {svc.get('out_degree', 0)}")
        lines.append(f"   Health: {svc.get('health_score', 100):.0f}%, Risk: {svc.get('risk_level', 'low')}")
        lines.append(f"   Cascade risk: {svc.get('cascading_failure_risk', 'low')}")
        if svc.get("single_point_of_failure"):
            lines.append("   ** SINGLE POINT OF FAILURE **")
        for p in svc.get("dependency_patterns", [])[:3]:
            lines.append(f"   Pattern: {p}")
    lines.append("")

    # Section 3
    lines.append("=" * 55)
    lines.append("SECTION 3: COST ANALYSIS")
    lines.append("=" * 55)
    lines.append("\nTop Expensive Services:")
    for i, h in enumerate(pkg.get("top_expensive", [])[:5], 1):
        lines.append(f"  {i}. {h.get('name', '?')}: ${h.get('cost_monthly', 0):,.2f}")
    if pkg.get("cost_outliers"):
        lines.append("\nCost Outliers (>2x expected):")
        for o in pkg["cost_outliers"]:
            lines.append(f"  - {o['name']}: Expected ${o.get('expected_cost', 0):,.2f}, Actual ${o.get('actual_cost', 0):,.2f} ({o.get('ratio', 0)}x)")
            lines.append(f"    Reason: {o.get('reason', '')}")
    if pkg.get("waste_detected"):
        lines.append(f"\nTotal Waste: ${pkg.get('total_waste_monthly', 0):,.2f}/month")
        for w in pkg["waste_detected"]:
            lines.append(f"  - {w['category']}: ${w.get('estimated_monthly', 0):,.2f}/mo — {w.get('description', '')}")
    lines.append("")

    # Section 4
    lines.append("=" * 55)
    lines.append("SECTION 4: ARCHITECTURAL ANTI-PATTERNS")
    lines.append("=" * 55)
    for i, ap in enumerate(pkg.get("anti_patterns", []), 1):
        lines.append(f"\n  {i}. {ap.get('name', '?')} ({ap.get('severity', '?').upper()})")
        lines.append(f"     {ap.get('description', '')}")
        lines.append(f"     Fix: {ap.get('recommendation', '')}")
        sav = ap.get("estimated_savings", 0)
        if sav > 0:
            lines.append(f"     Estimated savings: ${sav:,.2f}/month")
    lines.append("")

    # Section 5
    lines.append("=" * 55)
    lines.append("SECTION 5: RISK ASSESSMENT")
    lines.append("=" * 55)
    for i, r in enumerate(pkg.get("risks", []), 1):
        lines.append(f"\n  {i}. {r.get('name', '?')} ({r.get('severity', '?').upper()})")
        lines.append(f"     {r.get('description', '')}")
        lines.append(f"     Impact: {r.get('impact', '')}")
    lines.append("")

    # Section 6
    lines.append("=" * 55)
    lines.append("SECTION 6: BEHAVIORAL ANOMALIES")
    lines.append("=" * 55)
    for i, a in enumerate(pkg.get("anomalies", [])[:10], 1):
        lines.append(f"\n  {i}. {a.get('name', '?')} on {a.get('node_name', '?')} ({a.get('severity', '?').upper()})")
        lines.append(f"     {a.get('description', '')}")
    lines.append("")

    # Section 7
    lines.append("=" * 55)
    lines.append("SECTION 7: HISTORICAL TRENDS")
    lines.append("=" * 55)
    ct = pkg.get("cost_trends", {})
    if ct:
        lines.append(f"  Data: {ct.get('data_points', 0)} days")
        lines.append(f"  Growth: {ct.get('growth_rate_pct', 0):.1f}%, Trend: {ct.get('trend', 'N/A')}")
    gt = pkg.get("growth_trajectory", {})
    if gt:
        lines.append(f"  Current: ${gt.get('current_monthly', 0):,.2f}/mo → Projected: ${gt.get('projected_90d', 0):,.2f}/mo")
    if not ct and not gt:
        lines.append("  Insufficient data for trend analysis")
    lines.append("")

    # Section 8
    lines.append("=" * 55)
    lines.append("SECTION 8: DEPENDENCY ANALYSIS")
    lines.append("=" * 55)
    for i, d in enumerate(pkg.get("critical_dependencies", [])[:5], 1):
        lines.append(f"  {i}. {d.get('source', '?')} → {d.get('target', '?')} (impacts {d.get('impact_count', 0)})")
    circ = pkg.get("circular_dependencies", [])
    if circ:
        for cd in circ:
            lines.append(f"  Circular: {cd.get('description', '')}")
    orph = pkg.get("orphaned_services", [])
    if orph:
        lines.append(f"  Orphaned: {', '.join(orph)}")
    for dc in pkg.get("deep_chains", []):
        lines.append(f"  Deep chain ({dc.get('depth', 0)}-hop): {dc.get('chain', '')}")
    lines.append("")

    return "\n".join(lines)
