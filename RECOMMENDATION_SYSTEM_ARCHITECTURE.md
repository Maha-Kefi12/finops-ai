# FinOps AI — Two-Tier Recommendation System Architecture

> **Deep-dive reference** for engineers, architects, and FinOps practitioners.
> Last updated after the dual-LLM-call pipeline refactor (narrative + recommendations).

---

## 1. What Does "Two-Tier Architecture" Mean?

Traditional cost-optimization tools are either **purely rule-based** (rigid, predictable, limited to known patterns) or **purely AI-driven** (creative but unreliable, prone to hallucinations, hard to trust in production). Neither approach alone is sufficient for enterprise FinOps.

This system solves the problem by splitting the work into **two complementary tiers that never overlap**:

```
┌──────────────────────────────────────────────────────────────────────┐
│                    TWO-TIER RECOMMENDATION SYSTEM                    │
│                                                                      │
│  ┌─────────────────────────────┐  ┌──────────────────────────────┐  │
│  │     TIER 1: ENGINE ⚙️       │  │    TIER 2: LLM 🤖            │  │
│  │                             │  │                              │  │
│  │  "What is obviously wrong"  │  │  "What you're missing"       │  │
│  │                             │  │                              │  │
│  │  Deterministic rules        │  │  Architectural intelligence  │  │
│  │  Real CloudWatch metrics    │  │  Cross-resource patterns     │  │
│  │  AWS pricing math           │  │  Hidden cost inefficiencies  │  │
│  │  Per-resource right-sizing  │  │  Narrative & justification   │  │
│  │                             │  │                              │  │
│  │  Actions:                   │  │  Actions:                    │  │
│  │  • DOWNSIZE                 │  │  • MOVE_TO_GRAVITON          │  │
│  │  • TERMINATE                │  │  • ADD_CACHE                 │  │
│  │  • STOP                     │  │  • ADD_VPC_ENDPOINT          │  │
│  │  • CHANGE_STORAGE_CLASS     │  │  • DISABLE_MULTI_AZ          │  │
│  │  • ADD_LIFECYCLE            │  │  • ADD_READ_REPLICA          │  │
│  │  • MOVE_TO_GRAVITON         │  │  • ELIMINATE_CROSS_AZ        │  │
│  │                             │  │  • TUNE_MEMORY               │  │
│  │  source: "engine"           │  │  • PURCHASE_RESERVED         │  │
│  │  Badge: ⚙️ Engine           │  │  • CHANGE_STORAGE_CLASS      │  │
│  │                             │  │                              │  │
│  │  Always correct.            │  │  source: "llm_proposed"      │  │
│  │  Always shown.              │  │  Badge: 🤖 AI Proposed       │  │
│  │                             │  │                              │  │
│  │  Trust level: absolute      │  │  Trust level: high           │  │
│  │                             │  │  (quality-gated, not raw)    │  │
│  └─────────────────────────────┘  └──────────────────────────────┘  │
│                                                                      │
│  Key principle: ZERO OVERLAP between tiers.                          │
│  The engine owns right-sizing. The LLM owns architectural insights.  │
│  They complement each other — they never compete.                    │
└──────────────────────────────────────────────────────────────────────┘
```

### Why Two Tiers Instead of One?

| Approach | Problem |
|----------|---------|
| Engine only | Misses caching gaps, VPC endpoint opportunities, Graviton migrations on well-utilized resources, reservation signals, cross-AZ waste — anything that requires *reasoning across resources* |
| LLM only | Hallucinates savings numbers, invents resources, duplicates obvious right-sizing the engine already handles better, generates unreliable action plans |
| **Two-tier** | Engine handles the **predictable** (per-resource, metric-driven). LLM handles the **unpredictable** (cross-resource, architectural, narrative-rich). Each tier is best at what it does. |

The mental model: **the engine is the accountant, the LLM is the architect**. The accountant finds the line items that are too high. The architect finds the structural design flaws that cause waste.

---

## 2. Tier 1: The Deterministic Engine

### What It Does

The engine scans every resource in the architecture graph against a library of **pattern detectors** — deterministic rules with explicit AWS thresholds. It finds:

- **Idle/underutilized resources** → TERMINATE or DOWNSIZE
- **Wrong instance family** → MOVE_TO_GRAVITON
- **Oversized storage** → CHANGE_STORAGE_CLASS
- **Missing lifecycle policies** → ADD_LIFECYCLE

### How It Works

```
Architecture Graph (JSON)
    │
    ▼
┌─────────────────────────────────┐
│  scanner.py: scan_architecture  │  Runs all detector patterns
│                                 │  against every service node
│  For each service:              │
│    for pattern in ALL_PATTERNS: │
│      if pattern.matches(svc):   │
│        emit PatternMatch        │
└──────────┬──────────────────────┘
           │ List[PatternMatch]
           ▼
┌─────────────────────────────────┐
│  enricher.py: enrich_matches    │  Adds graph-aware context:
│                                 │  • Dependency count
│  For each match:                │  • Blast radius %
│    add graph_metrics            │  • Single Point of Failure?
│    add dependency_analysis      │  • Cross-AZ data transfer cost
│    add redundancy_check         │  • Traffic (QPS, latency, errors)
│    add traffic_metrics          │  • Cascading failure risk
└──────────┬──────────────────────┘
           │ List[EnrichedMatch]
           ▼
┌─────────────────────────────────┐
│  _engine_to_cards()             │  Converts to frontend-ready
│                                 │  card format with:
│  For each enriched match:       │  • resource_identification
│    build card with:             │  • cost_breakdown (with line_items)
│    - graph_context              │  • graph_context (blast radius, deps)
│    - cost_breakdown             │  • recommendations[] (impl steps)
│    - implementation_steps       │  • linked_best_practice
│    - risk_mitigation            │  • source: "engine"
│    - why_it_matters narrative   │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  LLM Call #1: Narrative Pass    │  Qwen polishes engine cards:
│  _narrate_engine_cards()        │  • why_it_matters (2-3 sentences)
│                                 │  • full_analysis (4-6 sentences)
│  Sends compact payload (max 4   │  • graph_context.narrative
│  cards) to Qwen 2.5 7B.        │
│  Numbers/IDs/actions/savings    │  Numbers are NEVER changed —
│  are NEVER modified.            │  only text fields are enriched.
│                                 │
│  Graceful fallback: if LLM      │  Template narratives preserved
│  times out or fails, original   │  if LLM is unavailable.
│  template text is kept.         │
└─────────────────────────────────┘
```

### Key Files

| File | Role |
|------|------|
| `src/recommendation_engine/scanner.py` | Runs all detector patterns against architecture graph |
| `src/recommendation_engine/enricher.py` | Adds graph metrics, dependencies, blast radius, SPOF detection |
| `src/llm/client.py` → `_engine_to_cards()` | Converts enriched matches to frontend-compatible card dicts |

### Engine Card Structure

Every engine card has this shape (the frontend reads these exact field names):

```python
{
    "source": "engine",                          # Always "engine"
    "title": "AWS FinOps - Graviton Migration...",
    "service_type": "EC2",
    "total_estimated_savings": 156.80,
    "priority": "HIGH",
    "severity": "high",
    "risk_level": "LOW",
    "pattern_id": "graviton_migration",
    "linked_best_practice": "AWS FinOps - Graviton: ...",

    "resource_identification": {
        "resource_id": "cart-ec2-001",           # Exact graph node ID
        "service_type": "EC2",
        "region": "us-east-1",
        "environment": "production",
        "current_instance_type": "m5.xlarge",
        "recommended_instance_type": "m6g.xlarge",
        "current_config": "Instance Type: m5.xlarge | Service: EC2 | ..."
    },

    "cost_breakdown": {
        "current_monthly": 392.00,
        "projected_monthly": 235.20,
        "savings_percentage": 40.0,
        "annual_impact": 1881.60,
        "line_items": [...]
    },

    "graph_context": {
        "blast_radius_pct": 23.5,
        "dependency_count": 4,
        "dependent_services": ["checkout-svc", "inventory-svc"],
        "is_spof": false,
        "cascading_failure_risk": "medium",
        "narrative": "This EC2 instance powers 4 downstream services..."
    },

    "recommendations": [{
        "title": "Migrate to Graviton (m6g.xlarge)",
        "implementation_steps": ["1. Review current EC2...", "2. ..."],
        "performance_impact": "Savings: $156.80/mo (40% reduction)...",
        "risk_mitigation": "Risk Level: LOW. Always test in staging first",
        "estimated_monthly_savings": 156.80
    }]
}
```

### Engine Detection Thresholds

```python
# src/recommendation_engine/validator.py
VALIDATION_THRESHOLDS = {
    "ec2_idle_cpu_p95": 5.0,           # P95 CPU < 5% → idle
    "ec2_idle_network_mbps": 1.0,      # Network < 1 Mbps → idle
    "ec2_idle_min_days": 14,           # Must be idle 14+ days

    "rds_oversize_cpu_p95": 40.0,      # P95 CPU < 40% → oversize
    "rds_oversize_memory_pct": 30.0,   # Freeable memory > 30% → oversize
    "rds_oversize_min_days": 30,       # 30+ days observation

    "cache_oversize_memory_pct": 50.0, # Memory util < 50%
    "cache_oversize_evictions": 10,    # Evictions < 10/day

    "s3_lifecycle_min_age_days": 90,   # Objects > 90 days old
    "s3_lifecycle_min_size_gb": 100,   # At least 100 GB

    "min_monthly_savings": 50.0,       # Minimum $50/mo to report
}
```

---

## 3. Tier 2: The LLM Architectural Intelligence Layer

### What It Does

The LLM reads the **full architecture context** — every service, every metric, every dependency, every cost line — and finds **architectural deficiencies** that the engine structurally cannot detect:

- **Caching gaps**: "Your RDS receives 80% read traffic but has no ElastiCache layer"
- **Network waste**: "3 services call S3 through a NAT gateway — add a VPC endpoint"
- **Wrong Multi-AZ**: "Dev RDS has Multi-AZ enabled — disable it for non-prod"
- **Graviton opportunities**: "Well-utilized x86 instances that could migrate to ARM"
- **Reservation signals**: "5 identical m5.xlarge running 24/7 — buy Reserved Instances"
- **Cross-AZ waste**: "Services in us-east-1a talking to services in us-east-1b"

These are findings that require **reasoning across multiple resources** — something a per-resource rule engine cannot do.

### How It Works

```
Engine cards (already generated + AI-narrated)
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  STAGE 1: Build LLM Context                          │
│                                                      │
│  8-section context package:                          │
│  ┌─ SERVICE INVENTORY ──────────────────────────┐    │
│  │ All resources with IDs, types, costs, metrics │    │
│  └──────────────────────────────────────────────┘    │
│  ┌─ CLOUDWATCH METRICS ─────────────────────────┐    │
│  │ CPU, memory, IOPS, latency per resource       │    │
│  └──────────────────────────────────────────────┘    │
│  ┌─ GRAPH CONTEXT ──────────────────────────────┐    │
│  │ Dependencies, blast radius, SPOF analysis     │    │
│  └──────────────────────────────────────────────┘    │
│  ┌─ AWS FINOPS BEST PRACTICES ──────────────────┐    │
│  │ Curated rules from AWS Well-Architected       │    │
│  └──────────────────────────────────────────────┘    │
│  ┌─ ENGINE_FACTS (grounding) ───────────────────┐    │
│  │ What the engine already found (DO NOT repeat)  │    │
│  │ ALREADY_HANDLED: [(rid, action), ...]          │    │
│  └──────────────────────────────────────────────┘    │
└──────────┬───────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│  STAGE 2: LLM Call #2 (Qwen 2.5 7B via Ollama)      │
│                                                      │
│  System prompt enforces:                             │
│  • FORBIDDEN actions: DOWNSIZE, TERMINATE, STOP      │
│  • ALLOWED actions: MOVE_TO_GRAVITON, ADD_CACHE,     │
│    ADD_VPC_ENDPOINT, DISABLE_MULTI_AZ, etc.          │
│  • Must use exact resource_id from SERVICE INVENTORY │
│  • Must link to AWS FINOPS BEST PRACTICES            │
│  • Must include cost math                            │
│                                                      │
│  Output: JSON array of recommendation cards          │
└──────────┬───────────────────────────────────────────┘
           │ Raw LLM JSON
           ▼
┌──────────────────────────────────────────────────────┐
│  STAGE 2b: Quality Gates                             │
│  _apply_deterministic_quality_gates()                │
│                                                      │
│  1. Fuzzy resource ID matching                       │
│     LLM writes "creative-store-003" →                │
│     matched to "creative-store-elasticache-003"      │
│                                                      │
│  2. Action whitelist enforcement                     │
│     Only MOVE_TO_GRAVITON, ADD_CACHE, etc.           │
│                                                      │
│  3. Action remapping from card content               │
│     LLM writes "DOWNSIZE" but card text says         │
│     "migrate to Graviton" → remapped to              │
│     MOVE_TO_GRAVITON                                 │
│                                                      │
│  4. Engine duplicate rejection                       │
│     Same (resource_id, action) already in engine     │
│     → rejected                                       │
│                                                      │
│  5. Savings math validation (30% tolerance)          │
│  6. Generic title rewriting (warn, don't reject)     │
│  7. Minimum savings threshold ($10/mo)               │
│  8. Unknown actions → REVIEW_ARCHITECTURE fallback   │
└──────────┬───────────────────────────────────────────┘
           │ Cleaned LLM cards
           ▼
┌──────────────────────────────────────────────────────┐
│  STAGE 3: Mark as LLM Insights                       │
│                                                      │
│  For each surviving LLM card:                        │
│    card["source"] = "llm_proposed"                   │
│    card["validation_status"] = "llm_insight"         │
│    card["is_ai_insight"] = True                      │
│                                                      │
│  LLM cards BYPASS the engine validator entirely.     │
│  The validator only knows right-sizing patterns —    │
│  it would reject novel architectural insights.       │
└──────────────────────────────────────────────────────┘
```

### Why the LLM Bypasses the Engine Validator

The engine validator (`src/recommendation_engine/validator.py`) was built to validate **right-sizing and idle detection** — it checks CPU thresholds, memory thresholds, savings math. It knows how to validate "is this EC2 really idle?" but it has **no concept** of:

- "Should this architecture have a caching layer?"
- "Is this NAT gateway unnecessary because a VPC endpoint would work?"
- "Should dev environments disable Multi-AZ?"

If LLM cards went through the validator, they would be rejected with errors like *"Resource has high CPU — not a rightsize candidate"* — which is irrelevant when the LLM is proposing a VPC endpoint addition, not a rightsize.

The quality gates in Stage 2b replace the validator with checks that are **appropriate for architectural insights**: resource existence, action validity, engine overlap prevention, and savings sanity.

### LLM Allowed vs Forbidden Actions

```
FORBIDDEN (engine owns these):        ALLOWED (LLM's domain):
─────────────────────────────          ──────────────────────────
DOWNSIZE                               MOVE_TO_GRAVITON
TERMINATE                              CHANGE_STORAGE_CLASS
STOP                                   ADD_LIFECYCLE
DECOMMISSION                           ADD_CACHE
DELETE                                 ADD_VPC_ENDPOINT
RETIRE                                 DISABLE_MULTI_AZ
                                       ADD_READ_REPLICA
                                       ELIMINATE_CROSS_AZ
                                       TUNE_MEMORY
                                       PURCHASE_RESERVED
```

If the LLM generates DOWNSIZE/TERMINATE (small models sometimes ignore prompt constraints), the quality gate:
1. Checks the card's **text content** (title, summary, linked_best_practice)
2. Infers the **actual architectural action** from keywords
3. Remaps the action (e.g., "DOWNSIZE to m6g.large" → MOVE_TO_GRAVITON)
4. If action is engine-only (DOWNSIZE/TERMINATE/STOP) and can't be remapped → rejected
5. If action is unknown but not engine-only → kept as `REVIEW_ARCHITECTURE`

The normalizer also guards against re-inference: if an LLM card has `REVIEW_ARCHITECTURE`, the normalizer will **not** override it with an engine-owned action (DOWNSIZE/TERMINATE/STOP) even if context keywords match.

### Key Files

| File | Role |
|------|------|
| `src/llm/prompts.py` | System + user prompt with forbidden/allowed actions |
| `src/llm/client.py` → `generate_recommendations()` | Full pipeline orchestrator |
| `src/llm/client.py` → `_apply_deterministic_quality_gates()` | Fuzzy matching, action remapping, dedup |
| `src/llm/_llm_card_aligner.py` | Fills engine-format fields on LLM cards for frontend parity |
| `src/llm/client.py` → `_enrich_cards()` | Adds graph context, metrics, dependencies to LLM cards |

---

## 4. The Full Pipeline (6 Stages)

```
STAGE 0a: Engine Scan
    scan_architecture() → enrich_matches() → _engine_to_cards()
    Result: engine_cards[] with source="engine"
    │
STAGE 0b: LLM Call #1 — Narrative Pass
    _narrate_engine_cards(engine_cards)
    Qwen writes rich why_it_matters, full_analysis, narrative
    Max 4 cards, 3000 tokens, compact payload
    Graceful fallback: template text kept on failure
    Result: engine_cards[] with AI-written narratives
    │
STAGE 1: Build LLM Context
    8 sections: inventory, metrics, graph, pricing, best practices
    + ENGINE_FACTS grounding (what engine already found)
    + ALREADY_HANDLED list (resource+action pairs to skip)
    │
STAGE 2: LLM Call #2 + Quality Gates
    call_llm() → parse JSON → fuzzy match resource IDs
    → remap actions → reject engine duplicates → validate math
    → unknown actions → REVIEW_ARCHITECTURE fallback
    Result: llm_cards[] (cleaned, quality-gated)
    │
STAGE 3: Mark LLM Cards
    source="llm_proposed", validation_status="llm_insight"
    LLM cards bypass engine validator entirely
    │
STAGE 4: Merge
    _merge_engine_and_llm_cards(engine_cards, llm_cards)
    → _dedupe_and_resolve_conflicts()
    → Sort by savings (highest first)
    Result: merged[] with both engine + LLM cards
    │
STAGE 5: Normalize
    normalize_recommendations(merged)
    → normalize_card() per card (canonical action, costs, schema)
    → detect_duplicates_and_conflicts() (cross-tier aware)
    Result: final cards[] ready for API response
```

### Stage 4: Merge Strategy

```python
# src/llm/client.py → _merge_engine_and_llm_cards()

# 1. Engine cards ALWAYS included (deterministic baseline)
merged = [coerce(c) for c in engine_cards]

# 2. ALL quality-gated LLM cards appended
for llm_card in llm_cards:
    merged.append(coerce(llm_card))

# 3. Smart dedup: same resource + same canonical action + same savings
#    Only removes TRUE duplicates (identical cards), never cross-tier
merged = _dedupe_and_resolve_conflicts(merged)

# 4. Sort by savings descending
merged.sort(key=lambda c: savings(c), reverse=True)
```

### Stage 5: Normalizer (Cross-Tier Aware)

The normalizer (`src/llm/normalizer.py`) converts all cards to a unified flat schema and detects duplicates/conflicts. **Critical rule**: it never marks an LLM card as a duplicate of an engine card.

```python
# src/llm/normalizer.py → detect_duplicates_and_conflicts()

for prev_idx, prev_action in seen:
    if same_action_family(action, prev_action):
        # CRITICAL: Only dedup WITHIN same source tier
        cur_is_engine = card["source"] in ("engine", "engine_backed")
        prev_is_engine = cards[prev_idx]["source"] in ("engine", "engine_backed")
        if cur_is_engine != prev_is_engine:
            continue  # Different tiers — keep both
        # Same tier → mark as duplicate
        cards[idx]["is_duplicate_of"] = cards[prev_idx]["id"]
```

This ensures an engine MOVE_TO_GRAVITON card and an LLM MOVE_TO_GRAVITON card on the same resource **both survive** — they represent different perspectives (engine found it through CPU metrics, LLM found it through architectural analysis).

---

## 5. Frontend Rendering

### Badge System

The frontend reads `card.source` and `card.validation_status` to display the appropriate badge:

```
┌──────────────────────────────────────────────────────┐
│  source="engine"           →  ⚙️ Engine              │
│  source="engine_backed"    →  🤖✓ AI Validated       │
│  source="llm_proposed"     →  🤖 AI Proposed         │
│  validation_status="rejected" → 💡✗ AI Insight       │
│  validation_status="conflict" → ⚠️ Conflict          │
└──────────────────────────────────────────────────────┘
```

**Component**: `frontend/src/components/StyledRecommendationCard.jsx` → `SourceBadge`

```jsx
function SourceBadge({ source, validationStatus }) {
  const isEngineBacked = source === 'engine' || source === 'engine_backed';

  if (isEngineBacked) {
    if (validationStatus === 'validated') return '🤖✓ AI Validated';
    return '⚙️ Engine';
  } else {
    if (validationStatus === 'rejected') return '💡✗ AI Insight';
    if (validationStatus === 'conflict') return '⚠️ Conflict';
    return '🤖 AI Proposed';  // ← LLM architectural insights land here
  }
}
```

### Card Rendering Flow

```
API Response: { recommendations: [...] }
    │
    ▼
AnalysisPage.jsx → recResult.recommendations
    │
    ▼
displayRecommendations = filter out summary cards
    │
    ▼
RecommendationCarousel (3 cards per page, paginated)
    │
    ▼
StyledRecommendationCard (per card)
    ├── SourceBadge (⚙️ Engine or 🤖 AI Proposed)
    ├── Title + Action
    ├── Savings amount
    ├── Priority / Risk badges
    └── "View Details" → expands to full card
```

All cards render identically in layout — the only visual distinction is the badge. Engine cards get **⚙️ Engine**, LLM cards get **🤖 AI Proposed**. This gives users a clear signal of provenance while treating both tiers as first-class recommendations.

---

## 6. Quality Gate Deep Dive

The quality gate (`_apply_deterministic_quality_gates`) is the most critical function in the LLM pipeline. It ensures LLM output is trustworthy without using the engine validator.

### Gate 1: Fuzzy Resource ID Matching

Small LLMs often write approximate resource IDs. The gate uses 3-stage matching:

```
1. Exact match:   "cart-ec2-001" → "cart-ec2-001"           ✓
2. Substring:     "creative-store-003" → "creative-store-elasticache-003"  ✓
3. Token overlap: "fast-reports" → "fast-reports-005"        ✓ (1+ token overlap)
```

If matched, the card's `resource_id` is corrected to the real ID.

### Gate 2: Action Whitelist + Remapping

```python
_LLM_ALLOWED_ACTIONS = {
    "MOVE_TO_GRAVITON", "CHANGE_STORAGE_CLASS", "ADD_LIFECYCLE",
    "ADD_CACHE", "ADD_VPC_ENDPOINT", "DISABLE_MULTI_AZ",
    "ADD_READ_REPLICA", "ELIMINATE_CROSS_AZ", "TUNE_MEMORY",
    "PURCHASE_RESERVED",
}

# If action not in whitelist, scan card text for keywords:
_REMAP_KEYWORDS = [
    (["graviton", "arm64", "m6g", "m7g", "c6g"], "MOVE_TO_GRAVITON"),
    (["cache", "elasticache", "redis", "memcached"], "ADD_CACHE"),
    (["vpc endpoint", "nat gateway", "privatelink"], "ADD_VPC_ENDPOINT"),
    (["multi-az", "single-az", "standby"],          "DISABLE_MULTI_AZ"),
    (["read replica", "read-replica"],               "ADD_READ_REPLICA"),
    (["reserved", "savings plan", "commitment"],     "PURCHASE_RESERVED"),
    # ... more mappings
]
```

### Gate 3: Engine Duplicate Rejection

Builds a set of `(resource_id, canonical_action)` pairs from engine cards. Rejects any LLM card that duplicates an exact engine pair.

```python
# Engine has MOVE_TO_GRAVITON for staging-creative-store-014
# LLM also generates MOVE_TO_GRAVITON for staging-creative-store-014
# → Rejected as engine_duplicate

# Engine has DOWNSIZE for fast-reports-005
# LLM generates MOVE_TO_GRAVITON for fast-reports-005
# → KEPT (different action — LLM adds value beyond what engine found)
```

### Gate 4: Savings Math Validation

- `savings > 0`
- `savings < current_monthly_cost` (can't save more than you spend)
- `savings >= $10/mo` (minimum threshold — relaxed to let more LLM insights through)

---

## 7. Data Flow Diagram (Complete)

```
                    ┌─────────────────────┐
                    │  Architecture Graph  │
                    │  (Neo4j or JSON)     │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  GraphAnalyzer       │
                    │  (deep analysis)     │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
     ┌────────────┐   ┌──────────────┐  ┌────────────┐
     │  Engine     │   │  Context     │  │  Business   │
     │  Scanner    │   │  Assembler   │  │  Graph RAG  │
     │  + Enricher │   │  (8 sections)│  │  Translator │
     └──────┬─────┘   └──────┬───────┘  └──────┬─────┘
            │                │                  │
            ▼                ▼                  ▼
     ┌────────────┐   ┌──────────────────────────────┐
     │ engine     │   │  LLM Prompt                   │
     │ _cards[]   │──▶│  (system + user + engine_ctx) │
     │ source:    │   └──────────┬───────────────────┘
     │ "engine"   │              │
     └──────┬─────┘              ▼
            │           ┌─────────────────┐
            │           │  Qwen 2.5 7B    │
            │           │  (via Ollama)    │
            │           └────────┬────────┘
            │                    │ raw JSON
            │                    ▼
            │           ┌─────────────────┐
            │           │  Quality Gates  │
            │           │  • Fuzzy ID     │
            │           │  • Action remap │
            │           │  • Engine dedup │
            │           │  • Savings math │
            │           └────────┬────────┘
            │                    │ llm_cards[]
            │                    │ source: "llm_proposed"
            │                    │
            ▼                    ▼
     ┌───────────────────────────────────┐
     │  Merge + Dedup + Conflict Resolve │
     │  _merge_engine_and_llm_cards()    │
     └──────────────┬────────────────────┘
                    │
                    ▼
     ┌───────────────────────────────────┐
     │  Normalizer                       │
     │  normalize_recommendations()      │
     │  • Canonical action mapping       │
     │  • Cross-tier-aware dedup         │
     │  • Unified flat schema            │
     └──────────────┬────────────────────┘
                    │
                    ▼
     ┌───────────────────────────────────┐
     │  API Response                     │
     │  POST /api/analyze/recommendations│
     │                                   │
     │  { recommendations: [             │
     │      { source: "engine", ... },   │
     │      { source: "llm_proposed" },  │
     │    ],                             │
     │    total_estimated_savings: ...    │
     │  }                                │
     └──────────────┬────────────────────┘
                    │
                    ▼
     ┌───────────────────────────────────┐
     │  Frontend                         │
     │  RecommendationCarousel           │
     │                                   │
     │  ⚙️ Engine    │ 🤖 AI Proposed    │
     │  DOWNSIZE     │ ADD_VPC_ENDPOINT  │
     │  $156/mo      │ $89/mo           │
     │  ─────────────┼──────────────────│
     │  ⚙️ Engine    │ 🤖 AI Proposed    │
     │  TERMINATE    │ MOVE_TO_GRAVITON │
     │  $392/mo      │ $67/mo           │
     └───────────────────────────────────┘
```

---

## 8. Example Output

Real pipeline output for a 23-service Adtech architecture:

```
=== FINAL: 14 cards ===
Sources: {'engine': 9, 'llm_proposed': 5}

  ENGINE ⚙️                              LLM 🤖 AI Proposed
  ──────────────────────                  ──────────────────────────
  DOWNSIZE creative-store-021             MOVE_TO_GRAVITON reports-016
  TERMINATE reports-ec2-001               MOVE_TO_GRAVITON pacing-006
  TERMINATE secondary-reports-016         MOVE_TO_GRAVITON creative-store-021
  TERMINATE public-pacing-006             CHANGE_STORAGE_CLASS creative-store-021
  DOWNSIZE fast-reports-005               MOVE_TO_GRAVITON fast-reports-005
  DOWNSIZE fast-frequency-cap-007
  MOVE_TO_GRAVITON staging-store-014
  CHANGE_STORAGE_CLASS creative-store-021
  ADD_LIFECYCLE main-bidder-011
```

Notice: the engine found creative-store-021 needs DOWNSIZE. The LLM independently found the *same* resource also needs MOVE_TO_GRAVITON and CHANGE_STORAGE_CLASS — different actions that represent different optimization opportunities. Both survive because cross-tier dedup is disabled.

---

## 9. Configuration

### LLM Backend

```bash
# Environment variables
OLLAMA_URL=http://localhost:11434        # Ollama endpoint
FINOPS_MODEL=qwen2.5:7b                 # Primary model
USE_GEMINI=false                         # Set true + GEMINI_API_KEY for Gemini Flash
```

### Quality Gate Thresholds

```python
# src/llm/client.py → _apply_deterministic_quality_gates()
min_monthly_savings = 10.0               # Minimum savings to keep LLM card (relaxed)
```

### Engine Thresholds

```python
# src/recommendation_engine/validator.py
VALIDATION_THRESHOLDS = { ... }          # See Tier 1 section above
```

---

## 10. API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/analyze/recommendations` | Run full pipeline (engine + LLM). Returns both tiers. |
| `GET` | `/api/analyze/recommendations/last` | Load last stored result (no re-run). |
| `GET` | `/api/analyze/recommendations/history` | Historical snapshots. |

### Response Shape

```json
{
  "recommendations": [
    {
      "source": "engine",
      "action": "DOWNSIZE",
      "resource_id": "creative-store-021",
      "total_estimated_savings": 156.80,
      "engine_confidence": 0.92,
      "resource_identification": { ... },
      "cost_breakdown": { ... },
      "graph_context": { ... },
      "recommendations": [{ "implementation_steps": [...] }]
    },
    {
      "source": "llm_proposed",
      "action": "ADD_VPC_ENDPOINT",
      "resource_id": "cart-ec2-001",
      "validation_status": "llm_insight",
      "is_ai_insight": true,
      "total_estimated_savings": 89.00,
      "llm_confidence": 0.7,
      "resource_identification": { ... },
      "cost_breakdown": { ... },
      "recommendations": [{ "implementation_steps": [...] }]
    }
  ],
  "total_estimated_savings": 2345.67,
  "llm_used": true,
  "generation_time_ms": 52000
}
```

---

## 11. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **LLM bypasses engine validator** | Validator only knows right-sizing. Would reject all novel architectural insights. |
| **Banned actions (DOWNSIZE/TERMINATE/STOP)** | Prevents LLM from duplicating what engine does better deterministically. |
| **Fuzzy resource ID matching** | Small models (7B) often write approximate IDs. 3-stage matching recovers them. |
| **Action remapping from card text** | Small models ignore enum constraints. Content-based inference is more reliable. |
| **Cross-tier dedup disabled** | Engine and LLM represent different analytical perspectives — both should survive. |
| **Dual LLM calls** | Call #1 narrates engine cards (text only). Call #2 generates novel LLM recommendations. Separated to limit token budgets and allow graceful fallback. |
| **REVIEW_ARCHITECTURE fallback** | Unknown but non-engine-owned actions are kept as REVIEW_ARCHITECTURE instead of rejected. |
| **Normalizer guards engine actions** | LLM cards are never re-inferred to DOWNSIZE/TERMINATE/STOP by the normalizer, even if context keywords match. |
| **Normalizer default changed from DOWNSIZE** | Old default silently converted unknown LLM actions to DOWNSIZE, which then got rejected. |
| **Engine facts injected into LLM prompt** | Grounds the LLM with what's already found, reducing redundant output. |

---

## 12. File Reference

| File | Purpose |
|------|---------|
| `src/recommendation_engine/scanner.py` | Deterministic pattern scanning |
| `src/recommendation_engine/enricher.py` | Graph-aware enrichment (deps, blast radius) |
| `src/recommendation_engine/validator.py` | Engine validation thresholds (used for engine cards, NOT LLM) |
| `src/llm/client.py` | Full pipeline orchestrator, quality gates, merge logic |
| `src/llm/prompts.py` | System + user prompts with forbidden/allowed actions + narrative prompts |
| `src/llm/normalizer.py` | Unified schema normalization, cross-tier-aware dedup |
| `src/llm/_llm_card_aligner.py` | Fills engine-format fields on LLM cards |
| `src/llm/recommendation_card_schema.py` | Dataclass schema definitions, enums |
| `src/api/handlers/analyze.py` | API endpoint handler |
| `frontend/src/components/StyledRecommendationCard.jsx` | Card rendering + SourceBadge |
| `frontend/src/pages/AnalysisPage.jsx` | Main analysis page, carousel, expanded details |
