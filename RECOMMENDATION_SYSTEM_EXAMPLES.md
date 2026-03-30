# FinOps AI Recommendation System - Examples & Usage

## Quick Start

### 1. Generate Recommendations for an Architecture

```python
from src.api.handlers.analyze import generate_recommendations
from src.graph.models import get_db

# Generate recommendations
result = await generate_recommendations(
    req={"architecture_id": "arch-prod-123"},
    db=next(get_db())
)

print(f"Generated {len(result['recommendations'])} recommendations")
print(f"Total savings: ${result['total_estimated_savings']:.2f}/month")
```

### 2. Separate Engine-Backed vs LLM-Proposed

```python
engine_backed = [r for r in result['recommendations'] if r['source'] == 'engine_backed']
llm_proposed = [r for r in result['recommendations'] if r['source'] == 'llm_proposed']

print(f"Engine-backed (validated): {len(engine_backed)}")
print(f"LLM-proposed (ideas): {len(llm_proposed)}")
```

### 3. Filter by Validation Status

```python
validated = [r for r in result['recommendations'] 
             if r.get('validation_status') == 'validated']
rejected = [r for r in result['recommendations'] 
            if r.get('validation_status') == 'rejected']
conflicts = [r for r in result['recommendations'] 
             if r.get('validation_status') == 'conflict']

print(f"Validated: {len(validated)}")
print(f"Rejected: {len(rejected)}")
print(f"Conflicts: {len(conflicts)}")
```

---

## Example Recommendation Outputs

### Example 1: Engine-Backed EC2 Rightsizing

```json
{
  "title": "Rightsize EC2 instance i-0abc123def456 from m5.2xlarge to m5.xlarge",
  "resource_id": "i-0abc123def456",
  "service_type": "EC2",
  "environment": "production",
  "category": "right-sizing",
  "priority": "HIGH",
  "severity": "high",
  "risk_level": "MEDIUM",
  
  "source": "engine_backed",
  "action": "rightsize_ec2",
  "engine_confidence": 0.92,
  "validation_status": "validated",
  
  "total_estimated_savings": 450.00,
  "current_monthly_cost": 876.00,
  "projected_monthly_cost": 426.00,
  
  "resource_identification": {
    "resource_id": "i-0abc123def456",
    "resource_name": "api-server-prod",
    "service_type": "EC2",
    "environment": "production",
    "region": "us-east-1",
    "current_instance_type": "m5.2xlarge",
    "recommended_instance_type": "m5.xlarge",
    "current_config": "Instance Type: m5.2xlarge | Service: EC2 | Region: us-east-1 | CPU Utilization: 18%"
  },
  
  "cost_breakdown": {
    "current_monthly": 876.00,
    "projected_monthly": 426.00,
    "savings_percentage": 51.4,
    "annual_impact": 5400.00,
    "line_items": [
      {
        "item": "EC2 Instance Cost",
        "usage": "730 hours",
        "cost": 876.00
      }
    ]
  },
  
  "graph_context": {
    "blast_radius_pct": 12.5,
    "blast_radius_services": 3,
    "dependency_count": 2,
    "depends_on_count": 1,
    "dependent_services": ["web-frontend", "mobile-api"],
    "cross_az_count": 0,
    "is_spof": false,
    "cascading_failure_risk": "low",
    "centrality": 0.234,
    "narrative": "Powers 2 downstream service(s). Handling 450 queries/sec."
  },
  
  "recommendations": [
    {
      "title": "Downgrade to m5.xlarge",
      "full_analysis": "Pattern Detected: ec2_underutilized\nCurrent State: m5.2xlarge in us-east-1 (production environment)\nRecommended: Migrate to m5.xlarge\nEstimated Savings: $450.00/month ($5400.00/year)\n\nImpact Analysis: Powers 2 downstream service(s). Handling 450 queries/sec.",
      "implementation_steps": [
        "1. Review current EC2 resource: i-0abc123def456",
        "2. Verify no active deployments depend on current configuration",
        "3. Notify teams owning dependent services: web-frontend, mobile-api",
        "4. Execute change in staging first:",
        "   aws ec2 modify-instance-attribute --instance-id i-0abc123def456 --instance-type m5.xlarge --region us-east-1",
        "5. Monitor CloudWatch metrics for 24h post-change",
        "6. Validate: aws cloudwatch get-metric-statistics --namespace AWS/EC2"
      ],
      "performance_impact": "Savings: $450.00/mo (51.4% reduction). Annual impact: $5400.00/yr",
      "risk_mitigation": "Risk Level: MEDIUM. Impact: 2 dependent service(s) - web-frontend, mobile-api. Always test in staging/dev environment first",
      "estimated_monthly_savings": 450.00,
      "confidence": "high"
    }
  ],
  
  "finops_best_practice": "AWS Well-Architected: Right-size EC2 instances based on actual utilization",
  "why_it_matters": "Powers 2 downstream service(s). Handling 450 queries/sec. CPU utilization at 18% indicates significant over-provisioning."
}
```

### Example 2: LLM-Proposed (Validated) - Dev Environment Campaign

```json
{
  "title": "Schedule all dev EC2 instances to stop nights and weekends",
  "resource_id": "campaign-dev-ec2-schedule",
  "service_type": "EC2",
  "environment": "development",
  "category": "waste-elimination",
  "priority": "MEDIUM",
  "severity": "medium",
  "risk_level": "LOW",
  
  "source": "engine_backed",
  "action": "schedule_ec2_stop",
  "llm_confidence": 0.85,
  "engine_confidence": 0.78,
  "validation_status": "validated",
  "validation_notes": "Validated: Pattern detected across 8 dev instances with no weekend usage",
  
  "total_estimated_savings": 1240.00,
  "justification": "Analysis of CloudWatch metrics shows 8 dev EC2 instances run 24/7 but have zero usage outside business hours (7PM-7AM) and weekends. Implementing stop schedules would reduce runtime by 65%.",
  
  "implementation_steps": [
    "1. Create EventBridge rule for stop schedule: aws events put-rule --name dev-ec2-stop-schedule --schedule-expression 'cron(0 19 ? * MON-FRI *)'",
    "2. Create EventBridge rule for start schedule: aws events put-rule --name dev-ec2-start-schedule --schedule-expression 'cron(0 7 ? * MON-FRI *)'",
    "3. Tag all dev instances: aws ec2 create-tags --resources i-* --tags Key=AutoStop,Value=true",
    "4. Add Lambda function to stop/start tagged instances",
    "5. Monitor for 2 weeks to ensure no disruption"
  ],
  
  "why_this_matters": "8 development EC2 instances run continuously but are only used during business hours. This pattern wastes 65% of compute costs with no business value.",
  "problem": "Dev instances running 24/7 with zero usage outside business hours",
  "solution": "Implement EventBridge-based stop/start schedules for dev environment"
}
```

### Example 3: LLM-Proposed (Rejected)

```json
{
  "title": "Terminate idle EC2 instance i-0xyz789abc123",
  "resource_id": "i-0xyz789abc123",
  "service_type": "EC2",
  "environment": "production",
  "category": "waste-elimination",
  "priority": "LOW",
  "severity": "low",
  "risk_level": "HIGH",
  
  "source": "llm_proposed",
  "action": "terminate_ec2",
  "llm_confidence": 0.65,
  "engine_confidence": null,
  "validation_status": "rejected",
  "validation_notes": "Rejected: P95 CPU 42.3% does not indicate idle instance. Network I/O shows active usage.",
  
  "total_estimated_savings": 320.00,
  "justification": "LLM observed low average CPU (12%) and proposed termination. However, validation revealed P95 CPU at 42% with bursty workload pattern.",
  
  "is_downgraded_due_to_conflict": false,
  "why_this_matters": "This recommendation was rejected by the engine validation layer. Metrics show the instance handles bursty workloads despite low average utilization."
}
```

### Example 4: LLM-Proposed (Conflict with Engine)

```json
{
  "title": "Terminate EC2 instance i-0abc123def456 (idle)",
  "resource_id": "i-0abc123def456",
  "service_type": "EC2",
  "environment": "production",
  "category": "waste-elimination",
  
  "source": "llm_proposed",
  "action": "terminate_ec2",
  "llm_confidence": 0.70,
  "validation_status": "conflict",
  "validation_notes": "Conflicts with engine-backed recommendation on same resource. Engine action: rightsize_ec2",
  
  "is_downgraded_due_to_conflict": true,
  "alternative_to_engine_rec_id": "i-0abc123def456",
  "conflicting_rec_ids": ["i-0abc123def456"],
  
  "total_estimated_savings": 876.00,
  "justification": "LLM proposed termination based on low CPU. Engine determined rightsizing is more appropriate given dependency graph.",
  
  "why_this_matters": "This is an alternative approach to the engine-backed rightsizing recommendation. The engine's recommendation takes precedence due to dependency analysis showing 2 downstream services rely on this instance."
}
```

---

## Usage Patterns

### Pattern 1: Display Validated Recommendations Only

```python
# Frontend: Show only validated recommendations in main tab
validated_recs = [
    r for r in recommendations 
    if r['source'] == 'engine_backed' or r['validation_status'] == 'validated'
]

for rec in validated_recs:
    display_recommendation_card(
        title=rec['title'],
        savings=rec['total_estimated_savings'],
        confidence=rec.get('engine_confidence', rec.get('llm_confidence', 0)),
        badge="Validated" if rec['source'] == 'engine_backed' else "AI Validated",
        badge_color="green"
    )
```

### Pattern 2: Show AI Insights Separately

```python
# Frontend: Show LLM ideas in separate "AI Insights" tab
ai_insights = [
    r for r in recommendations 
    if r['source'] == 'llm_proposed' and r['validation_status'] in ['rejected', 'conflict']
]

for insight in ai_insights:
    display_insight_card(
        title=insight['title'],
        savings=insight['total_estimated_savings'],
        confidence=insight['llm_confidence'],
        badge="AI Insight",
        badge_color="blue",
        validation_notes=insight.get('validation_notes', ''),
        is_experimental=True
    )
```

### Pattern 3: Conflict Warning

```python
# Frontend: Show conflict warnings
conflicts = [r for r in recommendations if r.get('is_downgraded_due_to_conflict')]

for conflict in conflicts:
    engine_rec_id = conflict['alternative_to_engine_rec_id']
    display_conflict_warning(
        llm_title=conflict['title'],
        engine_rec_id=engine_rec_id,
        message=f"This LLM-proposed recommendation conflicts with an engine-backed recommendation on the same resource. The engine's recommendation takes precedence."
    )
```

### Pattern 4: Filter by Service Type

```python
# Get all EC2 recommendations
ec2_recs = [r for r in recommendations if r['service_type'] == 'EC2']

# Get all RDS recommendations
rds_recs = [r for r in recommendations if r['service_type'] == 'RDS']

# Get all storage recommendations
storage_recs = [r for r in recommendations if r['category'] == 'storage']
```

### Pattern 5: Sort by Savings

```python
# Sort by estimated savings (highest first)
sorted_recs = sorted(
    recommendations,
    key=lambda r: r.get('total_estimated_savings', 0),
    reverse=True
)

# Top 10 highest-impact recommendations
top_10 = sorted_recs[:10]
```

---

## API Integration Examples

### Example 1: Generate Recommendations

```bash
curl -X POST http://localhost:8000/analyze/recommendations \
  -H "Content-Type: application/json" \
  -d '{
    "architecture_id": "arch-prod-123"
  }'
```

Response:
```json
{
  "recommendations": [...],
  "total_estimated_savings": 12345.67,
  "llm_used": true,
  "generation_time_ms": 8500,
  "card_count": 12,
  "architecture_name": "Production Architecture"
}
```

### Example 2: Get Last Recommendations

```bash
curl http://localhost:8000/analyze/recommendations/last?architecture_id=arch-prod-123
```

### Example 3: Filter Response

```python
import requests

response = requests.post(
    "http://localhost:8000/analyze/recommendations",
    json={"architecture_id": "arch-prod-123"}
)

data = response.json()

# Separate by source
engine_backed = [r for r in data['recommendations'] if r['source'] == 'engine_backed']
llm_proposed = [r for r in data['recommendations'] if r['source'] == 'llm_proposed']

print(f"Engine: {len(engine_backed)}, LLM: {len(llm_proposed)}")
print(f"Total savings: ${data['total_estimated_savings']:.2f}/month")
```

---

## Testing Examples

### Test 1: Validate LLM Recommendations

```python
from src.recommendation_engine.validator import validate_llm_recommendations

# Simulate LLM proposals
llm_proposals = [
    {
        "resource_id": "i-test123",
        "action": "rightsize_ec2",
        "total_estimated_savings": 100.0,
        "service_type": "EC2",
        "llm_confidence": 0.75
    }
]

# Load test architecture
with open("data/synthetic/test_architecture.json") as f:
    graph_data = json.load(f)

# Validate
validated, rejected = validate_llm_recommendations(llm_proposals, graph_data)

assert len(validated) > 0, "At least one recommendation should validate"
assert all(r['validation_status'] == 'validated' for r in validated)
```

### Test 2: Conflict Resolution

```python
from src.llm.recommendation_card_schema import apply_conflict_resolution

# Create test recommendations
engine_rec = {
    "resource_id": "i-abc123",
    "source": "engine_backed",
    "action": "rightsize_ec2"
}

llm_rec = {
    "resource_id": "i-abc123",
    "source": "llm_proposed",
    "action": "terminate_ec2"
}

recs = [engine_rec, llm_rec]
resolved = apply_conflict_resolution(recs)

# LLM rec should be downgraded
llm_result = [r for r in resolved if r['action'] == 'terminate_ec2'][0]
assert llm_result['is_downgraded_due_to_conflict'] == True
assert llm_result['validation_status'] == 'conflict'
```

### Test 3: Full Pipeline

```python
from src.recommendation_engine.scanner import scan_architecture
from src.recommendation_engine.enricher import enrich_matches
from src.llm.client import generate_recommendations
from src.analysis.context_assembler import ContextAssembler
from src.analysis.graph_analyzer import GraphAnalyzer

# Load architecture
with open("data/synthetic/production.json") as f:
    graph_data = json.load(f)

# Run full pipeline
analyzer = GraphAnalyzer(graph_data)
report = analyzer.analyze()

assembler = ContextAssembler(graph_data, report)
context_package = assembler.assemble()

result = generate_recommendations(
    context_package=context_package,
    architecture_name="Test Architecture",
    raw_graph_data=graph_data
)

# Verify results
assert len(result.cards) > 0
assert result.total_estimated_savings > 0
assert result.llm_used == True

# Check source distribution
sources = [c.get('source') for c in result.cards]
assert 'engine_backed' in sources
assert 'llm_proposed' in sources or len([s for s in sources if s == 'engine_backed']) == len(sources)
```

---

## Frontend Integration Examples

### React Component Example

```jsx
import React, { useState, useEffect } from 'react';
import { generateRecommendations } from './api/client';

function RecommendationDashboard({ architectureId }) {
  const [recommendations, setRecommendations] = useState([]);
  const [activeTab, setActiveTab] = useState('validated');
  
  useEffect(() => {
    async function loadRecs() {
      const result = await generateRecommendations(architectureId);
      setRecommendations(result.recommendations);
    }
    loadRecs();
  }, [architectureId]);
  
  const validatedRecs = recommendations.filter(r => 
    r.source === 'engine_backed' || r.validation_status === 'validated'
  );
  
  const aiInsights = recommendations.filter(r => 
    r.source === 'llm_proposed' && 
    ['rejected', 'conflict'].includes(r.validation_status)
  );
  
  return (
    <div>
      <div className="tabs">
        <button onClick={() => setActiveTab('validated')}>
          Validated Recommendations ({validatedRecs.length})
        </button>
        <button onClick={() => setActiveTab('insights')}>
          AI Insights ({aiInsights.length})
        </button>
      </div>
      
      {activeTab === 'validated' && (
        <div>
          {validatedRecs.map(rec => (
            <RecommendationCard
              key={rec.resource_id}
              {...rec}
              badge={rec.source === 'engine_backed' ? 'Validated' : 'AI Validated'}
              badgeColor="green"
            />
          ))}
        </div>
      )}
      
      {activeTab === 'insights' && (
        <div>
          {aiInsights.map(rec => (
            <InsightCard
              key={rec.resource_id}
              {...rec}
              badge="AI Insight"
              badgeColor="blue"
              validationNotes={rec.validation_notes}
            />
          ))}
        </div>
      )}
    </div>
  );
}
```

---

## Common Scenarios

### Scenario 1: All Recommendations are Engine-Backed

**Situation**: LLM didn't propose any new ideas, or all LLM proposals were rejected.

**Response**:
```json
{
  "recommendations": [
    // All have source: "engine_backed"
  ],
  "total_estimated_savings": 5000.00,
  "llm_used": true
}
```

**Interpretation**: The deterministic engine found all optimization opportunities. This is normal for well-optimized architectures.

### Scenario 2: Mix of Engine and Validated LLM

**Situation**: LLM proposed new ideas that passed validation.

**Response**:
```json
{
  "recommendations": [
    { "source": "engine_backed", ... },
    { "source": "engine_backed", "validation_status": "validated", "llm_confidence": 0.85, ... }
  ]
}
```

**Interpretation**: Best case - engine found core issues, LLM found additional patterns that validated.

### Scenario 3: LLM Conflicts with Engine

**Situation**: LLM proposed termination, engine proposed rightsizing on same resource.

**Response**:
```json
{
  "recommendations": [
    { "source": "engine_backed", "action": "rightsize_ec2", "resource_id": "i-abc123" },
    { 
      "source": "llm_proposed", 
      "action": "terminate_ec2", 
      "resource_id": "i-abc123",
      "validation_status": "conflict",
      "is_downgraded_due_to_conflict": true
    }
  ]
}
```

**Interpretation**: Show engine rec in main tab, LLM rec in "Alternative Ideas" section with conflict warning.

---

## Troubleshooting

### Issue: No Recommendations Generated

**Check**:
1. Are there resources in the architecture graph?
2. Do resources have metrics (CPU, memory, cost)?
3. Are detector thresholds too strict?

**Solution**:
```python
# Check graph data
print(f"Services: {len(graph_data.get('services', []))}")
print(f"Nodes: {len(graph_data.get('nodes', []))}")

# Check if scanner finds matches
from src.recommendation_engine.scanner import scan_architecture
matches = scan_architecture(graph_data)
print(f"Scanner found {len(matches)} matches")
```

### Issue: All LLM Recommendations Rejected

**Check**:
1. Are validation thresholds too strict?
2. Are metrics available in graph data?
3. Is LLM proposing unrealistic savings?

**Solution**:
```python
# Review validation thresholds
from src.recommendation_engine.validator import VALIDATION_THRESHOLDS
print(VALIDATION_THRESHOLDS)

# Check rejected recommendations
rejected = [r for r in recommendations if r['validation_status'] == 'rejected']
for r in rejected:
    print(f"{r['title']}: {r['validation_notes']}")
```

### Issue: Too Many Conflicts

**Check**:
1. Is LLM proposing on same resources as engine?
2. Are action types conflicting (terminate vs rightsize)?

**Solution**: This is expected behavior. Engine-backed always wins. Show LLM conflicts as "alternative ideas" in UI.

---

## Best Practices

1. **Always separate validated from insights in UI**
2. **Show validation_notes for rejected recommendations**
3. **Use confidence scores to prioritize**
4. **Display conflict warnings clearly**
5. **Allow users to provide feedback on LLM insights**
6. **Track which recommendations were implemented**
7. **Measure actual savings vs estimated**

---

## Next Steps

1. Review `RECOMMENDATION_SYSTEM_ARCHITECTURE.md` for system design
2. Check `src/recommendation_engine/validator.py` for validation rules
3. Explore `src/llm/recommendation_card_schema.py` for data structures
4. Test with your own architecture data
5. Customize thresholds in `validator.py` as needed
