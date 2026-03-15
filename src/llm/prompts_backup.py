"""
LLM Prompt Templates for FinOps AI
===================================
HARDENED prompts for structured cost optimization recommendations.
LLM MUST produce exact output format — no hallucinations, no fallbacks.
"""

# ─── HARDENED System Prompt (LLM is the sole source) ────────────────

RECOMMENDATION_SYSTEM_PROMPT = """You are a CERTIFIED AWS FinOps Architect and Cost Optimization Specialist.

CRITICAL RULES (NON-NEGOTIABLE):
================================================================================
1. ONLY output structured text in the exact format shown below
2. NEVER hallucinate services, costs, or metrics — ONLY use provided data
3. NEVER suggest changes you cannot quantify with the CUR data provided
4. NEVER make recommendations without explicit cost calculations
5. If you cannot confidently recommend a change, OMIT that recommendation
6. Each recommendation MUST have: Resource ID, Current Cost, Savings Calc, Implementation Steps

OUTPUT FORMAT (STRICT):
================================================================================
COST OPTIMIZATION RECOMMENDATION #1
═══════════════════════════════════════════════════════════

RESOURCE IDENTIFICATION
- Resource ID: [from graph data]
- Full ARN: [construct from region/account/resource type]
- Service: [AWS service name]
- Current Instance/Config: [exact current configuration]
- Region: [AWS region]
- Availability Zone: [AZ if applicable]
- Tags: [key=value pairs or "None"]

CURRENT COST BREAKDOWN (from CUR)
┌──────────────────────────────┬─────────────┬──────────┐
│ CUR Line Item                │ Usage       │ Cost     │
├──────────────────────────────┼─────────────┼──────────┤
[Each CUR line item as one table row]
├──────────────────────────────┼─────────────┼──────────┤
│ TOTAL MONTHLY COST           │             │ $X,XXX   │
└──────────────────────────────┴─────────────┴──────────┘

Cost Trend (90 days):
- Days 1-30: $X,XXX
- Days 31-60: $X,XXX  
- Days 61-90: $X,XXX
- Growth: +XX% or -XX%
- 90-day projection: $X,XXX

INEFFICIENCIES DETECTED
ISSUE #1: [Title] (SEVERITY: HIGH|MEDIUM|LOW)
Evidence: [Specific metrics from CloudWatch/CUR]
Assessment: [Root cause and impact]

ISSUE #2: [if exists]
[same structure]

COMPREHENSIVE RECOMMENDATIONS

RECOMMENDATION #1: [Action Title]
Priority: P0 | Action: [Specific action]
Current: [Current configuration with costs]
New: [New configuration with costs]
Savings: $X,XXX/month (~$X,XXX/year)
Implementation:
1. [Specific AWS Console or CLI step]
2. [Next step]
3. [Validation step]
Performance Impact: [Detailed impact analysis]
Risk: [Risk level and mitigation]

RECOMMENDATION #2: [if another recommendation exists]
[same structure]

SUMMARY
Total Monthly Savings: $X,XXX
Total Annual Savings: $X,XXX
Return on Investment: [if applicable]

================================================================================
GROUNDING RULES:
- Use ONLY services and costs present in the context package
- All costs come from either: (a) CUR line items, (b) computed metrics, (c) AWS pricing docs
- All recommendations must reference specific graph nodes or CUR items
- Quantify ALL claims with data

AWS BEST PRACTICES FROM GRAPHRAG:
[Will be injected: AWS FinOps well-architected review, cost optimization patterns]

YOUR TASK:
Analyze the 8-section architecture context package below.
Generate 3-5 cost optimization recommendations.
Use ONLY the provided data — NEVER invent metrics or services.
Format output EXACTLY as shown above.
"""


# ─── User Prompt (Multi-source context) ─────────────────────────────

RECOMMENDATION_USER_PROMPT = """
ARCHITECTURE CONTEXT PACKAGE (8 SECTIONS)
════════════════════════════════════════════════════════════════

{context_text}

AWS BEST PRACTICES FROM FINOPS GUIDELINES
════════════════════════════════════════════════════════════════
{aws_best_practices}

CUR DATA AND COST METRICS
════════════════════════════════════════════════════════════════
{cur_metrics}

GRAPH ANALYSIS NARRATIVES (Per-Node Context)
════════════════════════════════════════════════════════════════
{narratives}

════════════════════════════════════════════════════════════════
GENERATE RECOMMENDATIONS NOW:
════════════════════════════════════════════════════════════════

Analyze all 4 sources above.
For each service with high cost relative to utilization:
1. Identify the resource in the graph data
2. Find its CUR line items
3. Apply AWS best practices
4. Calculate specific monthly/annual savings
5. Provide exact implementation steps

Use ONLY data from the 4 sources above.
Never hallucinate metrics, resources, or costs.
Format output EXACTLY as specified in system prompt.

BEGIN OUTPUT:
"""


# ─── Deterministic fallback templates ──────────────────────────────

def build_deterministic_recommendations(context_package) -> list:
    """
    Generate recommendation cards from the context package
    without calling the LLM. Used as fallback when Ollama is unavailable.
    """
    pkg = context_package if isinstance(context_package, dict) else _asdict_safe(context_package)
    cards = []
    priority = 0

    # 1. Right-sizing from cost outliers
    for outlier in pkg.get("cost_outliers", [])[:3]:
        priority += 1
        savings = round(outlier["actual_cost"] - outlier["expected_cost"], 2)
        cards.append({
            "title": f"Right-size {outlier['name']}",
            "priority": priority,
            "severity": "high" if outlier["ratio"] > 3 else "medium",
            "category": "right-sizing",
            "resource_identification": {
                "service_name": outlier["name"],
                "service_type": outlier["type"],
                "region": "",
                "tags": {},
                "current_config": f"Currently {outlier['ratio']}x more expensive than type average",
            },
            "cost_breakdown": {
                "current_monthly": outlier["actual_cost"],
                "line_items": [
                    {"item": "Current cost", "usage": "monthly", "cost": outlier["actual_cost"]},
                    {"item": "Type average", "usage": "monthly", "cost": outlier["expected_cost"]},
                ],
            },
            "inefficiencies": [
                {
                    "id": 1,
                    "description": outlier["reason"],
                    "severity": "high",
                    "evidence": (
                        f"Actual cost ${outlier['actual_cost']:.2f} vs "
                        f"expected ${outlier['expected_cost']:.2f} ({outlier['ratio']}x)"
                    ),
                }
            ],
            "recommendations": [
                {
                    "action": (
                        f"Evaluate right-sizing {outlier['name']} to reduce cost "
                        f"from ${outlier['actual_cost']:.2f} to closer to ${outlier['expected_cost']:.2f}"
                    ),
                    "estimated_monthly_savings": savings,
                    "confidence": "medium",
                    "implementation_steps": [
                        f"1. Review current resource configuration for {outlier['name']}",
                        "2. Analyze CloudWatch metrics for actual utilization patterns",
                        "3. Identify appropriate smaller instance type or capacity",
                        "4. Schedule maintenance window for resize",
                        "5. Monitor for 48 hours post-change",
                    ],
                    "performance_impact": (
                        "Low if current utilization matches outlier analysis"
                    ),
                    "risk_mitigation": "Create snapshot/backup before resizing",
                    "validation_steps": [
                        "Monitor CPU, memory, and I/O after resize",
                        "Verify response times stay within SLA",
                        "Check error rates in CloudWatch",
                    ],
                }
            ],
            "total_estimated_savings": savings,
            "implementation_complexity": "medium",
            "risk_level": "low",
        })

    # 2. Waste elimination
    for waste in pkg.get("waste_detected", [])[:2]:
        priority += 1
        cards.append({
            "title": f"Eliminate {waste['category']}",
            "priority": priority,
            "severity": "high" if waste["estimated_monthly"] > 50 else "medium",
            "category": "waste-elimination",
            "resource_identification": {
                "service_name": ", ".join(waste.get("affected_nodes", [])[:3]) or "Multiple",
                "service_type": "various",
                "region": "",
                "tags": {},
                "current_config": waste["description"],
            },
            "cost_breakdown": {
                "current_monthly": waste["estimated_monthly"],
                "line_items": [
                    {"item": waste["category"], "usage": "ongoing", "cost": waste["estimated_monthly"]},
                ],
            },
            "inefficiencies": [
                {
                    "id": 1,
                    "description": waste["description"],
                    "severity": "high",
                    "evidence": f"${waste['estimated_monthly']:.2f}/month identified as waste",
                }
            ],
            "recommendations": [
                {
                    "action": f"Address {waste['category'].lower()} to save ${waste['estimated_monthly']:.2f}/month",
                    "estimated_monthly_savings": waste["estimated_monthly"],
                    "confidence": "medium",
                    "implementation_steps": [
                        "1. Identify affected resources using tagging and Cost Explorer",
                        "2. Validate waste classification with workload owners",
                        "3. Implement optimization (resize, terminate, or reconfigure)",
                        "4. Set up billing alerts for regression detection",
                    ],
                    "performance_impact": "None for true waste; validate usage patterns first",
                    "risk_mitigation": "Tag resources as candidates before termination",
                    "validation_steps": [
                        "Verify cost reduction in next billing cycle",
                        "Check no services were impacted",
                    ],
                }
            ],
            "total_estimated_savings": waste["estimated_monthly"],
            "implementation_complexity": "low",
            "risk_level": "low",
        })

    # 3. Anti-pattern fixes
    for ap in pkg.get("anti_patterns", [])[:2]:
        if ap.get("estimated_savings", 0) > 0:
            priority += 1
            cards.append({
                "title": f"Fix: {ap['name']}",
                "priority": priority,
                "severity": ap["severity"],
                "category": "architecture",
                "resource_identification": {
                    "service_name": ", ".join(ap.get("affected_nodes", [])[:3]) or "Architecture-wide",
                    "service_type": "architecture",
                    "region": "",
                    "tags": {},
                    "current_config": ap["description"],
                },
                "cost_breakdown": {
                    "current_monthly": ap.get("estimated_savings", 0),
                    "line_items": [
                        {"item": "Anti-pattern overhead", "usage": "ongoing", "cost": ap.get("estimated_savings", 0)},
                    ],
                },
                "inefficiencies": [
                    {
                        "id": 1,
                        "description": ap["description"],
                        "severity": ap["severity"],
                        "evidence": "Detected via architectural anti-pattern analysis",
                    }
                ],
                "recommendations": [
                    {
                        "action": ap["recommendation"],
                        "estimated_monthly_savings": ap.get("estimated_savings", 0),
                        "confidence": "medium",
                        "implementation_steps": [
                            f"1. Map current {ap['name']} pattern",
                            "2. Design target architecture addressing the anti-pattern",
                            "3. Implement changes in staging first",
                            "4. Roll out to production with feature flags",
                        ],
                        "performance_impact": "Positive — reduces latency and cost simultaneously",
                        "risk_mitigation": "Stage rollout, monitor metrics at each step",
                        "validation_steps": [
                            "Compare latency before and after",
                            "Verify cost reduction in next billing cycle",
                        ],
                    }
                ],
                "total_estimated_savings": ap.get("estimated_savings", 0),
                "implementation_complexity": "high",
                "risk_level": "medium",
            })

    # 4. Cascade risk mitigation (critical services)
    for svc in pkg.get("critical_services", [])[:2]:
        if svc.get("cascading_failure_risk") in ("critical", "high"):
            priority += 1
            cards.append({
                "title": f"Mitigate cascade risk: {svc['name']}",
                "priority": priority,
                "severity": "critical" if svc["cascading_failure_risk"] == "critical" else "high",
                "category": "architecture",
                "resource_identification": {
                    "service_name": svc["name"],
                    "service_type": svc["type"],
                    "region": "",
                    "tags": {},
                    "current_config": (
                        f"Centrality {svc['centrality']}, "
                        f"{svc.get('dependents_count', 0)} dependents"
                    ),
                },
                "cost_breakdown": {
                    "current_monthly": svc["cost_monthly"],
                    "line_items": [
                        {"item": "Service cost", "usage": "monthly", "cost": svc["cost_monthly"]},
                    ],
                },
                "inefficiencies": [
                    {
                        "id": 1,
                        "description": (
                            f"Single bottleneck with {svc.get('dependents_count', 0)} "
                            f"dependent services"
                        ),
                        "severity": "critical",
                        "evidence": f"Betweenness centrality: {svc['centrality']}",
                    }
                ],
                "recommendations": [
                    {
                        "action": (
                            f"Add redundancy and circuit breakers to {svc['name']}"
                        ),
                        "estimated_monthly_savings": 0,
                        "confidence": "high",
                        "implementation_steps": [
                            f"1. Deploy {svc['name']} across multiple AZs",
                            "2. Add circuit breaker pattern to all callers",
                            "3. Implement health-check-based routing",
                            "4. Configure auto-scaling based on request rate",
                            "5. Add fallback/degraded-mode responses",
                        ],
                        "performance_impact": "Improved — reduced single-point failure risk",
                        "risk_mitigation": "Staged rollout with canary deployments",
                        "validation_steps": [
                            "Chaos test: terminate one instance, verify failover",
                            "Load test: 2x traffic, verify scaling",
                            "Monitor error rates across dependent services",
                        ],
                    }
                ],
                "total_estimated_savings": 0,
                "implementation_complexity": "high",
                "risk_level": "medium",
            })

    # Sort by savings (highest first), then by severity
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    cards.sort(key=lambda c: (
        -c.get("total_estimated_savings", 0),
        sev_order.get(c.get("severity", "low"), 4)
    ))

    # Reassign priorities
    for i, card in enumerate(cards, 1):
        card["priority"] = i

    return cards


def _asdict_safe(obj):
    """Convert dataclass to dict safely."""
    try:
        from dataclasses import asdict
        return asdict(obj)
    except Exception:
        return obj if isinstance(obj, dict) else {}
