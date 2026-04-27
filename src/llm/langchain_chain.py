"""
LangChain Two-Agent Sequential Chain for FinOps Recommendations
================================================================
Wires Agent 1 (KB Linker) → Agent 2 (FinOps Generator) using LangChain
SequentialChain so that Agent 2's input is automatically fed from Agent 1's
output.

Supports both Ollama (local Qwen 2.5 7B) and Gemini Flash backends,
wrapped as LangChain-compatible LLMs.
"""

import os
import json
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# CONFIG (shared with client.py)
# ═══════════════════════════════════════════════════════════════════════════

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("FINOPS_MODEL", "qwen2.5:7b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash-exp"
USE_GEMINI = os.getenv("USE_GEMINI", "false").lower() == "true" and GEMINI_API_KEY
TIMEOUT = int(os.getenv("LLM_TIMEOUT", "1800"))


# ═══════════════════════════════════════════════════════════════════════════
# LangChain LLM Wrappers — thin adapters over existing HTTP backends
# ═══════════════════════════════════════════════════════════════════════════

from langchain_core.language_models.llms import LLM
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda


class OllamaFinOpsLLM(LLM):
    """LangChain LLM wrapper for Qwen 2.5 via Ollama HTTP API."""

    model: str = OLLAMA_MODEL
    base_url: str = OLLAMA_URL
    temperature: float = 0.2
    max_tokens: int = 16000
    timeout: int = TIMEOUT

    @property
    def _llm_type(self) -> str:
        return "ollama-finops"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs) -> str:
        import requests

        # Extract system prompt if embedded in the prompt via delimiter
        system_prompt = ""
        user_prompt = prompt
        if "<<<SYSTEM>>>" in prompt and "<<<USER>>>" in prompt:
            parts = prompt.split("<<<USER>>>")
            system_prompt = parts[0].replace("<<<SYSTEM>>>", "").strip()
            user_prompt = parts[1].strip() if len(parts) > 1 else prompt

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        import time
        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": self.temperature,
                            "num_predict": self.max_tokens,
                            "num_ctx": 131072,
                        },
                    },
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    text = resp.json().get("message", {}).get("content", "")
                    return text
                else:
                    raise RuntimeError(f"Ollama returned {resp.status_code}: {resp.text[:200]}")
            except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError) as e:
                if attempt == 2:
                    raise RuntimeError(f"Ollama LangChain call failed after 3 attempts: {e}")
                logger.warning("[LANGCHAIN] Ollama connection error (attempt %d/3), retrying...", attempt + 1)
                time.sleep(2)
            except Exception as e:
                raise RuntimeError(f"Ollama LangChain call failed: {e}")
        return ""


class GeminiFinOpsLLM(LLM):
    """LangChain LLM wrapper for Gemini Flash API."""

    model_name: str = GEMINI_MODEL
    api_key: str = GEMINI_API_KEY
    temperature: float = 0.2
    max_tokens: int = 16000

    @property
    def _llm_type(self) -> str:
        return "gemini-finops"

    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs) -> str:
        try:
            import google.generativeai as genai

            system_prompt = ""
            user_prompt = prompt
            if "<<<SYSTEM>>>" in prompt and "<<<USER>>>" in prompt:
                parts = prompt.split("<<<USER>>>")
                system_prompt = parts[0].replace("<<<SYSTEM>>>", "").strip()
                user_prompt = parts[1].strip() if len(parts) > 1 else prompt

            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt if system_prompt else None,
            )
            response = model.generate_content(
                user_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens,
                ),
            )
            return response.text
        except Exception as e:
            raise RuntimeError(f"Gemini LangChain call failed: {e}")


def _get_llm(max_tokens: int = 6000, temperature: float = 0.2) -> LLM:
    """Get the appropriate LangChain LLM based on environment config."""
    if USE_GEMINI:
        logger.info("[LANGCHAIN] Using Gemini Flash backend")
        return GeminiFinOpsLLM(
            api_key=GEMINI_API_KEY,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    else:
        logger.info("[LANGCHAIN] Using Ollama (%s) backend", OLLAMA_MODEL)
        return OllamaFinOpsLLM(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_URL,
            temperature=temperature,
            max_tokens=max_tokens,
        )


# ═══════════════════════════════════════════════════════════════════════════
# LANGCHAIN SEQUENTIAL PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def _build_prompt_string(system_prompt: str, user_prompt: str) -> str:
    """Build a single prompt string with system/user delimiters for our LLM wrappers."""
    return f"<<<SYSTEM>>>{system_prompt}<<<USER>>>{user_prompt}"


def run_finops_chain(
    context_parts: Dict[str, str],
    architecture_name: str = "",
) -> str:
    """Run single-agent FinOps pipeline (KB + Generator combined).

    Combines KB linking and recommendation generation into ONE LLM call to
    stay well within the frontend timeout budget.

    Args:
        context_parts: Dict with keys: service_inventory, cost_anchors,
                        best_practices, rag_knowledge, dependency_map.
        architecture_name: Name of the architecture being analyzed.

    Returns:
        Raw JSON string of recommendations, ready for parsing.
    """
    from src.llm.prompts import (
        FINOPS_GENERATOR_SYSTEM_PROMPT,
    )

    logger.info("=" * 70)
    logger.info("[LANGCHAIN] Starting single-agent FinOps pipeline (timeout-safe)")
    logger.info("[LANGCHAIN] Backend: %s", "Gemini Flash" if USE_GEMINI else f"Ollama ({OLLAMA_MODEL})")
    logger.info("=" * 70)

    pipeline_start = time.time()

    llm = _get_llm(max_tokens=16000, temperature=0.2)

    # Build a single combined user prompt with all context sections
    combined_user = f"""
\u2501\u2501\u2501 SECTION 1: SERVICE INVENTORY (every node with type, env, monthly cost) \u2501\u2501\u2501
{context_parts.get("service_inventory", "(no inventory)")}

\u2501\u2501\u2501 SECTION 2: COST ANCHORS (exact monthly costs \u2014 use only these) \u2501\u2501\u2501
{context_parts.get("cost_anchors", "(no cost data)")}

\u2501\u2501\u2501 SECTION 3: FINOPS KNOWLEDGE BASE (AWS best practices) \u2501\u2501\u2501
{context_parts.get("best_practices", "(no KB)")}

\u2501\u2501\u2501 SECTION 4: RAG KNOWLEDGE (retrieved best-practice chunks) \u2501\u2501\u2501
{context_parts.get("rag_knowledge", "(no RAG)")}

\u2501\u2501\u2501 SECTION 5: ARCHITECTURAL DEPENDENCIES (graph edges) \u2501\u2501\u2501
{context_parts.get("dependency_map", "(no dependencies)")}

\u2501\u2501\u2501 SECTION 6: PRE-COMPUTED WASTE SIGNALS (mandatory action hints) \u2501\u2501\u2501
{context_parts.get("waste_signals", "(no pre-computed signals)")}

\u2501\u2501\u2501 SECTION 6: PRE-COMPUTED WASTE SIGNALS (mandatory action hints) \u2501\u2501\u2501
{context_parts.get("waste_signals", "(no pre-computed signals)")}

\u2501\u2501\u2501 GENERATE RECOMMENDATIONS \u2501\u2501\u2501
For EVERY resource in Section 1:
  1. If Section 6 has a waste signal for this resource, USE its ACTION and savings directly.
  2. Otherwise find the best KB strategy from Sections 3-4.
  3. Look up the exact monthly cost from Section 2.
  4. Write a DETAILED finding: type, config, strategy, cost, savings math ($X x Y% = $Z/mo).
  5. Write why_it_matters: annual savings (x12), affected services, risk level.
  6. Provide a real AWS CLI remediation command.

STRICT RULES:
- /aws/* log groups: ALWAYS SET_LOG_RETENTION (50% savings). NEVER REVIEW_ARCHITECTURE.
- ECR/registry: ALWAYS ADD_LIFECYCLE (40% savings). NEVER REVIEW_ARCHITECTURE.
- ECS/fargate/container: ALWAYS MOVE_TO_GRAVITON (20% savings). NEVER REVIEW_ARCHITECTURE.
- Any Section 6 signal resource: use its ACTION. NEVER REVIEW_ARCHITECTURE.
- REVIEW_ARCHITECTURE ONLY if truly no other action is possible.

Sort by estimated_savings_monthly descending.
Return ONLY a valid JSON array - no markdown, no wrapping.
"""

    prompt = _build_prompt_string(FINOPS_GENERATOR_SYSTEM_PROMPT, combined_user)

    logger.info("[LANGCHAIN] Calling single agent (%d char prompt)...", len(prompt))
    t_start = time.time()

    recommendations_raw = llm.invoke(prompt)

    elapsed = time.time() - t_start
    logger.info("=" * 70)
    logger.info("[LANGCHAIN] Single-agent complete in %.1fs (%d chars output)", elapsed, len(recommendations_raw or ""))
    logger.info("=" * 70)

    return recommendations_raw or "[]"


# ═══════════════════════════════════════════════════════════════════════════
# BATCHED PIPELINE — 3-5 nodes per LLM call, fast + reliable
# ═══════════════════════════════════════════════════════════════════════════

def _build_batch_inventory(batch_services: List[Dict]) -> str:
    """Build compact inventory lines for a batch of services."""
    lines = []
    for svc in batch_services:
        sid = svc.get("id", svc.get("name", "unknown"))
        stype = svc.get("type", "service")
        cost = svc.get("cost_monthly", 0)
        env = svc.get("environment", svc.get("env", "production"))
        region = svc.get("region", "us-east-1")
        name = svc.get("name", sid)
        config = svc.get("instance_type", svc.get("config", ""))
        lines.append(
            f"  • {sid} | type={stype} | name={name} | cost=${cost:.2f}/mo | "
            f"env={env} | region={region}"
            + (f" | config={config}" if config else "")
        )
    return "\n".join(lines) if lines else "(empty batch)"


def _build_batch_costs(batch_services: List[Dict]) -> str:
    """Build cost anchor table for a batch."""
    lines = ["Resource ID | Current $/mo"]
    lines.append("-" * 50)
    for svc in batch_services:
        sid = svc.get("id", svc.get("name", "unknown"))
        cost = svc.get("cost_monthly", 0)
        lines.append(f"  {sid} | ${cost:.2f}/mo")
    lines.append("")
    lines.append("⚠️ Use ONLY these cost figures. Do NOT invent costs.")
    return "\n".join(lines)


def _build_batch_deps(batch_services: List[Dict], all_edges: List[Dict]) -> str:
    """Build dependency context for nodes in this batch."""
    batch_ids = {svc.get("id", svc.get("name", "")) for svc in batch_services}
    relevant = []
    for edge in all_edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        if src in batch_ids or tgt in batch_ids:
            etype = edge.get("type", "depends_on")
            relevant.append(f"  {src} → {tgt} ({etype})")
    return "\n".join(relevant[:20]) if relevant else "(no dependencies for these resources)"


def _build_batch_kb(batch_services: List[Dict]) -> str:
    """Build targeted KB snippets for the service types in this batch."""
    from src.knowledge_base.aws_finops_best_practices import get_compact_kb_for_service_type

    seen_types = set()
    lines = []
    for svc in batch_services:
        stype = svc.get("type", "service")
        if stype not in seen_types:
            seen_types.add(stype)
            kb = get_compact_kb_for_service_type(stype)
            lines.append(f"[{stype}] {kb}")
    return "\n\n".join(lines) if lines else "(no KB available)"


def _build_batch_rag(batch_services: List[Dict]) -> str:
    """Retrieve targeted RAG context from pgvector for this batch's service types.

    Queries the persistent doc_chunks table (populated once from /docs PDFs and MDs)
    and returns the most relevant FinOps strategies for the services in this batch.
    This grounds the LLM in real AWS documentation rather than generic knowledge.
    """
    try:
        from src.rag.retrieval_service import retrieve

        # Build a targeted query from the batch's service names and types
        service_names = [svc.get("name", svc.get("id", "")) for svc in batch_services]
        service_types = list({svc.get("type", "service") for svc in batch_services})

        query = (
            f"AWS FinOps cost optimization strategies for "
            f"{', '.join(service_types)}. "
            f"Resources: {', '.join(service_names[:5])}. "
            f"Right-sizing, Savings Plans, Reserved Instances, Graviton migration, "
            f"storage tiering, lifecycle policies, scheduling."
        )

        chunks = retrieve(query, top_k=4)
        if not chunks:
            logger.debug("[RAG] No chunks retrieved for batch query")
            return "(no RAG context available)"

        rag_parts = []
        for c in chunks:
            # Keep each chunk concise but informative
            text = c.text[:800] if hasattr(c, 'text') else str(c.get('text', ''))[:800]
            source = c.source_file if hasattr(c, 'source_file') else c.get('source_file', 'unknown')
            rag_parts.append(f"[Source: {source}]\n{text}")

        combined = "\n\n".join(rag_parts)
        logger.info("[RAG] Injected %d chars from %d chunks into batch",
                    len(combined), len(chunks))
        return combined

    except Exception as e:
        logger.warning("[RAG] Failed to retrieve doc chunks for batch: %s", e)
        return "(RAG retrieval unavailable)"


def _build_batch_waste(batch_services: List[Dict], waste_signals_text: str) -> str:
    """Extract waste signals relevant to nodes in this batch."""
    if not waste_signals_text or waste_signals_text.strip() in ("(no pre-computed signals)", ""):
        return "(no waste signals for these resources)"

    batch_ids = {svc.get("id", svc.get("name", "")).lower() for svc in batch_services}
    batch_names = {svc.get("name", "").lower() for svc in batch_services}
    all_ids = batch_ids | batch_names

    relevant_lines = []
    for line in waste_signals_text.split("\n"):
        line_lower = line.lower()
        if any(bid in line_lower for bid in all_ids if bid):
            relevant_lines.append(line.strip())

    return "\n".join(relevant_lines) if relevant_lines else "(no waste signals for these resources)"


def _recover_json_array(text: str) -> List[Dict]:
    """Attempt to parse JSON array from LLM output, with truncation recovery."""
    import re

    cleaned = text.strip()
    # Remove markdown fences
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    cleaned = cleaned.strip()

    # Direct parse
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            # Handle {"recommendations": [...]} wrapper
            for key in ("recommendations", "results", "cards"):
                if isinstance(parsed.get(key), list):
                    return parsed[key]
            return [parsed]
    except json.JSONDecodeError:
        pass

    # Find JSON array in the text
    arr_match = re.search(r'\[', cleaned)
    if arr_match:
        arr_start = arr_match.start()
        # Try progressively shorter substrings
        for end in range(len(cleaned), arr_start + 10, -1):
            fragment = cleaned[arr_start:end].rstrip().rstrip(",")
            if not fragment.endswith("]"):
                fragment += "]"
            try:
                result = json.loads(fragment)
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                continue

    # Try to find individual JSON objects
    objects = []
    for m in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned):
        try:
            obj = json.loads(m.group())
            if isinstance(obj, dict) and obj.get("resource"):
                objects.append(obj)
        except json.JSONDecodeError:
            continue

    return objects


def run_finops_chain_batched(
    services: List[Dict],
    edges: List[Dict],
    waste_signals_text: str = "",
    architecture_name: str = "",
    batch_size: int = 2,
) -> str:
    """Run batched FinOps pipeline — 2 nodes per LLM call, SEQUENTIAL.

    Ollama processes one inference at a time. Parallel requests just queue
    and cause cascading timeouts. This function runs batches sequentially
    with a tight per-request timeout and retry on empty responses.

    Args:
        services: List of service dicts from graph_data["services"].
        edges: List of dependency dicts from graph_data["dependencies"].
        waste_signals_text: Pre-computed waste signals text from context assembler.
        architecture_name: Name of the architecture.
        batch_size: Number of nodes per batch (default 2 for speed).

    Returns:
        Raw JSON string — a concatenated array of all batch results.
    """
    from src.llm.prompts import FINOPS_BATCH_SYSTEM_PROMPT, FINOPS_BATCH_USER_PROMPT

    logger.info("=" * 70)
    logger.info("[BATCH] Starting SEQUENTIAL batched pipeline (%d services, batch=%d)",
                len(services), batch_size)
    logger.info("[BATCH] Backend: %s", "Gemini Flash" if USE_GEMINI else f"Ollama ({OLLAMA_MODEL})")
    logger.info("=" * 70)

    pipeline_start = time.time()

    # ── Filter: only send cost-relevant services to the LLM ──
    # Skip $0 networking primitives (subnets, SGs, route tables, VPCs, IGWs, IAM)
    # that waste LLM tokens generating useless "Review subnet" recommendations.
    SKIP_TYPES = {
        "subnet", "security_group", "route_table", "vpc", "internet_gateway",
        "iam_role", "iam_policy", "iam_user", "iam_group",
        "network_acl", "dhcp_options", "vpc_peering",
    }
    cost_relevant = []
    skipped = []
    for svc in services:
        stype = (svc.get("type") or svc.get("service_type") or "").lower().replace(" ", "_")
        cost = float(svc.get("cost_monthly", 0) or 0)
        name = (svc.get("name") or svc.get("id") or "").lower()

        # Skip if type is a networking primitive AND cost is $0
        if stype in SKIP_TYPES and cost <= 0:
            skipped.append(name)
            continue
        # Also skip by name patterns for resources without proper type tags
        if cost <= 0 and any(pat in name for pat in ("subnet-", "sg-", "rtb-", "igw-", "vpc-", "iam-")):
            skipped.append(name)
            continue
        cost_relevant.append(svc)

    if skipped:
        logger.info("[BATCH] Filtered out %d zero-cost networking/IAM resources: %s",
                    len(skipped), ", ".join(skipped[:10]) + ("..." if len(skipped) > 10 else ""))
    logger.info("[BATCH] %d cost-relevant services remain (from %d total)",
                len(cost_relevant), len(services))

    # If nothing cost-relevant, fall back to top services by cost
    if not cost_relevant:
        cost_relevant = sorted(services, key=lambda s: float(s.get("cost_monthly", 0) or 0), reverse=True)[:10]
        logger.info("[BATCH] Fallback: using top %d services by cost", len(cost_relevant))

    # High-performance batching: reduction in API roundtrips
    # Qwen (local) is faster with 10-20 per batch; Gemini (cloud) scales to 50+
    optimal_batch_size = 50 if USE_GEMINI else 15
    
    batches = [cost_relevant[i:i + optimal_batch_size] for i in range(0, len(cost_relevant), optimal_batch_size)]

    logger.info("[BATCH] Split %d services into %d batches of %d (OPTIMIZED FOR SPEED)",
                len(services), len(batches), optimal_batch_size)

    all_recommendations = []
    batch_times = []
    failed_batches = 0

    # Get LLM with generous context budget
    # Gemini Flash supports huge output; Qwen 2.5 handles context up to 128k
    llm_tokens = 64000 if USE_GEMINI else 40000
    llm = _get_llm(max_tokens=llm_tokens, temperature=0.2)
    llm.timeout = 900  # 15 minutes max per batch for massive production batches

    # SEQUENTIAL execution — Ollama can only handle 1 inference at a time
    for batch_idx, batch_services in enumerate(batches):
        batch_ids = [s.get("id", s.get("name", "?")) for s in batch_services]
        logger.info("[BATCH %d/%d] Processing: %s",
                    batch_idx + 1, len(batches), ", ".join(batch_ids))

        batch_start = time.time()
        batch_recs = []
        max_retries = 2

        for attempt in range(max_retries):
            try:
                # Build per-batch context with ALL signals
                inventory = _build_batch_inventory(batch_services)
                costs = _build_batch_costs(batch_services)
                batch_waste = _build_batch_waste(batch_services, waste_signals_text)
                batch_kb = _build_batch_kb(batch_services)
                batch_deps = _build_batch_deps(batch_services, edges)
                batch_rag = _build_batch_rag(batch_services)

                user_prompt = FINOPS_BATCH_USER_PROMPT.format(
                    batch_inventory=inventory,
                    batch_costs=costs,
                    batch_waste_signals=batch_waste,
                    batch_kb=batch_kb,
                    batch_deps=batch_deps,
                    batch_rag=batch_rag,
                )
                prompt = _build_prompt_string(FINOPS_BATCH_SYSTEM_PROMPT, user_prompt)

                # Call LLM
                raw = llm.invoke(prompt)

                batch_elapsed = time.time() - batch_start
                logger.info("[BATCH %d/%d] LLM response in %.1fs (%d chars)",
                            batch_idx + 1, len(batches), batch_elapsed, len(raw or ""))

                if raw and raw.strip() and len(raw.strip()) > 5:
                    batch_recs = _recover_json_array(raw)
                    if batch_recs:
                        break  # Success — stop retrying
                    else:
                        logger.warning("[BATCH %d/%d] JSON parse returned empty (attempt %d/%d)",
                                       batch_idx + 1, len(batches), attempt + 1, max_retries)
                else:
                    logger.warning("[BATCH %d/%d] Empty/short response (attempt %d/%d)",
                                   batch_idx + 1, len(batches), attempt + 1, max_retries)

            except Exception as e:
                logger.error("[BATCH %d/%d] Error (attempt %d/%d): %s",
                             batch_idx + 1, len(batches), attempt + 1, max_retries, str(e)[:200])

            # Brief pause before retry
            if attempt < max_retries - 1:
                time.sleep(2)

        batch_elapsed = time.time() - batch_start
        batch_times.append(batch_elapsed)

        if batch_recs:
            logger.info("[BATCH %d/%d] ✓ Parsed %d recommendations in %.1fs",
                        batch_idx + 1, len(batches), len(batch_recs), batch_elapsed)
            all_recommendations.extend(batch_recs)
        else:
            logger.warning("[BATCH %d/%d] ✗ Failed after %d attempts (%.1fs)",
                           batch_idx + 1, len(batches), max_retries, batch_elapsed)
            failed_batches += 1

    total_elapsed = time.time() - pipeline_start
    avg_batch_time = sum(batch_times) / len(batch_times) if batch_times else 0

    logger.info("=" * 70)
    logger.info("[BATCH] Pipeline complete: %d recommendations from %d/%d batches "
                "in %.1fs (avg %.1fs/batch)",
                len(all_recommendations), len(batches) - failed_batches,
                len(batches), total_elapsed, avg_batch_time)
    if failed_batches:
        logger.warning("[BATCH] %d batches failed (partial results returned)", failed_batches)
    logger.info("=" * 70)

    return json.dumps(all_recommendations)


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

__all__ = ["run_finops_chain", "run_finops_chain_batched"]

