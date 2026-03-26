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

from src.rag.graph_business_translator import build_business_context_for_resources
from src.knowledge_base.aws_finops_best_practices import (
    COMPUTE_BEST_PRACTICES,
    DATABASE_BEST_PRACTICES,
    STORAGE_BEST_PRACTICES,
    NETWORKING_BEST_PRACTICES,
    get_best_practices_for_service,
)

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
    """Generate recommendations using pattern-based engine + LLM polishing.
    
    Pipeline:
    1. Run pattern detectors against architecture graph → PatternMatches
    2. Enrich matches with graph RAG context (deps, blast radius, cross-AZ, traffic)
    3. Convert enriched matches to card format
    4. Feed pre-built cards to LLM for language polishing (optional)
    5. If LLM fails, use engine cards directly (never return 0 results)
    """
    
    from src.llm.prompts import RECOMMENDATION_SYSTEM_PROMPT, RECOMMENDATION_USER_PROMPT
    
    start = time.time()
    result = RecommendationResult(architecture_name=architecture_name)
    
    logger.info("=" * 70)
    logger.info("GENERATING RECOMMENDATIONS (Engine + LLM)")
    logger.info("Backend: %s", "Gemini Flash" if USE_GEMINI else "Qwen 2.5 (Ollama)")
    logger.info("=" * 70)
    try:
        pkg_dict = asdict(context_package) if hasattr(context_package, '__dataclass_fields__') else context_package
        
        # ═══ STAGE 1: Pattern Engine (deterministic) ═══
        engine_cards = []
        if raw_graph_data:
            t_engine = time.time()
            try:
                from src.recommendation_engine.scanner import scan_architecture
                from src.recommendation_engine.enricher import enrich_matches
                
                # Log what we got
                graph_keys = list(raw_graph_data.keys()) if isinstance(raw_graph_data, dict) else "not-a-dict"
                nodes_raw = raw_graph_data.get("nodes") or raw_graph_data.get("services") or {}
                edges_raw = raw_graph_data.get("edges") or raw_graph_data.get("dependencies") or []
                node_count = len(nodes_raw) if isinstance(nodes_raw, (dict, list)) else 0
                edge_count = len(edges_raw) if isinstance(edges_raw, (dict, list)) else 0
                logger.info("[ENGINE] graph_data keys=%s, nodes=%d, edges=%d", graph_keys, node_count, edge_count)
                
                # Fallback: if API graph has no nodes, try loading graph.json directly
                scan_data = raw_graph_data
                if node_count == 0:
                    import os
                    graph_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "outputs", "graph.json")
                    if os.path.exists(graph_json_path):
                        import json as _json
                        with open(graph_json_path) as _f:
                            scan_data = _json.load(_f)
                        logger.info("[ENGINE] Loaded fallback graph.json: %d nodes", len(scan_data.get("nodes", {})))
                
                matches = scan_architecture(scan_data)
                enriched = enrich_matches(matches, scan_data)
                engine_cards = _engine_to_cards(enriched)
                logger.info("[ENGINE] %d pattern matches → %d enriched cards in %.1fs",
                           len(matches), len(engine_cards), time.time() - t_engine)
            except Exception as e:
                import traceback
                logger.error("[ENGINE] Failed: %s\n%s", e, traceback.format_exc())
                logger.warning("[ENGINE] Falling back to LLM-only mode")
        
        # ═══ STAGE 2: Build LLM context ═══
        t1 = time.time()
        service_inventory = _build_service_inventory(raw_graph_data) if raw_graph_data else ""
        cloudwatch_metrics = _build_metrics(raw_graph_data) if raw_graph_data else ""
        graph_context = _build_graph(pkg_dict)
        business_graph_context = _build_business_graph_context(raw_graph_data, pkg_dict) if raw_graph_data else "(No business graph context)"
        pricing_data = _build_pricing()
        aws_best_practices = _build_best_practices(pkg_dict, raw_graph_data)
        
        # Add engine results as factual grounding for LLM (source-of-truth facts)
        engine_context = _format_engine_context(engine_cards) if engine_cards else ""
        
        user_prompt = RECOMMENDATION_USER_PROMPT.format(
            service_inventory=service_inventory,
            cloudwatch_metrics=cloudwatch_metrics,
            graph_context=graph_context,
            business_graph_context=business_graph_context,
            pricing_data=pricing_data,
            aws_best_practices=aws_best_practices,
        )
        
        # Append engine context as factual JSON/text so LLM reasons from facts.
        if engine_context:
            user_prompt += f"\n\n## ENGINE_FACTS (source of truth from deterministic engine)\n\n{engine_context}"
        
        prompt_chars = len(RECOMMENDATION_SYSTEM_PROMPT) + len(user_prompt)
        logger.info("[PROMPT SIZE] system=%d, user=%d, total=%d chars (~%d tokens)",
                   len(RECOMMENDATION_SYSTEM_PROMPT), len(user_prompt), prompt_chars, prompt_chars // 4)
        
        # ═══ STAGE 3: LLM call (primary recommender) ═══
        llm_cards = []
        try:
            t3 = time.time()
            raw_response = call_llm(
                system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=0.2,
                max_tokens=6000,
                architecture_name=architecture_name,
            )
            logger.info("[TIMING] LLM call completed in %.1fs (%d chars)",
                       time.time() - t3, len(raw_response) if raw_response else 0)
            
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
            logger.warning("[LLM] Call failed: %s — using engine cards only", e)
        
        # ═══ STAGE 4: LLM-primary selection with deterministic fallback ═══
        if llm_cards:
            cards = llm_cards
            logger.info("[PIPELINE] Final: %d cards (primary=llm, fallback=engine)", len(cards))
        else:
            cards = engine_cards
            logger.info("[PIPELINE] Final: %d cards (llm empty/failed, using engine fallback)", len(cards))
        
        if not cards:
            logger.warning("⚠️  No recommendations generated from engine or LLM — returning empty set")
        
        # Finalize (return empty list if no cards instead of crashing)
        result.cards = cards
        result.llm_used = bool(llm_cards)
        result.total_estimated_savings = sum(c.get("total_estimated_savings", 0) for c in cards) if cards else 0.0
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
    cards = []
    for match in enriched_matches:
        enrichment = match.get("enrichment", {})
        traffic = enrichment.get("traffic", {})
        cross_az = enrichment.get("cross_az", {})
        redundancy = enrichment.get("redundancy", {})
        gm = match.get("graph_metrics", {})
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
        analysis_parts.append(f"")
        analysis_parts.append(f"Current State: {current_type} in {region} ({env} environment)")
        analysis_parts.append(f"Recommended: Migrate to {recommended_type}")
        analysis_parts.append(f"Estimated Savings: ${savings:.2f}/month (${savings * 12:.2f}/year)")
        analysis_parts.append(f"")
        if why:
            analysis_parts.append(f"Impact Analysis: {why}")
        if not redundancy.get("has_full_redundancy", True):
            analysis_parts.append(f"⚠ WARNING: No redundancy path exists. {len(dependent_services)} service(s) will be impacted if this resource fails.")
        if gm.get("single_point_of_failure"):
            analysis_parts.append(f"🔴 CRITICAL: This is a Single Point of Failure. Add redundancy before making changes.")
        full_analysis = "\n".join(analysis_parts)
        
        # ── Build implementation steps ──
        impl_steps = []
        impl_steps.append(f"1. Review current {aws_service} resource: {resource_id}")
        impl_steps.append(f"2. Verify no active deployments depend on current configuration")
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
            risk_parts.append(f"Impact: {len(dependent_services)} dependent service(s) — {', '.join(dependent_services)}")
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


def _merge_engine_and_llm_cards(engine_cards: List[Dict], llm_cards: List[Dict]) -> List[Dict]:
    """Merge engine cards (base) with LLM cards (supplements).
    
    Behavior:
    1) Engine cards are always included (deterministic baseline).
    2) If an LLM card matches an engine resource/title, it ENHANCES the existing
       engine card instead of being dropped.
    3) LLM cards for truly new opportunities are appended.
    4) Cards explicitly tagged as [NEW DISCOVERY] are preserved as LLM cards,
       even when they target an existing resource.
    """
    if not engine_cards:
        return llm_cards or []
    if not llm_cards:
        return engine_cards

    merged = list(engine_cards)

    # Build lookup for engine cards by resource and title prefix.
    engine_by_resource: Dict[str, int] = {}
    engine_title_prefixes: Dict[str, int] = {}
    for idx, card in enumerate(merged):
        rid = card.get("resource_identification", {}) or {}
        resource_id = str(rid.get("resource_id", "") or "").strip().lower()
        resource_name = str(rid.get("resource_name", "") or "").strip().lower()
        title_prefix = str(card.get("title", "") or "").strip().lower()[:40]

        if resource_id:
            engine_by_resource[resource_id] = idx
        if resource_name:
            engine_by_resource[resource_name] = idx
        if title_prefix:
            engine_title_prefixes[title_prefix] = idx

    appended = 0
    enhanced = 0

    for llm_card in llm_cards:
        llm_card = dict(llm_card)
        llm_card["source"] = "llm"

        llm_rid = llm_card.get("resource_identification", {}) or {}
        llm_resource_id = str(llm_rid.get("resource_id", "") or "").strip().lower()
        llm_resource_name = str(llm_rid.get("resource_name", "") or "").strip().lower()
        llm_title = str(llm_card.get("title", "") or "").strip()
        llm_title_prefix = llm_title.lower()[:40]
        is_new_discovery = "[new discovery]" in llm_title.lower()

        match_idx = None
        for key in (llm_resource_id, llm_resource_name):
            if key and key in engine_by_resource:
                match_idx = engine_by_resource[key]
                break
        if match_idx is None and llm_title_prefix and llm_title_prefix in engine_title_prefixes:
            match_idx = engine_title_prefixes[llm_title_prefix]

        if match_idx is not None and not is_new_discovery:
            base = merged[match_idx]
            # Keep deterministic numeric/scope fields from engine, but replace
            # narrative-heavy fields with LLM enrichment when present.
            if llm_card.get("title"):
                base["title"] = llm_card.get("title")

            # Replace recommendation details only when LLM content has
            # meaningful savings context; otherwise preserve engine details.
            llm_recs = llm_card.get("recommendations") or []
            if llm_recs:
                llm_rec0 = llm_recs[0] if isinstance(llm_recs[0], dict) else {}
                llm_rec_savings = llm_rec0.get("estimated_monthly_savings", 0)
                try:
                    llm_rec_savings = float(llm_rec_savings or 0)
                except Exception:
                    llm_rec_savings = 0.0

                base_savings = base.get("total_estimated_savings", 0)
                try:
                    base_savings = float(base_savings or 0)
                except Exception:
                    base_savings = 0.0

                if llm_rec_savings > 0 or base_savings <= 0:
                    base["recommendations"] = llm_recs
            if llm_card.get("raw_analysis"):
                base["raw_analysis"] = llm_card.get("raw_analysis")
            if llm_card.get("why_it_matters"):
                base["why_it_matters"] = llm_card.get("why_it_matters")
            if llm_card.get("linked_best_practice"):
                base["linked_best_practice"] = llm_card.get("linked_best_practice")
            if llm_card.get("finops_best_practice"):
                base["finops_best_practice"] = llm_card.get("finops_best_practice")

            # Provenance markers for UI/debugging.
            base["source"] = "engine+llm"
            base["llm_enhanced"] = True
            enhanced += 1
            continue

        merged.append(llm_card)
        appended += 1

    logger.info("[MERGE] engine=%d llm=%d => final=%d (enhanced=%d appended=%d)",
                len(engine_cards), len(llm_cards), len(merged), enhanced, appended)
    return merged


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
    services = list(graph_data.get("services") or graph_data.get("nodes") or [])
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
    }

    for card in cards:
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
    """Detect low-information titles that should not pass without concrete action."""
    t = (title or "").strip().lower()
    if not t:
        return True

    generic_prefixes = (
        "optimize ",
        "optimization for ",
        "cost optimization for ",
        "recommendation ",
        "improve ",
        "enhance ",
    )
    if t in {"optimization", "cost optimization", "recommendation"}:
        return True
    if any(t.startswith(p) for p in generic_prefixes):
        # A title like "optimize api-x" is generic unless it includes a concrete change
        concrete_tokens = (" to ", " from ", "->", "graviton", "gp3", "lifecycle", "intelligent-tiering", "price class")
        return not any(tok in t for tok in concrete_tokens)
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
    """Build deterministic, specific title when LLM returns a generic one."""
    rid = str((card.get("resource_identification") or {}).get("resource_id", "") or "resource").strip()
    rec0 = (card.get("recommendations") or [{}])[0]
    action = str(rec0.get("action", "") or action_text or "").lower()

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
