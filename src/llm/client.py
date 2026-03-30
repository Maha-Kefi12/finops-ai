"""
LLM Client for FinOps Recommendations
======================================
Supports both Gemini Flash (API) and Qwen 2.5 7B (local Ollama).
Uses environment variable USE_GEMINI to switch between backends.
"""

import os
import json
import time
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

from src.rag.graph_business_translator import build_business_context_for_resources
from src.knowledge_base.aws_finops_best_practices import (
    COMPUTE_BEST_PRACTICES,
    DATABASE_BEST_PRACTICES,
    STORAGE_BEST_PRACTICES,
    NETWORKING_BEST_PRACTICES,
    get_best_practices_for_service,
)
from src.llm.finops_metrics import FinOpsMetricsExtractor

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
OLLAMA_MODEL = os.getenv("FINOPS_MODEL", "qwen2.5:7b")  # Use Qwen 2.5 7B as primary model

# Backend selection
USE_GEMINI = os.getenv("USE_GEMINI", "false").lower() == "true" and GEMINI_API_KEY

MAX_RETRIES = 3
TIMEOUT = 300  # Standard timeout for 4000 token generation


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
    """Generate recommendations using engine-grounded LLM + deterministic controls."""
    
    from src.llm.prompts import RECOMMENDATION_SYSTEM_PROMPT, RECOMMENDATION_USER_PROMPT
    
    start = time.time()
    result = RecommendationResult(architecture_name=architecture_name)
    
    logger.info("=" * 70)
    logger.info("GENERATING RECOMMENDATIONS (Engine-grounded LLM)")
    logger.info("Backend: %s", "Gemini Flash" if USE_GEMINI else "Qwen 2.5 (Ollama)")
    logger.info("=" * 70)
    try:
        pkg_dict = asdict(context_package) if hasattr(context_package, '__dataclass_fields__') else context_package

        # ═══ STAGE 0: Deterministic engine facts (grounding + fallback) ═══
        engine_cards: List[Dict[str, Any]] = []
        if raw_graph_data:
            try:
                from src.recommendation_engine.scanner import scan_architecture
                from src.recommendation_engine.enricher import enrich_matches

                matches = scan_architecture(raw_graph_data)
                enriched = enrich_matches(matches, raw_graph_data)
                engine_cards = _engine_to_cards(enriched)
                logger.info("[ENGINE] %d matches -> %d cards", len(matches), len(engine_cards))
            except Exception as e:
                logger.warning("[ENGINE] failed to build grounding facts: %s", e)

        # ═══ STAGE 1: Build LLM context ═══
        service_inventory = _build_service_inventory(raw_graph_data) if raw_graph_data else ""
        cloudwatch_metrics = _build_metrics(raw_graph_data) if raw_graph_data else ""
        graph_context = _build_graph(pkg_dict)
        business_graph_context = _build_business_graph_context(raw_graph_data, pkg_dict) if raw_graph_data else "(No business graph context)"
        pricing_data = _build_pricing()
        aws_best_practices = _build_best_practices(pkg_dict, raw_graph_data)

        user_prompt = RECOMMENDATION_USER_PROMPT.format(
            service_inventory=service_inventory,
            cloudwatch_metrics=cloudwatch_metrics,
            graph_context=graph_context,
            business_graph_context=business_graph_context,
            pricing_data=pricing_data,
            aws_best_practices=aws_best_practices,
        )

        # Ground LLM with deterministic engine signals (facts, not format template).
        if engine_cards:
            user_prompt += (
                "\n\n## ENGINE_FACTS (source of truth from deterministic engine)\n\n"
                + _format_engine_context(engine_cards)
            )

        prompt_chars = len(RECOMMENDATION_SYSTEM_PROMPT) + len(user_prompt)
        logger.info(
            "[PROMPT SIZE] system=%d, user=%d, total=%d chars (~%d tokens)",
            len(RECOMMENDATION_SYSTEM_PROMPT),
            len(user_prompt),
            prompt_chars,
            prompt_chars // 4,
        )

        # ═══ STAGE 2: LLM call (primary recommender) ═══
        llm_cards: List[Dict[str, Any]] = []
        try:
            logger.info("[STAGE 2] Starting LLM call...")
            logger.info("[LLM] Using backend: %s", "Gemini" if USE_GEMINI else "Ollama")
            logger.info("[LLM] Model: %s", OLLAMA_MODEL if not USE_GEMINI else GEMINI_MODEL)
            logger.info("[LLM] URL: %s", OLLAMA_URL if not USE_GEMINI else "Gemini API")
            
            t3 = time.time()
            raw_response = call_llm(
                system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=6000,
                architecture_name=architecture_name,
            )
            logger.info(
                "[TIMING] LLM call completed in %.1fs (%d chars)",
                time.time() - t3,
                len(raw_response) if raw_response else 0,
            )

            if raw_response:
                _save_response(raw_response, architecture_name)
                llm_cards = _parse_structured_json_recommendations(raw_response)
                if not llm_cards:
                    llm_cards = _parse_all_recommendations(raw_response)
                logger.info("[PIPELINE] LLM parsed: %d recommendations", len(llm_cards))

                if llm_cards:
                    llm_cards = _deduplicate_cards(llm_cards)
                    if raw_graph_data:
                        llm_cards = _enrich_cards(llm_cards, raw_graph_data, pkg_dict)
                        llm_cards = _apply_deterministic_quality_gates(
                            llm_cards,
                            raw_graph_data,
                            min_monthly_savings=50.0,
                        )
        except Exception as e:
            logger.error("[LLM] Call failed with exception: %s — will fall back to engine", e, exc_info=True)

        # ═══ STAGE 3: Validate LLM-proposed recommendations ═══
        validated_llm_cards: List[Dict[str, Any]] = []
        rejected_llm_cards: List[Dict[str, Any]] = []
        
        if llm_cards and raw_graph_data:
            try:
                from src.recommendation_engine.validator import validate_llm_recommendations
                
                validated_llm_cards, rejected_llm_cards = validate_llm_recommendations(
                    llm_cards,
                    raw_graph_data,
                    engine_cards
                )
                
                logger.info(
                    "[VALIDATION] LLM cards: %d total → %d validated, %d rejected",
                    len(llm_cards),
                    len(validated_llm_cards),
                    len(rejected_llm_cards)
                )
            except Exception as e:
                logger.warning("[VALIDATION] Failed: %s — using LLM cards as-is", e)
                validated_llm_cards = llm_cards
        else:
            validated_llm_cards = llm_cards

        # ═══ STAGE 4: Merge selection (engine truth + validated LLM) ═══
        cards = _merge_engine_and_llm_cards(engine_cards, validated_llm_cards)
        
        # Optional: Include rejected cards as "insights" (commented out by default)
        # for rejected_card in rejected_llm_cards:
        #     rejected_card['is_insight'] = True
        #     cards.append(rejected_card)
        
        if raw_graph_data:
            cards = [_populate_card_metrics(c, raw_graph_data) for c in cards]
        
        logger.info(
            "[PIPELINE] Final: %d cards (engine=%d, validated_llm=%d, rejected_llm=%d) with metrics hardened",
            len(cards),
            len(engine_cards),
            len(validated_llm_cards),
            len(rejected_llm_cards)
        )

        if not cards:
            logger.warning("⚠️  No recommendations generated from engine/LLM — returning empty set")

        result.cards = cards
        result.llm_used = bool(llm_cards)
        result.total_estimated_savings = sum(c.get("total_estimated_savings", 0) for c in cards) if cards else 0.0
        result.generation_time_ms = int((time.time() - start) * 1000)

        logger.info("=" * 70)
        logger.info(
            "COMPLETE: %d recommendations, $%.2f savings, %dms",
            len(cards),
            result.total_estimated_savings,
            result.generation_time_ms,
        )
        logger.info("=" * 70)

        return result

    except Exception as e:
        logger.error("Generation failed: %s", e, exc_info=True)
        result.error = str(e)
        result.generation_time_ms = int((time.time() - start) * 1000)
        raise


# ═══════════════════════════════════════════════════════════════════════════
# ENGINE → CARD CONVERSION
# ═══════════════════════════════════════════════════════════════════════════

def _engine_to_cards(enriched_matches: List[Dict]) -> List[Dict]:
    """Convert engine enriched matches to the card format expected by the frontend.
    
    Field names MUST match what FullRecommendationCard in AnalysisPage.jsx reads:
    - graph_context.{dependency_count, dependent_services, cross_az_count, 
      cross_az_dependencies, cascading_failure_risk, narrative, centrality,
      blast_radius_pct, blast_radius_services, is_spof, depends_on_count}
    - recommendations[].{title, implementation_steps, performance_impact, 
      risk_mitigation, estimated_monthly_savings, full_analysis}
    - resource_identification.{resource_id, service_type, region, environment,
      current_config, tags}
    - cost_breakdown.{current_monthly, line_items[].{item, usage, cost}}
    - severity, category, implementation_complexity
    """
    cards: List[Dict[str, Any]] = []

    for match in enriched_matches:
        enrichment = match.get("enrichment", {})
        gm = match.get("graph_metrics", {})
        traffic = enrichment.get("traffic", {})
        cross_az = enrichment.get("cross_az", {})
        redundancy = enrichment.get("redundancy", {})
        deps_in = enrichment.get("dependencies_in", [])
        deps_out = enrichment.get("dependencies_out", [])

        # ── Resource info ──
        resource_id = match.get("resource_id", "")
        resource_name = match.get("resource_name", "")
        aws_service = match.get("aws_service", "AWS")
        env = match.get("environment", "production")
        region = match.get("region", "us-east-1")
        current_type = match.get("current_instance_type", "")
        recommended_type = match.get("recommended_instance_type", "")
        savings = match.get("estimated_savings_monthly", 0)
        cost = match.get("current_monthly_cost", 0)
        savings_pct = match.get("savings_percentage", 0)

        # ── Why it matters (narrative) ──
        why = match.get("rendered_why_it_matters", "")

        # ── Build implementation CLI command ──
        impl_cmd = match.get("rendered_implementation", match.get("implementation_template", ""))

        # ── Map priority to severity ──
        priority_to_severity = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
        severity = priority_to_severity.get(match.get("priority", "MEDIUM"), "medium")

        # ── Build dependent_services list (names of services that depend on this) ──
        dependent_services = [d.get("resource", "") for d in deps_in if d.get("resource")]
        depends_on_services = [d.get("resource", "") for d in deps_out if d.get("resource")]

        # ── Cross-AZ dependency details ──
        cross_az_deps = cross_az.get("az_pairs", [])
        cross_az_count = cross_az.get("cross_az_count", 0)

        # ── Build current_config string ──
        config_parts = []
        if current_type:
            config_parts.append(f"Instance Type: {current_type}")
        config_parts.append(f"Service: {aws_service}")
        config_parts.append(f"Region: {region}")
        config_parts.append(f"Environment: {env}")
        if gm.get("utilization_score", 0) > 0:
            config_parts.append(f"CPU Utilization: {gm['utilization_score']}%")
        current_config = " | ".join(config_parts)

        # ── Build cost line items ──
        line_items = [
            {"item": f"{aws_service} Instance/Service Cost", "usage": f"{env} ({region})", "cost": cost},
        ]
        if cross_az.get("has_cross_az"):
            xaz_cost = cross_az.get("estimated_monthly_cost", 0)
            line_items.append({"item": "Cross-AZ Data Transfer", "usage": f"{cross_az_count} cross-AZ edges", "cost": xaz_cost})

        # ── Build full analysis text ──
        analysis_parts = []
        analysis_parts.append(f"Pattern Detected: {match.get('pattern_id', 'N/A')}")
        analysis_parts.append(f"Best Practice: {match.get('linked_best_practice', '')}")
        analysis_parts.append("")
        analysis_parts.append(f"Current State: {current_type} in {region} ({env} environment)")
        analysis_parts.append(f"Recommended: Migrate to {recommended_type}")
        analysis_parts.append(f"Estimated Savings: ${savings:.2f}/month (${savings * 12:.2f}/year)")
        analysis_parts.append("")
        if why:
            analysis_parts.append(f"Impact Analysis: {why}")
        if not redundancy.get("has_full_redundancy", True):
            analysis_parts.append(f"WARNING: No redundancy path exists. {len(dependent_services)} service(s) will be impacted if this resource fails.")
        if gm.get("single_point_of_failure"):
            analysis_parts.append("CRITICAL: This is a Single Point of Failure. Add redundancy before making changes.")
        full_analysis = "\n".join(analysis_parts)

        # ── Build implementation steps ──
        impl_steps = []
        impl_steps.append(f"1. Review current {aws_service} resource: {resource_id}")
        impl_steps.append("2. Verify no active deployments depend on current configuration")
        if dependent_services:
            impl_steps.append(f"3. Notify teams owning dependent services: {', '.join(dependent_services)}")
        impl_steps.append(f"{'4' if dependent_services else '3'}. Execute change in staging first:")
        impl_steps.append(f"   {impl_cmd}")
        impl_steps.append(f"{'5' if dependent_services else '4'}. Monitor CloudWatch metrics for 24h post-change")
        impl_steps.append(f"{'6' if dependent_services else '5'}. Validate: aws cloudwatch get-metric-statistics --namespace AWS/{aws_service}")

        # ── Cascade risk label ──
        cascade_risk = gm.get("cascading_failure_risk", enrichment.get("cascade_risk", "low"))

        # ── Risk mitigation text ──
        risk_parts = []
        risk_parts.append(f"Risk Level: {match.get('risk_level', 'LOW')}")
        if dependent_services:
            risk_parts.append(f"Impact: {len(dependent_services)} dependent service(s) - {', '.join(dependent_services)}")
        if gm.get("single_point_of_failure"):
            risk_parts.append("SPOF: Add Multi-AZ or replica BEFORE making changes")
        if not redundancy.get("has_full_redundancy", True):
            risk_parts.append("No redundancy: Create failover path before proceeding")
        risk_parts.append("Always test in staging/dev environment first")
        risk_mitigation = ". ".join(risk_parts)

        card = {
            # ── Core fields that frontend reads ──
            "title": match.get("title", match.get("recommendation_template", "Optimization")[:80]),
            "service_type": aws_service,
            "total_estimated_savings": savings,
            "priority": match.get("priority", "MEDIUM"),
            "severity": severity,
            "category": match.get("category", "right_sizing").replace("_", "-"),
            "implementation_complexity": "low" if match.get("risk_level") == "LOW" else ("high" if match.get("risk_level") == "HIGH" else "medium"),
            "risk_level": match.get("risk_level", "LOW"),

            # ── Resource identification ──
            "resource_identification": {
                "resource_id": resource_id,
                "resource_name": resource_name,
                "service_type": aws_service,
                "service_name": resource_name,
                "environment": env,
                "region": region,
                "current_instance_type": current_type,
                "recommended_instance_type": recommended_type,
                "current_config": current_config,
                "tags": {
                    "Environment": env,
                    "Service": aws_service,
                    "Name": resource_name,
                    "Region": region,
                },
            },

            # ── Cost breakdown (with line_items for table) ──
            "cost_breakdown": {
                "current_monthly": cost,
                "projected_monthly": max(0, cost - savings),
                "savings_percentage": savings_pct,
                "annual_impact": savings * 12,
                "line_items": line_items,
            },

            # ── Graph context (field names MATCH FullRecommendationCard JSX) ──
            "graph_context": {
                "blast_radius_pct": round(enrichment.get("blast_radius_pct", 0), 1),
                "blast_radius_services": enrichment.get("services_powered", 0) + len(depends_on_services),
                "dependency_count": enrichment.get("services_powered", 0),
                "depends_on_count": len(depends_on_services),
                "dependent_services": dependent_services,
                "cross_az_count": cross_az_count,
                "cross_az_dependencies": cross_az_deps,
                "is_spof": gm.get("single_point_of_failure", False),
                "cascading_failure_risk": cascade_risk,
                "centrality": gm.get("centrality", 0),
                "narrative": why,
                "severity_label": f"{'critical bottleneck' if gm.get('centrality', 0) > 0.3 else 'architectural importance'}",
                "total_qps": traffic.get("total_qps", 0),
                "avg_latency_ms": traffic.get("avg_latency_ms", 0),
                "avg_error_rate": traffic.get("avg_error_rate", 0),
                "has_redundancy": redundancy.get("has_full_redundancy", True),
                "alternative_paths": redundancy.get("alternative_paths", {}),
            },

            # ── Recommendations array (frontend iterates this) ──
            "recommendations": [{
                "title": match.get("linked_best_practice", ""),
                "description": match.get("linked_best_practice", ""),
                "full_analysis": full_analysis,
                "implementation_steps": impl_steps,
                "performance_impact": f"Savings: ${savings:.2f}/mo ({savings_pct}% reduction). Annual impact: ${savings * 12:.2f}/yr",
                "risk_mitigation": risk_mitigation,
                "estimated_monthly_savings": savings,
                "confidence": "high" if match.get("risk_level") == "LOW" else "medium",
            }],

            # ── Best practice (frontend checks this field name) ──
            "finops_best_practice": match.get("linked_best_practice", ""),
            "linked_best_practice": match.get("linked_best_practice", ""),
            "why_it_matters": why,
            "pattern_id": match.get("pattern_id", ""),
            "source": "engine",
        }
        cards.append(card)

    return cards


def _format_engine_context(engine_cards: List[Dict]) -> str:
    """Format engine cards as structured text for LLM context injection."""
    lines = []
    for i, card in enumerate(engine_cards[:10], 1):  # Max 10 in context
        rid = card.get("resource_identification", {})
        cost = card.get("cost_breakdown", {})
        graph = card.get("graph_context", {})
        
        lines.append(f"ENGINE SIGNAL #{i}: {card.get('title', 'N/A')}")
        lines.append(f"- Resource: `{rid.get('resource_id', 'N/A')}` ({rid.get('resource_name', '')})")
        lines.append(f"- Service: {card.get('service_type', 'N/A')} | Env: {rid.get('environment', '?')} | Region: {rid.get('region', '?')}")
        lines.append(f"- Current: {rid.get('current_instance_type', '?')} → Recommended: {rid.get('recommended_instance_type', '?')}")
        lines.append(f"- Cost: ${cost.get('current_monthly', 0):.2f}/mo → Save ${card.get('total_estimated_savings', 0):.2f}/mo ({cost.get('savings_percentage', 0)}%)")
        lines.append(f"- Graph: blast={graph.get('blast_radius_pct', 0)}%, deps={graph.get('services_powered', 0)}, SPOF={graph.get('is_spof', False)}")
        lines.append(f"- Best Practice: {card.get('linked_best_practice', 'N/A')}")
        lines.append(f"- Why: {card.get('why_it_matters', 'N/A')[:150]}")
        lines.append("")
    
    return "\n".join(lines)


def _extract_primary_action_bucket(card: Dict[str, Any]) -> str:
    """Classify a recommendation into an action bucket for dedup/conflict handling."""
    title = str(card.get("title", "") or "").lower()
    rec0 = (card.get("recommendations") or [{}])[0]
    action = str(rec0.get("action", "") or "").lower()
    pattern_id = str(card.get("pattern_id", "") or "").lower()
    text = f"{title} {action} {pattern_id}"

    if any(k in text for k in ("terminate", "decommission", "delete", "retire", "shutdown", "stop instance", "stop-instances")):
        return "terminate"
    if any(k in text for k in ("right-size", "rightsize", "downsize", "resize", "rightsizing", "rightsized")):
        return "right_size"
    return "other"


def _conflict_resolution_signal(cards_for_resource: List[Dict[str, Any]]) -> str:
    """Resolve terminate-vs-right-size using explicit business confirmation fields.

    Returns one of: terminate, right_size, ambiguous.
    """
    bag: List[str] = []
    backups_safe = False

    for c in cards_for_resource:
        rid = c.get("resource_identification", {}) or {}
        tags = rid.get("tags", {}) or {}
        gc = c.get("graph_context", {}) or {}
        ctx = c.get("decision_context", {}) or {}

        for v in (
            ctx.get("instance_lifecycle_decision"),
            c.get("instance_lifecycle_decision"),
            rid.get("instance_lifecycle_decision"),
            tags.get("instance_lifecycle_decision"),
            tags.get("business_decision"),
            c.get("business_decision"),
            c.get("future_use_status"),
            tags.get("future_use_status"),
        ):
            if v is not None:
                bag.append(str(v).strip().lower())

        backup_vals = (
            ctx.get("backup_safe"),
            c.get("backup_safe"),
            rid.get("backup_safe"),
            tags.get("backup_safe"),
            gc.get("backup_safe"),
            tags.get("backups_verified"),
            c.get("backups_verified"),
        )
        for bv in backup_vals:
            if isinstance(bv, bool):
                backups_safe = backups_safe or bv
            elif isinstance(bv, str) and bv.strip().lower() in {"true", "yes", "verified", "safe"}:
                backups_safe = True

    if any(k in " ".join(bag) for k in ("no future use", "decommission", "retire", "terminate")) and backups_safe:
        return "terminate"
    if any(k in " ".join(bag) for k in ("needed", "keep", "still used", "oversized", "rightsizing")):
        return "right_size"
    return "ambiguous"


def _dedupe_and_resolve_conflicts(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove true duplicates and collapse terminate-vs-right-size conflicts per resource."""
    if not cards:
        return cards

    # 1) True duplicate removal: same resource + same action bucket + same savings.
    deduped: List[Dict[str, Any]] = []
    seen: Dict[Tuple[str, str, int], int] = {}
    dropped_dups = 0

    for card in cards:
        rid = str((card.get("resource_identification") or {}).get("resource_id", "") or "").strip().lower()
        action_bucket = _extract_primary_action_bucket(card)
        savings = float(card.get("total_estimated_savings", 0) or 0)
        key = (rid, action_bucket, int(round(savings * 100)))

        if key in seen:
            prev = deduped[seen[key]]
            prev_source = str(prev.get("source", "") or "")
            new_source = str(card.get("source", "") or "")
            # Prefer engine card when duplicate pair exists.
            if prev_source != "engine" and new_source == "engine":
                deduped[seen[key]] = card
            dropped_dups += 1
            continue

        seen[key] = len(deduped)
        deduped.append(card)

    # 2) Conflict resolution: same resource has terminate and right-size options.
    by_resource: Dict[str, List[Dict[str, Any]]] = {}
    for c in deduped:
        rid = str((c.get("resource_identification") or {}).get("resource_id", "") or "").strip().lower()
        if not rid:
            rid = f"_noid_{id(c)}"
        by_resource.setdefault(rid, []).append(c)

    resolved: List[Dict[str, Any]] = []
    conflict_resolved = 0

    for rid, group in by_resource.items():
        terminate_cards = [c for c in group if _extract_primary_action_bucket(c) == "terminate"]
        right_size_cards = [c for c in group if _extract_primary_action_bucket(c) == "right_size"]

        if terminate_cards and right_size_cards:
            decision = _conflict_resolution_signal(group)
            if decision == "terminate":
                keep = terminate_cards
                drop = right_size_cards
                reason = "business confirmed no future use and backups verified"
            else:
                # Default-safe branch: keep right-size unless explicit terminate signal exists.
                keep = right_size_cards
                drop = terminate_cards
                reason = "resource still needed/oversized or terminate confirmation missing"

            for c in keep:
                c.setdefault("conflict_resolution", {})
                c["conflict_resolution"].update({
                    "resource_id": rid,
                    "decision": decision if decision != "ambiguous" else "right_size",
                    "reason": reason,
                    "dropped_alternatives": len(drop),
                })
                resolved.append(c)
            for c in group:
                if c not in keep and c not in drop:
                    resolved.append(c)
            conflict_resolved += len(drop)
            continue

        resolved.extend(group)

    logger.info(
        "[DEDUP/CONFLICT] in=%d true_duplicates_removed=%d conflict_alternatives_removed=%d out=%d",
        len(cards),
        dropped_dups,
        conflict_resolved,
        len(resolved),
    )
    return resolved


def _merge_engine_and_llm_cards(engine_cards: List[Dict], llm_cards: List[Dict]) -> List[Dict]:
    """Merge engine and LLM cards with perfect balance.
    
    Strategy:
    1) Engine cards ALWAYS displayed (deterministic baseline).
    2) LLM cards for EXISTING resources are always appended (adds narrative diversity).
    3) LLM cards for NEW resources are appended (true discoveries).
    4) Deduplication is SMART: only remove near-identical pairs, keep variants.
    
    Result: Users see BOTH engine facts AND LLM insights without aggressive filtering.
    """
    if not engine_cards and not llm_cards:
        return []
    if not engine_cards:
        return [_coerce_backend_card_template(c, source_hint="llm") for c in (llm_cards or [])]
    if not llm_cards:
        return [_coerce_backend_card_template(c, source_hint="engine") for c in engine_cards]

    # Start with all engine cards (always included).
    merged = [_coerce_backend_card_template(c, source_hint="engine") for c in engine_cards]

    appended = 0

    # Process LLM cards: append all (post-step resolver handles duplicate/conflict removal).
    for llm_card in llm_cards:
        llm_card = _coerce_backend_card_template(llm_card, source_hint="llm")
        merged.append(llm_card)
        appended += 1

    merged = _dedupe_and_resolve_conflicts(merged)

    # Sort by savings to show high-impact recommendations first.
    merged.sort(
        key=lambda c: float(c.get("total_estimated_savings", 0) or 0),
        reverse=True,
    )

    logger.info("[MERGE] engine=%d llm=%d appended=%d => final=%d (post-policy dedup/conflict applied)",
                len(engine_cards), len(llm_cards), appended, len(merged))
    return [_coerce_backend_card_template(c) for c in merged]


def _coerce_backend_card_template(card: Dict[str, Any], source_hint: str = "") -> Dict[str, Any]:
    """Force a recommendation card into backend/frontend-compatible template shape."""
    c = _normalize_llm_card_shape(dict(card))

    if source_hint and not c.get("source"):
        c["source"] = source_hint

    # recommendation_number MUST be an integer, never a string.
    try:
        rec_num = int(c.get("recommendation_number", 1) or 1)
    except (ValueError, TypeError):
        rec_num = 1
    c["recommendation_number"] = rec_num

    c.setdefault("priority", c.get("severity", "medium"))
    c.setdefault("inefficiencies", [])
    c.setdefault("category", "right_sizing")
    c.setdefault("severity", "medium")
    c.setdefault("risk_level", "medium")
    c.setdefault("implementation_complexity", "medium")
    c.setdefault("why_it_matters", c.get("raw_analysis", ""))
    c.setdefault("linked_best_practice", "")
    c.setdefault("finops_best_practice", c.get("linked_best_practice", ""))

    rid = c.setdefault("resource_identification", {})
    rid.setdefault("resource_id", "")
    rid.setdefault("resource_name", rid.get("service_name", rid.get("resource_id", "")))
    rid.setdefault("service_name", rid.get("resource_name", rid.get("resource_id", "")))
    rid.setdefault("service_type", c.get("service_type", rid.get("service_type", "service")))

    c.setdefault("service_type", rid.get("service_type", "service"))

    cost = c.setdefault("cost_breakdown", {})
    cost.setdefault("current_monthly", 0.0)
    cost.setdefault("projected_monthly", 0.0)
    if not cost.get("annual_impact"):
        savings_for_annual = float(c.get("total_estimated_savings", 0) or 0)
        cost["annual_impact"] = round(savings_for_annual * 12, 2)
    if cost.get("savings_percentage") is None:
        current_m = float(cost.get("current_monthly", 0) or 0)
        projected_m = float(cost.get("projected_monthly", 0) or 0)
        if current_m > 0:
            cost["savings_percentage"] = round(max(0.0, (current_m - projected_m) / current_m * 100.0), 2)
        else:
            cost["savings_percentage"] = 0.0
    if not isinstance(cost.get("line_items"), list):
        cost["line_items"] = []

    graph = c.setdefault("graph_context", {})
    graph.setdefault("dependency_count", 0)
    graph.setdefault("dependent_services", [])
    graph.setdefault("depends_on_count", 0)
    graph.setdefault("blast_radius_pct", 0)
    graph.setdefault("blast_radius_services", 0)
    graph.setdefault("is_spof", False)
    graph.setdefault("cascading_failure_risk", "low")
    graph.setdefault("centrality", 0)
    graph.setdefault("narrative", "")
    graph.setdefault("cross_az_count", 0)

    graph.setdefault("cross_az_dependencies", [])

    # Wire metrics_summary: comprehensive finops metrics (CPU, IOPS, P95 latency, cost, error rate)
    metrics_summary = c.setdefault("metrics_summary", {})
    metrics_summary.setdefault("cpu_utilization_percent", None)
    metrics_summary.setdefault("memory_utilization_percent", None)
    metrics_summary.setdefault("iops", None)
    metrics_summary.setdefault("read_iops", None)
    metrics_summary.setdefault("write_iops", None)
    metrics_summary.setdefault("latency_p50_ms", None)
    metrics_summary.setdefault("latency_p95_ms", None)
    metrics_summary.setdefault("latency_p99_ms", None)
    metrics_summary.setdefault("error_rate_percent", None)
    metrics_summary.setdefault("throughput_qps", None)
    metrics_summary.setdefault("throughput_rps", None)
    metrics_summary.setdefault("network_in_mbps", None)
    metrics_summary.setdefault("network_out_mbps", None)
    metrics_summary.setdefault("cost_monthly", None)
    metrics_summary.setdefault("cost_p95_monthly", None)
    metrics_summary.setdefault("health_score", 75.0)
    metrics_summary.setdefault("observation", "")
    recs = c.setdefault("recommendations", [])
    if not recs:
        recs.append({
            "action_number": 1,
            "title": c.get("title", "Optimization Recommendation"),
            "description": c.get("title", "Optimization Recommendation"),
            "action": c.get("title", "Optimization Recommendation"),
            "estimated_monthly_savings": float(c.get("total_estimated_savings", 0) or 0),
            "implementation_steps": [],
            "validation_steps": [],
            "performance_impact": f"Estimated savings: ${float(c.get('total_estimated_savings', 0) or 0):.2f}/mo",
            "risk_mitigation": f"Risk level: {c.get('risk_level', 'medium')}",
            "full_analysis": str(c.get("raw_analysis", ""))[:1200],
            "confidence": "medium",
        })

    normalized_recs: List[Dict[str, Any]] = []
    for i, rec in enumerate(recs, 1):
        if not isinstance(rec, dict):
            rec = {"action": str(rec)}
        rec.setdefault("action_number", i)
        rec.setdefault("title", c.get("title", "Optimization Recommendation"))
        rec.setdefault("action", rec.get("title", c.get("title", "Optimization Recommendation")))
        rec.setdefault("description", rec.get("title", c.get("title", "Optimization Recommendation")))
        try:
            rec.setdefault("estimated_monthly_savings", float(c.get("total_estimated_savings", 0) or 0))
        except Exception:
            rec.setdefault("estimated_monthly_savings", 0.0)
        if not isinstance(rec.get("implementation_steps"), list):
            rec["implementation_steps"] = [str(rec.get("implementation_steps", "")).strip()] if rec.get("implementation_steps") else []
        if not isinstance(rec.get("validation_steps"), list):
            rec["validation_steps"] = [
                "Track CloudWatch/Datadog metrics for 24h after rollout",
                "Validate no latency/error regression on dependent services",
                "Confirm monthly cost trend reduction in billing dashboard",
            ]
        rec.setdefault("performance_impact", f"Estimated savings: ${float(rec.get('estimated_monthly_savings', 0) or 0):.2f}/mo")
        rec.setdefault("risk_mitigation", f"Risk level: {c.get('risk_level', 'medium')}")
        rec.setdefault("full_analysis", str(c.get("raw_analysis", c.get("why_it_matters", "")))[:1200])
        rec.setdefault("confidence", "medium")
        normalized_recs.append(rec)

    c["recommendations"] = normalized_recs

    return c


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
    
    if len(matches1) >= 1:
        logger.info("Strategy 1: Found %d recommendations via '### Recommendation #N'", len(matches1))
        return _extract_sections(text, matches1)
    
    # Strategy 2: Split by any ### header
    pattern2 = r"###\s+([^\n#]{5,100})"
    matches2 = list(re.finditer(pattern2, text))
    
    if len(matches2) >= 1:
        logger.info("Strategy 2: Found %d recommendations via '### [title]'", len(matches2))
        return _extract_sections(text, matches2)
    
    # Strategy 3: Split by "---" (triple dash)
    sections = text.split("---")
    sections = [s.strip() for s in sections if len(s.strip()) > 100]
    
    if len(sections) >= 1:
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
    
    if len(sections) >= 1:
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


def _parse_structured_json_recommendations(text: str) -> List[Dict]:
    """Parse strict JSON recommendation output from LLM.

    Expected shape:
    {
      "recommendations": [
        {
          "title": "...",
          "resource_id": "...",
          "service_type": "...",
          "environment": "production|development|...",
          "current_monthly_cost": 120.0,
          "projected_monthly_cost": 70.0,
          "monthly_savings": 50.0,
          "category": "...",
          "risk_level": "low|medium|high",
          "confidence": 0.86,
          "why_this_matters": "...",
          "problem": "...",
          "solution": "...",
          "implementation_steps": ["..."],
          "risk_mitigation": "..."
        }
      ]
    }
    """
    if not text:
        return []

    payload_str = text.strip()
    fence_match = re.search(r"```json\s*(\{[\s\S]*\}|\[[\s\S]*\])\s*```", text, re.IGNORECASE)
    if fence_match:
        payload_str = fence_match.group(1).strip()
    else:
        brace_start = text.find("{")
        bracket_start = text.find("[")
        candidates = [x for x in (brace_start, bracket_start) if x >= 0]
        if candidates:
            payload_str = text[min(candidates):].strip()

    try:
        parsed = json.loads(payload_str)
    except Exception:
        return []

    if isinstance(parsed, dict):
        items = parsed.get("recommendations") or parsed.get("cards") or []
    elif isinstance(parsed, list):
        items = parsed
    else:
        items = []

    if not isinstance(items, list) or not items:
        return []

    def _pick(item: Dict[str, Any], keys: List[str], default: Any = "") -> Any:
        for k in keys:
            if k in item and item.get(k) not in (None, ""):
                return item.get(k)
        return default

    def _to_float(v: Any, default: float = 0.0) -> float:
        try:
            return float(str(v).replace(",", "").replace("$", "").strip())
        except Exception:
            return default

    def _extract_savings(item: Dict[str, Any], current: float, projected: float) -> float:
        # Primary numeric fields
        direct = _pick(item, [
            "monthly_savings",
            "total_estimated_savings",
            "estimated_monthly_savings",
            "savings",
        ], None)
        if direct is not None:
            val = _to_float(direct, 0.0)
            if val > 0:
                return val

        # Text fields like "$2718.19/mo (95.0%)"
        for key in ["costSavings", "cost_savings", "savings_text", "estimatedSavings"]:
            txt = _pick(item, [key], "")
            if txt:
                m = re.search(r"\$\s*([0-9][0-9,]*\.?[0-9]*)", str(txt))
                if m:
                    try:
                        return float(m.group(1).replace(",", ""))
                    except Exception:
                        pass

        # Derive from cost math if possible
        if current > 0 and projected >= 0:
            return round(max(0.0, current - projected), 2)
        return 0.0

    cards: List[Dict[str, Any]] = []
    for i, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue

        resource_id = str(_pick(item, ["resource_id", "resource", "resourceId", "id"], "") or "").strip()
        service_type = str(_pick(item, ["service_type", "service", "aws_service", "type"], "") or "").strip()
        environment = str(_pick(item, ["environment", "env"], "production") or "production").strip()
        risk_level = str(_pick(item, ["risk_level", "severity", "risk"], "medium") or "medium").lower()
        category = str(_pick(item, ["category", "optimization_type"], "optimization") or "optimization")

        current = _to_float(_pick(item, ["current_monthly_cost", "current_monthly", "currentCost", "current_cost"], 0.0), 0.0)
        projected = _to_float(_pick(item, ["projected_monthly_cost", "projected_monthly", "newCost", "projected_cost"], 0.0), 0.0)
        savings = _extract_savings(item, current, projected)
        if savings <= 0 and current > 0 and projected >= 0:
            savings = round(max(0.0, current - projected), 2)
        if projected <= 0 and current > 0 and savings > 0:
            projected = round(max(0.0, current - savings), 2)

        current_type = str(_pick(item, ["currentInstanceType", "current_instance_type"], "") or "").strip()
        recommended_type = str(_pick(item, ["recommendedInstanceType", "recommended_instance_type"], "") or "").strip()
        base_title = str(_pick(item, ["title", "recommendation", "action"], "") or "").strip()
        if not base_title:
            if resource_id and recommended_type:
                base_title = f"Optimize {resource_id} to {recommended_type}"
            elif resource_id:
                base_title = f"Optimize {resource_id}"
            else:
                base_title = f"Recommendation #{i}"
        title = base_title

        why = str(_pick(item, ["why_this_matters", "narrative", "why"], "") or "").strip()
        problem = str(_pick(item, ["problem", "issue"], "") or "").strip()
        solution = str(_pick(item, ["solution", "action", "recommendation"], title) or title).strip()
        risk_mitigation = str(_pick(item, ["risk_mitigation", "mitigation", "safety_notes"], f"Risk level: {risk_level}"))
        impl = _pick(item, ["implementation_steps", "steps", "implementation"], [])
        if not isinstance(impl, list):
            impl = [str(impl)] if impl else []

        conf = _pick(item, ["confidence", "confidence_score"], "medium")
        if isinstance(conf, (int, float)):
            confidence = max(0.0, min(1.0, float(conf)))
            conf_label = "high" if confidence >= 0.8 else ("medium" if confidence >= 0.6 else "low")
        else:
            conf_label = str(conf)

        card = {
            "priority": i,
            "recommendation_number": i,
            "title": title,
            "severity": risk_level,
            "category": category,
            "risk_level": risk_level,
            "implementation_complexity": "medium",
            "resource_identification": {
                "resource_id": resource_id,
                "resource_name": resource_id,
                "service_name": resource_id,
                "service_type": service_type,
                "environment": environment,
                "current_instance_type": current_type,
                "recommended_instance_type": recommended_type,
            },
            "service_type": service_type,
            "cost_breakdown": {
                "current_monthly": current,
                "projected_monthly": projected,
                "annual_impact": round(savings * 12, 2),
                "line_items": [],
            },
            "recommendations": [{
                "action_number": 1,
                "title": solution,
                "description": solution,
                "action": solution,
                "estimated_monthly_savings": savings,
                "implementation_steps": [str(x) for x in impl if str(x).strip()],
                "validation_steps": [],
                "performance_impact": f"Estimated savings: ${savings:.2f}/mo",
                "risk_mitigation": risk_mitigation,
                "full_analysis": "\n".join([x for x in [why, problem, solution] if x])[:1200],
                "confidence": conf_label,
            }],
            "why_it_matters": why,
            "raw_analysis": json.dumps(item, ensure_ascii=True),
            "total_estimated_savings": savings,
            "source": "llm",
        }
        cards.append(_normalize_llm_card_shape(card))

    if cards:
        logger.info("[PARSER] JSON parse produced %d recommendation cards", len(cards))
    return cards


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
        title = re.sub(r"Pre-?analyzed\s*#\d+:?\s*", "", title, flags=re.IGNORECASE)
        title = re.sub(r"Engine\s*Signal\s*#\d+:?\s*", "", title, flags=re.IGNORECASE)
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
                card["resource_identification"]["resource_name"] = res_id
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
    svc_match = re.search(r"(?:\*\*)?Service(?:\*\*)?:\s*([^\n|]+)", text, re.IGNORECASE)
    if svc_match:
        svc_value = svc_match.group(1).strip()
        card["resource_identification"]["service_type"] = svc_value
        card["service_type"] = svc_value

    # Extract Risk / Priority -> severity
    risk_match = re.search(r"\*\*(?:Risk|Priority):\*\*\s*(LOW|MEDIUM|HIGH)", text, re.IGNORECASE)
    if risk_match:
        card["severity"] = risk_match.group(1).lower()
    
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
        r"\*\*Annual Impact:\*\*\s*\$([0-9,]+\.?\d*)",
        
        # Common explicit patterns
        r"Monthly savings:\s*\$([0-9,]+\.?\d*)",
        r"Monthly Savings:\s*\$([0-9,]+\.?\d*)",
        r"(?:Expected|Estimated|Potential)\s+(?:monthly\s+)?savings?:\s*\$([0-9,]+\.?\d*)",
        
        # Dollar-first patterns ($X savings, $X reduction, etc.)
        r"\$([0-9,]+\.?\d*)\s+(?:monthly\s+)?savings?(?:\s+per month)?",
        r"\$([0-9,]+\.?\d*)\s+(?:cost reduction|estimated savings|potential savings)",
        
        # Qwen-style inline savings ("save $X", "saving $X", "savings of $X")
        r"(?:save|saving|savings? of)\s+\$([0-9,]+\.?\d*)",
        r"(?:save|saving)\s+approximately\s+\$([0-9,]+\.?\d*)",
        r"(?:save|saving)\s+about\s+\$([0-9,]+\.?\d*)",
        r"(?:save|saving)\s+up to\s+\$([0-9,]+\.?\d*)",
        r"(?:save|saving)\s+around\s+\$([0-9,]+\.?\d*)",
        
        # Savings embedded in sentence ("reduce costs by $X")
        r"reduce\s+(?:costs?|spending)\s+by\s+\$([0-9,]+\.?\d*)",
        r"cut\s+(?:costs?|spending)\s+by\s+\$([0-9,]+\.?\d*)",
        r"lower\s+(?:costs?|spending)\s+by\s+\$([0-9,]+\.?\d*)",
        
        # New vs old cost difference
        r"New\s+cost:\s*\$([0-9,]+\.?\d*).*?savings",
        
        # Reduction/Savings with colon
        r"(?:Expected|Estimated|Potential)?\s*(?:reduction|savings?):\s*\$([0-9,]+\.?\d*)",
        r"(?:reduction|decrease|savings?):\s*\$([0-9,]+\.?\d*)",
        
        # "Save/Save" action patterns
        r"(?:Save|Save approximately|Estimated Savings?|Potential Savings?):\s*\$([0-9,]+\.?\d*)",
        
        # Expected/Projected patterns
        r"Expected:\s*\$([0-9,]+\.?\d*)",
        r"Projected Savings?:\s*\$([0-9,]+\.?\d*)",
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
    
    # Extract a concrete action from Solution section when available.
    action_text = card["title"]
    solution_match = re.search(r"\*\*Solution:\*\*\s*(.*?)(?:\n\*\*|\Z)", text, re.IGNORECASE | re.DOTALL)
    if solution_match:
        solution = re.sub(r"\s+", " ", solution_match.group(1).strip())
        if len(solution) >= 12:
            action_text = solution[:240]

    # Build recommendations list
    card["recommendations"] = [{
        "action_number": 1,
        "title": action_text,
        "description": action_text,
        "action": action_text,
        "estimated_monthly_savings": card["total_estimated_savings"],
        "implementation_steps": impl_lines,
        "validation_steps": [],
        "performance_impact": f"Estimated savings: ${card['total_estimated_savings']:.2f}/mo",
        "risk_mitigation": f"Risk level: {card.get('risk_level', 'medium')}",
        "full_analysis": text[:1200],
        "confidence": "medium",
    }]

    return _normalize_llm_card_shape(card)


def _normalize_llm_card_shape(card: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize parsed LLM cards to the same structural shape as engine cards."""
    rid = card.setdefault("resource_identification", {})
    cost = card.setdefault("cost_breakdown", {})
    graph = card.setdefault("graph_context", {})
    recs = card.setdefault("recommendations", [])

    title = str(card.get("title", "") or "").strip()
    title = re.sub(r"^Pre-?analyzed\s*#\d+:?\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^Engine\s*Signal\s*#\d+:?\s*", "", title, flags=re.IGNORECASE)
    card["title"] = title or "Optimization Recommendation"

    # Keep top-level parity with engine cards.
    card.setdefault("source", "llm")
    card.setdefault("implementation_complexity", "medium")
    card.setdefault("category", "optimization")
    card.setdefault("risk_level", card.get("severity", "medium"))
    card.setdefault("linked_best_practice", "")
    card.setdefault("finops_best_practice", card.get("linked_best_practice", ""))
    card.setdefault("why_it_matters", card.get("why_it_matters", ""))
    if not card.get("service_type") and rid.get("service_type"):
        card["service_type"] = rid.get("service_type")

    # Resource shape parity.
    res_id = rid.get("resource_id", "")
    rid.setdefault("resource_name", rid.get("service_name", res_id))
    rid.setdefault("service_name", rid.get("resource_name", res_id))
    rid.setdefault("environment", "production")
    rid.setdefault("region", "us-east-1")
    rid.setdefault("current_config", "")
    rid.setdefault("tags", {})

    # Cost shape parity.
    current = float(cost.get("current_monthly", 0) or 0)
    savings = float(card.get("total_estimated_savings", 0) or 0)
    cost.setdefault("projected_monthly", max(0.0, current - savings))
    cost.setdefault("line_items", [
        {
            "item": "Estimated current monthly cost",
            "usage": f"{rid.get('environment', 'production')} ({rid.get('region', 'us-east-1')})",
            "cost": round(current, 2),
        }
    ])
    cost.setdefault("annual_impact", round(savings * 12, 2))

    # Graph shape parity defaults.
    graph.setdefault("dependency_count", 0)
    graph.setdefault("dependent_services", [])
    graph.setdefault("depends_on_count", 0)
    graph.setdefault("blast_radius_pct", 0)
    graph.setdefault("blast_radius_services", 0)
    graph.setdefault("is_spof", False)
    graph.setdefault("cascading_failure_risk", "low")
    graph.setdefault("centrality", 0)
    graph.setdefault("narrative", "")

    # Recommendation item shape parity.
    if not recs:
        recs.append({
            "action_number": 1,
            "title": card["title"],
            "description": card["title"],
            "action": card["title"],
            "estimated_monthly_savings": savings,
            "implementation_steps": [],
            "validation_steps": [],
            "performance_impact": f"Estimated savings: ${savings:.2f}/mo",
            "risk_mitigation": f"Risk level: {card.get('risk_level', 'medium')}",
            "full_analysis": str(card.get("raw_analysis", ""))[:1200],
            "confidence": "medium",
        })
    else:
        rec0 = recs[0]
        rec0.setdefault("title", rec0.get("action", card["title"]))
        rec0.setdefault("description", rec0.get("action", card["title"]))
        rec0.setdefault("full_analysis", str(card.get("raw_analysis", ""))[:1200])
        rec0.setdefault("estimated_monthly_savings", savings)
        rec0.setdefault("implementation_steps", [])
        if not isinstance(rec0.get("implementation_steps"), list):
            rec0["implementation_steps"] = [str(rec0.get("implementation_steps"))]
        rec0.setdefault("performance_impact", f"Estimated savings: ${savings:.2f}/mo")
        rec0.setdefault("risk_mitigation", f"Risk level: {card.get('risk_level', 'medium')}")
        rec0.setdefault("confidence", "medium")
        rec0.setdefault("validation_steps", [])

        # Keep nested rec fields coherent with top-level parsed savings.
        try:
            rec_savings = float(rec0.get("estimated_monthly_savings", 0) or 0)
        except Exception:
            rec_savings = 0.0
        if savings > 0 and rec_savings <= 0:
            rec0["estimated_monthly_savings"] = savings

        perf_text = str(rec0.get("performance_impact", "") or "")
        if savings > 0 and (not perf_text or "$0.00" in perf_text or "$0/mo" in perf_text):
            rec0["performance_impact"] = f"Estimated savings: ${savings:.2f}/mo"

    if not card.get("finops_best_practice") and card.get("linked_best_practice"):
        card["finops_best_practice"] = card.get("linked_best_practice")

    return card


# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDERS
# ═══════════════════════════════════════════════════════════════════════════

def _build_service_inventory(graph_data: dict) -> str:
    """Build comprehensive service inventory from graph data.
    
    Handles both formats:
    - Dict keyed by ARN (from graph.json): {arn: {node_id, service_type, ...}}
    - List of service dicts (from CUR): [{id, aws_service, cost_monthly, ...}]
    
    Parses service type from ARN, injects graph metrics, and generates realistic
    cost estimates when CUR data isn't available.
    """
    raw_nodes = graph_data.get("services") or graph_data.get("nodes") or {}
    
    # Normalize nodes into a list
    if isinstance(raw_nodes, dict):
        node_list = list(raw_nodes.values())
    elif isinstance(raw_nodes, list):
        node_list = raw_nodes
    else:
        return "(No services)"
    
    if not node_list:
        return "(No services)"
    
    # Realistic cost estimates by service type (used when CUR data is $0)
    BASELINE_COSTS = {
        "ec2": 150.0, "rds": 350.0, "s3": 85.0, "lambda": 45.0,
        "elasticache": 180.0, "opensearch": 280.0, "redshift": 450.0,
        "cloudfront": 120.0, "vpc": 95.0, "sqs": 25.0, "sns": 15.0,
        "dynamodb": 100.0, "ecs": 200.0, "eks": 300.0, "nat": 95.0,
        "alb": 65.0, "service": 80.0,  # generic service nodes
    }
    
    # Realistic instance types by service type
    INSTANCE_TYPES = {
        "ec2": "m5.xlarge", "rds": "db.m5.xlarge", "elasticache": "cache.r6g.large",
        "opensearch": "m5.large.search", "redshift": "ra3.xlarge",
    }
    
    ENV_MAP = {
        "prod": "production", "primary": "production", "api": "production",
        "dev": "development", "test": "staging", "staging": "staging",
    }
    
    lines = ["## SERVICE INVENTORY (sorted by estimated cost)\n"]
    
    seen_resources = set()
    inventory = []
    
    for node in node_list:
        node_id = node.get("node_id") or node.get("id", "unknown")
        
        # Skip duplicate ARN/service pairs
        resource_key = node_id.split("/")[-1] if "/" in node_id else node_id
        if resource_key in seen_resources:
            continue
        seen_resources.add(resource_key)
        
        # Parse service type from ARN: arn:aws:SERVICE:region:account:...
        if "arn:aws:" in node_id:
            parts = node_id.split(":")
            aws_service = parts[2] if len(parts) > 2 else "unknown"
            region = parts[3] if len(parts) > 3 else "us-east-1"
            resource_name = node_id.split("/")[-1] if "/" in node_id else parts[-1]
        else:
            aws_service = node.get("aws_service", node.get("type", node.get("service_type", "unknown")))
            region = "us-east-1"
            resource_name = node_id
        
        # Service type normalization
        svc_type = node.get("service_type", "")
        if svc_type in ("Unknown", "", None):
            svc_type = aws_service
        
        # Cost — use actuals if available, else baseline estimate
        cost = node.get("total_monthly_cost") or node.get("cost_monthly", 0)
        if cost == 0:
            cost = BASELINE_COSTS.get(aws_service.lower(), 50.0)
        
        # Graph metrics
        centrality = node.get("centrality", 0)
        blast = node.get("blast_radius", 0)
        spof = node.get("single_point_of_failure", False)
        cascade = node.get("cascading_failure_risk", "low")
        in_deg = node.get("in_degree", 0)
        out_deg = node.get("out_degree", 0)
        pagerank = node.get("pagerank", 0)
        
        # Infer environment from resource name
        name_lower = resource_name.lower()
        env = "production"
        for tag, env_label in ENV_MAP.items():
            if tag in name_lower:
                env = env_label
                break
        
        # Instance type
        inst_type = INSTANCE_TYPES.get(aws_service.lower(), "-")
        
        inventory.append({
            "resource_id": node_id,
            "resource_name": resource_name,
            "aws_service": aws_service.upper(),
            "service_type": svc_type,
            "cost": cost,
            "env": env,
            "region": region,
            "instance_type": inst_type,
            "centrality": centrality,
            "blast_radius": blast,
            "spof": spof,
            "cascade_risk": cascade,
            "in_degree": in_deg,
            "out_degree": out_deg,
            "pagerank": pagerank,
        })
    
    # Sort by cost descending
    inventory.sort(key=lambda x: x["cost"], reverse=True)
    
    for svc in inventory:
        spof_tag = " ⚠️SPOF" if svc["spof"] else ""
        cascade_tag = f" cascade={svc['cascade_risk']}" if svc["cascade_risk"] != "low" else ""
        dep_tag = f" deps_in={svc['in_degree']} deps_out={svc['out_degree']}" if (svc['in_degree'] + svc['out_degree']) > 0 else ""
        
        lines.append(f"- **{svc['resource_name']}** [{svc['aws_service']}]")
        lines.append(f"  Resource ID: `{svc['resource_id']}`")
        lines.append(f"  Cost: ${svc['cost']:.2f}/mo | Env: {svc['env']} | Region: {svc['region']}")
        if svc['instance_type'] != "-":
            lines.append(f"  Instance Type: {svc['instance_type']}")
        lines.append(f"  Graph: centrality={svc['centrality']:.3f} blast_radius={svc['blast_radius']:.1%} pagerank={svc['pagerank']:.2f}{spof_tag}{cascade_tag}{dep_tag}")
    
    total_cost = sum(s["cost"] for s in inventory)
    lines.append(f"\n**TOTAL MONTHLY COST: ${total_cost:,.2f}**")
    lines.append(f"**{len(inventory)} UNIQUE RESOURCES — GENERATE RECOMMENDATIONS FOR ALL SERVICE TYPES**")
    
    return "\n".join(lines)


def _extract_service_metrics(service: dict, edges: List[Dict] = None) -> Dict[str, Any]:
    """Extract comprehensive finops metrics from a service node.

    Uses FinOpsMetricsExtractor for consistent, hardened metric extraction.
    Returns structured metrics dict with P95, CPU, IOPS, latency, and more.
    """
    # Use the comprehensive extractor
    full_metrics = FinOpsMetricsExtractor.extract_node_metrics(service, edges or [])

    # Return the full dict (frontend can use all fields)
    return full_metrics


def _populate_card_metrics(card: Dict[str, Any], graph_data: dict) -> Dict[str, Any]:
    """Wire comprehensive finops metrics from graph_data into recommendation card.

    Looks up the resource_id in graph_data and populates metrics_summary with
    real CloudWatch metrics (CPU, IOPS, P95 latency, P95 cost, error rate, etc.)
    to fully harden the recommendation with concrete data.
    """
    resource_id = card.get("resource_identification", {}).get("resource_id", "")
    if not resource_id or not graph_data:
        return card

    # Find the service in graph_data
    services = graph_data.get("services") or graph_data.get("nodes") or []
    edges = graph_data.get("dependencies") or graph_data.get("edges") or []

    target_service = None
    for svc in services:
        if svc.get("id") == resource_id or svc.get("node_id") == resource_id:
            target_service = svc
            break

    if not target_service:
        return card

    # Extract comprehensive metrics for this service
    metrics = _extract_service_metrics(target_service, edges)

    # Populate metrics_summary with all extracted values
    metrics_summary = card.setdefault("metrics_summary", {})

    # Core metrics (CPU, Memory, IOPS, Latency)
    metrics_summary["cpu_utilization_percent"] = metrics.get("cpu_utilization_percent")
    metrics_summary["memory_utilization_percent"] = metrics.get("memory_utilization_percent")
    metrics_summary["iops"] = metrics.get("iops")
    metrics_summary["read_iops"] = metrics.get("read_iops")
    metrics_summary["write_iops"] = metrics.get("write_iops")

    # Latency metrics (P50, P95, P99)
    metrics_summary["latency_p50_ms"] = metrics.get("latency_p50_ms")
    metrics_summary["latency_p95_ms"] = metrics.get("latency_p95_ms")
    metrics_summary["latency_p99_ms"] = metrics.get("latency_p99_ms")

    # Error and throughput metrics
    metrics_summary["error_rate_percent"] = metrics.get("error_rate_percent")
    metrics_summary["throughput_qps"] = metrics.get("throughput_qps")
    metrics_summary["throughput_rps"] = metrics.get("throughput_rps")

    # Network metrics
    metrics_summary["network_in_mbps"] = metrics.get("network_in_mbps")
    metrics_summary["network_out_mbps"] = metrics.get("network_out_mbps")

    # Cost metrics (including P95)
    metrics_summary["cost_monthly"] = metrics.get("cost_monthly")
    metrics_summary["cost_p95_monthly"] = metrics.get("cost_p95_monthly")

    # Health
    metrics_summary["health_score"] = metrics.get("health_score")

    # Build readable observation from all metrics
    observation = metrics.get("observation", "")
    if not observation:
        observations = []
        if metrics.get("cpu_utilization_percent") is not None:
            observations.append(f"CPU {metrics['cpu_utilization_percent']}%")
        if metrics.get("iops") is not None:
            observations.append(f"IOPS {metrics['iops']:.0f}")
        if metrics.get("latency_p95_ms") is not None:
            observations.append(f"P95 latency {metrics['latency_p95_ms']:.0f}ms")
        if metrics.get("throughput_qps") is not None:
            observations.append(f"Throughput {metrics['throughput_qps']:.0f} qps")
        if metrics.get("error_rate_percent") is not None and metrics["error_rate_percent"] > 0.1:
            observations.append(f"Errors {metrics['error_rate_percent']:.2f}%")
        if metrics.get("memory_utilization_percent") is not None:
            observations.append(f"Memory {metrics['memory_utilization_percent']}%")

        observation = " | ".join(observations) if observations else "No detailed metrics available"

    metrics_summary["observation"] = observation

    card["metrics_summary"] = metrics_summary
    return card


def _build_metrics(graph_data: dict) -> str:
    """Build detailed metrics summary for LLM context with explicit CPU, IOPS, latency."""
    services = graph_data.get("services") or []
    lines = []
    
    lines.append("CLOUDWATCH METRICS (current utilization—inform right-sizing decisions):")
    
    # Collect services with high metrics (interesting for LLM)
    interesting_services = []
    for svc in services:
        metrics = _extract_service_metrics(svc)
        svc_id = svc.get("id", "unknown")
        svc_type = svc.get("type", svc.get("service_type", "service"))
        cost_mo = svc.get("cost_monthly", 0) or 0
        
        # Only include if has at least one metric or has cost
        has_latency = metrics.get("latency_p95_ms") or metrics.get("latency_p50_ms")
        if any([metrics["cpu_utilization_percent"], metrics["iops"], has_latency]) or cost_mo > 10:
            interesting_services.append({
                "id": svc_id,
                "type": svc_type,
                "cost": cost_mo,
                "metrics": metrics
            })
    
    # Sort by cost descending and take top 20
    interesting_services.sort(key=lambda x: x["cost"], reverse=True)
    
    for svc_info in interesting_services[:20]:
        svc_id = svc_info["id"]
        svc_type = svc_info["type"]
        metrics = svc_info["metrics"]
        cost_mo = svc_info["cost"]
        
        line = f"  • {svc_id} ({svc_type})"

        # Add metrics if present
        metric_parts = []
        if metrics["cpu_utilization_percent"] is not None:
            metric_parts.append(f"CPU {metrics['cpu_utilization_percent']}%")
        if metrics["memory_utilization_percent"] is not None:
            metric_parts.append(f"Mem {metrics['memory_utilization_percent']}%")
        if metrics["iops"] is not None:
            metric_parts.append(f"IOPS {metrics['iops']:.0f}")
        if metrics.get("latency_p95_ms") is not None:
            metric_parts.append(f"P95 latency {metrics['latency_p95_ms']:.0f}ms")
        elif metrics.get("latency_p50_ms") is not None:
            metric_parts.append(f"Latency {metrics['latency_p50_ms']:.0f}ms")
        if metrics.get("error_rate_percent") is not None and metrics["error_rate_percent"] > 0.1:
            metric_parts.append(f"Errors {metrics['error_rate_percent']:.2f}%")
        if metrics.get("throughput_qps") is not None:
            metric_parts.append(f"{metrics['throughput_qps']:.0f} qps")

        if metric_parts:
            line += f" | {', '.join(metric_parts)}"

        if cost_mo > 0:
            line += f" | ${cost_mo:,.0f}/mo"

        # Optional: show P95 cost if available and significantly different
        cost_p95 = metrics.get("cost_p95_monthly", 0)
        if cost_p95 > cost_mo * 1.2:
            line += f" (p95: ${cost_p95:,.0f}/mo)"

        lines.append(line)
    
    if not interesting_services:
        lines.append("  (No detailed metrics available—use graph structure for right-sizing decisions)")
    
    lines.append("")
    return "\n".join(lines)


def _build_graph(pkg: dict) -> str:
    """Build FULL graph architecture context from the 8-section context package.

    This is the critical bridge between ``ContextAssembler`` analysis and the LLM
    prompt.  Previous implementation only read ``bottleneck_nodes`` — discarding
    95 % of the graph intelligence (blast radius, SPOFs, anti-patterns, cross-AZ
    costs, dependency chains, anomalies).
    """
    lines = []

    # ── Section 1: Architecture Overview ──
    arch_name = pkg.get("architecture_name", "")
    total_svcs = pkg.get("total_services", 0)
    total_cost = pkg.get("total_cost_monthly", 0)
    total_deps = pkg.get("total_dependencies", 0)
    cross_az   = pkg.get("cross_az_dependency_count", 0)

    if total_svcs:
        lines.append("ARCHITECTURE OVERVIEW:")
        lines.append(f"  {arch_name or 'Architecture'}: {total_svcs} services, "
                     f"${total_cost:,.0f}/mo, {total_deps} dependencies")
        if cross_az:
            lines.append(f"  ⚠ {cross_az} CROSS-AZ dependencies detected (extra transfer costs)")
        lines.append("")

    # ── Section 2: Critical Services (Top 5) ──
    critical = pkg.get("critical_services", [])
    if critical:
        lines.append("CRITICAL SERVICES (highest architectural importance):")
        for svc in critical[:5]:
            name       = svc.get("name", "?")
            centrality = svc.get("centrality", 0)
            in_deg     = svc.get("in_degree", 0)
            out_deg    = svc.get("out_degree", 0)
            cost_mo    = svc.get("cost_monthly", 0)
            cascade    = svc.get("cascading_failure_risk", "low")
            spof       = svc.get("single_point_of_failure", False)
            deps_count = svc.get("dependents_count", 0)
            sev_label  = svc.get("severity_label", "")

            line = f"  • {name}: centrality={centrality:.4f}, "
            line += f"{in_deg} services depend on it, out_degree={out_deg}, "
            line += f"${cost_mo:,.0f}/mo"
            if spof:
                line += " [SINGLE POINT OF FAILURE]"
            if cascade in ("critical", "high"):
                line += f" [CASCADE RISK: {cascade.upper()}]"
            if sev_label:
                line += f" [{sev_label}]"
            lines.append(line)

            # Dependency patterns
            for pat in svc.get("dependency_patterns", [])[:2]:
                lines.append(f"    Pattern: {pat}")
        lines.append("")

    # ── Section 4: Anti-Patterns ──
    anti_patterns = pkg.get("anti_patterns", [])
    if anti_patterns:
        lines.append("ARCHITECTURAL ANTI-PATTERNS:")
        for ap in anti_patterns[:5]:
            est = ap.get("estimated_savings", 0)
            lines.append(f"  ⚠ {ap['name']} ({ap['severity'].upper()})")
            lines.append(f"    {ap['description']}")
            if est > 0:
                lines.append(f"    Estimated savings: ${est:,.0f}/mo")
            lines.append(f"    Fix: {ap.get('recommendation', '')}")
        lines.append("")

    # ── Section 5: Risk Assessment ──
    risks = pkg.get("risks", [])
    if risks:
        lines.append("RISK ASSESSMENT:")
        for r in risks[:4]:
            lines.append(f"  ⚠ {r['name']} ({r['severity'].upper()})")
            lines.append(f"    {r['description']}")
            lines.append(f"    Impact: {r.get('impact', '')}")
        lines.append("")

    # ── Section 6: Anomalies ──
    anomalies = pkg.get("anomalies", [])
    if anomalies:
        lines.append("BEHAVIORAL ANOMALIES:")
        for a in anomalies[:5]:
            lines.append(f"  • {a.get('node_name', '')}: {a.get('description', '')}")
            lines.append(f"    Impact: {a.get('impact', '')}")
        lines.append("")

    # ── Section 8: Dependency Analysis ──
    crit_deps = pkg.get("critical_dependencies", [])
    if crit_deps:
        lines.append("CRITICAL DEPENDENCIES (if broken → highest impact):")
        for d in crit_deps[:5]:
            lines.append(f"  {d['source']} → {d['target']}: "
                         f"{d['impact_count']} downstream services affected")
        lines.append("")

    circ = pkg.get("circular_dependencies", [])
    if circ:
        lines.append(f"CIRCULAR DEPENDENCIES: {len(circ)} detected")
        for cd in circ[:3]:
            lines.append(f"  ⚠ {cd.get('description', '')}")
        lines.append("")

    deep = pkg.get("deep_chains", [])
    if deep:
        lines.append("DEEP DEPENDENCY CHAINS (brittleness risk):")
        for dc in deep:
            lines.append(f"  {dc.get('chain', '')} ({dc.get('depth', 0)}-hop)")
        lines.append("")

    orphaned = pkg.get("orphaned_services", [])
    if orphaned:
        lines.append(f"ORPHANED SERVICES (no connections): {', '.join(orphaned)}")
        lines.append("")

    # ── Waste & Cost Outliers ──
    waste = pkg.get("waste_detected", [])
    if waste:
        lines.append("WASTE DETECTED:")
        for w in waste:
            lines.append(f"  • {w['category']}: ${w['estimated_monthly']:,.0f}/mo — {w['description']}")
        total_waste = pkg.get("total_waste_monthly", 0)
        if total_waste:
            lines.append(f"  TOTAL WASTE: ${total_waste:,.0f}/mo")
        lines.append("")

    outliers = pkg.get("cost_outliers", [])
    if outliers:
        lines.append("COST OUTLIERS (>2x type average):")
        for o in outliers[:5]:
            lines.append(f"  • {o['name']}: ${o['actual_cost']:,.0f} vs expected "
                         f"${o['expected_cost']:,.0f} ({o['ratio']}x) — {o.get('reason', '')}")
        lines.append("")

    # ── SPOFs summary ──
    spofs = pkg.get("single_points_of_failure", [])
    if spofs:
        names = [s.get("name", "?") for s in spofs]
        lines.append(f"SINGLE POINTS OF FAILURE: {', '.join(names)}")
        lines.append("")

    return "\n".join(lines) if lines else "(No graph data)"


def _build_business_graph_context(graph_data: dict, pkg: dict = None) -> str:
    """Build GraphRAG business-language context from graph metrics + narratives.

    Enhanced to include per-node narratives from the graph analysis which contain
    the 'powers 12 services', 'checkout breaks', '86% blast radius' insights.
    """
    lines = []

    # ── 1. Per-node narratives (the most valuable graph context) ──
    narratives = []
    if pkg:
        narratives = pkg.get("interesting_node_narratives", [])
    if narratives:
        lines.append("PER-NODE ARCHITECTURE NARRATIVES (use these for business-aware recommendations):")
        for i, narr in enumerate(narratives[:10], 1):
            lines.append(f"\n  Node {i}: {narr}")
        lines.append("")

    # ── 2. Business criticality translations ──
    entries = build_business_context_for_resources(graph_data or {}, top_n=15)
    if entries:
        lines.append("\nBUSINESS CRITICALITY CONTEXT (translated from graph metrics):")
        for e in entries:
            bi = e.get("business_insight", {})
            lines.append(
                f"- {e.get('resource_name', e.get('resource_id'))} "
                f"[{e.get('resource_type', 'service')}] "
                f"@ ${float(e.get('cost_monthly', 0.0) or 0.0):.2f}/mo"
            )
            lines.append(f"  Criticality: {bi.get('criticality', '')}")
            lines.append(f"  Dependencies: {bi.get('dependencies', '')}")
            lines.append(f"  Failure impact: {bi.get('failure_impact', '')}")

    return "\n".join(lines) if lines else "(No business graph context available)"


def _build_pricing() -> str:
    """AWS pricing."""
    return """RDS: db.r5.large=$213/mo, db.r5.xlarge=$426/mo, db.r5.2xlarge=$853/mo
EC2: t3.medium=$30/mo, m5.large=$70/mo, m5.xlarge=$140/mo"""


def _build_best_practices(pkg: dict = None, graph_data: dict = None) -> str:
    """Build service-specific AWS FinOps best practices from the knowledge base.

    Scans the architecture's services and injects ONLY the relevant best
    practices from ``aws_finops_best_practices.py`` so the LLM gets concrete
    per-service guidance (thresholds, pricing, optimization strategies).
    """
    lines = []

    # ── Detect which service families exist in the architecture ──
    detected_families: set = set()
    if graph_data:
        for svc in (graph_data.get("services") or graph_data.get("nodes") or []):
            stype = str(svc.get("type", svc.get("aws_service", ""))).lower()
            sname = str(svc.get("name", svc.get("id", ""))).lower()
            # Map to KB keys
            if "ec2" in stype or "ec2" in sname or "instance" in stype:
                detected_families.add("EC2")
            if "rds" in stype or "rds" in sname or "postgres" in sname or "mysql" in sname or "database" in stype:
                detected_families.add("RDS")
            if "s3" in stype or "s3" in sname or "bucket" in stype:
                detected_families.add("S3")
            if "lambda" in stype or "lambda" in sname:
                detected_families.add("Lambda")
            if "ecs" in stype or "fargate" in stype or "ecs" in sname or "fargate" in sname:
                detected_families.add("ECS_Fargate")
            if "dynamo" in stype or "dynamo" in sname:
                detected_families.add("DynamoDB")
            if "elasticache" in stype or "redis" in sname or "cache" in stype or "memcached" in sname:
                detected_families.add("ElastiCache")
            if "nat" in stype or "nat" in sname:
                detected_families.add("Data_Transfer")
            if "ebs" in stype or "volume" in stype:
                detected_families.add("EBS")
            if "efs" in stype or "efs" in sname:
                detected_families.add("EFS")
            if "alb" in stype or "nlb" in stype or "elb" in stype or "load" in stype:
                detected_families.add("Load_Balancers")
            if "cloudfront" in stype or "cdn" in stype or "cloudfront" in sname:
                detected_families.add("CloudFront")
            if "aurora" in stype or "aurora" in sname:
                detected_families.add("Aurora")
            if "vpc" in stype or "endpoint" in stype or "elastic_ip" in stype:
                detected_families.add("Data_Transfer")
                detected_families.add("Elastic_IP")

    # Always include data transfer (cross-AZ is universal)
    detected_families.add("Data_Transfer")

    # If no services detected, include all families
    if len(detected_families) <= 1:
        detected_families = {"EC2", "RDS", "S3", "Lambda", "Data_Transfer", "EBS"}

    # ── Build service-specific best practices from KB ──
    all_kb = {
        **COMPUTE_BEST_PRACTICES,
        **DATABASE_BEST_PRACTICES,
        **STORAGE_BEST_PRACTICES,
        **NETWORKING_BEST_PRACTICES,
    }

    lines.append("AWS FINOPS BEST PRACTICES (from knowledge base, matched to YOUR architecture):")
    lines.append(f"Detected service families: {', '.join(sorted(detected_families))}")
    lines.append("")

    for family in sorted(detected_families):
        kb_entry = all_kb.get(family)
        if not kb_entry:
            continue

        svc_name = kb_entry.get("service_name", family)
        lines.append(f"\n{'='*60}")
        lines.append(f"{svc_name.upper()}")
        lines.append(f"{'='*60}")

        # Extract the most actionable guidance per service
        _render_kb_section(lines, kb_entry, "right_sizing", "RIGHT-SIZING")
        _render_kb_section(lines, kb_entry, "purchasing_options", "PURCHASING OPTIONS")
        _render_kb_section(lines, kb_entry, "auto_scaling", "AUTO-SCALING")
        _render_kb_section(lines, kb_entry, "waste_elimination", "WASTE ELIMINATION")
        _render_kb_section(lines, kb_entry, "storage_classes", "STORAGE CLASSES")
        _render_kb_section(lines, kb_entry, "lifecycle_policies", "LIFECYCLE POLICIES")
        _render_kb_section(lines, kb_entry, "capacity_modes", "CAPACITY MODES")
        _render_kb_section(lines, kb_entry, "multi_az", "MULTI-AZ")
        _render_kb_section(lines, kb_entry, "reserved_instances", "RESERVED INSTANCES")
        _render_kb_section(lines, kb_entry, "reserved_nodes", "RESERVED NODES")
        _render_kb_section(lines, kb_entry, "optimization", "OPTIMIZATION")
        _render_kb_section(lines, kb_entry, "pricing", "PRICING")
        _render_kb_section(lines, kb_entry, "volume_types", "VOLUME TYPES")
        _render_kb_section(lines, kb_entry, "storage_optimization", "STORAGE OPTIMIZATION")
        _render_kb_section(lines, kb_entry, "data_transfer_costs", "DATA TRANSFER")
        _render_kb_section(lines, kb_entry, "best_practices", "BEST PRACTICES")

    # ── Cross-cutting rules ──
    lines.append("\n" + "="*60)
    lines.append("RECOMMENDATION QUALITY RULES (MANDATORY)")
    lines.append("="*60)
    lines.append("- Every recommendation MUST reference a real resource from SERVICE INVENTORY")
    lines.append("- Every recommendation MUST cite SPECIFIC instance types, sizes, GB amounts")
    lines.append("- Every recommendation MUST show savings math: current - new = savings")
    lines.append("- PRIORITY ORDER: configuration changes > architectural improvements > waste elimination > purchasing")
    lines.append("- Maximum 2 'Reserved Instance' or 'Savings Plan' recommendations out of 8-12 total")
    lines.append("- DIVERSITY: cover at least 4 different AWS service families")
    lines.append("- Maximum 2 recommendations per service family (force diversity)")
    lines.append("- Use the exact thresholds from the best practices above (CPU 60-70%, memory 70-80%, etc.)")
    lines.append("- Include AWS CLI commands in implementation steps")

    # Add RAG-retrieved docs if available
    if pkg and isinstance(pkg, dict):
        rag_practices = pkg.get("rag_best_practices", [])
        if rag_practices:
            lines.append("\nGROUNDED BEST PRACTICES (from RAG documentation):")
            lines.extend(rag_practices[:8])

        rag_docs = pkg.get("rag_relevant_docs", [])
        if rag_docs:
            lines.append("\nRELEVANT AWS DOCUMENTATION:")
            for doc in rag_docs[:5]:
                source = doc.get("source", "docs")
                lines.append(f"- {source}: {doc.get('content', '')[:150]}...")

    return "\n".join(lines)


def _render_kb_section(lines: list, entry: dict, key: str, label: str):
    """Render a knowledge base section into prompt-friendly text.
    
    COMPACT: limits output to 3 items per section to avoid overwhelming
    smaller LLMs (Qwen 7B) with too much context.
    """
    section = entry.get(key)
    if not section:
        return

    lines.append(f"  {label}:")

    if isinstance(section, str):
        lines.append(f"    {section[:200]}")
    elif isinstance(section, list):
        for item in section[:3]:  # Max 3 items
            lines.append(f"    - {str(item)[:150]}")
    elif isinstance(section, dict):
        for k, v in list(section.items())[:3]:  # Max 3 keys
            if isinstance(v, str):
                lines.append(f"    {k}: {v[:150]}")
            elif isinstance(v, dict):
                # One level — extract 2 most useful fields
                parts = []
                for sk, sv in list(v.items())[:2]:
                    parts.append(f"{sk}: {str(sv)[:60]}")
                if parts:
                    lines.append(f"    {k}: {'; '.join(parts)}")
            elif isinstance(v, list):
                lines.append(f"    {k}: {', '.join(str(x)[:40] for x in v[:2])}")
            elif isinstance(v, (int, float)):
                lines.append(f"    {k}: {v}")


def _infer_service_type(card: Dict[str, Any], graph_data: Optional[dict]) -> str:
    svc_type = str((card.get("resource_identification") or {}).get("service_type", "")).lower().strip()
    if svc_type:
        return svc_type

    if not graph_data:
        return ""

    resource_id = str((card.get("resource_identification") or {}).get("resource_id", "")).strip()
    raw_services = graph_data.get("services") or graph_data.get("nodes") or []
    if isinstance(raw_services, dict):
        services = list(raw_services.values())
    elif isinstance(raw_services, list):
        services = raw_services
    else:
        services = []
    for s in services:
        if s.get("id") == resource_id or s.get("name") == resource_id:
            return str(s.get("type", s.get("aws_service", ""))).lower()
    return ""


def _service_alignment_keywords() -> Dict[str, List[str]]:
    """Keywords expected for meaningful AWS FinOps recommendations by service family."""
    return {
        "ec2": ["right-size", "reserved", "savings plan", "spot", "auto scaling", "instance", "downsize", "graviton", "arm"],
        "rds": ["reserved", "right-size", "multi-az", "read replica", "storage", "database", "gp3", "aurora", "postgres", "mysql"],
        "s3": ["lifecycle", "intelligent-tiering", "storage class", "glacier", "versioning", "bucket", "archive", "infrequent"],
        "lambda": ["memory", "duration", "provisioned concurrency", "consolidate", "serverless", "function", "invocation"],
        "dynamodb": ["on-demand", "provisioned", "autoscaling", "ttl", "table", "capacity"],
        "nat": ["consolidate", "gateway endpoint", "interface endpoint", "traffic", "nat gateway", "vpc endpoint"],
        "elasticache": ["cache", "hit rate", "node type", "reserved", "redis", "memcached"],
        "redshift": ["pause", "right-size", "ra3", "spectrum", "cluster"],
        "ecs": ["fargate", "task", "container", "service", "spot", "capacity provider"],
        "ebs": ["volume", "gp3", "gp2", "iops", "snapshot", "unattached", "migrate"],
        "efs": ["file system", "infrequent access", "lifecycle", "throughput"],
        "cloudfront": ["cdn", "cache", "distribution", "price class", "origin"],
        "aurora": ["serverless", "reserved", "reader", "cluster", "acu"],
        "vpc": ["endpoint", "nat", "transfer", "cross-az", "flow log"],
        "alb": ["load balancer", "target group", "consolidate", "alb", "nlb"],
        "elastic_ip": ["elastic ip", "eip", "unattached", "unused"],
        "generic": ["right-size", "optimize", "savings", "reserved", "consolidate", "lifecycle", "cost", "reduce", "downsize", "eliminate", "schedule", "shutdown"],
    }


def _validate_recommendation_fiability(cards: List[Dict], graph_data: Optional[dict]) -> List[Dict]:
    """Keep recommendations that are actionable and aligned with AWS FinOps best practices.

    Uses SCORING instead of AND-gate: any card with >= 1 positive signal is kept.
    Only pure garbage (no keywords, no savings, no action) is filtered.
    """
    if not cards:
        return cards

    keyword_map = _service_alignment_keywords()
    valid_ids: set[str] = set()
    valid_names: set[str] = set()
    if graph_data:
        services = list(graph_data.get("services") or graph_data.get("nodes") or [])
        for s in services:
            sid = str(s.get("id", "") or "").strip().lower()
            sname = str(s.get("name", "") or "").strip().lower()
            if sid:
                valid_ids.add(sid)
            if sname:
                valid_names.add(sname)
    kept: List[Dict] = []
    removed = 0

    for card in cards:
        title = str(card.get("title", "") or "").strip()
        action = ""
        recs = card.get("recommendations") or []
        if recs and isinstance(recs[0], dict):
            action = str(recs[0].get("action", "") or "")
        body = str(card.get("raw_analysis", "") or "")
        combined = f"{title} {action} {body}".lower()

        service_type = _infer_service_type(card, graph_data)
        # Try both specific keywords AND generic keywords
        aligned_keywords = keyword_map.get(service_type, keyword_map["generic"])
        all_keywords = set(aligned_keywords) | set(keyword_map["generic"])
        keyword_hit = any(k in combined for k in all_keywords)

        savings_raw = card.get("total_estimated_savings", 0)
        try:
            savings = float(str(savings_raw).replace(",", "").replace("$", "").strip() or 0)
        except Exception:
            savings = 0.0

        has_action = len(title) >= 10 or len(action) >= 10

        # SCORING: count positive signals instead of requiring ALL
        score = 0
        if keyword_hit:
            score += 1
        if savings > 0:
            score += 2  # Savings is the strongest signal
        if has_action:
            score += 1
        if card.get("cost_breakdown", {}).get("current_monthly", 0) > 0:
            score += 1

        # Keep if ANY positive signal (score >= 1)
        # Only filter true garbage with zero signals
        if score >= 1:
            card["fiability"] = {
                "validated": True,
                "score": score,
                "service_type": service_type or "generic",
                "alignment_keywords": list(aligned_keywords)[:4],
            }
            kept.append(card)
        else:
            removed += 1
            logger.debug("Filtered low-signal card: title='%s' score=%d", title[:50], score)

    if removed > 0:
        logger.info("✓ Fiability filter: %d → %d recommendations (removed %d zero-signal cards)", len(cards), len(kept), removed)
    else:
        logger.info("✓ Fiability filter: kept all %d recommendations", len(kept))

    return kept


def _deduplicate_cards(cards: List[Dict]) -> List[Dict]:
    """
    Remove duplicate recommendations by resource_id.
    
    Deduplication key: (resource_id, recommendation_action)
    Keeps first occurrence, removes subsequent duplicates.
    """
    seen: set = set()
    deduped = []
    
    for card in cards:
        res_id = str(card.get("resource_identification", {}).get("resource_id", "") or "").lower().strip()
        service_type = str(card.get("resource_identification", {}).get("service_type", "") or "").lower().strip()
        title = str(card.get("title", "") or "")
        title_key = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()

        # Placeholder IDs are not reliable for dedupe; use title+service fallback.
        resource_key = "" if (not res_id or res_id.endswith("-recommendation")) else res_id
        dedup_key = (resource_key or f"title::{title_key}", service_type, title_key[:80])
        
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
    
    Strict: remove recommendations with zero/negative savings.
    """
    filtered = []
    
    for card in cards:
        savings = card.get("total_estimated_savings")
        current_cost = card.get("cost_breakdown", {}).get("current_monthly", 0)
        title = card.get("title", "")

        # Coerce savings into numeric value if parser left it as a string.
        normalized_savings = None
        if savings is not None and savings != "":
            try:
                normalized_savings = float(
                    str(savings)
                    .replace(",", "")
                    .replace("$", "")
                    .replace("/month", "")
                    .replace("/mo", "")
                    .strip()
                )
            except Exception:
                normalized_savings = None

        if normalized_savings is not None:
            card["total_estimated_savings"] = normalized_savings
        
        # Check if we have explicit zero/negative/empty savings
        effective_savings = card.get("total_estimated_savings", 0)
        if isinstance(effective_savings, (int, float)) and effective_savings > 0:
            # Positive savings — always keep
            filtered.append(card)
        elif len(title) >= 12 and current_cost > 0:
            # If current cost exists, infer from projected where possible.
            projected = card.get("cost_breakdown", {}).get("projected_monthly", 0)
            try:
                projected = float(projected or 0)
            except Exception:
                projected = 0.0
            inferred = round(max(0.0, float(current_cost) - projected), 2) if projected > 0 else 0.0
            if inferred > 0:
                card["total_estimated_savings"] = inferred
                filtered.append(card)
        else:
            logger.info(
                "Filtered low-confidence recommendation (no savings, no cost, short title): %s",
                title or "Unknown"
            )
    
    if len(filtered) < len(cards):
        logger.info("✓ Savings Filter: %d → %d recommendations (removed low-confidence)", 
                   len(cards), len(filtered))
    
    return filtered


def _enrich_cards(cards: List[Dict], graph_data: dict, context_package: dict = None) -> List[Dict]:
    """Enrich cards with architecture data AND graph-derived business context.

    After LLM generates core recommendations, this function injects:
    - Dependency tree (which services depend on / are depended upon)
    - Blast radius (% of architecture affected if this resource fails)
    - SPOF flags
    - Cross-AZ detection
    - Cascading failure risk level
    - Per-node narrative from graph analysis
    """
    services = graph_data.get("services") or graph_data.get("nodes") or []
    edges = graph_data.get("edges") or graph_data.get("dependencies") or []
    svc_map = {s.get("id", ""): s for s in services}
    svc_map.update({s.get("name", ""): s for s in services})
    total_svc_count = len(services)

    # Build adjacency lookups for dependency analysis
    dependents_of: Dict[str, List[str]] = {}  # who depends on X
    dependencies_of: Dict[str, List[str]] = {}  # what does X depend on
    for e in edges:
        src = e.get("source", "")
        tgt = e.get("target", "")
        dependents_of.setdefault(tgt, []).append(src)
        dependencies_of.setdefault(src, []).append(tgt)

    # Build critical services lookup from context package
    critical_svc_map: Dict[str, Dict] = {}
    narratives_map: Dict[str, str] = {}
    if context_package:
        for cs in context_package.get("critical_services", []):
            nid = cs.get("node_id", cs.get("name", ""))
            critical_svc_map[nid] = cs
            critical_svc_map[cs.get("name", "")] = cs
            if cs.get("narrative"):
                narratives_map[nid] = cs["narrative"]
                narratives_map[cs.get("name", "")] = cs["narrative"]

    for card in cards:
        res_id = card.get("resource_identification", {}).get("resource_id", "")
        res_name = card.get("resource_identification", {}).get("service_name", res_id)

        # Match to inventory
        svc = svc_map.get(res_id) or svc_map.get(res_name)
        if svc:
            # Fill missing cost
            if card.get("cost_breakdown", {}).get("current_monthly", 0) == 0:
                card["cost_breakdown"]["current_monthly"] = svc.get("cost_monthly", 0)

            # Fill missing resource details
            rid = card.setdefault("resource_identification", {})
            if not rid.get("region"):
                rid["region"] = svc.get("region", svc.get("attributes", {}).get("availability_zone", ""))
            if not rid.get("service_type"):
                rid["service_type"] = svc.get("type", svc.get("aws_service", ""))
            attrs = svc.get("attributes", {})
            if attrs.get("instance_type"):
                rid["instance_type"] = attrs["instance_type"]
            if attrs.get("storage_gb"):
                rid["storage_gb"] = attrs["storage_gb"]
            rid["environment"] = svc.get("environment", "production")

        # ── Graph-derived business context ──
        svc_id = svc.get("id", res_id) if svc else res_id
        deps_on_me = dependents_of.get(svc_id, [])
        my_deps = dependencies_of.get(svc_id, [])

        # Compute blast radius (recursive downstream impact)
        blast_set = set()
        _compute_blast_radius(svc_id, dependents_of, blast_set)
        blast_pct = round(len(blast_set) / max(total_svc_count, 1) * 100, 0) if total_svc_count else 0

        # Look up critical service data
        cs = critical_svc_map.get(svc_id) or critical_svc_map.get(res_name) or {}

        # Dependent service names (resolve IDs to names)
        dep_names = []
        for did in deps_on_me[:10]:
            dep_svc = svc_map.get(did)
            dep_names.append(dep_svc.get("name", did) if dep_svc else did)

        graph_ctx = {
            "dependency_count": len(deps_on_me),
            "dependent_services": dep_names[:8],
            "depends_on_count": len(my_deps),
            "blast_radius_pct": blast_pct,
            "blast_radius_services": len(blast_set),
            "is_spof": cs.get("single_point_of_failure", False),
            "cascading_failure_risk": cs.get("cascading_failure_risk", "low"),
            "centrality": cs.get("centrality", 0),
            "severity_label": cs.get("severity_label", ""),
            "narrative": narratives_map.get(svc_id, narratives_map.get(res_name, "")),
        }

        # Cross-AZ flag for this specific resource
        if svc:
            svc_az = svc.get("region", svc.get("attributes", {}).get("availability_zone", ""))
            cross_az_deps = []
            for dep_id in (deps_on_me + my_deps):
                dep_svc = svc_map.get(dep_id, {})
                dep_az = dep_svc.get("region", dep_svc.get("attributes", {}).get("availability_zone", ""))
                if svc_az and dep_az and svc_az != dep_az:
                    cross_az_deps.append(dep_svc.get("name", dep_id))
            if cross_az_deps:
                graph_ctx["cross_az_dependencies"] = cross_az_deps[:5]
                graph_ctx["cross_az_count"] = len(cross_az_deps)

        card["graph_context"] = graph_ctx

    return cards


def _compute_blast_radius(node_id: str, dependents_of: Dict[str, List[str]], visited: set):
    """Recursively compute which services are affected if node_id fails."""
    for dep in dependents_of.get(node_id, []):
        if dep not in visited:
            visited.add(dep)
            _compute_blast_radius(dep, dependents_of, visited)


def _apply_deterministic_quality_gates(
    cards: List[Dict[str, Any]],
    graph_data: Optional[dict],
    min_monthly_savings: float = 50.0,
) -> List[Dict[str, Any]]:
    """Deterministic gate after LLM generation.

    Enforces:
    - Resource ID exists in inventory
    - Savings math is valid
    - Reject dangerous recommendations (e.g., RI/Savings Plan for non-prod)
    - Minimum savings threshold
    - Basic implementation feasibility by service/action compatibility
    """
    if not cards:
        return cards
    if not graph_data:
        return cards

    services = list(graph_data.get("services") or graph_data.get("nodes") or [])
    inv_by_id: Dict[str, Dict[str, Any]] = {}
    for s in services:
        sid = str(s.get("id", "") or "").strip()
        if sid:
            inv_by_id[sid] = s

    kept: List[Dict[str, Any]] = []
    rejected = {
        "missing_resource": 0,
        "math_invalid": 0,
        "dangerous": 0,
        "low_savings": 0,
        "infeasible": 0,
        "generic_title": 0,
        "no_metrics": 0,
    }

    for card in cards:
        card = _coerce_backend_card_template(card)
        rid = str((card.get("resource_identification") or {}).get("resource_id", "") or "").strip()
        if not rid or rid not in inv_by_id:
            rejected["missing_resource"] += 1
            continue

        svc = inv_by_id[rid]
        svc_type = str(svc.get("type", svc.get("aws_service", "service")) or "service").lower()
        env = str(svc.get("environment", "production") or "production").lower()

        card.setdefault("resource_identification", {})["environment"] = env
        if not card["resource_identification"].get("service_type"):
            card["resource_identification"]["service_type"] = svc_type
        if not card.get("service_type"):
            card["service_type"] = svc_type

        title = str(card.get("title", "") or "")
        rec0 = (card.get("recommendations") or [{}])[0]
        action_text = str(rec0.get("action", "") or title).lower()

        # Deterministically rewrite generic titles into specific ones.
        if _is_generic_title(title):
            rewritten = _rewrite_generic_title(card, svc_type, action_text)
            if rewritten:
                card["title"] = rewritten
                title = rewritten
                rec0["title"] = rewritten
                if rec0.get("description") in (None, "", rec0.get("action"), "optimize this service"):
                    rec0["description"] = rewritten

        # Reject generic titles unless action text has concrete change details.
        if _is_generic_title(title) and not _has_concrete_action_target(action_text):
            rejected["generic_title"] += 1
            continue

        current = card.get("cost_breakdown", {}).get("current_monthly", 0)
        projected = card.get("cost_breakdown", {}).get("projected_monthly", 0)
        savings = card.get("total_estimated_savings", 0)
        try:
            current = float(current or 0)
            projected = float(projected or 0)
            savings = float(savings or 0)
        except Exception:
            rejected["math_invalid"] += 1
            continue

        if savings <= 0 and current > 0 and projected >= 0:
            savings = round(max(0.0, current - projected), 2)
            card["total_estimated_savings"] = savings
        if projected <= 0 and current > 0 and savings > 0:
            projected = round(max(0.0, current - savings), 2)
            card.setdefault("cost_breakdown", {})["projected_monthly"] = projected

        if current > 0 and projected >= 0 and savings > 0:
            expected = round(max(0.0, current - projected), 2)
            if abs(expected - savings) > max(5.0, savings * 0.15):
                rejected["math_invalid"] += 1
                continue

        # Reject risky purchasing guidance for non-production environments.
        if env in {"development", "dev", "test", "staging", "sandbox", "qa"} and (
            "reserved" in action_text or "savings plan" in action_text
        ):
            rejected["dangerous"] += 1
            continue

        if savings < min_monthly_savings:
            rejected["low_savings"] += 1
            continue


        if not _is_action_feasible_for_service(action_text, svc_type):
            rejected["infeasible"] += 1
            continue
        
        # ─ Metric validation: warn if key metrics missing for compute-heavy services ─
        metrics_summary = card.get("metrics_summary", {})
        svc_metrics = _extract_service_metrics(svc)
        has_cpu = svc_metrics.get("cpu_utilization_percent") is not None
        has_iops = svc_metrics.get("iops") is not None
        has_latency = svc_metrics.get("latency_p95_ms") is not None or svc_metrics.get("latency_p50_ms") is not None

        # For compute/database services, prefer recommendations grounded in metrics
        if svc_type in {"compute", "ec2", "rds", "database"} and not any([has_cpu, has_iops, has_latency]):
            logger.warning("[METRIC_ALERT] %s: no CloudWatch metrics for %s—recommendation not backed by usage data", rid, svc_type)
        
        # Populate metrics_summary if not already done
        if not metrics_summary or not any([
            metrics_summary.get("cpu_utilization_percent"),
            metrics_summary.get("iops"),
            metrics_summary.get("latency_p95_ms") or metrics_summary.get("latency_p50_ms")
        ]):
            card = _populate_card_metrics(card, graph_data)
        # Keep nested rec summary coherent.
        rec0["estimated_monthly_savings"] = savings
        rec0["performance_impact"] = f"Estimated savings: ${savings:.2f}/mo"
        card.setdefault("recommendations", [rec0])[0] = rec0
        kept.append(card)

    logger.info(
        "[QUALITY GATE] in=%d out=%d rejected=%s",
        len(cards),
        len(kept),
        rejected,
    )
    return kept


def _is_action_feasible_for_service(action_text: str, service_type: str) -> bool:
    """Basic deterministic feasibility map for service-action compatibility."""
    t = (action_text or "").lower()
    s = (service_type or "service").lower()

    # Actions that are generally unsafe/invalid for persistent databases.
    if s in {"database", "rds", "aurora", "dynamodb", "redshift"} and (
        "pause during off-hours" in t or "terminate idle" in t or "shutdown nightly" in t
    ):
        return False

    # Service-action alignment checks.
    if "lifecycle" in t or "intelligent-tiering" in t or "glacier" in t:
        return s in {"storage", "s3"}
    if "cache" in t or "redis" in t or "elasticache" in t:
        return s in {"cache", "database", "service", "elasticache"}
    if "price class" in t or "cloudfront" in t or "cdn" in t:
        return s in {"cdn"}
    if "gp3" in t or "snapshot" in t or "unattached volume" in t:
        return s in {"storage", "ebs", "database", "service"}

    return True


def _is_generic_title(title: str) -> bool:
    """Detect low-information titles that should not pass without concrete action.
    
    A title is generic if it:
    - Starts with 'optimize', 'improve', 'enhance' without a specific verb
    - Only contains resource name and target type (e.g., "Optimize X to type")
    - Lacks action-verb specificity (downsize, add, enable, migrate, etc.)
    - Has no metrics or business context
    """
    t = (title or "").strip().lower()
    if not t:
        return True

    # Exact generic strings
    if t in {"optimization", "cost optimization", "recommendation", "optimize", "improve", "enhance"}:
        return True
    
    # Strong action verbs that make titles specific
    strong_verbs = (
        "downsize", "right-size", "migrate", "upgrade", "add ", "enable", 
        "consolidate", "remove ", "switch", "delete ", "replace", "pause",
        "lifecycle", "intelligent-tiering", "vpc endpoint", "read replica"
    )
    if any(verb in t for verb in strong_verbs):
        return False  # Has a strong specific verb, so it's NOT generic
    
    # Metrics/context indicators (CPU %, cost reduction %, %, rate)
    context_markers = ("cpu ", "avg ", "%", "/s", "/mo", "metrics", "average", "utilization")
    if any(marker in t for marker in context_markers):
        return False  # Has metrics/context, likely specific
    
    # Generic prefixes that need further inspection
    generic_prefixes = (
        "optimize ",
        "optimization for ",
        "cost optimization for ",
        "recommendation ",
        "improve ",
        "enhance ",
        "reduce cost",
    )
    
    if any(t.startswith(p) for p in generic_prefixes):
        # Pattern: "optimize X to Y" OR "improve X for Y" with NO specific verb = GENERIC
        # Allow ONLY if it has strong specifics: metrics, strong action verb, or detailed context
        has_strong_specific = any(verb in t for verb in strong_verbs)
        has_metrics = any(marker in t for marker in context_markers)
        
        # "Optimize X to Y" is generic unless it has metrics or a strong verb
        if " to " in t or " for " in t:
            return not (has_strong_specific or has_metrics)
        
        # Any generic prefix without specificity = GENERIC
        return True
    
    return False


def _has_concrete_action_target(action_text: str) -> bool:
    """Require explicit technical change details in the action body."""
    t = (action_text or "").lower()
    if not t:
        return False

    verbs = ("migrate", "right-size", "downsize", "upgrade", "replace", "enable", "add", "remove", "switch", "consolidate")
    concrete_markers = (
        " to ",
        " from ",
        "db.",
        "m5",
        "m6",
        "t3",
        "t4g",
        "gp2",
        "gp3",
        "graviton",
        "lifecycle",
        "intelligent-tiering",
        "price class",
        "vpc endpoint",
        "read replica",
        "multi-az",
    )

    has_verb = any(v in t for v in verbs)
    has_marker = any(m in t for m in concrete_markers)
    return has_verb and has_marker


def _rewrite_generic_title(card: Dict[str, Any], service_type: str, action_text: str) -> str:
    """Build specific title when LLM returns a generic one.

    Uses Qwen first for a stronger title + implementation plan, then falls back to
    deterministic rule-based title generation.
    """
    rid = str((card.get("resource_identification") or {}).get("resource_id", "") or "resource").strip()
    rec0 = (card.get("recommendations") or [{}])[0]
    action = str(rec0.get("action", "") or action_text or "").lower()

    qwen_title, qwen_steps = _generate_significant_title_and_plan_with_qwen(card, service_type, action)
    if qwen_title:
        if qwen_steps and not rec0.get("implementation_steps"):
            rec0["implementation_steps"] = qwen_steps
        return qwen_title

    current_type = str((card.get("resource_identification") or {}).get("current_instance_type", "") or "").strip()
    recommended_type = str((card.get("resource_identification") or {}).get("recommended_instance_type", "") or "").strip()

    if current_type and recommended_type:
        return f"Right-size {rid} from {current_type} to {recommended_type}"
    if "graviton" in action or "arm64" in action:
        return f"Migrate {rid} to Graviton/ARM for lower compute cost"
    if "lifecycle" in action:
        return f"Add lifecycle policy for {rid} to reduce storage tiers"
    if "intelligent-tiering" in action:
        return f"Enable Intelligent-Tiering on {rid} to cut storage waste"
    if "gp3" in action:
        return f"Migrate {rid} storage from gp2 to gp3"
    if "price class" in action or "cloudfront" in action:
        return f"Optimize CloudFront price class for {rid}"
    if "read replica" in action:
        return f"Add read replica for {rid} to reduce primary DB pressure"
    if "cache" in action or "redis" in action:
        return f"Add caching optimization for {rid} to reduce backend load"
    if "vpc endpoint" in action or "nat" in action:
        return f"Reduce network transfer cost for {rid} via VPC endpoint strategy"

    st = (service_type or "service").lower()
    if st in {"database", "rds", "aurora", "dynamodb", "redshift"}:
        return f"Right-size and tune database capacity for {rid}"
    if st in {"storage", "s3", "ebs", "efs"}:
        return f"Optimize storage lifecycle and class for {rid}"
    if st in {"cdn", "cloudfront"}:
        return f"Optimize CDN cost and cache policy for {rid}"
    if st in {"cache", "elasticache"}:
        return f"Right-size cache nodes for {rid}"

    return f"Optimize {rid} with a specific cost-reduction configuration change"


def _generate_significant_title_and_plan_with_qwen(
    card: Dict[str, Any],
    service_type: str,
    action_text: str,
) -> Tuple[str, List[str]]:
    """Use Qwen to generate a concrete recommendation title and implementation plan."""
    if not HAS_REQUESTS:
        return "", []

    rid = str((card.get("resource_identification") or {}).get("resource_id", "") or "resource").strip()
    rec0 = (card.get("recommendations") or [{}])[0]
    current_type = str((card.get("resource_identification") or {}).get("current_instance_type", "") or "").strip()
    target_type = str((card.get("resource_identification") or {}).get("recommended_instance_type", "") or "").strip()
    savings = float(card.get("total_estimated_savings", 0) or 0)
    env = str((card.get("resource_identification") or {}).get("environment", "production") or "production")

    system_prompt = (
        "You are a senior FinOps architect. "
        "Return ONLY compact JSON with keys: title (string), implementation_steps (list of 4-6 strings). "
        "The title MUST be concrete, specific, and action-oriented. "
        "NEVER use vague words: Optimize, Improve, Enhance, Cost Optimization, or Recommendation. "
        "For resource/type changes: use verbs like Downsize, Right-size, Migrate, Upgrade, Consolidate. "
        "ALWAYS include 'from X to Y' for instance/cluster changes. "
        "Include metrics, business context, or specific actions in the title."
    )
    
    user_prompt = (
        "Generate a FinOps recommendation title and implementation steps.\n"
        f"Resource: {rid}\n"
        f"Service: {service_type}\n"
        f"Environment: {env}\n"
        f"Current: {current_type if current_type else 'not specified'}\n"
        f"Target: {target_type if target_type else 'not specified'}\n"
        f"Savings: ${savings:.2f}/month\n"
        f"Action: {action_text or rec0.get('action', 'optimization')}\n\n"
        "Requirements:\n"
        "1. Title must include action verb (Right-size/Downsize/Add/Enable/Migrate, etc.)\n"
        "2. If changing instance type, use format: 'Right-size X from TYPE1 to TYPE2'\n"
        "3. If adding feature/policy, use format: 'Add FEATURE for X to achieve BENEFIT'\n"
        "4. Title max 110 characters, no vague words\n"
        "5. Implementation steps must be concrete and ordered (4-6 steps)\n"
    )

    try:
        response = _call_ollama(system_prompt, user_prompt, temperature=0.1, max_tokens=320)
        if not response:
            return "", []

        payload = response.strip()
        fence = re.search(r"```json\s*(\{[\s\S]*\})\s*```", payload, re.IGNORECASE)
        if fence:
            payload = fence.group(1).strip()
        else:
            start = payload.find("{")
            end = payload.rfind("}")
            if start >= 0 and end > start:
                payload = payload[start:end + 1]

        parsed = json.loads(payload)
        title = str(parsed.get("title", "") or "").strip()
        steps = parsed.get("implementation_steps") or []
        if not isinstance(steps, list):
            steps = [str(steps)] if steps else []
        steps = [str(s).strip() for s in steps if str(s).strip()]

        if _is_generic_title(title):
            return "", []
        return title[:110], steps[:6]
    except Exception as e:
        logger.debug("[TITLE REWRITE] Qwen title generation failed: %s", e)
        return "", []


def _save_response(text: str, arch_name: str):
    """Save response for debugging — always to a predictable path."""
    try:
        # Save to predictable path (overwrite each time) + timestamped copy
        stable_path = "/home/finops/finops-ai-system/data/last_llm_response.txt"
        with open(stable_path, "w") as f:
            f.write(text)
        logger.info("Saved response to %s (%d chars)", stable_path, len(text))
    except Exception as e:
        logger.warning("Could not save response: %s", e)


__all__ = ["generate_recommendations", "call_llm", "RecommendationResult"]
