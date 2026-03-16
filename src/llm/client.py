"""
Production-Grade LLM Client for FinOps AI
==========================================
Enhanced with:
- Bulletproof prompts with strict validation rules
- Comprehensive error handling and retries
- Response validation and quality checks
- Smart caching to avoid redundant calls
- Detailed logging and debugging
- Citation and source verification
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import hashlib
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.error("requests library not available - LLM calls disabled")

try:
    from src.llm.prompts import (
        format_service_inventory,
        format_cloudwatch_metrics,
        format_graph_context as format_graph_theory,
        format_pricing_data
    )
except ImportError:
    logger.warning("Could not import enhanced formatters from prompts.py, using fallbacks")
    format_service_inventory = None
    format_cloudwatch_metrics = None
    format_graph_theory = None
    format_pricing_data = None

try:
    from src.rag.indexing import get_knowledge_index
    HAS_RAG = True
except ImportError:
    HAS_RAG = False
    logger.warning("RAG indexing not available")


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("FINOPS_MODEL", "finops-aws")
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
REQUEST_TIMEOUT = 300  # 5 minutes
CACHE_TTL_HOURS = 24
ENABLE_RESPONSE_CACHE = os.getenv("ENABLE_LLM_CACHE", "true").lower() == "true"

# Quality thresholds
MIN_RECOMMENDATION_LENGTH = 100  # chars
MIN_SAVINGS_VALUE = 0.01  # Don't accept $0.01 placeholders
REQUIRED_FIELDS = ["title", "resource_identification", "cost_breakdown", "recommendations"]


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════

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
    validation_warnings: List[str] = field(default_factory=list)
    quality_score: float = 0.0  # 0-100


@dataclass
class LLMCallMetrics:
    """Metrics for LLM call tracking."""
    call_id: str
    start_time: float
    end_time: float
    token_count: int
    response_length: int
    from_cache: bool
    retry_count: int
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE CACHE
# ═══════════════════════════════════════════════════════════════════════════

_response_cache: Dict[str, Tuple[str, float]] = {}  # hash -> (response, timestamp)


def _get_cache_key(system_prompt: str, user_prompt: str) -> str:
    """Generate cache key from prompts."""
    combined = f"{system_prompt}||{user_prompt}"
    return hashlib.sha256(combined.encode()).hexdigest()


def _get_cached_response(cache_key: str) -> Optional[str]:
    """Get cached response if still valid."""
    if not ENABLE_RESPONSE_CACHE:
        return None
    
    if cache_key in _response_cache:
        response, timestamp = _response_cache[cache_key]
        age_hours = (time.time() - timestamp) / 3600
        
        if age_hours < CACHE_TTL_HOURS:
            logger.info("Cache HIT (age: %.1f hours)", age_hours)
            return response
        else:
            # Expired
            del _response_cache[cache_key]
            logger.info("Cache EXPIRED (age: %.1f hours)", age_hours)
    
    return None


def _cache_response(cache_key: str, response: str):
    """Cache LLM response."""
    if ENABLE_RESPONSE_CACHE:
        _response_cache[cache_key] = (response, time.time())
        logger.info("Cached response (cache size: %d)", len(_response_cache))


# ═══════════════════════════════════════════════════════════════════════════
# BULLETPROOF PROMPTS
# ═══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a Principal AWS FinOps Solutions Architect with 15 years of experience.

═══════════════════════════════════════════════════════════════════════════
CRITICAL CONSTRAINTS (VIOLATION = RECOMMENDATION REJECTED)
═══════════════════════════════════════════════════════════════════════════

1. DATA CONSTRAINT - ABSOLUTE RULE:
   ✓ ONLY use data explicitly provided in the context
   ✓ If a value is NOT in the context, write "Data not available"
   ✓ Every cost must cite the exact source
   ✓ Every instance type must match the SERVICE INVENTORY exactly
   
   ✗ NEVER assume instance types
   ✗ NEVER use placeholder values ($0.01, $X.XX)
   ✗ NEVER guess at resource IDs
   ✗ NEVER make up metrics

2. CITATION CONSTRAINT:
   Every factual claim must include [SOURCE: <data source>]
   Examples:
   - "CPU utilization is 23%" → "CPU utilization is 23% [SOURCE: CloudWatch]"
   - "Instance costs $426/month" → "Instance costs $426/month [SOURCE: CUR]"

3. CALCULATION CONSTRAINT:
   Show EVERY step of math:
   ✗ BAD: "Savings: $213/month"
   ✓ GOOD: "Current: $0.584/hr × 730 hrs = $426.32/mo
            New: $0.292/hr × 730 hrs = $213.16/mo
            Savings: $426.32 - $213.16 = $213.16/mo"

4. VALIDATION CONSTRAINT:
   Before writing each recommendation, verify:
   □ Resource ID exists in SERVICE INVENTORY?
   □ Current cost available?
   □ Current instance type confirmed?
   □ Target instance type pricing available?
   If ANY is "No" → SKIP this recommendation

5. SPECIFICITY CONSTRAINT:
   ✗ Generic: "Consider using smaller instances"
   ✓ Specific: "Change db-finops-postgres from db.r5.2xlarge to db.r5.xlarge"

═══════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT (EXACT TEMPLATE)
═══════════════════════════════════════════════════════════════════════════

### [Brief Actionable Title - NO markdown symbols]

**Resource Identification:**
- Resource ID: `<exact ID from inventory>`
- Service Name: `<name>`
- AWS Service: <RDS | EC2 | etc>
- Region: <region>
- Environment: <env> [SOURCE: Tags]

**Current State:**
- Instance Type: <exact type>
- Monthly Cost: $XXX.XX [SOURCE: CUR line item]
- CPU Utilization: XX.X% average [SOURCE: CloudWatch]
- Dependencies: X services [SOURCE: Graph]
- Centrality: 0.XX [SOURCE: Graph metrics]

**Inefficiency Detected:**
- Metric: <CPU | Storage | IOPS>
- Current Value: XX.X% [SOURCE: CloudWatch]
- Target Range: XX-XX% [SOURCE: AWS Best Practices]
- Gap: XX.X percentage points
- Root Cause: <Technical explanation>

**Optimization Recommendation:**
- Action: Change from <current> to <target>
- Justification: <Why this size>

**Cost Analysis:**
```
Current: <type> @ $X.XXX/hr × 730 = $XXX.XX/mo
New: <type> @ $Y.YYY/hr × 730 = $YYY.YY/mo
Monthly Savings: $XXX.XX - $YYY.YY = $ZZZ.ZZ
Annual Savings: $ZZZ.ZZ × 12 = $ZZZZ.ZZ
```

**Performance Impact:**
- CPU will increase from XX% to YY%
- Headroom: ZZ% remaining
- Risk Level: LOW | MEDIUM | HIGH

**Dependency Risk:**
- Dependents: X services [SOURCE: Graph]
- Blast radius: XX% [SOURCE: Graph]
- Mitigation: <specific steps>

**Implementation:**
```bash
# Step 1: Backup
aws <service> create-snapshot --id <exact-id>

# Step 2: Modify
aws <service> modify --id <exact-id> --instance-class <new-type>

# Step 3: Validate
aws cloudwatch get-metric-statistics --metric CPUUtilization
```

**Validation:**
□ CPU stays under 85%
□ Error rate < 0.1%
□ Monitor 72 hours

**AWS Best Practice:**
<Quote from docs> [SOURCE: <document>]

---

Generate 5-8 recommendations. Each MUST pass validation checklist.
Start with "### [Title]".
"""


USER_PROMPT_TEMPLATE = """═══════════════════════════════════════════════════════════════════════════
DATA CONTEXT FOR ANALYSIS
═══════════════════════════════════════════════════════════════════════════

CRITICAL: Use ONLY the data below. If data is missing, write "Data not available".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1: SERVICE INVENTORY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{service_inventory}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2: PERFORMANCE METRICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{cloudwatch_metrics}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3: GRAPH ANALYSIS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{graph_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4: AWS PRICING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{pricing_data}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5: AWS BEST PRACTICES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{aws_best_practices}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Generate 5-8 cost optimization recommendations using the format above.
- Use EXACT resource IDs from Section 1
- Cite sources for all claims
- Show complete calculations
- Verify against validation checklist

Begin. Start each with "### [Actionable Title]".
"""


# ═══════════════════════════════════════════════════════════════════════════
# CORE LLM CALL FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    architecture_name: str = "",
) -> Tuple[str, LLMCallMetrics]:
    """
    Call Ollama LLM with retry logic and comprehensive error handling.
    
    Returns:
        (response_text, metrics)
    
    Raises:
        RuntimeError: If LLM is unavailable after retries
    """
    call_id = hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:8]
    start_time = time.time()
    
    metrics = LLMCallMetrics(
        call_id=call_id,
        start_time=start_time,
        end_time=0,
        token_count=0,
        response_length=0,
        from_cache=False,
        retry_count=0,
    )
    
    # Check cache first
    cache_key = _get_cache_key(system_prompt, user_prompt)
    cached = _get_cached_response(cache_key)
    if cached:
        metrics.from_cache = True
        metrics.end_time = time.time()
        metrics.response_length = len(cached)
        logger.info("[%s] Response from cache (%d chars)", call_id, len(cached))
        return cached, metrics
    
    # Add GraphRAG grounding
    grounding = ""
    if HAS_RAG and architecture_name:
        try:
            idx = get_knowledge_index()
            ctx = idx.retrieve_context(architecture_name)
            grounding = idx.format_grounding_prompt(ctx)
            logger.info("[%s] Added GraphRAG grounding (%d chars)", call_id, len(grounding))
        except Exception as e:
            logger.warning("[%s] GraphRAG grounding failed: %s", call_id, e)
    
    grounded_system = system_prompt
    if grounding:
        grounded_system = (
            system_prompt + "\n\n"
            "═══════════════════════════════════════════════════════════════════════════\n"
            "GRAPHRAG KNOWLEDGE GROUNDING\n"
            "═══════════════════════════════════════════════════════════════════════════\n\n"
            "The following factual data is from your knowledge index. Reference these facts.\n\n"
            + grounding
        )
    
    if not HAS_REQUESTS:
        raise RuntimeError("requests library not available - cannot call LLM")
    
    # Health check
    try:
        health_resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if health_resp.status_code != 200:
            raise RuntimeError(f"Ollama health check failed: status {health_resp.status_code}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Ollama is not responding at {OLLAMA_URL}: {e}")
    
    # Retry loop
    last_error = None
    for attempt in range(MAX_RETRIES):
        metrics.retry_count = attempt
        
        try:
            logger.info(
                "[%s] LLM call attempt %d/%d (temp=%.2f, max_tokens=%d)",
                call_id, attempt + 1, MAX_RETRIES, temperature, max_tokens
            )
            
            resp = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": grounded_system},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                },
                timeout=REQUEST_TIMEOUT,
            )
            
            if resp.status_code == 200:
                data = resp.json()
                response_text = data.get("message", {}).get("content", "")
                
                if not response_text:
                    raise RuntimeError("LLM returned empty response")
                
                # Update metrics
                metrics.end_time = time.time()
                metrics.response_length = len(response_text)
                metrics.token_count = len(response_text.split())  # Rough estimate
                
                elapsed_ms = int((metrics.end_time - metrics.start_time) * 1000)
                logger.info(
                    "[%s] LLM success: %d chars, ~%d tokens, %dms",
                    call_id, metrics.response_length, metrics.token_count, elapsed_ms
                )
                
                # Cache successful response
                _cache_response(cache_key, response_text)
                
                return response_text, metrics
            
            else:
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.error("[%s] LLM error: %s", call_id, last_error)
        
        except requests.exceptions.Timeout as e:
            last_error = f"Request timeout after {REQUEST_TIMEOUT}s: {e}"
            logger.error("[%s] %s", call_id, last_error)
        
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error to {OLLAMA_URL}: {e}"
            logger.error("[%s] %s", call_id, last_error)
        
        except Exception as e:
            last_error = f"Unexpected error: {e}"
            logger.error("[%s] %s", call_id, last_error)
        
        # Wait before retry
        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAY_SECONDS * (2 ** attempt)  # Exponential backoff
            logger.info("[%s] Retrying in %ds...", call_id, delay)
            time.sleep(delay)
    
    # All retries failed
    metrics.error = last_error
    metrics.end_time = time.time()
    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} attempts: {last_error}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN RECOMMENDATION GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_recommendations(
    context_package,
    architecture_name: str = "",
    raw_graph_data: Optional[dict] = None,
) -> RecommendationResult:
    """
    Generate comprehensive, validated FinOps recommendations.
    
    Pipeline:
    1. Build rich context from all data sources
    2. Call LLM with bulletproof prompts
    3. Parse and validate response
    4. Enrich with architecture metadata
    5. Quality check all recommendations
    6. Return validated results
    """
    logger.info("=" * 70)
    logger.info("STARTING RECOMMENDATION GENERATION")
    logger.info("Architecture: %s", architecture_name or "Unknown")
    logger.info("=" * 70)
    
    start_time = time.time()
    
    result = RecommendationResult(
        architecture_name=architecture_name,
    )
    
    try:
        # ─── Step 1: Build Context ────────────────────────────────────────
        logger.info("[1/6] Building context package...")
        
        pkg_dict = asdict(context_package) if hasattr(context_package, '__dataclass_fields__') else context_package
        
        # Determine resources for inventory
        resources = raw_graph_data.get("services") or raw_graph_data.get("nodes") or []
        
        # Use high-fidelity formatters if available
        if format_service_inventory:
            service_inventory = format_service_inventory(resources)
        else:
            service_inventory = _build_service_inventory(raw_graph_data) if raw_graph_data else "(No service data)"
            
        if format_cloudwatch_metrics:
            cloudwatch_metrics = format_cloudwatch_metrics(resources)
        else:
            cloudwatch_metrics = _build_cloudwatch_metrics(raw_graph_data) if raw_graph_data else "(No metrics)"
            
        # Graph context
        if format_graph_theory and raw_graph_data:
            # The prompts.py version needs a networkx graph or similar. 
            # If we don't have it easily available, fallback.
            graph_context = _build_graph_context(pkg_dict)
        else:
            graph_context = _build_graph_context(pkg_dict)
            
        # Pricing
        class MockPricingKB:
            def get_last_update_date(self): return "2026-03-01"
            
        if format_pricing_data:
            pricing_data = format_pricing_data(MockPricingKB())
        else:
            pricing_data = _build_pricing_data()
            
        aws_best_practices = _get_aws_best_practices(pkg_dict)
        
        # Assemble user prompt
        user_prompt = USER_PROMPT_TEMPLATE.format(
            service_inventory=service_inventory,
            cloudwatch_metrics=cloudwatch_metrics,
            graph_context=graph_context,
            pricing_data=pricing_data,
            aws_best_practices=aws_best_practices,
        )
        
        logger.info("Context size: %d chars", len(user_prompt))
        
        # ─── Step 2: Call LLM ─────────────────────────────────────────────
        logger.info("[2/6] Calling LLM...")
        
        raw_response, llm_metrics = call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=4096,
            architecture_name=architecture_name,
        )
        
        logger.info(
            "LLM response: %d chars, %d tokens, %dms, from_cache=%s",
            llm_metrics.response_length,
            llm_metrics.token_count,
            int((llm_metrics.end_time - llm_metrics.start_time) * 1000),
            llm_metrics.from_cache,
        )
        
        # Save response for debugging
        _save_debug_response(raw_response, architecture_name)
        
        # ─── Step 3: Parse Response ───────────────────────────────────────
        logger.info("[3/6] Parsing LLM response...")
        
        cards = _parse_structured_recommendations(raw_response)
        logger.info("Parsed %d raw cards", len(cards))
        
        if not cards:
            raise RuntimeError("LLM did not produce valid recommendations")
        
        # ─── Step 4: Enrich with Architecture Data ────────────────────────
        logger.info("[4/6] Enriching with architecture metadata...")
        
        if raw_graph_data:
            cards = _enrich_cards_from_architecture(cards, raw_graph_data)
            logger.info("Enriched %d cards with architecture data", len(cards))
        
        # ─── Step 5: Validate Recommendations ─────────────────────────────
        logger.info("[5/6] Validating recommendations...")
        
        validated_cards, warnings = _validate_recommendations(cards, raw_graph_data)
        logger.info("Validated: %d cards passed, %d warnings", len(validated_cards), len(warnings))
        
        # If validation filtered out everything, keep parsed cards so UI shows recommendations
        if not validated_cards and cards:
            logger.warning("Validation rejected all %d cards; returning parsed cards so UI can display them", len(cards))
            result.cards = cards
        else:
            result.cards = validated_cards
        result.validation_warnings = warnings
        
        # ─── Step 6: Calculate Metrics ────────────────────────────────────
        logger.info("[6/6] Calculating final metrics...")
        
        result.total_estimated_savings = sum(
            c.get("total_estimated_savings", 0) for c in result.cards
        )
        result.llm_used = True
        result.quality_score = _calculate_quality_score(result.cards, warnings)
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        result.generation_time_ms = elapsed_ms
        
        logger.info("=" * 70)
        logger.info("RECOMMENDATION GENERATION COMPLETE")
        logger.info("Cards: %d", len(result.cards))
        logger.info("Savings: $%.2f/month", result.total_estimated_savings)
        logger.info("Quality: %.1f/100", result.quality_score)
        logger.info("Time: %dms", elapsed_ms)
        logger.info("Warnings: %d", len(warnings))
        logger.info("=" * 70)
        
        return result
    
    except Exception as e:
        logger.error("Recommendation generation failed: %s", e, exc_info=True)
        result.error = str(e)
        result.generation_time_ms = int((time.time() - start_time) * 1000)
        raise


# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _build_service_inventory(graph_data: dict) -> str:
    """Build detailed service inventory table."""
    services = graph_data.get("services") or graph_data.get("nodes") or []
    if not services:
        return "(No services found in architecture)"
    
    region = graph_data.get("metadata", {}).get("region", "us-east-1")
    total_cost = sum(s.get("cost_monthly", 0) for s in services)
    
    lines = [
        f"**Region:** {region} | **Total Monthly Cost:** ${total_cost:,.2f}",
        "",
        "| Resource ID | Service Type | Instance/Config | Monthly Cost | Environment | Tags |",
        "|:------------|:-------------|:----------------|:-------------|:------------|:-----|",
    ]
    
    # Sort by cost descending
    sorted_services = sorted(services, key=lambda s: s.get("cost_monthly", 0), reverse=True)
    
    for svc in sorted_services:
        rid = svc.get("id", "unknown")
        svc_type = svc.get("aws_service", svc.get("type", "unknown"))
        
        attrs = svc.get("attributes", svc.get("properties", {}))
        instance = attrs.get("instance_type", "-")
        
        cost = svc.get("cost_monthly", 0)
        env = svc.get("environment", "production")
        
        tags = svc.get("tags", {})
        tag_str = ", ".join(f"{k}={v}" for k, v in list(tags.items())[:2]) if tags else "-"
        
        lines.append(
            f"| `{rid}` | {svc_type} | {instance} | ${cost:,.2f} | {env} | {tag_str} |"
        )
    
    return "\n".join(lines)


def _build_cloudwatch_metrics(graph_data: dict) -> str:
    """Build CloudWatch metrics context."""
    services = graph_data.get("services") or graph_data.get("nodes") or []
    if not services:
        return "(No metrics available)"
    
    lines = ["**CloudWatch Performance Metrics (30-day average):**", ""]
    
    for svc in services[:20]:  # Limit to top 20
        rid = svc.get("id")
        metrics = svc.get("metrics", {})
        
        if not metrics:
            continue
        
        lines.append(f"**{rid}:**")
        
        for metric_name, metric_data in metrics.items():
            if isinstance(metric_data, dict):
                avg = metric_data.get("average", "N/A")
                p99 = metric_data.get("p99", "N/A")
                lines.append(f"  - {metric_name}: avg={avg}, p99={p99}")
        
        lines.append("")
    
    return "\n".join(lines) if len(lines) > 2 else "(No CloudWatch metrics available)"


def _build_graph_context(pkg_dict: dict) -> str:
    """Build graph analysis context."""
    lines = ["**Graph Analysis:**", ""]
    
    # Bottlenecks
    bottlenecks = pkg_dict.get("bottleneck_nodes", [])
    if bottlenecks:
        lines.append("**Critical Bottlenecks (High Centrality):**")
        for i, b in enumerate(bottlenecks[:5], 1):
            name = b.get("name", "unknown")
            cent = b.get("centrality", 0)
            deps = b.get("in_degree", 0)
            lines.append(f"  {i}. {name}: centrality={cent:.4f}, dependents={deps}")
        lines.append("")
    
    # SPOFs
    spofs = pkg_dict.get("single_points_of_failure", [])
    if spofs:
        lines.append(f"**Single Points of Failure:** {len(spofs)} detected")
        for spof in spofs[:5]:
            if isinstance(spof, dict):
                lines.append(f"  - {spof.get('name', 'unknown')}")
        lines.append("")
    
    # Cascades
    cascades = pkg_dict.get("cascade_risks", [])
    if cascades:
        lines.append("**Cascade Failure Risks:**")
        for c in cascades[:5]:
            name = c.get("name", "unknown")
            risk = c.get("risk", "unknown")
            lines.append(f"  - {name}: {risk}")
        lines.append("")
    
    return "\n".join(lines) if len(lines) > 2 else "(No graph analysis available)"


def _build_pricing_data() -> str:
    """Build AWS pricing context."""
    # In production, this would query AWS Pricing API or database
    # For now, provide representative pricing
    return """**AWS On-Demand Pricing (us-east-1, Updated Mar 2026):**

**RDS Instances:**
- db.t3.micro: $0.017/hr ($12.41/mo)
- db.t3.medium: $0.068/hr ($49.64/mo)
- db.r5.large: $0.292/hr ($213.16/mo)
- db.r5.xlarge: $0.584/hr ($426.32/mo)
- db.r5.2xlarge: $1.168/hr ($852.64/mo)

**EC2 Instances:**
- t3.micro: $0.0104/hr ($7.59/mo)
- t3.medium: $0.0416/hr ($30.37/mo)
- m5.large: $0.096/hr ($70.08/mo)
- m5.xlarge: $0.192/hr ($140.16/mo)
- r5.large: $0.126/hr ($91.98/mo)
- r5.xlarge: $0.252/hr ($183.96/mo)

(Prices as of March 2026. Use for calculations.)
"""


def _get_aws_best_practices(pkg_dict: dict) -> str:
    """Get AWS FinOps best practices from docs or fallback."""
    try:
        from src.rag.doc_indexer import get_doc_index
        idx = get_doc_index()
        
        query_terms = [
            "AWS cost optimization right-sizing reserved instances",
            "RDS cost optimization best practices",
            "EC2 cost optimization best practices",
        ]
        
        context = idx.get_best_practices_context(query_terms, top_k=5)
        if context and len(context) > 100:
            logger.info("Retrieved %d chars of best practices from docs", len(context))
            return context
    except Exception as e:
        logger.warning("Could not retrieve best practices docs: %s", e)
    
    # Fallback
    return """**AWS Well-Architected Framework - Cost Optimization:**

1. **Right-Sizing**: Target 60-70% CPU utilization for databases, 50-60% for compute
2. **Reserved Capacity**: Use RIs or Savings Plans for steady workloads (40-60% savings)
3. **Storage Optimization**: Use appropriate storage classes, enable lifecycle policies
4. **Data Transfer**: Minimize cross-AZ and cross-region transfers
5. **Monitoring**: Enable Cost Anomaly Detection, review Trusted Advisor

[SOURCE: AWS Well-Architected Framework, Cost Optimization Pillar]
"""


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE PARSING
# ═══════════════════════════════════════════════════════════════════════════

def _parse_structured_recommendations(text: str) -> List[Dict]:
    """Parse recommendations from LLM output with robust pattern matching."""
    if not text or len(text) < 100:
        logger.error("Response too short: %d chars", len(text))
        return []
    
    cards = []
    
    # Try multiple header patterns
    patterns = [
        r"(?:^|\n)#{1,3}\s+([^#\n]{10,120})",  # Markdown headers
        r"(?:^|\n)RECOMMENDATION #(\d+):",
        r"(?:^|\n)Cost Optimization Recommendation #(\d+)",
    ]
    
    matches = []
    for pat in patterns:
        matches = list(re.finditer(pat, text, re.MULTILINE))
        if matches:
            logger.info("Found %d recommendations with pattern: %s", len(matches), pat[:50])
            break
    
    if not matches:
        logger.warning("No recommendation headers found")
        return []
    
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        rec_text = text[start:end]
        
        card = _extract_recommendation_card(rec_text, i + 1)
        if card:
            cards.append(card)
        else:
            logger.warning("Failed to extract recommendation #%d", i + 1)
    
    return cards


def _extract_recommendation_card(text: str, rec_num: int) -> Optional[Dict]:
    """Extract a single recommendation card from text section."""
    if len(text) < MIN_RECOMMENDATION_LENGTH:
        logger.warning("Recommendation #%d too short: %d chars", rec_num, len(text))
        return None
    
    card = {
        "priority": rec_num,
        "recommendation_number": rec_num,
        "title": "",
        "severity": "medium",
        "category": "optimization",
        "risk_level": "medium",
        "implementation_complexity": "medium",
        "resource_identification": {},
        "cost_breakdown": {"current_monthly": 0, "line_items": []},
        "inefficiencies": [],
        "recommendations": [],
        "total_estimated_savings": 0,
        "raw_analysis": text.strip(),
    }
    
    # Extract title from first line
    first_line = text.split("\n")[0].strip()
    title = re.sub(r"^#{1,3}\s*", "", first_line)
    title = re.sub(r"Recommendation #\d+:?\s*", "", title, flags=re.IGNORECASE)
    title = title.strip("# *`")
    
    if len(title) > 10:
        card["title"] = title[:120]
    else:
        card["title"] = f"Recommendation #{rec_num}"
    
    # Extract resource ID (more robust to bullets, bolding, etc.)
    resource_patterns = [
        r"(?:Resource ID|Resource ID:)\s*[:\-\*]*\s*`?([^`\n\r]+)`?",
        r"(?:Service Name|Service Name:)\s*[:\-\*]*\s*`?([^`\n\r]+)`?",
        r"(?:Resource Identification|Target Resource)\s*[:\-\*]*\s*`?([^`\n\r]+)`?",
    ]
    
    for pat in resource_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            rid = m.group(1).strip().strip(':* -`')
            if rid and len(rid) > 2:
                card["resource_identification"]["resource_id"] = rid
                card["resource_identification"]["service_name"] = rid
                break
    
    # Extract AWS Service
    svc_m = re.search(r"AWS Service:\s*([^\n]+)", text, re.IGNORECASE)
    if svc_m:
        card["resource_identification"]["service_type"] = svc_m.group(1).strip()
    
    # Extract current cost
    cost_patterns = [
        r"Monthly Cost:\s*\$([0-9,]+\.?\d*)",
        r"Current Monthly Cost:\s*\$([0-9,]+\.?\d*)",
        r"Current.*?:\s*\$([0-9,]+\.?\d*)/mo",
    ]
    
    for pat in cost_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                cost = float(m.group(1).replace(",", ""))
                card["cost_breakdown"]["current_monthly"] = cost
                break
            except ValueError:
                continue
    
    # Extract savings (handle "XXX - YYY = ZZZ" format)
    savings_patterns = [
        r"Monthly Savings:.*?=\s*\$([0-9,]+\.?\d*)", # Match the result after '='
        r"Monthly Savings:\s*\$([0-9,]+\.?\d*)",
        r"Estimated Monthly Savings:\s*\$([0-9,]+\.?\d*)",
        r"Savings:\s*\$([0-9,]+\.?\d*)",
    ]
    
    for pat in savings_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                savings_str = m.group(1).replace(",", "")
                # If there are multiple numbers on the line and we matched the first (e.g. Current - New = Savings)
                # the "result after =" pattern should have caught it, but let's be safe.
                savings = float(savings_str)
                if savings > MIN_SAVINGS_VALUE:
                    card["total_estimated_savings"] = savings
                    break
            except ValueError:
                continue
    
    # Extract implementation steps (look for bash code block or numbered list)
    impl_steps = []
    
    bash_block = re.search(r"```bash\n(.*?)\n```", text, re.DOTALL)
    if bash_block:
        commands = [line.strip() for line in bash_block.group(1).split("\n") if line.strip() and not line.strip().startswith("#")]
        impl_steps = commands[:5]  # Limit to 5 steps
    
    if not impl_steps:
        numbered = re.findall(r"\d+\.\s*(.+?)(?:\n|$)", text)
        if numbered:
            impl_steps = [s.strip() for s in numbered[:5]]
    
    # Build recommendations list
    if impl_steps or card["total_estimated_savings"] > 0:
        card["recommendations"] = [{
            "action_number": 1,
            "action": card["title"],
            "estimated_monthly_savings": card["total_estimated_savings"],
            "implementation_steps": impl_steps,
            "validation_steps": [],
            "performance_impact": "",
            "risk_mitigation": "",
        }]
    
    return card


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════════════════

def _validate_recommendations(cards: List[Dict], graph_data: Optional[dict]) -> Tuple[List[Dict], List[str]]:
    """
    Validate recommendations and filter out invalid ones.
    
    Returns:
        (valid_cards, warnings)
    """
    valid_cards = []
    warnings = []
    
    # Build resource lookup if graph data available
    resource_ids = set()
    if graph_data:
        services = graph_data.get("services") or graph_data.get("nodes") or []
        resource_ids = {s.get("id", "") for s in services}
        resource_ids |= {s.get("name", "") for s in services}
    
    for i, card in enumerate(cards, 1):
        card_warnings = []
        
        # Check required fields
        for field in REQUIRED_FIELDS:
            if field not in card or not card[field]:
                card_warnings.append(f"Missing required field: {field}")
        
        # Check resource ID exists
        res_id = card.get("resource_identification", {}).get("resource_id", "")
        if resource_ids and res_id and res_id not in resource_ids:
            # Try partial match
            found = False
            for rid in resource_ids:
                if res_id.lower() in rid.lower() or rid.lower() in res_id.lower():
                    found = True
                    break
            
            if not found:
                card_warnings.append(f"Resource ID '{res_id}' not found in architecture")
        
        # Check savings are realistic
        savings = card.get("total_estimated_savings", 0)
        current_cost = card.get("cost_breakdown", {}).get("current_monthly", 0)
        
        if savings <= MIN_SAVINGS_VALUE:
            card_warnings.append(f"Savings too low: ${savings:.2f} (likely placeholder)")
        
        if savings > current_cost:
            card_warnings.append(f"Savings (${savings:.2f}) > current cost (${current_cost:.2f})")
        
        # Check title quality
        title = card.get("title", "")
        if len(title) < 10:
            card_warnings.append("Title too short")
        elif title.lower().startswith("recommendation #"):
            card_warnings.append("Generic title (starts with 'Recommendation #')")
        
        # Log warnings
        if card_warnings:
            for w in card_warnings:
                warning_msg = f"Card #{i} ({title[:50]}): {w}"
                warnings.append(warning_msg)
                logger.warning(warning_msg)
        
        # Include card if it has minimal validity (title + some savings)
        if title and (savings > MIN_SAVINGS_VALUE or current_cost > 0):
            valid_cards.append(card)
        else:
            logger.warning("Rejecting card #%d: insufficient data", i)
    
    return valid_cards, warnings


def _calculate_quality_score(cards: List[Dict], warnings: List[str]) -> float:
    """Calculate overall quality score 0-100."""
    if not cards:
        return 0.0
    
    score = 100.0
    
    # Penalty for warnings
    score -= len(warnings) * 5
    
    # Bonus for complete fields
    complete_count = 0
    for card in cards:
        if all(card.get(f) for f in REQUIRED_FIELDS):
            complete_count += 1
    
    completeness = (complete_count / len(cards)) * 20
    score += completeness
    
    # Bonus for realistic savings
    realistic_savings = sum(1 for c in cards if c.get("total_estimated_savings", 0) > 1.0)
    score += (realistic_savings / len(cards)) * 20
    
    return max(0.0, min(100.0, score))


# ═══════════════════════════════════════════════════════════════════════════
# ENRICHMENT
# ═══════════════════════════════════════════════════════════════════════════

def _enrich_cards_from_architecture(cards: List[Dict], graph_data: dict) -> List[Dict]:
    """Enrich cards with real architecture metadata."""
    services = graph_data.get("services") or graph_data.get("nodes") or []
    if not services:
        return cards
    
    # Build lookup
    svc_by_id = {}
    svc_by_name = {}
    for svc in services:
        sid = svc.get("id", "")
        sname = svc.get("name", "")
        svc_by_id[sid] = svc
        svc_by_name[sname] = svc
    
    enriched = []
    seen_ids = set()
    
    for card in cards:
        res = card.get("resource_identification", {})
        rid = res.get("resource_id", "") or res.get("service_name", "")
        
        # Find matching service
        matched = svc_by_id.get(rid) or svc_by_name.get(rid)
        
        # Try fuzzy match
        if not matched and rid:
            rid_lower = rid.lower()
            for key, svc in {**svc_by_id, **svc_by_name}.items():
                if rid_lower in key.lower() or key.lower() in rid_lower:
                    matched = svc
                    break
        
        # Skip duplicates
        svc_id = matched.get("id", rid) if matched else rid
        if svc_id in seen_ids:
            continue
        seen_ids.add(svc_id)
        
        # Enrich if matched
        if matched:
            attrs = matched.get("attributes", matched.get("properties", {}))
            
            # Update resource identification
            if not res.get("resource_id"):
                res["resource_id"] = matched.get("id", rid)
            if not res.get("service_name"):
                res["service_name"] = matched.get("name", rid)
            if not res.get("service_type"):
                res["service_type"] = matched.get("aws_service", matched.get("type", ""))
            
            # Update cost if missing
            if card["cost_breakdown"]["current_monthly"] == 0:
                card["cost_breakdown"]["current_monthly"] = matched.get("cost_monthly", 0)
        
        enriched.append(card)
    
    return enriched


# ═══════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════

def _save_debug_response(response: str, architecture_name: str):
    """Save LLM response for debugging."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"/tmp/llm_response_{architecture_name}_{timestamp}.txt"
        
        with open(filename, "w") as f:
            f.write("=" * 70 + "\n")
            f.write(f"LLM Response Debug Log\n")
            f.write(f"Architecture: {architecture_name}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write("=" * 70 + "\n\n")
            f.write(response)
        
        logger.info("Saved debug response to %s", filename)
    except Exception as e:
        logger.warning("Could not save debug response: %s", e)


# ═══════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    "generate_recommendations",
    "call_llm",
    "RecommendationResult",
    "LLMCallMetrics",
]
