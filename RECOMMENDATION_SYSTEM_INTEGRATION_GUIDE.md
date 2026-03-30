# FinOps AI Recommendation System - Integration Guide

## Overview

This guide explains how to integrate the two-tier recommendation system into your FinOps AI platform.

---

## Architecture Components

### 1. Deterministic Engine Layer

**Location**: `src/recommendation_engine/`

**Components**:
- `detectors.py` - Pattern-based detectors with AWS thresholds
- `scanner.py` - Scans architecture against all patterns
- `enricher.py` - Adds graph RAG metrics
- `validator.py` - Validates LLM-proposed recommendations

**Purpose**: Produces engine-backed recommendations using real metrics and deterministic rules.

### 2. LLM Generation Layer

**Location**: `src/llm/`

**Components**:
- `client.py` - Main LLM generation logic
- `prompts.py` - System and user prompts
- `recommendation_card_schema.py` - Data structures

**Purpose**: Generates LLM-proposed recommendations that are validated by the engine.

### 3. API Layer

**Location**: `src/api/handlers/analyze.py`

**Endpoints**:
- `POST /analyze/recommendations` - Generate recommendations
- `GET /analyze/recommendations/last` - Get cached recommendations

---

## Integration Steps

### Step 1: Update LLM Client to Use Validator

The LLM client (`src/llm/client.py`) already has the basic structure. Ensure it calls the validator:

```python
from src.recommendation_engine.validator import validate_llm_recommendations

def generate_recommendations(context_package, architecture_name, raw_graph_data):
    # ... existing code ...
    
    # Stage 2: LLM call
    llm_cards = parse_recommendations(llm_response)
    
    # Stage 3: Validate LLM-proposed recommendations
    if llm_cards and raw_graph_data:
        validated_llm, rejected_llm = validate_llm_recommendations(
            llm_cards, 
            raw_graph_data, 
            engine_cards
        )
        
        # Merge validated LLM with engine cards
        cards = merge_engine_and_llm_cards(engine_cards, validated_llm)
        
        # Keep rejected as insights (optional)
        # cards.extend(rejected_llm)  # Include in response for "AI Insights" tab
    else:
        cards = engine_cards
    
    return RecommendationResult(cards=cards, ...)
```

### Step 2: Update API Response Schema

Ensure API responses include all two-tier fields:

```python
# src/api/schemas/persistence.py
class RecommendationCardSchema(BaseModel):
    # Core fields
    title: str
    service_type: str
    total_estimated_savings: float
    
    # Two-tier tracking
    source: str  # "engine_backed" or "llm_proposed"
    action: str  # Must be from RecommendationAction enum
    engine_confidence: Optional[float] = None
    llm_confidence: Optional[float] = None
    validation_status: Optional[str] = None  # pending, validated, rejected, conflict
    validation_notes: Optional[str] = None
    
    # Conflict tracking
    is_downgraded_due_to_conflict: bool = False
    conflicting_rec_ids: List[str] = []
    alternative_to_engine_rec_id: Optional[str] = None
    
    # ... rest of fields ...
```

### Step 3: Frontend Integration

Update frontend to display recommendations by source:

```jsx
// frontend/src/pages/AnalysisPage.jsx

function RecommendationTabs({ recommendations }) {
  const [activeTab, setActiveTab] = useState('validated');
  
  // Separate recommendations by validation status
  const validatedRecs = recommendations.filter(r => 
    r.source === 'engine_backed' || 
    r.validation_status === 'validated'
  );
  
  const aiInsights = recommendations.filter(r => 
    r.source === 'llm_proposed' && 
    ['rejected', 'conflict'].includes(r.validation_status)
  );
  
  return (
    <div className="recommendation-tabs">
      <div className="tabs-header">
        <button 
          className={activeTab === 'validated' ? 'active' : ''}
          onClick={() => setActiveTab('validated')}
        >
          Validated Recommendations ({validatedRecs.length})
        </button>
        <button 
          className={activeTab === 'insights' ? 'active' : ''}
          onClick={() => setActiveTab('insights')}
        >
          AI Insights ({aiInsights.length})
        </button>
      </div>
      
      <div className="tabs-content">
        {activeTab === 'validated' && (
          <ValidatedRecommendations recommendations={validatedRecs} />
        )}
        {activeTab === 'insights' && (
          <AIInsights insights={aiInsights} />
        )}
      </div>
    </div>
  );
}
```

### Step 4: Add Confidence Badges

Display confidence levels visually:

```jsx
function ConfidenceBadge({ recommendation }) {
  const confidence = recommendation.engine_confidence || 
                     recommendation.llm_confidence || 
                     0.5;
  
  const getColor = (conf) => {
    if (conf >= 0.85) return 'green';
    if (conf >= 0.60) return 'yellow';
    return 'orange';
  };
  
  const getLabel = (rec) => {
    if (rec.source === 'engine_backed') {
      return rec.validation_status === 'validated' 
        ? 'AI Validated' 
        : 'Engine Validated';
    }
    return 'AI Insight';
  };
  
  return (
    <div className={`confidence-badge ${getColor(confidence)}`}>
      <span className="badge-label">{getLabel(recommendation)}</span>
      <span className="confidence-score">{(confidence * 100).toFixed(0)}%</span>
    </div>
  );
}
```

### Step 5: Display Validation Notes

Show why LLM recommendations were rejected:

```jsx
function ValidationNotes({ recommendation }) {
  if (!recommendation.validation_notes) return null;
  
  const isRejected = recommendation.validation_status === 'rejected';
  const isConflict = recommendation.validation_status === 'conflict';
  
  return (
    <div className={`validation-notes ${isRejected ? 'rejected' : 'conflict'}`}>
      <div className="notes-header">
        {isRejected && <AlertCircle size={16} />}
        {isConflict && <AlertTriangle size={16} />}
        <span>
          {isRejected ? 'Validation Failed' : 'Conflicts with Engine Recommendation'}
        </span>
      </div>
      <p className="notes-content">{recommendation.validation_notes}</p>
      
      {isConflict && recommendation.alternative_to_engine_rec_id && (
        <a href={`#rec-${recommendation.alternative_to_engine_rec_id}`}>
          View engine recommendation →
        </a>
      )}
    </div>
  );
}
```

---

## Configuration

### Validation Thresholds

Edit `src/recommendation_engine/validator.py`:

```python
VALIDATION_THRESHOLDS = {
    # Adjust these based on your requirements
    "ec2_idle_cpu_p95": 5.0,           # Lower = stricter
    "rds_oversize_cpu_p95": 40.0,      # Higher = more lenient
    "min_monthly_savings": 50.0,       # Minimum savings to consider
    # ... more thresholds ...
}
```

### LLM Prompt Tuning

Edit `src/llm/prompts.py`:

```python
RECOMMENDATION_SYSTEM_PROMPT = """
# Adjust creativity vs. strictness
# More creative: Encourage more "llm_proposed" ideas
# More strict: Focus on elaborating engine facts
"""
```

---

## Testing

### Unit Tests

```python
# tests/test_validator.py
import pytest
from src.recommendation_engine.validator import validate_llm_recommendations

def test_validate_ec2_rightsize():
    llm_rec = {
        "resource_id": "i-test123",
        "action": "rightsize_ec2",
        "total_estimated_savings": 100.0,
        "service_type": "EC2"
    }
    
    graph_data = {
        "services": [{
            "id": "i-test123",
            "metrics": {
                "cpu_utilization_p95": 3.5,  # Below threshold
                "network_in_mbps": 0.5
            },
            "cost_monthly": 200.0
        }]
    }
    
    validated, rejected = validate_llm_recommendations([llm_rec], graph_data)
    
    assert len(validated) == 1
    assert validated[0]['validation_status'] == 'validated'
    assert validated[0]['source'] == 'engine_backed'  # Promoted
```

### Integration Tests

```python
# tests/test_recommendation_pipeline.py
def test_full_pipeline():
    from src.llm.client import generate_recommendations
    from src.analysis.context_assembler import ContextAssembler
    from src.analysis.graph_analyzer import GraphAnalyzer
    
    # Load test architecture
    graph_data = load_test_architecture()
    
    # Run pipeline
    analyzer = GraphAnalyzer(graph_data)
    report = analyzer.analyze()
    assembler = ContextAssembler(graph_data, report)
    context = assembler.assemble()
    
    result = generate_recommendations(
        context_package=context,
        architecture_name="Test",
        raw_graph_data=graph_data
    )
    
    # Verify two-tier separation
    sources = [c.get('source') for c in result.cards]
    assert 'engine_backed' in sources
    
    # Verify validation statuses
    statuses = [c.get('validation_status') for c in result.cards if c.get('validation_status')]
    assert all(s in ['validated', 'rejected', 'conflict', 'pending'] for s in statuses)
```

---

## Monitoring

### Metrics to Track

1. **Recommendation Distribution**:
   - % engine-backed
   - % LLM-proposed (validated)
   - % LLM-proposed (rejected)
   - % conflicts

2. **Validation Success Rate**:
   - Track how many LLM proposals pass validation
   - Identify common rejection reasons

3. **User Engagement**:
   - Which recommendations are implemented?
   - Do users prefer engine-backed or validated LLM?

4. **Savings Accuracy**:
   - Compare estimated vs actual savings
   - Track by source (engine vs LLM)

### Logging

```python
# src/llm/client.py
logger.info(
    "Recommendation generation complete: "
    "engine=%d, llm_validated=%d, llm_rejected=%d, conflicts=%d",
    len(engine_cards),
    len(validated_llm),
    len(rejected_llm),
    len(conflicts)
)
```

---

## Troubleshooting

### Issue: All LLM Recommendations Rejected

**Symptoms**: Every LLM proposal has `validation_status: "rejected"`

**Causes**:
1. Validation thresholds too strict
2. LLM proposing unrealistic savings
3. Metrics missing in graph data

**Solutions**:
1. Review `VALIDATION_THRESHOLDS` in `validator.py`
2. Check LLM prompt for savings calculation guidance
3. Ensure graph data includes CloudWatch metrics

### Issue: Too Many Conflicts

**Symptoms**: Many LLM proposals have `validation_status: "conflict"`

**Causes**:
1. LLM proposing on same resources as engine
2. Action types conflicting (e.g., terminate vs rightsize)

**Solutions**:
1. This is expected behavior - engine always wins
2. Display conflicts as "alternative ideas" in UI
3. Consider filtering out conflicts from main view

### Issue: No Engine Recommendations

**Symptoms**: All recommendations have `source: "llm_proposed"`

**Causes**:
1. No resources match detector patterns
2. Detector thresholds too strict
3. Metrics missing

**Solutions**:
1. Check `detectors.py` patterns
2. Verify graph data has metrics
3. Review scanner logs for match attempts

---

## Performance Optimization

### Caching

```python
# Cache validated recommendations
from src.storage.recommendation_cache import cache_recommendations

cache_recommendations(
    architecture_id=arch_id,
    recommendations=result.cards,
    ttl=3600  # 1 hour
)
```

### Async Validation

```python
# Validate LLM recommendations in parallel
import asyncio

async def validate_async(llm_recs, graph_data, engine_recs):
    tasks = [
        asyncio.to_thread(
            validate_single_recommendation,
            rec,
            graph_data
        )
        for rec in llm_recs
    ]
    results = await asyncio.gather(*tasks)
    return results
```

---

## Security Considerations

### 1. Input Validation

```python
# Validate LLM outputs before processing
def validate_llm_output(rec: dict) -> bool:
    required_fields = ['resource_id', 'action', 'source', 'total_estimated_savings']
    if not all(f in rec for f in required_fields):
        return False
    
    # Validate action is from allowed enum
    from src.llm.recommendation_card_schema import RecommendationAction
    if rec['action'] not in [a.value for a in RecommendationAction]:
        return False
    
    # Validate source
    if rec['source'] not in ['engine_backed', 'llm_proposed']:
        return False
    
    return True
```

### 2. Sanitize Resource IDs

```python
# Prevent injection attacks
import re

def sanitize_resource_id(resource_id: str) -> str:
    # Only allow AWS resource ID patterns
    if not re.match(r'^[a-zA-Z0-9\-:/_]+$', resource_id):
        raise ValueError(f"Invalid resource ID: {resource_id}")
    return resource_id
```

### 3. Rate Limiting

```python
# Limit LLM calls per user/architecture
from functools import lru_cache
from datetime import datetime, timedelta

@lru_cache(maxsize=1000)
def check_rate_limit(architecture_id: str) -> bool:
    # Implement rate limiting logic
    pass
```

---

## Deployment Checklist

- [ ] Update `src/llm/client.py` to call validator
- [ ] Update API schemas to include two-tier fields
- [ ] Update frontend to display validated vs insights tabs
- [ ] Add confidence badges to UI
- [ ] Display validation notes for rejected recs
- [ ] Configure validation thresholds
- [ ] Add unit tests for validator
- [ ] Add integration tests for full pipeline
- [ ] Set up monitoring and logging
- [ ] Document for team
- [ ] Test with production data
- [ ] Deploy to staging
- [ ] Monitor validation success rate
- [ ] Gather user feedback
- [ ] Adjust thresholds based on feedback

---

## Migration from Old System

If you have an existing recommendation system:

### Step 1: Add Source Field

```python
# Migration script
def migrate_existing_recommendations(old_recs):
    for rec in old_recs:
        # All existing recs are engine-backed
        rec['source'] = 'engine_backed'
        rec['validation_status'] = 'validated'
        rec['engine_confidence'] = 0.85  # Default
    return old_recs
```

### Step 2: Gradual Rollout

```python
# Feature flag
USE_TWO_TIER_SYSTEM = os.getenv('USE_TWO_TIER_SYSTEM', 'false') == 'true'

if USE_TWO_TIER_SYSTEM:
    # New two-tier pipeline
    validated, rejected = validate_llm_recommendations(...)
else:
    # Old pipeline
    cards = old_generate_recommendations(...)
```

### Step 3: A/B Testing

```python
# Show different UIs to different users
if user.is_beta_tester():
    return render_two_tier_ui(recommendations)
else:
    return render_legacy_ui(recommendations)
```

---

## Support

For issues or questions:

1. Check `RECOMMENDATION_SYSTEM_ARCHITECTURE.md` for system design
2. Review `RECOMMENDATION_SYSTEM_EXAMPLES.md` for usage examples
3. Check logs in `src/recommendation_engine/validator.py`
4. Review validation thresholds in `validator.py`
5. Test with synthetic data in `data/synthetic/`

---

## Next Steps

1. ✅ Review architecture documentation
2. ✅ Understand validation rules
3. ✅ Test with sample data
4. ⬜ Integrate into your pipeline
5. ⬜ Update frontend UI
6. ⬜ Deploy to staging
7. ⬜ Monitor and adjust thresholds
8. ⬜ Gather user feedback
9. ⬜ Optimize based on metrics
10. ⬜ Roll out to production
