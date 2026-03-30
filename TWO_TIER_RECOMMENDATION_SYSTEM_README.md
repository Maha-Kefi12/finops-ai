# Two-Tier FinOps Recommendation System

## 🎯 Overview

A production-ready AWS cost optimization recommendation system that combines **deterministic accuracy** with **LLM creativity**.

### The Problem

Traditional recommendation systems face a dilemma:
- **Pure rules**: Accurate but limited to known patterns
- **Pure LLM**: Creative but can hallucinate or propose invalid optimizations

### The Solution

**Two-tier architecture**:
1. **Engine-backed**: Deterministic rules + real metrics (always correct)
2. **LLM-proposed**: AI-generated ideas validated by the engine (creative but safe)

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Architecture Graph                        │
│              (Services, Dependencies, Metrics)               │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴────────────┐
        │                         │
        ▼                         ▼
┌───────────────┐         ┌──────────────┐
│ Engine Layer  │         │  LLM Layer   │
│ (Deterministic)│         │  (Creative)  │
└───────┬───────┘         └──────┬───────┘
        │                         │
        │ engine_backed           │ llm_proposed
        │ confidence: 0.92        │ confidence: 0.75
        │                         │
        └────────────┬────────────┘
                     │
                     ▼
            ┌────────────────┐
            │   Validator    │
            │  (validator.py)│
            └────────┬───────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
   VALIDATED     REJECTED    CONFLICT
   (promote)     (idea only) (downgrade)
        │            │            │
        └────────────┴────────────┘
                     │
                     ▼
            ┌────────────────┐
            │ Final Output   │
            │ - Validated    │
            │ - AI Insights  │
            └────────────────┘
```

---

## 📦 What's Included

### Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **Validator** | `src/recommendation_engine/validator.py` | Validates LLM proposals against engine rules |
| **Updated Prompts** | `src/llm/prompts.py` | Enforces two-tier system in LLM outputs |
| **Schema** | `src/llm/recommendation_card_schema.py` | Data structures (already existed) |
| **Scanner** | `src/recommendation_engine/scanner.py` | Generates engine-backed recs (already existed) |
| **Enricher** | `src/recommendation_engine/enricher.py` | Adds graph metrics (already existed) |

### Documentation

| Document | Size | Purpose |
|----------|------|---------|
| **QUICK_START_TWO_TIER_SYSTEM.md** | 8 KB | 5-minute quick start |
| **RECOMMENDATION_SYSTEM_SUMMARY.md** | 14 KB | Implementation summary |
| **RECOMMENDATION_SYSTEM_ARCHITECTURE.md** | 26 KB | Complete system design |
| **RECOMMENDATION_SYSTEM_EXAMPLES.md** | 22 KB | Code examples & patterns |
| **RECOMMENDATION_SYSTEM_INTEGRATION_GUIDE.md** | 18 KB | Step-by-step integration |

---

## 🚀 Quick Start

### 1. Read This First

Start with **`QUICK_START_TWO_TIER_SYSTEM.md`** (5 minutes)

### 2. Integrate Backend

Add validator call to `src/llm/client.py`:

```python
from src.recommendation_engine.validator import validate_llm_recommendations

# After LLM generates cards:
validated_llm, rejected_llm = validate_llm_recommendations(
    llm_cards, raw_graph_data, engine_cards
)

cards = _merge_engine_and_llm_cards(engine_cards, validated_llm)
```

### 3. Update Frontend

Add two tabs:
- **Validated Recommendations** (engine-backed + validated LLM)
- **AI Insights** (rejected + conflicted LLM)

### 4. Test

```python
from src.recommendation_engine.validator import validate_llm_recommendations

llm_rec = {
    "resource_id": "i-test123",
    "action": "rightsize_ec2",
    "total_estimated_savings": 100.0,
    "service_type": "EC2"
}

graph = {
    "services": [{
        "id": "i-test123",
        "metrics": {"cpu_utilization_p95": 3.5},
        "cost_monthly": 200.0
    }]
}

validated, rejected = validate_llm_recommendations([llm_rec], graph)
# Expected: validated=1, rejected=0
```

---

## 📊 How It Works

### Example Flow

**Input**: Production architecture with 50 AWS resources

**Engine Layer** (Deterministic):
- Scans 50 resources against 25 detector patterns
- Finds 8 matches (e.g., idle EC2, oversized RDS)
- Produces 8 engine-backed recommendations
- Confidence: 0.85-0.95

**LLM Layer** (Creative):
- Sees engine facts + architecture context
- Proposes 12 new ideas (e.g., "schedule all dev EC2")
- All marked as `source: "llm_proposed"`
- Confidence: 0.50-0.85

**Validator**:
- Re-runs metrics queries for each LLM proposal
- Checks against engine rules
- Results:
  - 5 validated → promoted to `engine_backed`
  - 4 rejected → stay as `llm_proposed` (shown in "AI Insights")
  - 3 conflicts → downgraded (conflict with engine recs)

**Final Output**:
- **Main Tab**: 13 validated recs (8 engine + 5 validated LLM)
- **AI Insights Tab**: 7 ideas (4 rejected + 3 conflicts)

---

## 🎨 Recommendation Types

### Type 1: Engine-Backed (Original)

```json
{
  "title": "Rightsize EC2 i-abc123 from m5.2xlarge to m5.xlarge",
  "source": "engine_backed",
  "action": "rightsize_ec2",
  "engine_confidence": 0.92,
  "validation_status": "validated",
  "total_estimated_savings": 450.00
}
```

**Display**: ✅ Main tab, green badge, "Validated"

### Type 2: LLM-Proposed → Validated

```json
{
  "title": "Schedule all dev EC2 to stop nights/weekends",
  "source": "engine_backed",  // Promoted!
  "action": "schedule_ec2_stop",
  "llm_confidence": 0.85,
  "engine_confidence": 0.78,
  "validation_status": "validated",
  "validation_notes": "Validated: Pattern detected across 8 instances"
}
```

**Display**: ✅ Main tab, green badge, "AI Validated"

### Type 3: LLM-Proposed → Rejected

```json
{
  "title": "Terminate idle EC2 i-xyz789",
  "source": "llm_proposed",
  "validation_status": "rejected",
  "validation_notes": "Rejected: P95 CPU 42% indicates active use"
}
```

**Display**: 💡 "AI Insights" tab, blue badge, show rejection reason

### Type 4: LLM-Proposed → Conflict

```json
{
  "title": "Terminate EC2 i-abc123",
  "source": "llm_proposed",
  "validation_status": "conflict",
  "is_downgraded_due_to_conflict": true,
  "validation_notes": "Conflicts with engine rightsizing recommendation"
}
```

**Display**: ⚠️ "AI Insights" tab, warning badge, link to engine rec

---

## ⚙️ Configuration

### Validation Thresholds

**File**: `src/recommendation_engine/validator.py`

```python
VALIDATION_THRESHOLDS = {
    # EC2
    "ec2_idle_cpu_p95": 5.0,           # P95 CPU < 5%
    "ec2_idle_network_mbps": 1.0,      # Network I/O < 1 Mbps
    
    # RDS
    "rds_oversize_cpu_p95": 40.0,      # P95 CPU < 40%
    "rds_oversize_memory_pct": 30.0,   # Freeable memory > 30%
    
    # ElastiCache
    "cache_oversize_memory_pct": 50.0, # Memory < 50%
    
    # S3
    "s3_lifecycle_min_age_days": 90,   # Objects > 90 days old
    "s3_lifecycle_min_size_gb": 100,   # At least 100 GB
    
    # Global
    "min_monthly_savings": 50.0,       # Minimum $50/month
}
```

**Adjust these** to control validation strictness.

---

## 🧪 Testing

### Unit Test

```bash
pytest tests/test_validator.py
```

### Integration Test

```bash
pytest tests/test_recommendation_pipeline.py
```

### Manual Test

```python
from src.llm.client import generate_recommendations
from src.analysis.context_assembler import ContextAssembler
from src.analysis.graph_analyzer import GraphAnalyzer

# Load architecture
with open("data/synthetic/production.json") as f:
    graph_data = json.load(f)

# Run pipeline
analyzer = GraphAnalyzer(graph_data)
report = analyzer.analyze()
assembler = ContextAssembler(graph_data, report)
context = assembler.assemble()

result = generate_recommendations(
    context_package=context,
    architecture_name="Production",
    raw_graph_data=graph_data
)

# Check results
print(f"Total: {len(result.cards)}")
print(f"Savings: ${result.total_estimated_savings:.2f}/month")

# Breakdown by source
sources = {}
for card in result.cards:
    src = card.get('source', 'unknown')
    sources[src] = sources.get(src, 0) + 1

print(f"Engine-backed: {sources.get('engine_backed', 0)}")
print(f"LLM-proposed: {sources.get('llm_proposed', 0)}")
```

---

## 📚 Documentation Guide

### For Quick Start (5 min)
→ **`QUICK_START_TWO_TIER_SYSTEM.md`**

### For Implementation Summary
→ **`RECOMMENDATION_SYSTEM_SUMMARY.md`**

### For System Architecture
→ **`RECOMMENDATION_SYSTEM_ARCHITECTURE.md`**

### For Code Examples
→ **`RECOMMENDATION_SYSTEM_EXAMPLES.md`**

### For Integration Steps
→ **`RECOMMENDATION_SYSTEM_INTEGRATION_GUIDE.md`**

---

## 🔑 Key Benefits

### 1. Accuracy + Creativity
- Engine provides deterministic baseline
- LLM adds creative patterns and campaigns
- Validation ensures LLM ideas are grounded

### 2. Transparency
- Clear source tracking (engine vs LLM)
- Confidence scores for each recommendation
- Validation notes explain rejections

### 3. Safety
- Engine-backed always wins in conflicts
- LLM cannot override deterministic rules
- Minimum savings thresholds prevent noise

### 4. Flexibility
- LLM can propose multi-resource campaigns
- Architectural improvements beyond single resources
- Pattern detection across environments

---

## 🎯 Use Cases

### Use Case 1: Standard Optimization
**Scenario**: Optimize production architecture

**Result**:
- Engine finds 10 standard optimizations (idle EC2, oversized RDS)
- LLM proposes 3 new patterns (dev scheduling, NAT consolidation)
- 2 LLM ideas validate → 12 total validated recommendations

### Use Case 2: Campaign Detection
**Scenario**: Multiple dev environments running 24/7

**Result**:
- Engine finds individual idle instances
- LLM detects pattern: "All dev EC2 run 24/7 but unused nights/weekends"
- LLM proposes campaign: "Schedule all dev EC2 to stop 7PM-7AM"
- Validator confirms pattern → Campaign validated

### Use Case 3: Architectural Improvement
**Scenario**: High NAT Gateway costs

**Result**:
- Engine finds idle NAT Gateways
- LLM proposes: "Replace NAT with VPC endpoints for S3/DynamoDB"
- Validator checks traffic patterns → Architectural improvement validated

---

## 🚨 Common Issues

### Issue: All LLM Recommendations Rejected

**Cause**: Validation thresholds too strict or metrics missing

**Fix**: 
1. Check `VALIDATION_THRESHOLDS` in `validator.py`
2. Verify graph data has metrics
3. Lower thresholds if needed

### Issue: No Recommendations Generated

**Cause**: No resources match patterns or metrics missing

**Fix**:
1. Check graph has services/nodes
2. Verify metrics are present
3. Review detector patterns in `detectors.py`

### Issue: Too Many Conflicts

**Cause**: LLM proposing on same resources as engine

**Fix**: This is expected - engine always wins. Display conflicts in "AI Insights" tab.

---

## 📈 Monitoring

### Metrics to Track

1. **Validation Success Rate**: % of LLM proposals that validate
2. **Source Distribution**: % engine vs validated LLM vs rejected
3. **User Engagement**: Which type gets implemented more?
4. **Savings Accuracy**: Estimated vs actual savings by source

### Logging

```python
logger.info(
    "Recommendations: engine=%d, llm_validated=%d, llm_rejected=%d",
    len(engine_cards),
    len(validated_llm),
    len(rejected_llm)
)
```

---

## 🔄 Deployment Workflow

1. ✅ Review documentation
2. ✅ Integrate validator into `src/llm/client.py`
3. ✅ Update frontend (tabs, badges, validation notes)
4. ✅ Test with sample data
5. ✅ Configure thresholds
6. ⬜ Deploy to staging
7. ⬜ Monitor validation success rate
8. ⬜ Gather user feedback
9. ⬜ Adjust thresholds based on metrics
10. ⬜ Deploy to production

---

## 🎓 Learning Path

### Day 1: Understand the System
- Read `QUICK_START_TWO_TIER_SYSTEM.md`
- Review `RECOMMENDATION_SYSTEM_SUMMARY.md`
- Understand two-tier architecture

### Day 2: Explore the Code
- Review `src/recommendation_engine/validator.py`
- Check `src/llm/prompts.py` changes
- Understand validation rules

### Day 3: Integration
- Follow `RECOMMENDATION_SYSTEM_INTEGRATION_GUIDE.md`
- Update backend code
- Update frontend UI

### Day 4: Testing
- Run unit tests
- Test with sample data
- Verify validation logic

### Day 5: Deploy
- Deploy to staging
- Monitor metrics
- Gather feedback

---

## 🤝 Contributing

### Adding New Validation Rules

1. Edit `src/recommendation_engine/validator.py`
2. Add service-specific validator function
3. Add threshold to `VALIDATION_THRESHOLDS`
4. Add unit test
5. Update documentation

### Adding New Actions

1. Edit `src/llm/recommendation_card_schema.py`
2. Add to `RecommendationAction` enum
3. Update `src/llm/prompts.py` allowed actions list
4. Add validation rule if needed
5. Update documentation

---

## 📞 Support

### Documentation
- Quick Start: `QUICK_START_TWO_TIER_SYSTEM.md`
- Architecture: `RECOMMENDATION_SYSTEM_ARCHITECTURE.md`
- Examples: `RECOMMENDATION_SYSTEM_EXAMPLES.md`
- Integration: `RECOMMENDATION_SYSTEM_INTEGRATION_GUIDE.md`

### Code
- Validator: `src/recommendation_engine/validator.py`
- Prompts: `src/llm/prompts.py`
- Schema: `src/llm/recommendation_card_schema.py`

---

## 🎉 You're Ready!

You now have a **production-ready two-tier recommendation system** that combines the best of both worlds:

✅ **Deterministic accuracy** from the engine
✅ **Creative insights** from the LLM
✅ **Validation safety** to ensure quality
✅ **Transparent tracking** of source and confidence
✅ **Comprehensive documentation** for your team

**Start with `QUICK_START_TWO_TIER_SYSTEM.md` and you'll be up and running in 5 minutes!**

---

## 📄 License

Same as the main FinOps AI system.

---

**Built with ❤️ for accurate, creative, and safe AWS cost optimization**
