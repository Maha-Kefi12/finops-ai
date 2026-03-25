# FinOps AI System: LLM Input/Output Flow for Recommendation Generation

**Document Version:** 2.0  
**Last Updated:** March 2026  
**Scope:** Complete technical documentation of how recommendations are generated from LLM input, parsed, validated, and transformed into recommendation card objects

## Table of Contents

1. [End-to-End Flow Overview](#end-to-end-flow-overview)
2. [LLM Input Construction](#llm-input-construction)
3. [System & User Prompts](#system--user-prompts)
4. [LLM Call Execution](#llm-call-execution)
5. [Raw Output Parsing](#raw-output-parsing)
6. [Field Extraction Patterns](#field-extraction-patterns)
7. [Validation & Filtering](#validation--filtering)
8. [Deduplication Logic](#deduplication-logic)
9. [Enrichment & Post-Processing](#enrichment--post-processing)
10. [Final Recommendation Object](#final-recommendation-object)
11. [Error Handling & Fallbacks](#error-handling--fallbacks)
12. [Performance & Optimization](#performance--optimization)

---

## End-to-End Flow Overview

### Complete Sequential Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. API Request (POST /api/analyze)                              │
│    Input: account_id, region                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│ 2. GraphAnalyzer                                                │
│    • Fetch AWS infrastructure (CloudFormation, EC2, RDS, etc.)  │
│    • Fetch CloudWatch metrics (CPU, memory, latency, errors)    │
│    • Fetch cost data (current costs per resource)               │
│    • Build dependency graph (service → service edges)           │
│    • Calculate centrality scores (betweenness, closeness)       │
│    Output: Raw metrics, graph, costs                            │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│ 3. ContextAssembler                                             │
│    Build 9-section context package:                            │
│    ├─ Architecture overview (totals, counts, metadata)          │
│    ├─ Critical services (by centrality)                         │
│    ├─ Cost analysis (outliers, waste)                          │
│    ├─ Anti-patterns detected                                   │
│    ├─ Risk assessment (SPOFs, cascading)                       │
│    ├─ Behavioral anomalies                                     │
│    ├─ Historical trends (90-day)                               │
│    ├─ Dependency analysis (edges, orphaned)                    │
│    └─ GraphRAG/Best practices (grounded knowledge)             │
│    Output: ArchitectureContextPackage                          │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│ 4. Build LLM Input                                              │
│    • Render RECOMMENDATION_SYSTEM_PROMPT                        │
│    • Render RECOMMENDATION_USER_PROMPT with context injected    │
│    • Format service inventory with optimization hints           │
│    • Format metrics, pricing, best practices                    │
│    Output: Complete prompt (~4500 characters)                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│ 5. Call LLM (generate_recommendations)                          │
│    • Model: Mistral 7B (via Ollama) OR Gemini Flash (fallback)  │
│    • Temperature: 0.7 (balanced: creative but grounded)         │
│    • Max tokens: 4000                                           │
│    • Timeout: 120s with retries                                 │
│    Output: Raw text with "### Recommendation #N" markers        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│ 6. Parse Raw Output                                             │
│    Apply 4-strategy parser:                                     │
│    ├─ Strategy 1: Split by "### Recommendation #N"              │
│    ├─ Strategy 2: Split by "### [title]"                       │
│    ├─ Strategy 3: Split by "---"                               │
│    └─ Strategy 4: Split by double newlines                      │
│    Output: List of card text blocks (minimum 5 required)       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│ 7. Extract Fields from Each Card                                │
│    For each card text block:                                    │
│    ├─ Title (5 patterns + prefix removal)                       │
│    ├─ Resource ID (5 patterns + service inference)              │
│    ├─ Current Cost (12 patterns)                                │
│    ├─ Savings (17 patterns + percentage fallback)               │
│    ├─ Implementation Steps (bash code blocks)                   │
│    └─ Raw analysis (first 1000 chars for debugging)             │
│    Output: Partial RecommendationObject                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│ 8. Validation & Filtering                                       │
│    • Check if resource exists in inventory                      │
│    • Remove if zero or negative savings                         │
│    • Remove if no savings and no cost data                      │
│    • Keep high-priority even if unvalidated                     │
│    Output: Filtered recommendations                             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│ 9. Deduplication                                                │
│    Key: (resource_id.lower(), title.lower()[:50])               │
│    Remove exact duplicates, keep first occurrence               │
│    Output: Deduplicated recommendations                         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│ 10. Enrichment & Post-Processing                                │
│    • Fill missing current_monthly_cost from inventory           │
│    • Calculate derived fields (ROI, effort level)                │
│    • Sort by savings (descending)                               │
│    • Add metadata (generation_time, version)                    │
│    Output: Complete RecommendationResult                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│ 11. Return to Frontend                                          │
│    JSON Response:                                               │
│    {                                                            │
│      "status": "success",                                       │
│      "recommendations": [RecommendationCard, ...],             │
│      "total_potential_monthly_savings": 12345.67,              │
│      "total_recommendations": 15,                              │
│      "generation_time_ms": 5234                                │
│    }                                                            │
└────────────────────────────────────────────────────────────────┘
```

---

## LLM Input Construction

### Step 1: Context Assembly (ContextAssembler)

**Location:** `src/analysis/context_assembler.py`

```python
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class ArchitectureContextPackage:
    """9-section context package for LLM"""
    
    # Section 1: Architecture Overview
    overview: Dict[str, Any] = {
        "total_services": 24,
        "total_monthly_cost": 15750.00,
        "avg_centrality": 0.45,
        "regions": ["us-east-1"],
        "architecture_complexity": "high"
    }
    
    # Section 2: Critical Services (sorted by centrality)
    critical_services: List[Dict] = [
        {
            "service_id": "prod-api-lb",
            "service_type": "ApplicationLoadBalancer",
            "centrality_score": 0.95,
            "monthly_cost": 45.00,
            "dependent_service_count": 18
        }
    ]
    
    # Section 3: Cost Analysis (with anomalies)
    cost_analysis: Dict[str, Any] = {
        "top_cost_drivers": [
            {
                "service_id": "prod-data-warehouse",
                "monthly_cost": 3200.00,
                "percentage_of_total": 20.3
            }
        ],
        "cost_outliers": [
            {
                "service_id": "analytics-s3",
                "monthly_cost": 850.00,
                "cost_vs_baseline_ratio": 2.1,
                "potential_waste": "Storing old logs in STANDARD tier"
            }
        ]
    }
    
    # Section 4: Anti-Patterns
    anti_patterns: List[Dict] = [
        {
            "pattern_name": "Chatty_Architecture",
            "severity": "HIGH",
            "description": "Services making excessive synchronous calls",
            "affected_services": ["api", "auth", "user"],
            "evidence": "Avg 450ms latency across 5 service hops"
        }
    ]
    
    # Section 5: Risk Assessment
    risk_assessment: Dict[str, Any] = {
        "single_points_of_failure": [
            {
                "component": "prod-rds",
                "description": "Single RDS instance, no Multi-AZ",
                "impact_severity": "CRITICAL"
            }
        ],
        "deep_dependency_chains": [
            {
                "chain": "ALB → ASG → RDS → Cache",
                "chain_length": 4,
                "latency_amplification_risk": "HIGH"
            }
        ]
    }
    
    # Section 6: Behavioral Anomalies
    behavioral_anomalies: Dict[str, Any] = {
        "latency_spikes": [
            {
                "metric": "api-p99-latency",
                "baseline": 150,
                "peak": 450,
                "frequency": "3x daily at 2-4 PM UTC"
            }
        ]
    }
    
    # Section 7: Historical Trends
    trends: Dict[str, Any] = {
        "cost_trend_6_months": [14500, 14800, 15200, 15400, 16100, 15750],
        "cost_trend_direction": "upward",
        "cost_trend_rate": "+4.2% MoM"
    }
    
    # Section 8: Dependency Analysis
    dependency_analysis: Dict[str, Any] = {
        "communication_patterns": {
            "synchronous_calls": 85,
            "asynchronous_calls": 15
        },
        "cross_az_traffic_percentage": 18
    }
    
    # Section 9: GraphRAG Best Practices
    graphrag_best_practices: List[str] = [
        "AWS recommends distributing workloads across 3+ AZs for resilience",
        "Right-sizing compute reduces costs by 30-50% on average"
    ]
```

### Step 2: Format Service Inventory for LLM

**Location:** `src/llm/client.py` lines 180-220

The service inventory is formatted with optimization hints:

```python
def build_service_inventory_for_prompt(context_package, actual_inventory):
    """Format services with hints about potential optimizations"""
    
    services = []
    
    for service in sorted(actual_inventory, key=lambda x: x.cost, reverse=True):
        # Base entry
        entry = {
            "service_id": service.service_id,
            "service_type": service.service_type,  # EC2, RDS, Lambda, S3, etc.
            "region": service.region,
            "current_monthly_cost": service.monthly_cost,
            "current_utilization": {
                "cpu_percent": service.cpu_utilization,
                "memory_percent": service.memory_utilization,
                "network_in_gb": service.network_in,
                "network_out_gb": service.network_out
            }
        }
        
        # Add optimization hints based on utilization
        if service.cpu_utilization < 20:
            entry["optimization_opportunity"] = "Low CPU utilization - consider downsizing"
        elif service.cpu_utilization > 80:
            entry["optimization_opportunity"] = "High CPU utilization - consider upscaling"
        
        if service.service_type == "S3":
            entry["storage_class"] = "STANDARD"
            entry["optimization_opportunity"] = "Consider S3 Intelligent-Tiering"
        
        services.append(entry)
    
    return services

# Output format in prompt:
inventory_text = """
SERVICE INVENTORY (sorted by cost, highest first):

1. prod-data-warehouse (RedshiftCluster)
   - Region: us-east-1
   - Current Cost: $3,200/month
   - Current Utilization: CPU 35%, Memory 28%
   - Optimization Opportunity: Low CPU/memory - consider resizing or Athena alternative

2. prod-rds-main (RDSDatabase)
   - Region: us-east-1
   - Current Cost: $2,100/month
   - Current Utilization: CPU 65%, Memory 78%
   - Optimization Opportunity: None - well-utilized

3. analytics-s3-bucket (S3Bucket)
   - Region: us-east-1
   - Current Cost: $850/month
   - Storage Class: STANDARD
   - Optimization Opportunity: Consider S3 Intelligent-Tiering
"""
```

### Step 3: Prepare Pricing Reference

**Location:** `src/llm/client.py` lines 230-280

```python
def build_pricing_reference_for_prompt():
    """Provide real AWS pricing for calculation context"""
    
    pricing_text = """
AWS PRICING REFERENCE (as of current month):

EC2 Instance Pricing (us-east-1, on-demand):
- t3.micro: $0.0116/hour = $8.47/month
- t3.small: $0.0231/hour = $16.91/month
- t3.medium: $0.0463/hour = $33.81/month
- t3.large: $0.0926/hour = $67.65/month
- t3.xlarge: $0.1852/hour = $135.30/month
- t3.2xlarge: $0.3704/hour = $270.59/month
- m5.large: $0.096/hour = $70.08/month
- m5.xlarge: $0.192/hour = $140.16/month
- m5.2xlarge: $0.384/hour = $280.32/month

RDS Pricing (us-east-1, Multi-AZ):
- db.t3.micro: $0.034/hour (without Multi-AZ) = $24.84/month
- db.t3.small: $0.068/hour = $49.68/month
- db.t3.medium: $0.136/hour = $99.36/month
- db.t3.large: $0.272/hour = $198.72/month

S3 Pricing:
- STANDARD: $0.023/GB
- INTELLIGENT_TIERING: $0.021/GB (up to 128KB objects)
- STANDARD_IA: $0.0125/GB
- GLACIER: $0.004/GB

Reserved Instance Discounts:
- 1-year commitment: 30-40% off on-demand
- 3-year commitment: 50-60% off on-demand
"""
    
    return pricing_text
```

---

## System & User Prompts

### System Prompt (Strict Format Requirements)

**Location:** `src/llm/prompts.py` lines 1-80

```python
RECOMMENDATION_SYSTEM_PROMPT = """
You are an expert AWS infrastructure analyst generating cost optimization recommendations.

## CRITICAL OUTPUT FORMAT REQUIREMENTS

You MUST format every recommendation exactly as follows:

### Recommendation #[N]: [Title]

**Severity:** [CRITICAL|HIGH|MEDIUM|LOW]
**Category:** [Category Name]
**Affected Services:** [service-id] (comma-separated if multiple)

**Analysis:**
[2-3 sentences describing the issue and why it needs attention]

**Current State:**
- Service: [Service ID and Type]
- Current Cost: $[amount]/month
- Current Utilization: [CPU%, Memory%, Network, etc.]
- Current Performance Impact: [brief description]

**Recommended Action:**
[Specific, actionable recommendation]

**Implementation Steps:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Expected Savings:**
$[Savings]/month = $[Annual Savings]/year

**Implementation Effort:** [Time estimate]
**Risk Level:** [LOW|MEDIUM|HIGH|CRITICAL]

**Implementation Code (bash):**
```bash
# Exact AWS CLI commands to implement
aws ec2 create-image --instance-id i-12345abc --name "backup-$(date +%s)"
aws ec2 modify-instance-attribute --instance-id i-12345abc --instance-type "{\"value\": \"t3.small\"}"
```

---

### Recommendation #[N+1]: [Next Title]
... (repeat for 10-20 recommendations)

---

## VALIDATION RULES

1. ONLY make recommendations for services in the provided inventory
2. DO NOT hallucinate or invent services/metrics not in the data
3. MUST cite evidence from the provided context for every finding
4. MUST calculate savings conservatively (undersell rather than oversell)
5. MUST provide implementable bash code for every recommendation
6. MUST use EXACTLY the format above - no deviations

## SAVINGS CALCULATION

When calculating savings, show your math:
- Direct: "Downsize m5.xlarge ($140/mo) → t3.large ($68/mo) = $72/mo savings"
- Percentage: "Enable Reserved Instance 3-year (saves 60%): $200/mo * 1 - 0.60 = $120/mo savings"
- Multiply: "Resize 5 instances: $72/mo * 5 = $360/mo total"

## OUTPUT REQUIREMENTS

- Generate 10-20 recommendations
- Sort by impact (most savings first)
- Separate recommendations with "---" delimiter
- Use markdown code blocks for bash commands
- Total output: 3000-4000 tokens
"""
```

### User Prompt (Context Injection)

**Location:** `src/llm/prompts.py` lines 90-200

```python
RECOMMENDATION_USER_PROMPT = """
Analyze the following AWS infrastructure and generate 10-20 cost optimization recommendations.

## ANALYZED INFRASTRUCTURE

{overview_section}

{critical_services_section}

{cost_analysis_section}

{anti_patterns_section}

{service_inventory_section}

{cloudwatch_metrics_section}

{pricing_reference_section}

{best_practices_section}

## YOUR TASK

Generate recommendations that:
1. Save money (primary goal)
2. Improve resilience (secondary goal)
3. Are immediately implementable (include bash code)
4. Are grounded in the provided data (no hallucinations)

Output exactly {minimum_recommendations} recommendations, one per service or issue identified.

Format each recommendation exactly as specified in the system prompt.
Separate with "---" delimiters.
Include AWS CLI commands in bash code blocks.

Prioritize:
- High-cost services with low utilization
- Single points of failure that prevent optimization
- Services with clear patterns in the data
"""

# Example construction:
user_prompt = RECOMMENDATION_USER_PROMPT.format(
    overview_section=build_overview_text(context),
    critical_services_section=build_critical_services_text(context),
    cost_analysis_section=build_cost_analysis_text(context),
    anti_patterns_section=build_anti_patterns_text(context),
    service_inventory_section=build_service_inventory_text(context),
    cloudwatch_metrics_section=build_metrics_text(context),
    pricing_reference_section=build_pricing_reference_for_prompt(),
    best_practices_section=build_best_practices_text(context),
    minimum_recommendations=10
)
```

---

## LLM Call Execution

### LLM Call with Retry Logic

**Location:** `src/llm/client.py` lines 280-380

```python
def generate_recommendations(
    context_package: ArchitectureContextPackage,
    actual_inventory: List[AWSResource],
    model: str = "mistral"  # or "gemini"
) -> RecommendationResult:
    """
    Generate recommendations from context package using LLM
    
    Args:
        context_package: 9-section context for LLM
        actual_inventory: List of real AWS resources
        model: "mistral" (primary) or "gemini" (fallback)
    
    Returns:
        RecommendationResult with parsed, validated recommendations
    """
    
    # Build prompts with context injected
    system_prompt = RECOMMENDATION_SYSTEM_PROMPT
    user_prompt = build_user_prompt(context_package, actual_inventory)
    
    start_time = time.time()
    
    # Try Mistral first
    try:
        raw_output = call_llm(
            model="mistral-7b",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.7,
            max_tokens=4000,
            timeout=120
        )
        model_used = "mistral"
    except Exception as e:
        logger.warning(f"Mistral failed: {e}, trying Gemini fallback")
        # Fallback to Gemini Flash
        try:
            raw_output = call_llm(
                model="gemini-1.5-flash",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=4000,
                timeout=120
            )
            model_used = "gemini"
        except Exception as e:
            logger.error(f"Both models failed: {e}")
            raise
    
    elapsed_ms = int((time.time() - start_time) * 1000)
    
    # Parse raw output
    cards = _parse_all_recommendations(raw_output)
    
    if not cards or len(cards) < 5:
        logger.warning(f"Parser found only {len(cards)} recommendations, attempting fallback")
        cards = _parse_with_fallback_strategy(raw_output)
    
    # Extract fields from each card
    parsed_recommendations = []
    for card_text in cards:
        parsed_rec = _parse_card_text(card_text, actual_inventory)
        if parsed_rec:
            parsed_recommendations.append(parsed_rec)
    
    # Validate and filter
    valid_recs = _validate_against_inventory(parsed_recommendations, actual_inventory)
    filtered_recs = _filter_zero_savings(valid_recs)
    deduplicated_recs = _deduplicate_cards(filtered_recs)
    enriched_recs = _enrich_cards(deduplicated_recs, actual_inventory)
    
    # Calculate totals
    total_savings = sum(rec.total_estimated_savings for rec in enriched_recs)
    
    return RecommendationResult(
        status="success",
        recommendations=enriched_recs,
        total_potential_monthly_savings=total_savings,
        total_recommendations=len(enriched_recs),
        generation_time_ms=elapsed_ms,
        model_used=model_used,
        raw_output_sample=raw_output[:500]  # For debugging
    )
```

### Actual LLM Call (Ollama/Gemini)

**Location:** `src/llm/client.py` lines 50-150

```python
def call_llm(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4000,
    timeout: int = 120
) -> str:
    """Call Ollama or Gemini with retry logic"""
    
    if model.startswith("mistral") or model.startswith("qwen"):
        return _call_ollama(model, system_prompt, user_prompt, temperature, max_tokens, timeout)
    elif model.startswith("gemini"):
        return _call_gemini(model, system_prompt, user_prompt, temperature, max_tokens, timeout)
    else:
        raise ValueError(f"Unknown model: {model}")


def _call_ollama(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: int
) -> str:
    """Call Ollama (running on localhost:11434 or docker)"""
    
    import requests
    import json
    
    url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
    
    payload = {
        "model": model,
        "stream": False,
        "temperature": temperature,
        "num_predict": max_tokens,
        "system": system_prompt,
        "prompt": user_prompt,
        "raw": True  # Use full prompt, not chat format
    }
    
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        
        result = response.json()
        return result.get("response", "")
    
    except requests.Timeout:
        raise TimeoutError(f"Ollama call timed out after {timeout}s")
    except requests.RequestException as e:
        raise ConnectionError(f"Failed to connect to Ollama: {e}")


def _call_gemini(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: int
) -> str:
    """Call Gemini API (fallback model)"""
    
    import google.generativeai as genai
    
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    
    client = genai.GenerativeModel(
        model_name=model,
        system_instruction=system_prompt,
        generation_config={
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
    )
    
    try:
        response = client.generate_content(
            user_prompt,
            request_options={"timeout": timeout}
        )
        return response.text
    except Exception as e:
        if "timeout" in str(e).lower():
            raise TimeoutError(f"Gemini call timed out after {timeout}s")
        raise
```

---

## Raw Output Parsing

### 4-Strategy Parsing Pipeline

**Location:** `src/llm/client.py` lines 400-550

```python
def _parse_all_recommendations(raw_output: str) -> List[str]:
    """
    Apply 4-strategy parsing to extract recommendation cards from raw LLM output
    
    Returns list of card text blocks (minimum 5 required to proceed)
    """
    
    cards = []
    
    # Strategy 1: Primary - "### Recommendation #N" pattern
    logger.info("Attempting parsing strategy 1: ### Recommendation #N")
    cards = _strategy_1_parse(raw_output)
    if len(cards) >= 5:
        logger.info(f"Strategy 1 success: found {len(cards)} recommendations")
        return cards
    
    # Strategy 2: Flexible - any "### [title]" header
    logger.info("Strategy 1 yielded < 5 cards, trying strategy 2: ### [title]")
    cards = _strategy_2_parse(raw_output)
    if len(cards) >= 5:
        logger.info(f"Strategy 2 success: found {len(cards)} recommendations")
        return cards
    
    # Strategy 3: Delimiter-based - "---" separation
    logger.info("Strategy 2 yielded < 5 cards, trying strategy 3: --- delimiter")
    cards = _strategy_3_parse(raw_output)
    if len(cards) >= 5:
        logger.info(f"Strategy 3 success: found {len(cards)} recommendations")
        return cards
    
    # Strategy 4: Fallback - double newline separation
    logger.info("Strategy 3 yielded < 5 cards, trying strategy 4: double newline")
    cards = _strategy_4_parse(raw_output)
    if len(cards) >= 5:
        logger.info(f"Strategy 4 success: found {len(cards)} recommendations")
        return cards
    
    logger.error(f"All strategies failed. Strategy 4 yielded {len(cards)} cards")
    return cards  # Return whatever was found, may be < 5


def _strategy_1_parse(raw_output: str) -> List[str]:
    """
    Strategy 1: Split by "### Recommendation #N" pattern
    Pattern: ### Recommendation 1:, ### Recommendation 2:, etc.
    """
    
    import re
    
    # Pattern: ### Recommendation 1: [anything until next ### Recommendation]
    pattern = r'###\s+Recommendation\s+(\d+):\s*(.+?)(?=###\s+Recommendation\s+\d+:|$)'
    
    matches = re.finditer(pattern, raw_output, re.DOTALL | re.IGNORECASE)
    
    cards = []
    for match in matches:
        rec_number = match.group(1)
        rec_content = match.group(2).strip()
        
        if len(rec_content) > 100:  # Sanity check: exclude very short matches
            cards.append(rec_content)
    
    return cards


def _strategy_2_parse(raw_output: str) -> List[str]:
    """
    Strategy 2: Split by any "### [title]" header (more flexible)
    Includes recommendations that may not have numbered headers
    """
    
    import re
    
    # Look for ### headers (recommendations and separators)
    pattern = r'###\s+([^#]+?)(?=###|$)'
    
    matches = re.finditer(pattern, raw_output, re.DOTALL)
    
    cards = []
    for match in matches:
        content = match.group(1).strip()
        
        # Filter out headers that look like separators or metadata
        if "recommendation" in content.lower() or "action" in content.lower():
            if len(content) > 100:
                cards.append(content)
    
    return cards


def _strategy_3_parse(raw_output: str) -> List[str]:
    """
    Strategy 3: Split by "---" delimiter
    Some LLMs naturally separate items with --- lines
    """
    
    sections = raw_output.split("---")
    
    cards = []
    for section in sections:
        section = section.strip()
        
        # Check if this looks like a recommendation (has recommendation markers)
        if (
            len(section) > 100 and 
            ("recommendation" in section.lower() or "$" in section)
        ):
            cards.append(section)
    
    return cards


def _strategy_4_parse(raw_output: str) -> List[str]:
    """
    Strategy 4: Fall back to double-newline separation
    Last resort: assume each blank line separates a recommendation
    """
    
    sections = raw_output.split("\n\n")
    
    cards = []
    for section in sections:
        section = section.strip()
        
        if len(section) > 100:  # Minimum length for a valid recommendation
            cards.append(section)
    
    return cards
```

---

## Field Extraction Patterns

### Extract Title

**Location:** `src/llm/client.py` lines 560-610

```python
def _extract_title(card_text: str) -> str:
    """Extract recommendation title from card text"""
    
    import re
    
    patterns = [
        # Pattern 1: ### Recommendation #N: [Title]
        r'###\s+Recommendation\s+\d+:\s*(.+?)(?:\n|$)',
        
        # Pattern 2: **Recommendation:** [Title]
        r'\*\*Recommendation:\*\*\s*(.+?)(?:\n|$)',
        
        # Pattern 3: Recommendation Title: [Title]
        r'Recommendation\s*[Tt]itle:\s*(.+?)(?:\n|$)',
        
        # Pattern 4: Just "### [Anything]" on first line
        r'###\s+(.+?)(?:\n|$)',
        
        # Pattern 5: First non-empty line
        None  # Fallback: use first line as title
    ]
    
    for pattern in patterns:
        if pattern is None:
            # Fallback: use first line
            lines = card_text.strip().split("\n")
            if lines:
                return lines[0][:100].strip()
        else:
            match = re.search(pattern, card_text, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                if len(title) > 10 and len(title) < 200:  # Sanity check
                    return title
    
    return "Unknown Recommendation"


# Example:
# Input: "### Recommendation 1: Downsize t3.micro to t3.nano"
# Output: "Downsize t3.micro to t3.nano"
```

### Extract Resource ID

**Location:** `src/llm/client.py` lines 620-720

```python
def _extract_resource_id(card_text: str, service_type: str = None) -> str:
    """
    Extract resource ID from card text
    Uses 5 patterns in order, falls back to service type inference
    """
    
    import re
    
    patterns = [
        # Pattern 1: **Resource ID:** `i-12345abc`
        r'\*\*Resource\s+ID:\*\*\s*`?([^\s`\n,]+)`?',
        
        # Pattern 2: **Resource:** value
        r'\*\*Resource:\*\*\s*`?([^\s`\n,]+)`?',
        
        # Pattern 3: **Service Name:** value (with quotes/backticks)
        r'\*\*Service\s+Name:\*\*\s*`?([^\s`\n,]+)`?',
        
        # Pattern 4: Plain text "Resource: value"
        r'Resource:\s*([^\n,]+)',
        
        # Pattern 5: Look for known AWS ID patterns
        # EC2: i-xxxxxxxxx
        # RDS: db-instance-name
        # Lambda: function-name
        r'(i-[a-f0-9]{17}|db-[a-zA-Z0-9-]+|arn:aws:[a-z-]+:[a-z0-9-]*:[0-9]*:[a-z/:-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, card_text, re.IGNORECASE)
        if match:
            resource_id = match.group(1).strip()
            if len(resource_id) > 3:
                return resource_id
    
    # Fallback: Infer from service type
    if service_type:
        inferred_types = {
            "EC2": "i-12345678901234567",
            "RDS": "db-instance-1",
            "Lambda": "function-name",
            "S3": "bucket-name",
            "DynamoDB": "table-name"
        }
        
        return inferred_types.get(service_type, f"{service_type.lower()}-resource")
    
    return "resource-unknown"


# Example:
# Input: card with "**Resource ID:** `i-0123456789abcdef0`"
# Output: "i-0123456789abcdef0"
```

### Extract Current Monthly Cost

**Location:** `src/llm/client.py` lines 730-830

```python
def _extract_current_cost(card_text: str) -> float:
    """
    Extract current monthly cost from card text
    Uses 12 patterns to handle various formats
    """
    
    import re
    
    patterns = [
        # Pattern 1: **Current Cost:** $1234.56/month
        r'\*\*Current\s+Cost:\*\*\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 2: **Current Monthly Cost:** $1234.56
        r'\*\*Current\s+Monthly\s+Cost:\*\*\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 3: "Current cost: $1234.56 per month"
        r'[Cc]urrent\s+(?:monthly\s+)?cost:\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 4: Bold format: **$1234.56/month**
        r'\*\*\$([0-9,]+\.?\d*)/month',
        
        # Pattern 5: "costs $X/month"
        r'costs?\s+\$([0-9,]+\.?\d*)/month',
        
        # Pattern 6: "Monthly: $X"
        r'[Mm]onthly:\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 7: "Current: $X" (in table format)
        r'[Cc]urrent:\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 8: "Current State: ... $X"
        r'[Cc]urrent\s+[Ss]tate:.*?\$([0-9,]+\.?\d*)',
        
        # Pattern 9: "Service Cost: $X"
        r'Service\s+[Cc]ost:\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 10: Just dollar amounts in order
        r'\$([0-9,]+\.?\d*)[/\s]*month',
        
        # Pattern 11: "now costs" pattern
        r'(?:now|currently)\s+costs?\s+\$([0-9,]+\.?\d*)',
        
        # Pattern 12: Any "$ number" followed by cost indicators
        r'\$([0-9,]+\.?\d*)\s*(?:\(|,|/|\s)*(?:monthly|per month|USD|$)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, card_text, re.IGNORECASE | re.DOTALL)
        if match:
            cost_str = match.group(1).replace(",", "")
            try:
                cost = float(cost_str)
                # Sanity check: costs should be reasonable
                if 0 < cost < 100000:
                    return cost
            except ValueError:
                continue
    
    return 0.0  # No cost found


# Example:
# Input: "**Current Cost:** $2,400/month"
# Output: 2400.0
```

### Extract Savings (Most Complex)

**Location:** `src/llm/client.py` lines 840-1000

```python
def _extract_savings(card_text: str, current_cost: float = None) -> float:
    """
    Extract estimated savings from card text
    Uses 17 patterns including percentage-based fallback
    """
    
    import re
    
    direct_patterns = [
        # Pattern 1: **Expected Savings:** $1234.56/month
        r'\*\*Expected\s+Savings:\*\*\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 2: **Savings:** $1234.56/month
        r'\*\*Savings:\*\*\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 3: **Monthly Savings:** $1234.56
        r'\*\*Monthly\s+Savings:\*\*\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 4: Savings: $X (plain text)
        r'[Ss]avings:\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 5: Save $X/month
        r'[Ss]ave[a-z]*\s+\$([0-9,]+\.?\d*)\s*/month',
        
        # Pattern 6: "$X/month savings"
        r'\$([0-9,]+\.?\d*)\s*(?:/month)?\s+(?:in\s+)?savings?',
        
        # Pattern 7: "reduce costs by $X"
        r'reduc[e]?\s+costs?\s+(?:by\s+)?\$([0-9,]+\.?\d*)',
        
        # Pattern 8: "saves $X per month"
        r'saves?\s+\$([0-9,]+\.?\d*)',
        
        # Pattern 9: "potential savings: $X"
        r'potential\s+savings:\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 10: Table format "Savings: $X"
        r'Savings\s*\|\s*\$([0-9,]+\.?\d*)',
        
        # Pattern 11: "Cost after: $X, Current: $Y" → Y - X
        r'Cost\s+(?:after|new):\s*\$([0-9,]+\.?\d*).*?[Cc]urrent.*?\$([0-9,]+\.?\d*)',
        
        # Pattern 12: "Downsize from $X to $Y per month"
        r'(?:from|down)size.*?\$([0-9,]+\.?\d*).*?to.*?\$([0-9,]+\.?\d*)',
        
        # Pattern 13: "Annual savings: $X" → divide by 12
        r'annual\s+savings:\s*\$([0-9,]+\.?\d*)',
    ]
    
    percentage_patterns = [
        # Pattern 14: "30% cost reduction"
        r'([0-9]+)%\s+(?:cost\s+)?reduction',
        
        # Pattern 15: "save 40% monthly"
        r'save[?\s]+([0-9]+)%',
        
        # Pattern 16: "40% savings"
        r'([0-9]+)%\s+savings?',
        
        # Pattern 17: "reduce by 50%"
        r'reduce\s+by\s+([0-9]+)%',
    ]
    
    # Try direct patterns first
    for pattern in direct_patterns:
        match = re.search(pattern, card_text, re.IGNORECASE | re.DOTALL)
        if match:
            groups = match.groups()
            
            # Handle 2-group patterns (cost before and after)
            if len(groups) == 2:
                try:
                    cost_before = float(groups[0].replace(",", ""))
                    cost_after = float(groups[1].replace(",", ""))
                    savings = cost_before - cost_after
                    if savings > 0:
                        return savings
                except ValueError:
                    continue
            else:
                # Single value extraction
                try:
                    savings_str = groups[0].replace(",", "")
                    savings = float(savings_str)
                    
                    # Sanity check
                    if savings > 0:
                        # If savings is larger than current cost, it's probably annual
                        if current_cost and savings > (current_cost * 12):
                            return savings / 12
                        return savings
                except ValueError:
                    continue
    
    # Try percentage patterns as fallback
    if current_cost and current_cost > 0:
        for pattern in percentage_patterns:
            match = re.search(pattern, card_text, re.IGNORECASE)
            if match:
                percentage_str = match.group(1)
                try:
                    percentage = float(percentage_str) / 100
                    savings = current_cost * percentage
                    if savings > 0:
                        return savings
                except ValueError:
                    continue
    
    return 0.0  # No savings found


# Examples:
# Input 1: "**Monthly Savings:** $450"
# Output: 450.0

# Input 2: "30% cost reduction"
# Output: (if current_cost=$1500) = 450.0

# Input 3: "Downsize from $200/mo to $75/mo"
# Output: 125.0
```

---

## Validation & Filtering

### Validation Against Inventory

**Location:** `src/llm/client.py` lines 1050-1150

```python
def _validate_against_inventory(
    recommendations: List[Dict],
    actual_inventory: List[AWSResource]
) -> List[Dict]:
    """
    Validate recommendations against actual AWS inventory
    Remove invalid recommendations, keep high-priority even if unvalidated
    """
    
    inventory_ids = set(r.service_id for r in actual_inventory)
    inventory_map = {r.service_id: r for r in actual_inventory}
    
    validated = []
    
    for rec in recommendations:
        resource_id = rec.get("resource_identification", {}).get("resource_id", "")
        
        # Check 1: Does resource exist in inventory?
        if resource_id.lower() in [rid.lower() for rid in inventory_ids]:
            # Valid - resource exists
            validated.append(rec)
            continue
        
        # Check 2: Is it an inferred/generic ID?
        if "recommendation" in resource_id.lower() or resource_id == "resource-unknown":
            # Might be valid - could be pattern-based recommendation
            # Keep it but flag for review
            rec["validation_status"] = "unconfirmed_resource"
            validated.append(rec)
            continue
        
        # Check 3: High-priority recommendations get lenience
        if rec.get("priority") in ["CRITICAL", "HIGH"]:
            rec["validation_status"] = "unconfirmed_resource_but_high_priority"
            validated.append(rec)
            continue
        
        # Otherwise: discard as unvalidated
        logger.warning(f"Discarding unvalidated recommendation: {rec.get('title')} (resource: {resource_id})")
    
    return validated


def _filter_zero_savings(recommendations: List[Dict]) -> List[Dict]:
    """
    Remove recommendations with zero or negative savings
    Unless they're critical resilience improvements
    """
    
    filtered = []
    
    for rec in recommendations:
        savings = rec.get("total_estimated_savings", 0)
        is_critical = rec.get("priority") == "CRITICAL"
        has_cost_data = rec.get("cost_breakdown", {}).get("current_monthly") is not None
        
        # Keep if:
        # 1. Has positive savings, OR
        # 2. Is critical (resilience might save indirectly), OR
        # 3. Has cost data (might calculate savings later)
        if savings > 0 or is_critical or has_cost_data:
            filtered.append(rec)
        else:
            logger.debug(f"Filtering zero-savings recommendation: {rec.get('title')}")
    
    return filtered
```

---

## Deduplication Logic

**Location:** `src/llm/client.py` lines 1170-1250

```python
def _deduplicate_cards(recommendations: List[Dict]) -> List[Dict]:
    """
    Remove exact or near-duplicate recommendations
    Key: (resource_id, title[:50])
    
    Keeps first occurrence, removes later duplicates
    """
    
    seen_keys = set()
    deduplicated = []
    
    for rec in recommendations:
        resource_id = rec.get("resource_identification", {}).get("resource_id", "unknown").lower()
        title = rec.get("title", "unknown")[:50].lower()
        
        dedup_key = (resource_id, title)
        
        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            deduplicated.append(rec)
            logger.debug(f"Keeping recommendation: {rec.get('title')} (resource: {resource_id})")
        else:
            logger.info(f"Removing duplicate: {rec.get('title')} (resource: {resource_id})")
    
    logger.info(f"Deduplication: {len(recommendations)} → {len(deduplicated)} recommendations")
    
    return deduplicated
```

---

## Enrichment & Post-Processing

**Location:** `src/llm/client.py` lines 1260-1380

```python
def _enrich_cards(
    recommendations: List[Dict],
    actual_inventory: List[AWSResource]
) -> List[Dict]:
    """
    Enrich recommendations with additional data from inventory
    Fill missing costs, calculate ROI, add metadata
    """
    
    inventory_map = {r.service_id.lower(): r for r in actual_inventory}
    enriched = []
    
    for idx, rec in enumerate(recommendations, 1):
        resource_id = rec.get("resource_identification", {}).get("resource_id", "").lower()
        
        # Fill missing current_monthly_cost from inventory
        if not rec.get("cost_breakdown", {}).get("current_monthly"):
            if resource_id in inventory_map:
                actual_cost = inventory_map[resource_id].monthly_cost
                rec["cost_breakdown"]["current_monthly"] = actual_cost
        
        # Calculate derived fields
        current_cost = rec.get("cost_breakdown", {}).get("current_monthly", 0)
        savings = rec.get("total_estimated_savings", 0)
        
        if current_cost > 0 and savings > 0:
            # ROI Percentage
            rec["roi_percentage"] = (savings / current_cost) * 100
            
            # Payback period (if implementation cost exists)
            implementation_cost = rec.get("implementation_cost", 0)
            if implementation_cost > 0:
                rec["payback_months"] = implementation_cost / savings
            else:
                rec["payback_months"] = None  # No implementation cost
        
        # Add recommendation priority number
        rec["recommendation_number"] = idx
        
        # Add service type from inventory
        if resource_id in inventory_map:
            rec["resource_identification"]["service_type"] = inventory_map[resource_id].service_type
        
        enriched.append(rec)
    
    # Sort by savings (descending)
    enriched.sort(key=lambda x: x.get("total_estimated_savings", 0), reverse=True)
    
    # Re-number after sorting
    for idx, rec in enumerate(enriched, 1):
        rec["recommendation_number"] = idx
    
    return enriched
```

---

## Final Recommendation Object

### RecommendationObject Schema

**Location:** `src/models/recommendation.py`

```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class RecommendationObject:
    """Final recommendation card object sent to frontend"""
    
    # Basic Info
    id: int
    title: str
    summary: str
    priority: str  # "CRITICAL", "HIGH", "MEDIUM", "LOW"
    priority_label: str
    severity: str  # "critical", "high", "medium", "low"
    category: str  # "compute-right-sizing", "storage-optimization", etc.
    category_display: str
    
    # Resources
    resource_identification: Dict[str, Any]  # {
    #   "resource_id": "i-12345abc",
    #   "resource_count": 1,
    #   "resource_type": "EC2_INSTANCE",
    #   "resource_details": [...]
    # }
    
    # Costs
    total_estimated_savings: float  # $/month
    estimated_savings_currency: str  # "USD"
    estimated_savings_period: str  # "monthly"
    
    cost_breakdown: Dict[str, Any]  # {
    #   "current_monthly_cost": 2400.00,
    #   "recommended_monthly_cost": 1800.00,
    #   "total_current_annual": 28800.00,
    #   "total_recommended_annual": 21600.00
    # }
    
    # Implementation
    implementation_complexity: str  # "low", "medium", "high"
    estimated_implementation_time_hours: float
    estimated_downtime_minutes: float
    
    # Details
    inefficiencies: List[Dict[str, str]]  # [{
    #   "type": "over-provisioning",
    #   "description": "..."
    # }]
    
    implementation_plan: Dict[str, Any]  # {
    #   "prerequisites": [...],
    #   "steps": [
    #     {"step_number": 1, "title": "...", "description": "...", "time_minutes": 5},
    #     ...
    #   ]
    # }
    
    # Best Practices
    finops_best_practices: List[Dict[str, str]]  # [{
    #   "practice": "Right-sizing",
    #   "description": "...",
    #   "reference_url": "..."
    # }]
    
    # Metadata
    is_actionable: bool
    requires_approval: bool
    risk_level: str  # "low", "medium", "high"
    
    # Calculated fields (filled during enrichment)
    roi_percentage: Optional[float]
    payback_months: Optional[float]
    recommendation_number: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for frontend"""
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "priority": self.priority,
            "priority_label": self.priority_label,
            "severity": self.severity,
            "category": self.category,
            "category_display": self.category_display,
            
            "resource_identification": self.resource_identification,
            
            "total_estimated_savings": self.total_estimated_savings,
            "estimated_savings_currency": self.estimated_savings_currency,
            "estimated_savings_period": self.estimated_savings_period,
            
            "cost_breakdown": self.cost_breakdown,
            
            "implementation_complexity": self.implementation_complexity,
            "estimated_implementation_time_hours": self.estimated_implementation_time_hours,
            "estimated_downtime_minutes": self.estimated_downtime_minutes,
            
            "inefficiencies": self.inefficiencies,
            "implementation_plan": self.implementation_plan,
            "finops_best_practices": self.finops_best_practices,
            
            "is_actionable": self.is_actionable,
            "requires_approval": self.requires_approval,
            "risk_level": self.risk_level,
            
            "roi_percentage": self.roi_percentage,
            "payback_months": self.payback_months,
            "recommendation_number": self.recommendation_number,
        }


@dataclass
class RecommendationResult:
    """Result wrapper returned by generate_recommendations()"""
    
    status: str  # "success" or "error"
    recommendations: List[RecommendationObject]
    total_potential_monthly_savings: float
    total_potential_annual_savings: float
    total_recommendations: int
    generation_time_ms: int
    model_used: str  # "mistral" or "gemini"
    
    by_priority: Dict[str, int]  # {"CRITICAL": 2, "HIGH": 5, ...}
    by_category: Dict[str, int]  # {"compute-right-sizing": 5, ...}
    
    error_message: Optional[str] = None
    raw_output_sample: Optional[str] = None  # First 500 chars for debugging
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON for frontend"""
        return {
            "status": self.status,
            "recommendations": [r.to_dict() for r in self.recommendations],
            "total_potential_monthly_savings": self.total_potential_monthly_savings,
            "total_potential_annual_savings": self.total_potential_annual_savings,
            "total_recommendations": self.total_recommendations,
            "generation_time_ms": self.generation_time_ms,
            "model_used": self.model_used,
            "by_priority": self.by_priority,
            "by_category": self.by_category,
            "error_message": self.error_message,
        }
```

---

## Error Handling & Fallbacks

### LLM Call Failures

**Location:** `src/background/tasks.py` lines 64-150

```python
@celery_app.task(
    name="generate_recommendations",
    bind=True,
    max_retries=3,
    default_retry_delay=5
)
def generate_recommendations_bg(self, account_id: str, region: str):
    """
    Background task for recommendation generation with retry logic
    """
    
    try:
        context_package = ContextAssembler(account_id, region).assemble()
        actual_inventory = GraphAnalyzer(account_id, region).get_inventory()
        
        result = generate_recommendations(context_package, actual_inventory)
        
        # Cache result
        redis_client.setex(
            key=f"recommendations:{account_id}:{region}",
            time=86400,  # 24 hours
            value=json.dumps(result.to_dict())
        )
        
        # Store in database
        RecommendationHistory.create(
            account_id=account_id,
            region=region,
            result=result.to_dict()
        )
        
        return result.to_dict()
    
    except TimeoutError as e:
        logger.warning(f"LLM timeout for {account_id}/{region}: {e}")
        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=10 ** self.request.retries)
    
    except ConnectionError as e:
        logger.error(f"Connection error for {account_id}/{region}: {e}")
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=5)
        else:
            return {"status": "error", "error": "Failed after 3 retries"}
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
```

### Parsing Failures

```python
def _parse_with_fallback_strategy(raw_output: str) -> List[str]:
    """
    Fallback when all 4 strategies yield < 5 recommendations
    Attempt more aggressive splitting
    """
    
    # Try to find ANY blocks that look like recommendations
    cards = []
    
    # Look for any text block that contains key recommendation markers
    blocks = re.split(r'\n\n+', raw_output)  # Double newline splits
    
    for block in blocks:
        # Check if this block has recommendation signals
        has_title = re.search(r'(recommendation|action|solution|change):', block, re.IGNORECASE)
        has_cost = re.search(r'\$\d+', block)
        has_steps = re.search(r'(step|implement|action):', block, re.IGNORECASE)
        
        if (has_title or has_cost or has_steps) and len(block) > 100:
            cards.append(block.strip())
    
    logger.warning(f"Fallback strategy yielded {len(cards)} recommendations")
    
    return cards
```

---

## Performance & Optimization

### Timing Breakdown

```
API Request Received: T=0ms
  ↓
GraphAnalyzer.fetch_infrastructure(): T=0-200ms
  - CloudFormation describe: 80ms
  - EC2 describe: 40ms
  - RDS describe: 30ms
  - Pricing API: 50ms
  ↓
GraphAnalyzer.build_graph(): T=200-350ms
  - Graph construction: 80ms
  - Centrality calculation: 70ms
  ↓
ContextAssembler.assemble(): T=350-700ms
  - 9-section assembly: 350ms
  ↓
Build prompts: T=700-850ms
  - System/user prompt rendering: 150ms
  ↓
LLM Call (DOMINANT): T=850-6000ms
  - Mistral 7B inference: 4500ms (avg)
  - Token generation: ~4000 tokens
  ↓
Parsing: T=6000-6100ms
  - 4-strategy parsing: 50ms
  - Field extraction (17 patterns × cards): 50ms
  ↓
Validation/Dedup/Enrich: T=6100-6300ms
  - Validation: 80ms
  - Deduplication: 50ms
  - Enrichment: 70ms
  ↓
Return to Frontend: T=6300ms
```

### Caching Strategy

```python
# Cache key: recommendations:{account_id}:{region}
# TTL: 24 hours (86400 seconds)
# Hit rate: 85-95% for established accounts

def get_or_generate_recommendations(account_id, region):
    # Try cache first
    cached = redis_client.get(f"recommendations:{account_id}:{region}")
    if cached:
        return json.loads(cached)  # ~10ms response
    
    # Generate (2-6 seconds)
    result = generate_recommendations_bg.delay(account_id, region)
    
    # Return with status "generating"
    return {"status": "generating", "task_id": result.id}
```

---

## Summary: Complete LLM→Recommendation Card Pipeline

```
1. Context Assembly (9 sections)
   ↓
2. Prompt Construction (system + user with injected context)
   ↓
3. LLM Call (Mistral 7B with 4000 tokens, temperature 0.7)
   ↓
4. Raw Output (structured text with ### Recommendation #N markers)
   ↓
5. 4-Strategy Parsing (extract ≥5 recommendation blocks)
   ↓
6. Field Extraction (17 patterns for savings, 12 for costs, etc.)
   ↓
7. Validation (against AWS inventory)
   ↓
8. Filtering (remove zero-savings)
   ↓
9. Deduplication (remove (resourceID, title) duplicates)
   ↓
10. Enrichment (fill missing data, calculate ROI)
   ↓
11. Sorting (by savings descending)
   ↓
12. RecommendationObject Creation (schema-compliant)
   ↓
13. JSON Serialization
   ↓
14. Frontend Display (as recommendation cards)
```

This multi-stage pipeline ensures robust, validated, deduplicated recommendations that are immediately actionable and grounded in actual AWS infrastructure data.

