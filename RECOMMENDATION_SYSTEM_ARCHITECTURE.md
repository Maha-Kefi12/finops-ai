# FinOps AI Recommendation System Architecture

## Executive Summary

This FinOps recommendation system uses a **two-tier architecture** to combine deterministic accuracy with LLM creativity:

1. **Engine-backed recommendations**: Deterministic rules using real metrics and AWS pricing. Always correct.
2. **LLM-proposed recommendations**: AI-generated ideas that must be validated by the engine before being shown as "real" recommendations.

This design ensures the LLM can propose new optimization patterns while maintaining strict accuracy through engine validation.

---

## Two-Tier Architecture

### Tier 1: Engine-Backed Recommendations (Deterministic)

**Source**: `src/recommendation_engine/`

**Components**:
- `detectors.py`: Pattern-based detectors with explicit AWS thresholds
- `scanner.py`: Scans architecture graph against all detector patterns
- `enricher.py`: Enriches matches with graph RAG metrics
- `validator.py`: Validates LLM-proposed recommendations

**Characteristics**:
- ✅ Uses explicit, AWS-style thresholds (constants/config)
- ✅ Real metrics from CloudWatch/Cost Explorer
- ✅ Deterministic savings calculations with AWS pricing
- ✅ Computes action, estimated_savings, engine_confidence
- ✅ Marks environment and blast radius
- ✅ **Always authoritative** - LLM cannot change these

**Example Thresholds** (from `validator.py`):
```python
VALIDATION_THRESHOLDS = {
    "ec2_idle_cpu_p95": 5.0,           # P95 CPU < 5%
    "ec2_idle_network_mbps": 1.0,      # Network I/O < 1 Mbps
    "ec2_idle_min_days": 14,           # 14+ days idle
    
    "rds_oversize_cpu_p95": 40.0,      # P95 CPU < 40%
    "rds_oversize_memory_pct": 30.0,   # P95 freeable memory > 30%
    "rds_oversize_min_days": 30,       # 30+ days observation
    
    "cache_oversize_memory_pct": 50.0, # Memory < 50%
    "cache_oversize_evictions": 10,    # Low evictions < 10/day
    
    "min_monthly_savings": 50.0,       # Must save at least $50/month
}
```

### Tier 2: LLM-Proposed Recommendations (Creative)

**Source**: `src/llm/client.py`, `src/llm/prompts.py`

**Characteristics**:
- 🧠 LLM can propose new optimization ideas
- 🔍 Must go through validation step (re-runs metrics/rules)
- ⚖️ Only promoted to `engine_backed` if validation passes
- 💡 Otherwise kept as "idea only" (shown in separate "Insights" tab)

**Example LLM-Proposed Ideas**:
- "Consider adding a VPC endpoint for S3 to reduce NAT costs"
- "Many dev RDS instances run 24/7; consider adding stop-schedules"
- "Consistent pattern of oversized t3/t4g in staging; propose a 'staging downsizing campaign'"

**Validation Flow**:
```
LLM generates idea
    ↓
validator.py runs metrics queries
    ↓
Checks against engine rules
    ↓
Validates savings with real pricing
    ↓
IF PASS → Promote to engine_backed
IF FAIL → Keep as llm_proposed (rejected/low confidence)
```

---

## Data Schema

### Recommendation Card Schema

**File**: `src/llm/recommendation_card_schema.py`

Every recommendation has these fields:

```python
@dataclass
class FullRecommendationCard:
    # ── Core identification ──
    title: str
    service_type: str
    total_estimated_savings: float
    priority: str  # HIGH, MEDIUM, LOW
    severity: str  # high, medium, low
    category: str  # right-sizing, waste-elimination, etc.
    
    # ── TWO-TIER SOURCE TRACKING (Critical) ──
    source: RecommendationSource  # engine_backed OR llm_proposed
    action: RecommendationAction  # Must be from known enum
    
    # ── Confidence tracking ──
    engine_confidence: Optional[float] = None  # 0-1.0 for engine
    llm_confidence: float = 0.5  # 0-1.0 for LLM
    
    # ── Validation state (for LLM-proposed) ──
    validation_status: ValidationStatus  # PENDING, VALIDATED, REJECTED, CONFLICT
    validation_notes: Optional[str] = None
    
    # ── Conflict resolution ──
    is_downgraded_due_to_conflict: bool = False
    conflicting_rec_ids: List[str] = []
    alternative_to_engine_rec_id: Optional[str] = None
    
    # ── Detailed sections ──
    resource_identification: ResourceIdentification
    cost_breakdown: CostBreakdown
    graph_context: GraphContext
    metrics_summary: MetricsSummary
    recommendations: List[Recommendation]
```

### Source Enum

```python
class RecommendationSource(str, Enum):
    ENGINE_BACKED = "engine_backed"  # Real metrics + rules
    LLM_PROPOSED = "llm_proposed"    # LLM idea, needs validation
```

### Action Enum (Strict)

```python
class RecommendationAction(str, Enum):
    # EC2
    RIGHTSIZE_EC2 = "rightsize_ec2"
    TERMINATE_EC2 = "terminate_ec2"
    MIGRATE_EC2_GRAVITON = "migrate_ec2_graviton"
    SCHEDULE_EC2_STOP = "schedule_ec2_stop"
    
    # RDS
    RIGHTSIZE_RDS = "rightsize_rds"
    DISABLE_MULTI_AZ = "disable_multi_az"
    MIGRATE_RDS_GP2_TO_GP3 = "migrate_rds_gp2_to_gp3"
    ADD_READ_REPLICA = "add_read_replica"
    
    # Storage
    S3_ADD_LIFECYCLE = "s3_add_lifecycle"
    EBS_MIGRATE_GP2_TO_GP3 = "ebs_migrate_gp2_to_gp3"
    
    # Network
    ADD_VPC_ENDPOINT = "add_vpc_endpoint"
    ELIMINATE_CROSS_AZ = "eliminate_cross_az"
    REPLACE_NAT_WITH_ENDPOINTS = "replace_nat_with_endpoints"
    
    # ... (see recommendation_card_schema.py for full list)
```

**LLM cannot invent new actions** - must use from this enum.

### Validation Status

```python
class ValidationStatus(str, Enum):
    PENDING = "pending"      # Waiting for engine validation
    VALIDATED = "validated"  # Engine confirmed, promoted to backed
    REJECTED = "rejected"    # Engine rejected, keep as idea only
    CONFLICT = "conflict"    # Conflicts with engine rec, downgraded
```

---

## Recommendation Generation Pipeline

### Full Pipeline Flow

```
1. Architecture Graph Input
    ↓
2. Engine Scanner (detectors.py)
    → Runs ALL detector patterns
    → Produces PatternMatch objects
    ↓
3. Engine Enricher (enricher.py)
    → Adds graph RAG metrics
    → Dependency analysis, blast radius, SPOF detection
    ↓
4. Engine Cards (engine-backed)
    → source: "engine_backed"
    → engine_confidence: 0.85-0.95
    → estimated_savings: from real pricing
    ↓
5. LLM Generation (llm/client.py)
    → LLM sees engine facts as grounding
    → Proposes new ideas
    → source: "llm_proposed"
    → llm_confidence: 0.5-0.8
    ↓
6. LLM Validation (validator.py)
    → Re-runs metrics queries
    → Checks against engine rules
    → Validates savings
    ↓
7. Promotion/Rejection
    IF VALID → source: "engine_backed", validation_status: "validated"
    IF INVALID → source: "llm_proposed", validation_status: "rejected"
    ↓
8. Conflict Resolution
    → Engine-backed always wins
    → LLM-proposed on same resource → downgraded to "conflict"
    ↓
9. Final Output
    → Validated recommendations (engine_backed)
    → AI insights (llm_proposed, rejected/conflict)
```

### Code Flow

**File**: `src/llm/client.py` → `generate_recommendations()`

```python
def generate_recommendations(context_package, architecture_name, raw_graph_data):
    # ═══ STAGE 0: Deterministic engine facts ═══
    engine_cards = []
    if raw_graph_data:
        matches = scan_architecture(raw_graph_data)
        enriched = enrich_matches(matches, raw_graph_data)
        engine_cards = _engine_to_cards(enriched)
    
    # ═══ STAGE 1: Build LLM context ═══
    user_prompt = build_prompt(context_package, raw_graph_data)
    
    # Ground LLM with engine facts
    if engine_cards:
        user_prompt += format_engine_context(engine_cards)
    
    # ═══ STAGE 2: LLM call ═══
    llm_response = call_llm(system_prompt, user_prompt)
    llm_cards = parse_recommendations(llm_response)
    
    # ═══ STAGE 3: Validate LLM-proposed ═══
    validated_llm, rejected_llm = validate_llm_recommendations(
        llm_cards, raw_graph_data, engine_cards
    )
    
    # ═══ STAGE 4: Merge ═══
    cards = merge_engine_and_llm_cards(engine_cards, validated_llm)
    
    # ═══ STAGE 5: Apply conflict resolution ═══
    cards = apply_conflict_resolution(cards)
    
    return RecommendationResult(
        cards=cards,
        llm_used=bool(llm_cards),
        total_estimated_savings=sum(c["total_estimated_savings"] for c in cards)
    )
```

---

## Conflict & Duplicate Handling

### Deduplication

**File**: `src/llm/client.py` → `_deduplicate_cards()`

- Merge recommendations on the same resource with the same action
- Keep highest savings estimate
- Combine justifications

### Conflict Resolution

**File**: `src/llm/recommendation_card_schema.py` → `apply_conflict_resolution()`

**Rules**:
1. If LLM-proposed rec targets same resource as engine-backed rec:
   - **Engine-backed always wins**
   - LLM rec is downgraded to `llm_proposed` with `validation_status: "conflict"`
   - Set `is_downgraded_due_to_conflict: true`
   - Set `alternative_to_engine_rec_id` to point to engine rec

2. Multiple LLM-proposed recs on same resource:
   - Keep highest confidence
   - Mark others as "alternative ideas"

### Example Conflict

```python
# Engine-backed rec
{
    "resource_id": "i-0123456789abcdef0",
    "action": "rightsize_ec2",
    "source": "engine_backed",
    "recommended_instance_type": "m5.large",
    "total_estimated_savings": 450.00,
    "engine_confidence": 0.92
}

# LLM-proposed rec (conflicts)
{
    "resource_id": "i-0123456789abcdef0",
    "action": "terminate_ec2",
    "source": "llm_proposed",  # Downgraded from engine_backed
    "validation_status": "conflict",
    "is_downgraded_due_to_conflict": true,
    "alternative_to_engine_rec_id": "i-0123456789abcdef0",
    "validation_notes": "Conflicts with engine-backed rec. Engine takes precedence."
}
```

---

## LLM Prompt Design

### System Prompt Constraints

**File**: `src/llm/prompts.py` → `RECOMMENDATION_SYSTEM_PROMPT`

**Key constraints**:
```
1. LLM MUST output structured JSON with these fields:
   - resource_id (exact from inventory)
   - action (must be from known enum)
   - source ("llm_proposed" for all LLM outputs)
   - estimated_savings_per_month (approximate, will be validated)
   - confidence_llm (LLM's own confidence, 0-1)
   - justification (references real metrics if present)

2. LLM CANNOT:
   - Invent new action types
   - Override engine-backed recommendations
   - Output recommendations without resource_id
   - Claim high confidence without metric evidence

3. LLM SHOULD:
   - Reference engine facts when available
   - Propose creative campaigns (e.g., "dev environment cleanup")
   - Suggest architectural improvements
   - Identify patterns across multiple resources
```

### User Prompt Structure

```
## SERVICE INVENTORY
[List of all AWS resources with IDs, types, costs]

## CLOUDWATCH METRICS
[Real metrics: CPU, memory, IOPS, latency, etc.]

## GRAPH CONTEXT
[Dependency tree, blast radius, SPOF analysis]

## PRICING DATA
[AWS pricing for EC2, RDS, S3, etc.]

## ENGINE_FACTS (source of truth)
[Deterministic engine recommendations - these are FACTS]
- Resource: i-abc123, Action: rightsize_ec2, Savings: $450/mo, Confidence: 0.92
- Resource: db-xyz789, Action: disable_multi_az, Savings: $320/mo, Confidence: 0.88
...

## YOUR TASK
Generate 8-12 recommendations across at least 4 service families.
You may:
- Elaborate on ENGINE_FACTS with better narratives
- Propose NEW ideas not covered by engine
- Suggest campaigns (e.g., "stop all dev EC2 on weekends")

All LLM outputs will be validated. Only validated recs become "real".
```

---

## Frontend Integration

### UI Display Strategy

**Validated Recommendations Tab** (default):
- Shows `source: "engine_backed"` AND `validation_status: "validated"`
- These are the "real" recommendations users should act on
- Display with high confidence badges

**AI Insights Tab** (secondary):
- Shows `source: "llm_proposed"` with `validation_status: "rejected"` or `"conflict"`
- Labeled as "Experimental Ideas" or "Alternative Approaches"
- Display with lower confidence badges
- Show validation_notes explaining why rejected

### Example Card Display

```jsx
// Validated recommendation
<RecommendationCard
  source="engine_backed"
  confidence={0.92}
  badge="Validated"
  badgeColor="green"
  title="Rightsize EC2 instance i-abc123"
  savings={450.00}
  validation_status="validated"
/>

// LLM insight (rejected)
<RecommendationCard
  source="llm_proposed"
  confidence={0.65}
  badge="AI Insight"
  badgeColor="blue"
  title="Consider terminating idle dev instances"
  savings={200.00}
  validation_status="rejected"
  validation_notes="Rejected: Metrics show instances are actively used"
/>
```

---

## AWS Service Coverage

### Supported Services (Engine + LLM)

| Service | Engine Detectors | LLM Proposals | Validation Rules |
|---------|-----------------|---------------|------------------|
| **EC2** | ✅ Idle, underutilized, Graviton migration | ✅ Scheduling, spot instances | ✅ CPU/network thresholds |
| **RDS** | ✅ Oversize, Multi-AZ, gp2→gp3 | ✅ Read replicas, Aurora Serverless | ✅ CPU/memory thresholds |
| **ElastiCache** | ✅ Oversize, Graviton migration | ✅ Caching strategies | ✅ Memory/eviction thresholds |
| **S3** | ✅ Lifecycle policies, Intelligent-Tiering | ✅ Cross-region replication review | ✅ Age/size thresholds |
| **EBS** | ✅ Unattached volumes, gp2→gp3 | ✅ Snapshot cleanup | ✅ Age/cost thresholds |
| **NAT Gateway** | ✅ Idle NAT, VPC endpoints | ✅ NAT consolidation | ✅ Traffic thresholds |
| **Lambda** | ✅ Memory tuning, ARM64 migration | ✅ Provisioned concurrency review | ✅ Memory/duration thresholds |
| **OpenSearch** | ✅ Oversize, UltraWarm | ✅ Index lifecycle management | ✅ CPU/storage thresholds |

---

## Configuration & Thresholds

### Threshold Configuration

**File**: `src/recommendation_engine/validator.py`

All thresholds are defined as constants:

```python
VALIDATION_THRESHOLDS = {
    # EC2
    "ec2_idle_cpu_p95": 5.0,
    "ec2_idle_network_mbps": 1.0,
    "ec2_idle_min_days": 14,
    
    # RDS
    "rds_oversize_cpu_p95": 40.0,
    "rds_oversize_memory_pct": 30.0,
    "rds_oversize_min_days": 30,
    
    # ElastiCache
    "cache_oversize_memory_pct": 50.0,
    "cache_oversize_evictions": 10,
    
    # S3
    "s3_lifecycle_min_age_days": 90,
    "s3_lifecycle_min_size_gb": 100,
    
    # NAT
    "nat_idle_bytes_per_hour": 1_000_000,
    
    # Lambda
    "lambda_memory_sweet_spot_min": 1024,
    "lambda_memory_sweet_spot_max": 1792,
    
    # Global
    "min_monthly_savings": 50.0,
    "high_confidence_threshold": 0.85,
    "medium_confidence_threshold": 0.60,
}
```

**To adjust thresholds**: Edit this dict and restart the service.

---

## Testing & Validation

### Unit Tests

**Test engine detectors**:
```bash
pytest tests/test_recommendation_engine.py
```

**Test LLM validation**:
```bash
pytest tests/test_validator.py
```

### Integration Tests

**Test full pipeline**:
```bash
pytest tests/test_recommendation_pipeline.py
```

### Manual Testing

```python
from src.recommendation_engine.scanner import scan_architecture
from src.recommendation_engine.enricher import enrich_matches
from src.recommendation_engine.validator import validate_llm_recommendations

# Load test architecture
with open("data/synthetic/test_architecture.json") as f:
    graph_data = json.load(f)

# Run engine
matches = scan_architecture(graph_data)
enriched = enrich_matches(matches, graph_data)

# Simulate LLM proposals
llm_proposals = [
    {
        "resource_id": "i-test123",
        "action": "rightsize_ec2",
        "total_estimated_savings": 100.0,
        "service_type": "EC2",
    }
]

# Validate
validated, rejected = validate_llm_recommendations(llm_proposals, graph_data, enriched)

print(f"Validated: {len(validated)}")
print(f"Rejected: {len(rejected)}")
```

---

## API Endpoints

### Generate Recommendations

```
POST /analyze/recommendations
{
    "architecture_id": "arch-123",
    "architecture_file": "production.json"
}

Response:
{
    "recommendations": [
        {
            "source": "engine_backed",
            "validation_status": "validated",
            "action": "rightsize_ec2",
            "total_estimated_savings": 450.00,
            "engine_confidence": 0.92,
            ...
        },
        {
            "source": "llm_proposed",
            "validation_status": "rejected",
            "action": "terminate_ec2",
            "llm_confidence": 0.65,
            "validation_notes": "Rejected: Instance is actively used",
            ...
        }
    ],
    "total_estimated_savings": 12345.67,
    "llm_used": true
}
```

### Get Last Recommendations

```
GET /analyze/recommendations/last?architecture_id=arch-123

Response: Same as above
```

---

## Best Practices

### For Engine Development

1. **Always use explicit thresholds** - No magic numbers in detector logic
2. **Reference AWS documentation** - Link to official best practices
3. **Include blast radius** - Every rec should know its impact
4. **Provide rollback steps** - Implementation must be reversible
5. **Test with real data** - Use actual CloudWatch metrics

### For LLM Prompt Engineering

1. **Ground with engine facts** - Always include engine recs in prompt
2. **Constrain output format** - Strict JSON schema
3. **Require metric references** - LLM must cite evidence
4. **Limit creativity scope** - Focus on campaigns and narratives
5. **Accept validation failures** - Not all LLM ideas will pass

### For Frontend Integration

1. **Separate tabs** - Validated vs AI Insights
2. **Clear badges** - Visual distinction between sources
3. **Show validation notes** - Explain why rejected
4. **Confidence indicators** - Display engine_confidence vs llm_confidence
5. **Conflict warnings** - Highlight when LLM conflicts with engine

---

## Troubleshooting

### No Engine Recommendations Generated

**Cause**: No resources match detector patterns
**Fix**: Check detector thresholds in `detectors.py`, verify metrics in graph data

### All LLM Recommendations Rejected

**Cause**: LLM proposals don't meet validation thresholds
**Fix**: Review `validator.py` thresholds, check if metrics are available in graph

### LLM Not Proposing New Ideas

**Cause**: Prompt doesn't encourage creativity
**Fix**: Update `RECOMMENDATION_SYSTEM_PROMPT` to explicitly request new patterns

### Conflicts Not Resolving

**Cause**: Conflict resolution logic not applied
**Fix**: Ensure `apply_conflict_resolution()` is called in pipeline

---

## Future Enhancements

1. **Dynamic threshold learning** - Adjust thresholds based on historical accuracy
2. **Cost Explorer integration** - Real-time pricing data
3. **CloudWatch Metrics API** - Live metrics instead of synthetic
4. **Recommendation feedback loop** - Track which recs were implemented
5. **Multi-account support** - Scan across AWS Organizations
6. **Terraform/CloudFormation generation** - Auto-generate IaC for approved recs
7. **Savings tracking** - Measure actual savings post-implementation

---

## References

- **Engine Code**: `src/recommendation_engine/`
- **LLM Code**: `src/llm/client.py`, `src/llm/prompts.py`
- **Validation**: `src/recommendation_engine/validator.py`
- **Schema**: `src/llm/recommendation_card_schema.py`
- **API**: `src/api/handlers/analyze.py`
- **Frontend**: `frontend/src/components/RecommendationCard.jsx`
