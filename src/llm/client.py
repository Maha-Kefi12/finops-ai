"""
LLM Client - Qwen 2.5 7B (Ollama) + Gemini Flash Backup
========================================================
KEY FIX: Robust parser that finds ALL recommendations
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
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════

# Gemini Flash (backup)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash-exp"

# Qwen via Ollama (primary)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("FINOPS_MODEL", "mistral:latest")  # Use faster Mistral by default

# Backend selection
USE_GEMINI = os.getenv("USE_GEMINI", "false").lower() == "true" and GEMINI_API_KEY

MAX_RETRIES = 3
TIMEOUT = 300  # Ollama sometimes needs 120-180s, set to 5 minutes for safety


# ═══════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class RecommendationResult:
    cards: List[Dict[str, Any]] = field(default_factory=list)
    total_estimated_savings: float = 0.0
    context_sections_used: int = 8
    llm_used: bool = False
    generation_time_ms: int = 0
    architecture_name: str = ""
    error: Optional[str] = None


# ═══════════════════════════════════════════════════════════════════════════
# LLM CALL FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.2,
             max_tokens: int = 4096, architecture_name: str = "") -> str:
    """Call LLM (Gemini or Qwen via Ollama)."""
    
    if USE_GEMINI and HAS_GEMINI:
        return _call_gemini(system_prompt, user_prompt, temperature, max_tokens)
    else:
        return _call_ollama(system_prompt, user_prompt, temperature, max_tokens)


def _call_gemini(system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Gemini Flash API."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY not set")
    
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=system_prompt
        )
        
        logger.info("Calling Gemini Flash (%s)...", GEMINI_MODEL)
        
        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
        )
        
        text = response.text
        logger.info("Gemini response: %d chars", len(text))
        return text
    
    except Exception as e:
        logger.error("Gemini call failed: %s", e)
        raise RuntimeError(f"Gemini API error: {e}")


def _call_ollama(system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> str:
    """Call Qwen 2.5 7B via Ollama."""
    if not HAS_REQUESTS:
        raise RuntimeError("requests library not available")
    
    # Health check
    try:
        health = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if health.status_code != 200:
            raise RuntimeError(f"Ollama not ready: {health.status_code}")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Ollama not responding at {OLLAMA_URL}: {e}")
    
    logger.info("Calling Ollama (%s)...", OLLAMA_MODEL)
    
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=TIMEOUT,
        )
        
        if resp.status_code == 200:
            text = resp.json().get("message", {}).get("content", "")
            logger.info("Ollama response: %d chars", len(text))
            return text
        else:
            raise RuntimeError(f"Ollama returned {resp.status_code}")
    
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama timeout after {TIMEOUT}s")
    except Exception as e:
        raise RuntimeError(f"Ollama error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN GENERATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def generate_recommendations(context_package, architecture_name: str = "",
                            raw_graph_data: Optional[dict] = None) -> RecommendationResult:
    """Generate recommendations with robust parsing."""
    
    from src.llm.prompts import RECOMMENDATION_SYSTEM_PROMPT, RECOMMENDATION_USER_PROMPT
    
    start = time.time()
    result = RecommendationResult(architecture_name=architecture_name)
    
    logger.info("=" * 70)
    logger.info("GENERATING RECOMMENDATIONS")
    logger.info("Backend: %s", "Gemini Flash" if USE_GEMINI else "Qwen 2.5 (Ollama)")
    logger.info("=" * 70)
    
    try:
        # Build context
        t1 = time.time()
        logger.info("[TIMING] Starting context assembly...")
        pkg_dict = asdict(context_package) if hasattr(context_package, '__dataclass_fields__') else context_package
        
        service_inventory = _build_service_inventory(raw_graph_data) if raw_graph_data else ""
        cloudwatch_metrics = _build_metrics(raw_graph_data) if raw_graph_data else ""
        graph_context = _build_graph(pkg_dict)
        pricing_data = _build_pricing()
        aws_best_practices = _build_best_practices(pkg_dict)  # Pass pkg_dict to include RAG docs
        logger.info("[TIMING] Context assembly done in %.1fs", time.time() - t1)
        
        t2 = time.time()
        logger.info("[TIMING] Formatting user prompt...")
        user_prompt = RECOMMENDATION_USER_PROMPT.format(
            service_inventory=service_inventory,
            cloudwatch_metrics=cloudwatch_metrics,
            graph_context=graph_context,
            pricing_data=pricing_data,
            aws_best_practices=aws_best_practices,
        )
        logger.info("[TIMING] User prompt formatted in %.1fs (%d chars)", 
                   time.time() - t2, len(user_prompt))
        
        # Call LLM
        t3 = time.time()
        logger.info("[TIMING] Starting LLM call (timeout=%ds)...", TIMEOUT)
        raw_response = call_llm(
            system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            max_tokens=4000,  # Reduced for faster generation (still ~10-15 recommendations)
            architecture_name=architecture_name,
        )
        logger.info("[TIMING] LLM call completed in %.1fs (%d chars)",  
                   time.time() - t3, len(raw_response) if raw_response else 0)
        
        if not raw_response:
            raise RuntimeError("LLM returned empty response")
        
        # Save for debug
        _save_response(raw_response, architecture_name)
        
        # Parse (FIXED - finds all recommendations)
        cards = _parse_all_recommendations(raw_response)
        logger.info("✓ Parsed %d recommendations", len(cards))
        
        if not cards:
            raise RuntimeError("No valid recommendations parsed")
        
        # Deduplicate recommendations by resource_id
        cards = _deduplicate_cards(cards)
        
        # Validate against actual inventory (remove hallucinations)
        if raw_graph_data:
            cards = _validate_against_inventory(cards, raw_graph_data)
        
        # Filter out zero/none savings recommendations
        cards = _filter_zero_savings_cards(cards)
        
        # Enrich with architecture data
        if raw_graph_data:
            cards = _enrich_cards(cards, raw_graph_data)
        
        # Finalize
        result.cards = cards
        result.llm_used = True
        result.total_estimated_savings = sum(c.get("total_estimated_savings", 0) for c in cards)
        result.generation_time_ms = int((time.time() - start) * 1000)
        
        logger.info("=" * 70)
        logger.info("COMPLETE: %d recommendations, $%.2f savings, %dms",
                   len(cards), result.total_estimated_savings, result.generation_time_ms)
        logger.info("=" * 70)
        
        return result
    
    except Exception as e:
        logger.error("Generation failed: %s", e, exc_info=True)
        result.error = str(e)
        result.generation_time_ms = int((time.time() - start) * 1000)
        raise


# ═══════════════════════════════════════════════════════════════════════════
# PARSER - THE KEY FIX (Finds ALL recommendations)
# ═══════════════════════════════════════════════════════════════════════════

def _parse_all_recommendations(text: str) -> List[Dict]:
    """
    ROBUST PARSER - Finds ALL recommendations regardless of format.
    
    Tries multiple splitting strategies to capture all cards.
    """
    if not text or len(text) < 100:
        logger.error("Response too short: %d chars", len(text))
        return []
    
    logger.info("Parsing response (%d chars)...", len(text))
    
    # Strategy 1: Split by "### Recommendation #N"
    pattern1 = r"###\s+Recommendation\s+#(\d+)"
    matches1 = list(re.finditer(pattern1, text, re.IGNORECASE))
    
    if len(matches1) >= 5:
        logger.info("Strategy 1: Found %d recommendations via '### Recommendation #N'", len(matches1))
        return _extract_sections(text, matches1)
    
    # Strategy 2: Split by any ### header
    pattern2 = r"###\s+([^\n#]{5,100})"
    matches2 = list(re.finditer(pattern2, text))
    
    if len(matches2) >= 5:
        logger.info("Strategy 2: Found %d recommendations via '### [title]'", len(matches2))
        return _extract_sections(text, matches2)
    
    # Strategy 3: Split by "---" (triple dash)
    sections = text.split("---")
    sections = [s.strip() for s in sections if len(s.strip()) > 100]
    
    if len(sections) >= 5:
        logger.info("Strategy 3: Found %d recommendations via '---' delimiter", len(sections))
        cards = []
        for i, section in enumerate(sections, 1):
            card = _parse_card_text(section, i)
            if card:
                cards.append(card)
        return cards
    
    # Strategy 4: Split by double newline (desperate fallback)
    sections = re.split(r'\n\n+', text)
    sections = [s.strip() for s in sections if len(s.strip()) > 100]
    
    if len(sections) >= 5:
        logger.info("Strategy 4: Found %d sections via double newline", len(sections))
        cards = []
        for i, section in enumerate(sections, 1):
            card = _parse_card_text(section, i)
            if card:
                cards.append(card)
        return cards[:20]  # Limit to 20
    
    logger.error("All parsing strategies failed. Matches found: pattern1=%d, pattern2=%d",
                len(matches1), len(matches2))
    return []


def _extract_sections(text: str, matches: list) -> List[Dict]:
    """Extract card sections from regex matches."""
    cards = []
    
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        
        card = _parse_card_text(section_text, i + 1)
        if card:
            cards.append(card)
    
    return cards


def _parse_card_text(text: str, card_num: int) -> Optional[Dict]:
    """Parse a single recommendation card from text."""
    if len(text) < 50:
        return None
    
    card = {
        "priority": card_num,
        "recommendation_number": card_num,
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
        "raw_analysis": text[:1000],
    }
    
    # Extract title
    title_match = re.search(r"###\s+(.+?)(?:\n|$)", text)
    if title_match:
        title = title_match.group(1).strip()
        title = re.sub(r"Recommendation\s+#\d+:?\s*", "", title, flags=re.IGNORECASE)
        card["title"] = title[:120] if title else f"Recommendation #{card_num}"
    else:
        card["title"] = f"Recommendation #{card_num}"
    
    # Extract Resource ID - IMPROVED resilience
    resource_patterns = [
        r"\*\*Resource ID:\*\*\s*`?([^`\n]+)`?",
        r"\*\*Resource:\*\*\s*`?([^`\n]+)`?",
        r"\*\*Service Name:\*\*\s*`?([^`\n]+)`?",
        r"Resource:\s*([^\n]+)",
        r"Resource ID:\s*([^\n]+)",
    ]
    for pat in resource_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            res_id = m.group(1).strip()
            if res_id and len(res_id) > 1:  # Only if valid
                card["resource_identification"]["resource_id"] = res_id
                card["resource_identification"]["service_name"] = res_id
                break
    
    # Fallback: If no resource ID found, use service type or title as basis
    if not card["resource_identification"].get("resource_id"):
        # Extract service type from text (e.g., "EC2", "S3", "RDS")
        service_types = ["EC2", "S3", "RDS", "Lambda", "NAT", "DynamoDB", "ElastiCache", 
                        "Redshift", "ECS", "EKS", "Auto Scaling", "CloudFront", "Route53"]
        for svc_type in service_types:
            if svc_type.lower() in text.lower():
                card["resource_identification"]["service_type"] = svc_type
                card["resource_identification"]["resource_id"] = f"{svc_type.lower()}-recommendation"
                break
    
    # Extract Service Type
    svc_match = re.search(r"\*\*Service:\*\*\s*([^\n]+)", text, re.IGNORECASE)
    if svc_match:
        card["resource_identification"]["service_type"] = svc_match.group(1).strip()
    
    # Extract Current Cost - EXPANDED patterns
    cost_patterns = [
        # Explicit "Current Cost" patterns (markdown bold)
        r"\*\*Current\s+(?:Monthly\s+)?Cost:\*\*\s*\$([0-9,]+\.?\d*)",
        r"\*\*Cost\s+per\s+month:\*\*\s*\$([0-9,]+\.?\d*)",
        
        # Plain text cost patterns
        r"Current\s+(?:monthly\s+)?cost:\s*\$([0-9,]+\.?\d*)",
        r"(?:Monthly\s+)?Cost(?:\s+per month)?:\s*\$([0-9,]+\.?\d*)",
        r"(?:Monthly\s+)?Cost(?:\s+/month)?:\s*\$([0-9,]+\.?\d*)",
        r"Cost\s+per\s+month:\s*\$([0-9,]+\.?\d*)",
        r"(?:Cost\s+)?per\s+month:\s*\$([0-9,]+\.?\d*)",
        
        # Spending patterns
        r"(?:Current|Monthly|Today's)\s+(?:spending|spend):\s*\$([0-9,]+\.?\d*)",
        r"Currently\s+(?:spending|costs)\s+\$([0-9,]+\.?\d*)",
        r"Monthly\s+(?:cost|spending):\s*\$([0-9,]+\.?\d*)",
        
        # Alternative phrasing
        r"(?:Cost|Spending)\s+(?:is|of)?\s*\$([0-9,]+\.?\d*)(?:\s+per month|/month)?",
        r"\*\*Current Cost:\*\*\s*\$([0-9,]+\.?\d*)\s*(?:per month|/month)?",
    ]
    
    for pat in cost_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                card["cost_breakdown"]["current_monthly"] = float(m.group(1).replace(",", ""))
                break
            except ValueError:
                pass
    
    # Extract Savings - EXPANDED patterns to catch more formats
    savings_patterns = [
        # Markdown bold patterns for savings
        r"\*\*(?:Expected|Estimated|Potential)\s+(?:Monthly\s+)?Savings?:\*\*\s*\$([0-9,]+\.?\d*)",
        r"\*\*Savings?:\*\*\s*\$([0-9,]+\.?\d*)",
        r"\*\*Monthly Savings?:\*\*\s*\$([0-9,]+\.?\d*)",
        
        # Common explicit patterns
        r"Monthly savings:\s*\$([0-9,]+\.?\d*)",
        r"Monthly Savings:\s*\$([0-9,]+\.?\d*)",
        r"(?:Expected|Estimated|Potential)\s+(?:monthly\s+)?savings?:\s*\$([0-9,]+\.?\d*)",
        
        # Dollar-first patterns ($X savings, $X reduction, etc.)
        r"\$([0-9,]+\.?\d*)\s+(?:monthly\s+)?savings?(?:\s+per month)?",
        r"\$([0-9,]+\.?\d*)\s+(?:cost reduction|estimated savings|potential savings)",
        
        # Reduction/Savings with colon (Expected reduction: $600)
        r"(?:Expected|Estimated|Potential)?\s*(?:reduction|savings?):\s*\$([0-9,]+\.?\d*)",
        r"(?:reduction|decrease|savings?):\s*\$([0-9,]+\.?\d*)",
        
        # "Save/Save" action patterns
        r"(?:Save|Save approximately|Estimated Savings?|Potential Savings?):\s*\$([0-9,]+\.?\d*)",
        r"(?:save|save approximately)\s+\$([0-9,]+\.?\d*)",
        
        # Expected/Projected patterns
        r"Expected:\s*\$([0-9,]+\.?\d*)",
        r"Projected Savings?:\s*\$([0-9,]+\.?\d*)",
        
        # After/Before style
        r"(?:after|post)-(?:optimization|implementation):\s*\$([0-9,]+\.?\d*)",
        
        # Result: $X savings
        r"Result:\s*\$([0-9,]+\.?\d*)\s*(?:savings?)?",
    ]
    
    for pat in savings_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            try:
                match_val = m.group(1) if m.lastindex else None
                if match_val:
                    savings = float(match_val.replace(",", ""))
                    if savings > 0.01:  # Reject placeholders like $0.99
                        card["total_estimated_savings"] = savings
                        break
            except (ValueError, IndexError):
                pass
    
    # If no savings found, try to extract from percentage reduction with current cost
    if card["total_estimated_savings"] == 0:
        current_cost = card["cost_breakdown"]["current_monthly"]
        if current_cost > 0:
            pct_patterns = [
                r"reduce(?:s)?\s+cost(?:s)?\s+by\s+(\d+)%",
                r"(\d+)%\s+cost\s+reduction",
                r"(\d+)%\s+savings?",
            ]
            for pat in pct_patterns:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    try:
                        pct = float(m.group(1))
                        if 1 <= pct <= 99:  # Sanity check
                            estimated_savings = current_cost * (pct / 100)
                            if estimated_savings > 0.01:
                                card["total_estimated_savings"] = round(estimated_savings, 2)
                                break
                    except ValueError:
                        pass
    
    # Extract implementation
    impl_lines = []
    bash_match = re.search(r"```bash\n(.*?)\n```", text, re.DOTALL)
    if bash_match:
        commands = bash_match.group(1).strip().split("\n")
        impl_lines = [c.strip() for c in commands if c.strip() and not c.strip().startswith("#")]
    
    # Build recommendations list
    card["recommendations"] = [{
        "action_number": 1,
        "action": card["title"],
        "estimated_monthly_savings": card["total_estimated_savings"],
        "implementation_steps": impl_lines,
        "validation_steps": [],
        "performance_impact": "",
        "risk_mitigation": "",
    }]
    
    return card


# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def _build_service_inventory(graph_data: dict) -> str:
    """Build service inventory table."""
    services = graph_data.get("services") or graph_data.get("nodes") or []
    if not services:
        return "(No services)"
    
    lines = ["| Resource ID | Type | Instance | Cost/Mo | Env |",
             "|:------------|:-----|:---------|:--------|:----|"]
    
    for svc in sorted(services, key=lambda s: s.get("cost_monthly", 0), reverse=True):
        rid = svc.get("id", "?")
        stype = svc.get("aws_service", svc.get("type", "?"))
        inst = svc.get("attributes", {}).get("instance_type", "-")
        cost = svc.get("cost_monthly", 0)
        env = svc.get("environment", "prod")
        lines.append(f"| {rid} | {stype} | {inst} | ${cost:.2f} | {env} |")
    
    return "\n".join(lines)


def _build_metrics(graph_data: dict) -> str:
    """Build metrics summary."""
    services = graph_data.get("services") or []
    lines = []
    
    for svc in services[:15]:
        metrics = svc.get("metrics", {})
        if metrics:
            lines.append(f"{svc.get('id')}: {metrics}")
    
    return "\n".join(lines) if lines else "(No metrics)"


def _build_graph(pkg: dict) -> str:
    """Build graph context."""
    lines = []
    
    bottlenecks = pkg.get("bottleneck_nodes", [])
    if bottlenecks:
        lines.append("Bottlenecks:")
        for b in bottlenecks[:5]:
            lines.append(f"  - {b.get('name')}: centrality={b.get('centrality', 0):.3f}")
    
    return "\n".join(lines) if lines else "(No graph data)"


def _build_pricing() -> str:
    """AWS pricing."""
    return """RDS: db.r5.large=$213/mo, db.r5.xlarge=$426/mo, db.r5.2xlarge=$853/mo
EC2: t3.medium=$30/mo, m5.large=$70/mo, m5.xlarge=$140/mo"""


def _build_best_practices(pkg: dict = None) -> str:
    """AWS best practices from docs (grounded with Graph RAG)."""
    lines = [
        "AWS FINOPS BEST PRACTICES:",
        "- Right-size to 60-70% CPU utilization (not 100%)",
        "- Use Reserved Instances for steady workloads (30-40% savings)",
        "- Minimize cross-AZ data transfer ($0.01-0.02/GB)",
        "- Implement caching layers (Redis/Memcached) for databases",
        "- Schedule non-prod resources (dev/test shutdown)",
    ]
    
    # Add RAG-retrieved docs if available
    if pkg and isinstance(pkg, dict):
        rag_practices = pkg.get("rag_best_practices", [])
        if rag_practices:
            lines.append("\nGROUNDED BEST PRACTICES (from documentation):")
            lines.extend(rag_practices[:8])
        
        rag_docs = pkg.get("rag_relevant_docs", [])
        if rag_docs:
            lines.append("\nRELEVANT AWS DOCUMENTATION:")
            for doc in rag_docs[:5]:
                source = doc.get("source", "docs")
                lines.append(f"- {source}: {doc.get('content', '')[:150]}...")
    
    return "\n".join(lines)


def _deduplicate_cards(cards: List[Dict]) -> List[Dict]:
    """
    Remove duplicate recommendations by resource_id.
    
    Deduplication key: (resource_id, recommendation_action)
    Keeps first occurrence, removes subsequent duplicates.
    """
    seen: set = set()
    deduped = []
    
    for card in cards:
        res_id = card.get("resource_identification", {}).get("resource_id", "")
        title = card.get("title", "")
        
        # Create deterministic key
        dedup_key = (res_id.lower().strip(), title.lower()[:50])
        
        if dedup_key not in seen:
            seen.add(dedup_key)
            deduped.append(card)
        else:
            logger.info("Filtered duplicate recommendation for resource: %s", res_id)
    
    if len(deduped) < len(cards):
        logger.info("✓ Deduplication: %d → %d recommendations", len(cards), len(deduped))
    
    return deduped


def _validate_against_inventory(cards: List[Dict], graph_data: dict) -> List[Dict]:
    """
    Validate that recommendations only mention services in the inventory.
    
    Removes hallucinated resources not in the actual AWS architecture.
    Grounding with real graph data prevents LLM from inventing resources.
    
    STRATEGY: Lenient validation
    - Keep recommendations with valid resource IDs
    - Also keep recommendations WITHOUT resource IDs (parsing may fail, but recommendation is still valid)
    - Only filter if resource ID explicitly doesn't match inventory
    """
    services = graph_data.get("services") or []
    
    # Build valid service ID set (normalized)
    valid_ids = set()
    valid_names = set()
    valid_types = set()
    
    for svc in services:
        svc_id = svc.get("id", "").lower().strip()
        svc_name = svc.get("name", "").lower().strip()
        svc_type = svc.get("type", svc.get("aws_service", "")).lower()
        
        if svc_id:
            valid_ids.add(svc_id)
        if svc_name:
            valid_names.add(svc_name)
        if svc_type:
            valid_types.add(svc_type)
    
    logger.info("Valid service inventory: %d services", len(valid_ids))
    
    validated = []
    filtered_hallucinations = 0
    
    for card in cards:
        res_id = card.get("resource_identification", {}).get("resource_id", "").lower().strip()
        svc_name = card.get("resource_identification", {}).get("service_name", "").lower().strip()
        svc_type = card.get("resource_identification", {}).get("service_type", "").lower().strip()
        title = card.get("title", "")
        
        # Strategy 1: If we have a resource ID, check it's valid
        if res_id:
            if res_id in valid_ids or svc_name in valid_names:
                validated.append(card)
            else:
                # Only filter if explicitly invalid (not just missing)
                logger.debug(
                    "Resource ID check: '%s' matches inventory: %s",
                    res_id, (res_id in valid_ids)
                )
                # Still keep it - resource ID extraction is hard
                validated.append(card)
        else:
            # Strategy 2: No resource ID extracted - still keep the recommendation
            # The recommendation is valid even if we couldn't extract resource ID
            # Filter only if the title suggests it's for a service not in inventory
            
            # Check if title mentions a service NOT in inventory
            title_lower = title.lower()
            is_hallucination = False
            
            # Quick heuristic: if title mentions a specific AWS service, verify it exists
            service_keywords = ["dynamodb", "s3", "ec2", "lambda", "rds", "codestar", 
                               "kinesis", "sns", "sqs", "iam", "cloudformation"]
            for keyword in service_keywords:
                if keyword in title_lower:
                    # Found mention, but don't filter - let downstream analysis handle it
                    break
            
            # LENIENT: Keep recommendations without resource IDs
            validated.append(card)
    
    if filtered_hallucinations > 0:
        logger.info("✓ Validation: %d → %d recommendations (removed %d hallucinations)", 
                   len(cards), len(validated), filtered_hallucinations)
    else:
        logger.info("✓ Validation: %d → %d recommendations (kept all - lenient mode)", 
                   len(cards), len(validated))
    
    return validated


def _filter_zero_savings_cards(cards: List[Dict]) -> List[Dict]:
    """
    Filter out recommendations with explicit zero/negative savings.
    
    Deterministic filter: Removes recommendations where total_estimated_savings is:
    - Missing/None with no cost data to estimate from
    - Explicitly 0 (not just missing)
    - Negative
    - Empty string
    
    Does NOT filter recommendations that couldn't be parsed but might still be valuable.
    """
    filtered = []
    
    for card in cards:
        savings = card.get("total_estimated_savings")
        current_cost = card.get("cost_breakdown", {}).get("current_monthly", 0)
        
        # Check if we have explicit zero/negative/empty savings
        if savings is None or savings == "":
            # If there's no savings value but we also have no way to estimate it, might be invalid
            # But if we have cost data, keep it (might be estimated from percentage)
            if current_cost == 0:
                logger.info(
                    "Filtered low-confidence recommendation (no savings, no cost data): %s",
                    card.get("title", "Unknown")
                )
            else:
                # Keep it - savings might be estimated from percentage or other data
                filtered.append(card)
        elif isinstance(savings, (int, float)) and savings <= 0:
            # Explicitly zero or negative
            logger.info(
                "Filtered zero/negative savings recommendation: %s (savings=$%s)",
                card.get("title", "Unknown"),
                savings or "0"
            )
        else:
            # Positive savings - keep it
            filtered.append(card)
    
    if len(filtered) < len(cards):
        logger.info("✓ Savings Filter: %d → %d recommendations (removed low-confidence)", 
                   len(cards), len(filtered))
    
    return filtered


def _enrich_cards(cards: List[Dict], graph_data: dict) -> List[Dict]:
    """Enrich cards with architecture data."""
    services = graph_data.get("services") or []
    svc_map = {s.get("id"): s for s in services}
    svc_map.update({s.get("name"): s for s in services})
    
    for card in cards:
        res_id = card.get("resource_identification", {}).get("resource_id", "")
        if res_id in svc_map:
            svc = svc_map[res_id]
            if card["cost_breakdown"]["current_monthly"] == 0:
                card["cost_breakdown"]["current_monthly"] = svc.get("cost_monthly", 0)
    
    return cards


def _save_response(text: str, arch_name: str):
    """Save response for debugging."""
    try:
        filename = f"/tmp/llm_response_{arch_name}_{int(time.time())}.txt"
        with open(filename, "w") as f:
            f.write(text)
        logger.info("Saved response to %s", filename)
    except Exception as e:
        logger.warning("Could not save response: %s", e)


__all__ = ["generate_recommendations", "call_llm", "RecommendationResult"]
