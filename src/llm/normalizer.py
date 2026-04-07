"""
Unified Recommendation Schema Normalizer
==========================================
Converts engine-backed and LLM-proposed cards into one flat, consistent schema.

Rules enforced here (per spec):
  - Engine fields (resource_id, service, region, environment, action,
    estimated_savings_monthly, current_monthly_cost, engine_confidence) are NEVER overwritten.
  - llm_confidence <= engine_confidence for engine_backed recs.
  - Duplicates: same resource_id + same action → merged, extras marked is_duplicate_of.
  - Conflicts:  same resource_id + different actions → both marked is_conflicting=True.
  - LLM-proposed recs must have source="llm_proposed" and engine_confidence=0.
"""

import uuid
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ACTION NORMALISATION MAP
# Maps the LLM's snake_case or free-text actions → canonical SCREAMING_SNAKE_CASE
# ─────────────────────────────────────────────────────────────────────────────
_ACTION_MAP: Dict[str, str] = {
    # EC2
    "rightsize_ec2": "DOWNSIZE",
    "rightsize": "DOWNSIZE",
    "downsize": "DOWNSIZE",
    "terminate_ec2": "TERMINATE",
    "terminate": "TERMINATE",
    "decommission": "TERMINATE",
    "migrate_ec2_graviton": "MOVE_TO_GRAVITON",
    "move_to_graviton": "MOVE_TO_GRAVITON",
    "graviton": "MOVE_TO_GRAVITON",
    "schedule_ec2_stop": "STOP",
    "stop": "STOP",
    "schedule_stop": "STOP",
    # RDS
    "rightsize_rds": "DOWNSIZE",
    "disable_multi_az": "DISABLE_MULTI_AZ",
    "migrate_rds_gp2_to_gp3": "CHANGE_STORAGE_CLASS",
    "change_storage_class": "CHANGE_STORAGE_CLASS",
    "storage_migration": "CHANGE_STORAGE_CLASS",
    "add_read_replica": "ADD_READ_REPLICA",
    # ElastiCache
    "rightsize_elasticache": "DOWNSIZE",
    "migrate_cache_graviton": "MOVE_TO_GRAVITON",
    # Storage
    "s3_add_lifecycle": "ADD_LIFECYCLE",
    "add_lifecycle": "ADD_LIFECYCLE",
    "s3_enable_intelligent_tiering": "CHANGE_STORAGE_CLASS",
    "ebs_migrate_gp2_to_gp3": "CHANGE_STORAGE_CLASS",
    # Network
    "add_vpc_endpoint": "ADD_VPC_ENDPOINT",
    "eliminate_cross_az": "ELIMINATE_CROSS_AZ",
    "replace_nat_with_endpoints": "ADD_VPC_ENDPOINT",
    # Lambda
    "lambda_tune_memory": "TUNE_MEMORY",
    "lambda_migrate_arm64": "MOVE_TO_GRAVITON",
    # Cache
    "add_cache": "ADD_CACHE",
    "add_elasticache": "ADD_CACHE",
    # Upscale
    "upscale": "UPSCALE",
    # Reservation
    "purchase_reserved": "PURCHASE_RESERVED",
    "savings_plan": "PURCHASE_SAVINGS_PLAN",
    "reserved_instance": "PURCHASE_RESERVED",
}

_KNOWN_CANONICAL = {
    "STOP", "TERMINATE", "DOWNSIZE", "UPSCALE", "MOVE_TO_GRAVITON",
    "CHANGE_STORAGE_CLASS", "ADD_LIFECYCLE", "ADD_CACHE", "ADD_VPC_ENDPOINT",
    "ADD_READ_REPLICA", "DISABLE_MULTI_AZ", "ELIMINATE_CROSS_AZ",
    "TUNE_MEMORY", "PURCHASE_RESERVED", "PURCHASE_SAVINGS_PLAN",
    "REVIEW_ARCHITECTURE",
}

# Engine-owned actions that should NEVER be inferred for LLM cards
_ENGINE_ONLY_ACTIONS = {"DOWNSIZE", "TERMINATE", "STOP"}


# Best-practice description phrases that must NOT be treated as action enums.
# These appear when _coerce_backend_card_template copies rec["title"] into rec["action"].
_BP_PREFIXES = ("aws finops", "aws best practice", "finops:", "right-sizing:", "right_sizing:")


def _is_best_practice_description(raw: str) -> bool:
    """Return True when raw looks like a best-practice description, not a canonical action."""
    if len(raw) > 50:
        return True
    lower = raw.lower()
    return any(lower.startswith(p) for p in _BP_PREFIXES)


def _normalise_action(raw: str) -> str:
    """Map a raw action string to canonical SCREAMING_SNAKE_CASE."""
    if not raw or _is_best_practice_description(raw):
        return ""
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    mapped = _ACTION_MAP.get(key)
    if mapped:
        return mapped
    upper = raw.strip().upper().replace(" ", "_").replace("-", "_")
    if upper in _KNOWN_CANONICAL:
        return upper
    # Best-effort: return upper-cased version so it's at least consistent
    return upper


# Keyword → canonical action mapping used by _infer_action_from_context
_CONTEXT_KEYWORDS: List[Tuple[List[str], str]] = [
    (["terminate", "decommission", "waste", "idle", "unused", "retire"],   "TERMINATE"),
    (["stop", "schedule_stop", "shutdown"],                                 "STOP"),
    (["graviton", "arm64", "graviton2", "graviton3"],                       "MOVE_TO_GRAVITON"),
    (["gp2", "gp3", "migrate.*storage", "storage.*migrat"],                 "CHANGE_STORAGE_CLASS"),
    (["lifecycle", "intelligent.tier", "s3.*tier"],                         "ADD_LIFECYCLE"),
    (["vpc.*endpoint", "nat.*endpoint", "interface.*endpoint"],             "ADD_VPC_ENDPOINT"),
    (["cross.az", "cross_az", "eliminate.*az"],                             "ELIMINATE_CROSS_AZ"),
    (["multi.az", "disable.*multi"],                                        "DISABLE_MULTI_AZ"),
    (["read.*replica", "replica"],                                          "ADD_READ_REPLICA"),
    (["cache", "elasticache", "memcached", "redis"],                        "ADD_CACHE"),
    (["tune.*mem", "memory.*tune", "lambda.*mem"],                          "TUNE_MEMORY"),
    (["reserved", "reservation", "ri ", "savings.plan"],                    "PURCHASE_RESERVED"),
    (["right.size", "rightsize", "downsize", "resize", "right_siz"],        "DOWNSIZE"),
]


def _infer_action_from_context(card: Dict[str, Any]) -> str:
    """Infer canonical action from pattern_id, category, and title when action is unavailable."""
    import re
    bag = " ".join(filter(None, [
        str(card.get("pattern_id") or ""),
        str(card.get("category") or ""),
        str(card.get("title") or ""),
        str(card.get("linked_best_practice") or ""),
        str(card.get("finops_best_practice") or ""),
        str((card.get("recommendations") or [{}])[0].get("title") or ""),
    ])).lower()

    for keywords, canonical in _CONTEXT_KEYWORDS:
        for kw in keywords:
            if re.search(kw, bag):
                return canonical
    # Do NOT default to DOWNSIZE — that belongs to the engine.
    # Return the card's raw action uppercased if available, else generic label.
    raw = str(card.get("action") or "").strip().upper().replace(" ", "_").replace("-", "_")
    return raw if raw else "OPTIMIZE"


def _normalise_priority(raw: Any) -> str:
    p = str(raw or "MEDIUM").strip().upper()
    return p if p in {"LOW", "MEDIUM", "HIGH"} else "MEDIUM"


def _normalise_effort(raw: Any) -> str:
    e = str(raw or "MEDIUM").strip().upper()
    return e if e in {"LOW", "MEDIUM", "HIGH"} else "MEDIUM"


def _normalise_risk(raw: Any) -> str:
    r = str(raw or "MEDIUM").strip().upper()
    return r if r in {"LOW", "MEDIUM", "HIGH"} else "MEDIUM"


def _clamp_confidence(value: Any, ceiling: float = 1.0) -> float:
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    return round(max(0.0, min(v, ceiling)), 3)


def _extract_justification(card: Dict) -> List[str]:
    """Build a list of concrete justification bullets from card fields."""
    bullets: List[str] = []

    # From existing justification / why_it_matters fields
    for field in ("justification", "why_it_matters", "why_this_matters", "problem"):
        val = card.get(field)
        if isinstance(val, list):
            bullets.extend(str(b).strip("- ").strip() for b in val if b)
        elif isinstance(val, str) and val.strip():
            bullets.append(val.strip()[:300])

    # From metrics summary
    ms = card.get("metrics_summary") or {}
    if ms:
        parts = []
        if ms.get("cpu_utilization_percent") is not None:
            parts.append(f"P95 CPU {ms['cpu_utilization_percent']:.1f}%")
        if ms.get("memory_utilization_percent") is not None:
            parts.append(f"memory {ms['memory_utilization_percent']:.1f}%")
        if ms.get("days_idle") is not None:
            parts.append(f"{ms['days_idle']} days idle")
        if parts:
            bullets.append("Metrics: " + ", ".join(parts))

    # From graph_context
    gc = card.get("graph_context") or {}
    if gc:
        parts = []
        if gc.get("blast_radius_pct") is not None:
            parts.append(f"blast radius {gc['blast_radius_pct']:.0f}%")
        if gc.get("services_powered") is not None:
            parts.append(f"{gc['services_powered']} downstream deps")
        if gc.get("is_spof"):
            parts.append("⚠ is a single point of failure")
        if parts:
            bullets.append("Graph context: " + ", ".join(parts))

    # Cost line
    current = float(card.get("current_monthly_cost") or
                    (card.get("cost_breakdown") or {}).get("current_monthly") or 0)
    savings = float(card.get("estimated_savings_monthly") or
                    card.get("total_estimated_savings") or 0)
    env = (card.get("environment") or
           (card.get("resource_identification") or {}).get("environment") or "")
    if current > 0 and savings > 0:
        pct = savings / current * 100
        bullets.append(
            f"Cost: ${current:.2f}/mo current → save ${savings:.2f}/mo ({pct:.0f}%)"
            + (f" [{env}]" if env else "")
        )

    # Validation notes
    vn = card.get("validation_notes") or card.get("notes") or ""
    if vn:
        bullets.append(str(vn)[:200])

    return bullets[:5] if bullets else ["No supporting metrics available."]


def _extract_implementation_notes(card: Dict) -> List[str]:
    """Extract concrete steps from card fields."""
    steps: List[str] = []

    for field in ("implementation_notes", "implementation_steps", "solution"):
        val = card.get(field)
        if isinstance(val, list):
            steps.extend(str(s).strip() for s in val if s)
        elif isinstance(val, str) and val.strip():
            steps.append(val.strip()[:300])

    # From nested recommendations[0]
    recs = card.get("recommendations") or []
    if recs:
        rec0 = recs[0] if isinstance(recs[0], dict) else {}
        for f in ("description", "action"):
            v = rec0.get(f, "")
            if v and v not in steps:
                steps.append(str(v)[:200])

    return steps[:6] if steps else ["Review resource usage and apply change during maintenance window."]


# ─────────────────────────────────────────────────────────────────────────────
# CORE NORMALISER
# ─────────────────────────────────────────────────────────────────────────────

def normalize_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """Augment an existing card with unified schema fields without dropping anything.

    Strategy: start with a full shallow copy of the original card so ALL legacy
    fields the frontend/engine rely on are preserved untouched.  Then derive and
    SET only the unified schema fields that are missing or need canonical values.
    Engine-authoritative fields (resource_id, service, savings, etc.) are never
    overwritten.
    """
    # ── Start from a full copy so legacy fields are preserved ─────────────────
    out = dict(card)

    rid_block = card.get("resource_identification") or {}

    # ── Identity (only fill if missing) ───────────────────────────────────────
    if not out.get("id"):
        out["id"] = card.get("recommendation_id") or str(uuid.uuid4())[:8]

    resource_id = (card.get("resource_id") or rid_block.get("resource_id") or
                   rid_block.get("name") or "unknown")
    if not out.get("resource_id"):
        out["resource_id"] = resource_id
    else:
        resource_id = out["resource_id"]

    service = (card.get("service") or card.get("service_type") or
               rid_block.get("service_type") or "UNKNOWN").upper()
    if not out.get("service"):
        out["service"] = service

    region = card.get("region") or rid_block.get("region") or "us-east-1"
    if not out.get("region"):
        out["region"] = region

    environment = (card.get("environment") or rid_block.get("environment") or "other").lower()
    if not out.get("environment"):
        out["environment"] = environment

    source = card.get("source") or "llm_proposed"
    if not out.get("source"):
        out["source"] = source

    # ── Action — canonical enum (never blank) ─────────────────────────────────
    # Guard: rec0["action"] is sometimes populated with the linked_best_practice
    # description string by _coerce_backend_card_template; discard it if so.
    _raw_top  = str(card.get("action") or "")
    _raw_rec0 = str(((card.get("recommendations") or [{}])[0]).get("action") or "")
    raw_action = _raw_top if not _is_best_practice_description(_raw_top) else ""
    if not raw_action:
        raw_action = _raw_rec0 if not _is_best_practice_description(_raw_rec0) else ""
    canonical_action = _normalise_action(raw_action)
    # If action is not a recognised canonical value, infer from context keywords.
    # This catches LLM outputs like "OPTIMIZE_FAST_FREQUENCY_CAP_007" that slipped
    # past the action-enum rule in the prompt.
    if canonical_action not in _KNOWN_CANONICAL:
        canonical_action = _infer_action_from_context(card)
    # Never let normalizer overwrite LLM cards with engine-owned actions
    _src = card.get("source", "")
    if _src in ("llm_proposed",) and canonical_action in _ENGINE_ONLY_ACTIONS:
        canonical_action = "REVIEW_ARCHITECTURE"
    out["action"] = canonical_action

    # ── Costs — engine values are authoritative; only fill missing ────────────
    cb = card.get("cost_breakdown") or {}
    current_monthly_cost = float(
        card.get("current_monthly_cost") or cb.get("current_monthly") or 0
    )
    out["current_monthly_cost"] = round(current_monthly_cost, 2)

    estimated_savings_monthly = float(
        card.get("estimated_savings_monthly") or
        card.get("total_estimated_savings") or
        cb.get("savings") or 0
    )
    out["estimated_savings_monthly"] = round(estimated_savings_monthly, 2)
    # Keep legacy alias so frontend code still works
    if not out.get("total_estimated_savings"):
        out["total_estimated_savings"] = out["estimated_savings_monthly"]

    # ── Confidence ────────────────────────────────────────────────────────────
    engine_conf_raw = card.get("engine_confidence") or 0
    engine_confidence = (_clamp_confidence(engine_conf_raw, 100.0)
                         if float(engine_conf_raw or 0) > 1
                         else _clamp_confidence(engine_conf_raw, 1.0))
    out["engine_confidence"] = engine_confidence

    llm_conf_raw = card.get("llm_confidence") or 0
    llm_confidence = _clamp_confidence(llm_conf_raw, 1.0)
    if source == "engine_backed":
        engine_conf_01 = engine_confidence if engine_confidence <= 1.0 else engine_confidence / 100.0
        if llm_confidence > engine_conf_01:
            llm_confidence = round(engine_conf_01 * 0.9, 3)
    out["llm_confidence"] = llm_confidence

    # ── Other normalised fields ────────────────────────────────────────────────
    out["effort"] = _normalise_effort(card.get("effort") or card.get("complexity"))
    out["risk_level"] = _normalise_risk(card.get("risk_level"))

    # priority: keep numeric engine value as-is; only normalise string values
    existing_priority = card.get("priority")
    if isinstance(existing_priority, str):
        out["priority"] = _normalise_priority(existing_priority)
    # else leave the numeric priority intact

    # ── Conflict / duplicate markers (only set if not already present) ────────
    if "is_conflicting" not in out:
        out["is_conflicting"] = False
    if "is_duplicate_of" not in out:
        out["is_duplicate_of"] = None

    # ── Summary — add unified field; never overwrite title ────────────────────
    title = card.get("title") or card.get("summary") or ""
    if not title or len(title) < 10:
        title = f"{out['action']} {resource_id} ({service})"
    out["summary"] = title          # unified field
    # keep "title" untouched so frontend card header still works

    # ── linked_best_practice / finops_best_practice on LLM cards ─────────────
    # The frontend header reads these fields; engine cards already have them.
    # Derive a human-readable best-practice line for LLM-proposed cards.
    _BP_LABEL: Dict[str, str] = {
        "DOWNSIZE":             "AWS FinOps - Right-Sizing: CPU or memory underutilised → downsize to save cost",
        "TERMINATE":            "AWS FinOps - Waste Elimination: idle/unused resource → terminate after backup",
        "STOP":                 "AWS FinOps - Scheduling: non-prod resource → stop during off-hours",
        "MOVE_TO_GRAVITON":     "AWS FinOps - Graviton Migration: same perf, 20-40% cheaper on ARM-based instances",
        "CHANGE_STORAGE_CLASS": "AWS FinOps - Storage: gp3 is 20% cheaper than gp2 with 3K baseline IOPS",
        "ADD_LIFECYCLE":        "AWS FinOps - S3 Lifecycle: move infrequent objects to IA/Glacier to cut storage cost",
        "ADD_VPC_ENDPOINT":     "AWS FinOps - Network: VPC endpoints eliminate NAT Gateway data-processing charges",
        "ELIMINATE_CROSS_AZ":   "AWS FinOps - Network: co-locate tightly coupled services to avoid cross-AZ transfer fees",
        "DISABLE_MULTI_AZ":     "AWS FinOps - RDS: disable Multi-AZ on non-prod databases to halve instance cost",
        "ADD_READ_REPLICA":     "AWS FinOps - RDS: offload reads to replica → right-size primary, improve throughput",
        "ADD_CACHE":            "AWS FinOps - Caching: ElastiCache reduces DB load and lowers per-query cost",
        "TUNE_MEMORY":          "AWS FinOps - Lambda: right-size memory allocation — over-provisioning wastes compute budget",
        "PURCHASE_RESERVED":    "AWS FinOps - Reservations: 1-yr Reserved Instances save 30-40% vs On-Demand for steady workloads",
        "REVIEW_ARCHITECTURE":  "AWS FinOps - Architecture Review: structural optimization opportunity identified by AI analysis",
    }
    if not out.get("linked_best_practice"):
        out["linked_best_practice"] = _BP_LABEL.get(out["action"], f"AWS FinOps - {out['action']} optimisation")
    if not out.get("finops_best_practice"):
        out["finops_best_practice"] = out["linked_best_practice"]

    # ── Justification bullets (add if missing) ────────────────────────────────
    if not out.get("justification"):
        out["justification"] = _extract_justification(card)

    # ── Implementation notes (add if missing) ─────────────────────────────────
    if not out.get("implementation_notes"):
        out["implementation_notes"] = _extract_implementation_notes(card)

    return out


# ─────────────────────────────────────────────────────────────────────────────
# DUPLICATE & CONFLICT DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def _are_same_action_family(a1: str, a2: str) -> bool:
    """Return True when two canonical actions are effectively the same optimisation."""
    same_groups = [
        {"DOWNSIZE", "STOP"},
        {"TERMINATE"},
        {"MOVE_TO_GRAVITON"},
        {"CHANGE_STORAGE_CLASS", "ADD_LIFECYCLE"},
        {"ADD_VPC_ENDPOINT", "ELIMINATE_CROSS_AZ"},
    ]
    for g in same_groups:
        if a1 in g and a2 in g:
            return True
    return a1 == a2


def _are_conflicting_actions(a1: str, a2: str) -> bool:
    """Return True when two actions directly contradict each other."""
    conflict_pairs = [
        ("TERMINATE", "DOWNSIZE"),
        ("TERMINATE", "UPSCALE"),
        ("TERMINATE", "MOVE_TO_GRAVITON"),
        ("TERMINATE", "STOP"),
        ("DOWNSIZE", "UPSCALE"),
        ("STOP", "UPSCALE"),
    ]
    pair = (a1, a2)
    rpair = (a2, a1)
    return pair in conflict_pairs or rpair in conflict_pairs


def detect_duplicates_and_conflicts(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Mark is_duplicate_of and is_conflicting on the normalised card list.

    Strategy:
      - Group cards by resource_id.
      - Within each group, if two cards share the same action family → the lower-priority
        one is marked as a duplicate of the first.
      - If two cards have conflicting actions → both get is_conflicting=True and a note
        is added to their summary.
    """
    # Group by resource_id
    by_resource: Dict[str, List[int]] = {}
    for i, card in enumerate(cards):
        rid = card.get("resource_id", "")
        by_resource.setdefault(rid, []).append(i)

    for rid, indices in by_resource.items():
        if len(indices) < 2:
            continue

        group = [(i, cards[i]) for i in indices]

        # Sort: engine_backed first, then by savings desc
        group.sort(key=lambda x: (
            0 if x[1].get("source") == "engine_backed" else 1,
            -float(x[1].get("estimated_savings_monthly") or 0),
        ))

        seen: List[Tuple[int, str]] = []  # (card_index, action)

        for idx, card in group:
            action = card.get("action", "")
            is_dup = False
            is_conf = False

            for prev_idx, prev_action in seen:
                if _are_same_action_family(action, prev_action):
                    # Cross-tier dedup: engine always wins over LLM.
                    cur_src = card.get("source", "")
                    prev_src = cards[prev_idx].get("source", "")
                    cur_is_engine = cur_src in ("engine", "engine_backed")
                    prev_is_engine = prev_src in ("engine", "engine_backed")
                    if cur_is_engine and not prev_is_engine:
                        # Current is engine, prev is LLM — mark LLM as dup
                        cards[prev_idx]["is_duplicate_of"] = card.get("id")
                        logger.debug(
                            "[NORMALISER] Cross-tier dup: LLM %s superseded by engine %s on %s",
                            prev_action, action, rid,
                        )
                        continue  # engine card keeps its spot in seen
                    elif not cur_is_engine and prev_is_engine:
                        # Current is LLM, prev is engine — mark LLM as dup
                        cards[idx]["is_duplicate_of"] = cards[prev_idx].get("id")
                        is_dup = True
                        logger.debug(
                            "[NORMALISER] Cross-tier dup: LLM %s superseded by engine %s on %s",
                            action, prev_action, rid,
                        )
                        break
                    else:
                        # Same tier — lower priority card loses
                        cards[idx]["is_duplicate_of"] = cards[prev_idx].get("id")
                        is_dup = True
                        logger.debug(
                            "[NORMALISER] Same-tier dup: %s action=%s is dup of %s",
                            rid, action, cards[prev_idx].get("id"),
                        )
                        break
                elif _are_conflicting_actions(action, prev_action):
                    # Conflict — mark both
                    cards[idx]["is_conflicting"] = True
                    cards[prev_idx]["is_conflicting"] = True
                    conflict_note = (
                        f"⚠ Conflicting alternative: {prev_action} vs {action} "
                        f"on {rid}. Review both before applying."
                    )
                    if conflict_note not in cards[idx].get("summary", ""):
                        cards[idx]["summary"] = cards[idx].get("summary", "") + " " + conflict_note
                    if conflict_note not in cards[prev_idx].get("summary", ""):
                        cards[prev_idx]["summary"] = cards[prev_idx].get("summary", "") + " " + conflict_note
                    is_conf = True
                    logger.warning(
                        "[NORMALISER] Conflict: %s has both %s and %s",
                        rid, prev_action, action,
                    )

            if not is_dup:
                seen.append((idx, action))

    return cards


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def normalize_recommendations(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Full pipeline: normalise → detect duplicates/conflicts → return unified list."""
    if not cards:
        return []

    normalised = [normalize_card(c) for c in cards]
    normalised = detect_duplicates_and_conflicts(normalised)

    dupes = sum(1 for c in normalised if c.get("is_duplicate_of"))
    conflicts = sum(1 for c in normalised if c.get("is_conflicting"))
    logger.info(
        "[NORMALISER] %d cards → %d normalised, %d duplicates, %d in conflicts",
        len(cards), len(normalised), dupes, conflicts,
    )
    return normalised
