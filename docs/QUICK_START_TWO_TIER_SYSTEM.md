# Quick Start: Two-Tier FinOps Recommendation System

## 🚀 5-Minute Overview

This system generates AWS cost optimization recommendations using **two layers**:

1. **Engine-backed** (deterministic): Real metrics + rules → Always correct
2. **LLM-proposed** (creative): AI ideas → Validated by engine before showing

---

## 📋 What You Need to Know

### Two Types of Recommendations

| Type | Source | Confidence | Show Where |
|------|--------|------------|------------|
| **Engine-backed** | Deterministic rules | 0.85-0.95 | Main tab (always) |
| **LLM-validated** | AI → passed validation | 0.60-0.90 | Main tab (promoted) |
| **LLM-rejected** | AI → failed validation | 0.40-0.70 | "AI Insights" tab |
| **LLM-conflict** | AI → conflicts with engine | 0.50-0.80 | "AI Insights" tab |

### Key Fields in Every Recommendation

```json
{
  "source": "engine_backed" | "llm_proposed",
  "action": "rightsize_ec2" | "terminate_ec2" | ...,
  "validation_status": "validated" | "rejected" | "conflict",
  "engine_confidence": 0.92,  // If engine-backed
  "llm_confidence": 0.75,     // If LLM-proposed
  "validation_notes": "Why validated/rejected"
}
```

---

## 🔧 Integration (3 Steps)

### Step 1: Backend - Add Validator Call

**File**: `src/llm/client.py`

```python
# Add import at top
from src.recommendation_engine.validator import validate_llm_recommendations

# In generate_recommendations(), after LLM generates cards:
def generate_recommendations(context_package, architecture_name, raw_graph_data):
    # ... existing code ...
    
    # After: llm_cards = parse_recommendations(llm_response)
    
    # NEW: Validate LLM-proposed recommendations
    if llm_cards and raw_graph_data:
        validated_llm, rejected_llm = validate_llm_recommendations(
            llm_cards, 
            raw_graph_data, 
            engine_cards
        )
        
        # Merge validated LLM with engine cards
        cards = _merge_engine_and_llm_cards(engine_cards, validated_llm)
        
        # Optional: Include rejected as "insights"
        # for insight in rejected_llm:
        #     insight['is_insight'] = True
        #     cards.append(insight)
    else:
        cards = engine_cards
    
    # ... rest of existing code ...
```

### Step 2: Frontend - Add Tabs

**File**: `frontend/src/pages/AnalysisPage.jsx`

```jsx
function RecommendationTabs({ recommendations }) {
  const [tab, setTab] = useState('validated');
  
  const validated = recommendations.filter(r => 
    r.source === 'engine_backed' || r.validation_status === 'validated'
  );
  
  const insights = recommendations.filter(r => 
    r.source === 'llm_proposed' && 
    ['rejected', 'conflict'].includes(r.validation_status)
  );
  
  return (
    <div>
      <div className="tabs">
        <button onClick={() => setTab('validated')}>
          Validated ({validated.length})
        </button>
        <button onClick={() => setTab('insights')}>
          AI Insights ({insights.length})
        </button>
      </div>
      
      {tab === 'validated' && validated.map(rec => 
        <RecommendationCard {...rec} badge="Validated" />
      )}
      
      {tab === 'insights' && insights.map(rec => 
        <InsightCard {...rec} badge="AI Insight" notes={rec.validation_notes} />
      )}
    </div>
  );
}
```

### Step 3: Frontend - Add Confidence Badges

```jsx
function ConfidenceBadge({ rec }) {
  const conf = rec.engine_confidence || rec.llm_confidence || 0.5;
  const color = conf >= 0.85 ? 'green' : conf >= 0.6 ? 'yellow' : 'orange';
  const label = rec.source === 'engine_backed' ? 'Validated' : 'AI Insight';
  
  return (
    <span className={`badge ${color}`}>
      {label} ({(conf * 100).toFixed(0)}%)
    </span>
  );
}
```

---

## 🧪 Test It

### Quick Test

```python
from src.recommendation_engine.validator import validate_llm_recommendations

# Simulate LLM proposal
llm_rec = {
    "resource_id": "i-test123",
    "action": "rightsize_ec2",
    "total_estimated_savings": 100.0,
    "service_type": "EC2"
}

# Mock graph with metrics
graph = {
    "services": [{
        "id": "i-test123",
        "metrics": {"cpu_utilization_p95": 3.5},  # Below 5% threshold
        "cost_monthly": 200.0
    }]
}

# Validate
validated, rejected = validate_llm_recommendations([llm_rec], graph)
print(f"✓ Validated: {len(validated)}, ✗ Rejected: {len(rejected)}")
```

**Expected**: `✓ Validated: 1, ✗ Rejected: 0`

---

## ⚙️ Configuration

### Adjust Validation Strictness

**File**: `src/recommendation_engine/validator.py`

```python
VALIDATION_THRESHOLDS = {
    "ec2_idle_cpu_p95": 5.0,        # Lower = stricter
    "min_monthly_savings": 50.0,    # Higher = stricter
    # ... adjust as needed ...
}
```

### Common Adjustments

| To Accept More LLM Ideas | Change |
|---------------------------|--------|
| More lenient CPU threshold | `ec2_idle_cpu_p95: 10.0` (from 5.0) |
| Lower savings minimum | `min_monthly_savings: 25.0` (from 50.0) |
| More lenient RDS threshold | `rds_oversize_cpu_p95: 50.0` (from 40.0) |

---

## 📊 Example Outputs

### Engine-Backed Recommendation

```json
{
  "title": "Rightsize EC2 i-abc123 from m5.2xlarge to m5.xlarge",
  "source": "engine_backed",
  "action": "rightsize_ec2",
  "engine_confidence": 0.92,
  "validation_status": "validated",
  "total_estimated_savings": 450.00,
  "resource_id": "i-abc123"
}
```

**Display**: Main tab, green "Validated" badge, 92% confidence

### LLM-Proposed → Validated

```json
{
  "title": "Schedule all dev EC2 to stop nights/weekends",
  "source": "engine_backed",  // Promoted!
  "action": "schedule_ec2_stop",
  "llm_confidence": 0.85,
  "engine_confidence": 0.78,
  "validation_status": "validated",
  "validation_notes": "Validated: Pattern detected across 8 dev instances",
  "total_estimated_savings": 1240.00
}
```

**Display**: Main tab, green "AI Validated" badge, 78% confidence

### LLM-Proposed → Rejected

```json
{
  "title": "Terminate idle EC2 i-xyz789",
  "source": "llm_proposed",
  "action": "terminate_ec2",
  "llm_confidence": 0.65,
  "validation_status": "rejected",
  "validation_notes": "Rejected: P95 CPU 42% indicates active use",
  "total_estimated_savings": 320.00
}
```

**Display**: "AI Insights" tab, blue badge, show validation notes

### LLM-Proposed → Conflict

```json
{
  "title": "Terminate EC2 i-abc123",
  "source": "llm_proposed",
  "action": "terminate_ec2",
  "validation_status": "conflict",
  "is_downgraded_due_to_conflict": true,
  "alternative_to_engine_rec_id": "i-abc123",
  "validation_notes": "Conflicts with engine rightsizing recommendation"
}
```

**Display**: "AI Insights" tab, warning icon, link to engine rec

---

## 🔍 Validation Rules

### EC2 Rightsizing

```python
# Validates if:
- P95 CPU < 5% (idle) OR < 30% (underutilized)
- Network I/O < 1 Mbps
- Savings >= $50/month
- Savings < current cost
```

### RDS Optimization

```python
# Validates if:
- P95 CPU < 40%
- Freeable memory > 30%
- Savings >= $50/month
```

### S3 Lifecycle

```python
# Validates if:
- Storage >= 100 GB
- Average object age >= 90 days
```

**See `src/recommendation_engine/validator.py` for all rules**

---

## 🐛 Troubleshooting

### All LLM Recommendations Rejected

**Check**:
1. Are metrics available in graph data?
2. Are thresholds too strict?
3. Is LLM proposing unrealistic savings?

**Fix**: Lower thresholds in `validator.py`

### No Recommendations Generated

**Check**:
1. Does graph have services/nodes?
2. Do resources have metrics?
3. Are detector patterns matching?

**Fix**: Check scanner logs, verify graph data structure

### Too Many Conflicts

**Expected behavior** - Engine always wins. Display conflicts in "AI Insights" tab as alternative ideas.

---

## 📚 Full Documentation

- **Architecture**: `RECOMMENDATION_SYSTEM_ARCHITECTURE.md` (26 KB)
- **Examples**: `RECOMMENDATION_SYSTEM_EXAMPLES.md` (22 KB)
- **Integration**: `RECOMMENDATION_SYSTEM_INTEGRATION_GUIDE.md` (18 KB)
- **Summary**: `RECOMMENDATION_SYSTEM_SUMMARY.md` (14 KB)

---

## ✅ Deployment Checklist

- [ ] Add validator call to `src/llm/client.py`
- [ ] Add tabs to frontend (Validated vs AI Insights)
- [ ] Add confidence badges
- [ ] Display validation notes
- [ ] Test with sample data
- [ ] Configure thresholds
- [ ] Deploy to staging
- [ ] Monitor validation success rate
- [ ] Deploy to production

---

## 🎯 Key Takeaways

1. **Engine-backed = Truth**: Always correct, based on real metrics
2. **LLM-proposed = Ideas**: Creative but must be validated
3. **Validation = Safety**: Ensures LLM ideas are grounded in reality
4. **Conflicts = Engine Wins**: Deterministic always takes precedence
5. **Two Tabs = Clarity**: Validated (main) vs AI Insights (experimental)

---

## 🚀 Ready to Go!

You now have everything you need to deploy a production-ready two-tier recommendation system that combines deterministic accuracy with LLM creativity.

**Start with the 3 integration steps above, then refer to the full documentation for details.**

Good luck! 🎉
