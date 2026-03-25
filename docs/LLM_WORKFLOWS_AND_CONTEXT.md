# FinOps AI System: LLM Workflows, Context & Logic - Complete Guide

**Document Version:** 2.0  
**Last Updated:** March 2026  
**Scope:** Comprehensive documentation of LLM integration, context pipeline, and recommendation generation

## Table of Contents

1. [System Overview](#system-overview)
2. [The 8-Section Context Package](#the-8-section-context-package)
3. [LLM Input Structure & Construction](#llm-input-structure--construction)
4. [5-Agent Sequential Pipeline](#5-agent-sequential-pipeline)
5. [Workflow Pipeline Architecture](#workflow-pipeline-architecture)
6. [Prompt Templates & System Instructions](#prompt-templates--system-instructions)
7. [RAG System & Knowledge Grounding](#rag-system--knowledge-grounding)
8. [Recommendation Generation & Output Formatting](#recommendation-generation--output-formatting)
9. [Error Handling & Caching Strategy](#error-handling--caching-strategy)
10. [Performance & Timing](#performance--timing)

---

## System Overview

The FinOps AI system is a **production-grade AWS cost optimization engine** that generates 10-15 precise, actionable recommendations using a sophisticated 5-agent sequential LLM pipeline.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    User API Request                             │
│               POST /api/analyze                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │
              ┌────────────▼─────────────┐
              │   GraphAnalyzer          │
              │ - Load AWS infrastructure│
              │ - Build dependency graph │
              │ - Extract metrics        │
              └────────────┬─────────────┘
                           │
              ┌────────────▼──────────────────┐
              │ ContextAssembler             │
              │ Build 8-Section Context Pkg  │
              │ - Architecture overview      │
              │ - Critical services          │
              │ - Cost analysis              │
              │ - Anti-patterns              │
              │ - Risk assessment            │
              │ - Behavioral anomalies       │
              │ - Historical trends          │
              │ - Dependency analysis        │
              └────────────┬──────────────────┘
                           │
        ┌──────────────────┼──────────────────────────┐
        │                  │                          │
   ┌────▼───────┐  ┌──────▼──────┐  ┌───────▼────┐
   │ Agent 1    │  │ Agent 2      │  │ Agent 3    │
   │ Topology   │  │ Behavior     │  │ Cost       │
   │ Analyst    │  │ Scientist    │  │ Economist  │
   └────┬───────┘  └──────┬───────┘  └───────┬────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                  ┌───────▼────────┐
                  │ Agent 4        │
                  │ Risk Detective │
                  └───────┬────────┘
                          │
                  ┌───────▼──────────────┐
                  │ Agent 5              │
                  │ Executive Synthesizer│
                  └───────┬──────────────┘
                          │
            ┌─────────────▼─────────────┐
            │ RecommendationParser      │
            │ - Extract fields via regex│
            │ - Validate against inv.   │
            │ - Deduplicate            │
            │ - Filter zero-savings    │
            └─────────────┬─────────────┘
                          │
           ┌──────────────┼──────────────┐
           │              │              │
      ┌────▼────┐  ┌──────▼──┐  ┌───────▼────┐
      │ Redis   │  │PostgreSQL│  │  JSON      │
      │ Cache   │  │ History  │  │  Response  │
      │ (24h)   │  │  DB      │  │  to User   │
      └─────────┘  └──────────┘  └────────────┘
```

---

## The 8-Section Context Package

The `ArchitectureContextPackage` is the central data structure that builds rich context for LLM analysis. It contains 8 distinct sections that provide comprehensive AWS infrastructure understanding.

### Section 1: Architecture Overview
**Purpose:** High-level metadata about the analyzed infrastructure

```python
{
    "metadata": {
        "account_id": "123456789",
        "region": "us-east-1",
        "total_services": 24,
        "total_monthly_cost": 15750.00,
        "cost_currency": "USD"
    },
    "service_inventory": {
        "ec2_instances": 12,
        "rds_databases": 3,
        "lambda_functions": 45,
        "s3_buckets": 8,
        "dynamodb_tables": 6,
        "cloudfront_distributions": 2,
        "vpcs": 2,
        "security_groups": 18
    },
    "cost_summary": {
        "compute": 7200.00,
        "database": 3500.00,
        "storage": 1800.00,
        "networking": 1250.00,
        "other": 2000.00
    }
}
```

**Why included:** Grounds the LLM with actual infrastructure scope and prevents hallucinations about non-existent services.

### Section 2: Critical Services (by Centrality)
**Purpose:** Identifies which services are most important to the infrastructure

```python
{
    "critical_services": [
        {
            "service_id": "prod-api-alb",
            "service_type": "ApplicationLoadBalancer",
            "centrality_score": 0.95,
            "dependent_count": 18,
            "monthly_cost": 45.00,
            "risk_level": "CRITICAL",
            "dependencies": [
                "prod-api-asg",
                "prod-web-asg",
                "analytics-lambda"
            ]
        },
        {
            "service_id": "prod-rds-main",
            "service_type": "RDSDatabase",
            "centrality_score": 0.92,
            "dependent_count": 16,
            "monthly_cost": 2100.00,
            "risk_level": "CRITICAL",
            "dependencies": ["prod-api-asg", "batch-processor"]
        }
    ]
}
```

**Why included:** Helps LLM prioritize recommendations on high-impact services where changes could affect multiple downstream services.

### Section 3: Cost Analysis
**Purpose:** Identifies spending anomalies, waste, and cost drivers

```python
{
    "cost_analysis": {
        "monthly_breakdown": {
            "2024-01": 15200.00,
            "2024-02": 15400.00,
            "2024-03": 16100.00,
            "2024-04": 15750.00
        },
        "cost_outliers": [
            {
                "resource_id": "prod-data-warehouse",
                "resource_type": "RedshiftCluster",
                "monthly_cost": 3200.00,
                "trend": "stable",
                "variance_from_mean": 1.8,
                "potential_waste": "dc2.large instances underutilized at 35% CPU"
            },
            {
                "resource_id": "analytics-s3-bucket",
                "resource_type": "S3Storage",
                "monthly_cost": 850.00,
                "trend": "increasing",
                "variance_from_mean": 2.1,
                "potential_waste": "Old logs in STANDARD class, should move to INTELLIGENT_TIERING"
            }
        ],
        "cost_trends": {
            "compute_trend": "increasing",
            "storage_trend": "stable",
            "database_trend": "increasing",
            "networking_trend": "stable"
        }
    }
}
```

**Why included:** Provides LLM with concrete evidence of where money is being spent inefficiently, enabling data-driven recommendations.

### Section 4: Anti-Patterns Detected
**Purpose:** Identifies AWS best practice violations and architectural anti-patterns

```python
{
    "anti_patterns": [
        {
            "pattern_name": "Chatty_Architecture",
            "severity": "HIGH",
            "affected_services": ["api-service", "auth-service", "user-service"],
            "description": "Services making synchronous calls in chain, causing latency",
            "evidence": "Request traces show avg 450ms latency across 5 service hops",
            "recommendation_category": "architecture-modernization"
        },
        {
            "pattern_name": "No_Auto_Scaling",
            "severity": "MEDIUM",
            "affected_services": ["batch-processor", "data-pipeline"],
            "description": "Services with fixed sizing that don't scale with demand",
            "evidence": "CPU utilization ranges 5% to 92%, avg 45%",
            "recommendation_category": "scaling-optimization"
        },
        {
            "pattern_name": "Unoptimized_Instance_Types",
            "severity": "MEDIUM",
            "affected_services": ["legacy-api", "web-server"],
            "description": "Running on m5.xlarge when t3.large sufficient",
            "evidence": "Memory utilization avg 18%, CPU avg 8%",
            "recommendation_category": "compute-rightsizing"
        }
    ]
}
```

**Why included:** Grounds recommendations in actual anti-pattern detection, not generic suggestions. LLM explains why change is needed based on real patterns.

### Section 5: Risk Assessment
**Purpose:** Identifies infrastructure vulnerabilities and failure modes

```python
{
    "risk_assessment": {
        "single_points_of_failure": [
            {
                "component": "prod-api-rds",
                "description": "Single RDS instance, no Multi-AZ deployment",
                "impact": "CRITICAL - Complete API outage if DB fails",
                "recommended_mitigation": "Enable Multi-AZ for automatic failover"
            },
            {
                "component": "internet-gateway",
                "description": "Single IGW, no redundancy",
                "impact": "CRITICAL - No internet access if IGW fails",
                "recommended_mitigation": "N/A - AWS manages IGW redundancy internally"
            }
        ],
        "deep_dependency_chains": [
            {
                "chain": "User → ALB → ASG → RDS → Elasticache",
                "chain_length": 5,
                "risk": "Latency amplification, cascading failures",
                "max_latency_observed": "450ms"
            }
        ],
        "availability_zones": {
            "us-east-1a": 8,
            "us-east-1b": 6,
            "us-east-1c": 4,
            "imbalance": "HIGH - uneven distribution"
        }
    }
}
```

**Why included:** Ensures LLM recommends changes that improve resilience, not just cost savings. Prioritizes stability.

### Section 6: Behavioral Anomalies
**Purpose:** Identifies unexpected patterns in application behavior and performance

```python
{
    "behavioral_anomalies": {
        "metrics_anomalies": [
            {
                "metric": "api-response-time-p99",
                "baseline": 150,
                "observed": 450,
                "anomaly_type": "spike",
                "frequency": "Occurs 3x per day around 2-4 PM UTC",
                "correlation": "Correlates with batch processing jobs starting",
                "metadata": {
                    "affected_endpoints": ["/api/v1/reports", "/api/v1/analytics"],
                    "user_impact_severity": "HIGH"
                }
            }
        ],
        "traffic_patterns": {
            "peak_traffic_time": "2:00-4:00 PM UTC",
            "peak_traffic_volume": 15000,
            "baseline_traffic": 5000,
            "peak_to_baseline_ratio": 3.0,
            "resource_scaling_readiness": "POOR - ASG scales too slowly"
        },
        "error_patterns": [
            {
                "error_type": "DatabaseConnectionPoolExhausted",
                "frequency_per_day": 5,
                "affected_service": "api-service",
                "root_cause": "N+1 queries in batch job",
                "current_workaround": "Manual restart required"
            }
        ]
    }
}
```

**Why included:** Helps LLM identify performance issues before they become reliability problems. Guides bottleneck optimization recommendations.

### Section 7: Historical Trends
**Purpose:** Provides time-series data showing how infrastructure has evolved

```python
{
    "historical_trends": {
        "cost_trend_6_months": {
            "month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            "cost": [14500, 14800, 15200, 15400, 16100, 15750],
            "trend_direction": "upward",
            "trend_rate": "+4.2% average month-over-month"
        },
        "service_growth": {
            "lambda_invocations_trend": "increasing",
            "lambda_invocations_rate": "+15% YoY",
            "ec2_instance_count_trend": "stable",
            "s3_storage_trend": "increasing",
            "s3_storage_rate": "+8% month-over-month"
        },
        "performance_trend": {
            "api_latency_trend": "degrading",
            "api_latency_rate": "+12% over 6 months",
            "error_rate_trend": "stable",
            "availability_trend": "stable"
        }
    }
}
```

**Why included:** Shows LLM whether infrastructure is optimized over time or degrading. Contextualizes need for architectural improvements.

### Section 8: Dependency Analysis
**Purpose:** Maps all service-to-service relationships and communication patterns

```python
{
    "dependency_analysis": {
        "service_graph": {
            "nodes": [
                {"id": "prod-api", "type": "ApiServer", "cost": 500},
                {"id": "prod-rds", "type": "Database", "cost": 2100},
                {"id": "prod-cache", "type": "Cache", "cost": 300},
                {"id": "s3-assets", "type": "Storage", "cost": 400}
            ],
            "edges": [
                {"from": "prod-api", "to": "prod-rds", "relationship": "read-write", "latency_p99": 45},
                {"from": "prod-api", "to": "prod-cache", "relationship": "read", "latency_p99": 5},
                {"from": "prod-api", "to": "s3-assets", "relationship": "read", "latency_p99": 120}
            ]
        },
        "communication_patterns": {
            "synchronous_calls": 85,
            "asynchronous_calls": 15,
            "queue_bottlenecks": [
                {
                    "queue": "image-processing",
                    "avg_processing_time": 45,
                    "queue_depth": 2500,
                    "max_depth_observed": 8000
                }
            ]
        },
        "network_topology": {
            "cross_az_traffic": "18%",
            "cross_region_traffic": "0%",
            "cross_az_traffic_cost": 120
        }
    }
}
```

**Why included:** Allows LLM to understand communication overhead and suggest architecture changes that reduce latency and cross-AZ costs.

---

## LLM Input Structure & Construction

### Input Flow - How Data is Packaged for LLM

```
┌─ AWS APIs ─────────────────────┐
│ • CloudFormation               │
│ • EC2/RDS/Lambda/etc metrics   │
│ • CloudWatch metrics           │
│ • Pricing API                  │
└─────────────┬──────────────────┘
              │
     ┌────────▼──────────┐
     │ GraphAnalyzer     │
     │ Builds dependency  │
     │ graph & metrics    │
     └────────┬──────────┘
              │
     ┌────────▼──────────────────┐
     │ ContextAssembler           │
     │ • Aggregates 8 sections    │
     │ • Validates data           │
     │ • Enriches with insights   │
     └────────┬──────────────────┘
              │
     ┌────────▼──────────────────────────────┐
     │ LLM Input Prompt Construction         │
     │                                       │
     │ System Prompt + Context Package +    │
     │ Task Instructions + Examples          │
     └───────────────────────────────────────┘
```

### Each Agent Receives Different Context

**Agent 1: Topology Analyst**
```
System Prompt: "You are an AWS infrastructure expert..."
Context Provided:
- Architecture Overview (Section 1)
- Critical Services (Section 2)
- Dependency Analysis (Section 8)
- Risk Assessment single points of failure (Section 5)
- Knowledge Base: AWS best practices for resilience

Task: "Analyze the infrastructure topology and identify single points of failure, bottlenecks, and deep dependency chains"
```

**Agent 2: Behavior Scientist**
```
System Prompt: "You are a cloud performance analyst..."
Context Provided:
- Behavioral Anomalies (Section 6)
- Historical Trends (Section 7)
- Risk Assessment availability zones (Section 5)
- Cost Analysis trends (Section 3)
- Knowledge Base: Behavioral patterns in cloud systems

Task: "Identify unusual patterns, traffic spikes, scaling issues, and performance degradation"
```

**Agent 3: Cost Economist**
```
System Prompt: "You are an AWS cost optimization specialist..."
Context Provided:
- Cost Analysis (Section 3)
- Architecture Overview (Section 1)
- Anti-Patterns (Section 4)
- Historical Trends (Section 7)
- Knowledge Base: Pricing models, instance families, reserved instances

Task: "Analyze spending patterns, identify waste, and calculate potential cost savings"
```

**Agent 4: Risk Detective**
```
System Prompt: "You are a risk and security analyst..."
Context Provided:
- Risk Assessment (Section 5)
- Anti-Patterns (Section 4)
- Dependency Analysis (Section 8)
- Findings from Agents 1-3 (cascading context)
- Knowledge Base: AWS resilience patterns, disaster recovery

Task: "Synthesize findings from topology, behavior, and cost analysis to identify root causes"
```

**Agent 5: Executive Synthesizer**
```
System Prompt: "You are a cloud solutions architect..."
Context Provided:
- ALL 8 context sections combined
- Findings from Agents 1-4 (full cascade)
- Knowledge Base: Implementation strategies, ROI calculations

Task: "Synthesize all findings into 10-15 prioritized, actionable recommendations with savings estimates"
```

### LLM Call Structure

Each agent receives:

```python
llm_input = {
    "model": "qwen2.5-7b",
    "temperature": 0.7,  # Balanced: creative but grounded
    "max_tokens": 2000,
    "system_prompt": f"""
        {BASE_SYSTEM_PROMPT}
        
        ## GROUNDING CONSTRAINT
        You MUST ONLY make claims supported by the provided context data.
        Do not hallucinate services, metrics, or costs not in the data.
        
        ## PROVIDED CONTEXT
        {json.dumps(context_package, indent=2)}
        
        ## PREVIOUS AGENT FINDINGS
        {previous_agent_outputs}
    """,
    "user_message": f"""
        {TASK_INSTRUCTIONS}
        
        Provide your analysis in the following format:
        
        ### Finding Title
        **Severity:** [CRITICAL|HIGH|MEDIUM|LOW]
        **Category:** [category]
        **Evidence:** [data from context]
        **Impact:** [business impact]
        **Recommendation:** [action]
    """
}

response = ollama.generate(llm_input)
```

---

## 5-Agent Sequential Pipeline

### Why 5 Agents? The Reasoning

The system uses **5 specialized agents instead of 1 general agent** because:

1. **Specialization improves quality** - Each agent has focused expertise (topology, behavior, cost, risk, synthesis)
2. **Separation of concerns** - Different aspects analyzed independently, then combined
3. **Cascading context** - Later agents have access to earlier findings, enabling root cause analysis
4. **Better hallucination prevention** - Each agent has specific grounding constraints
5. **Parallelizable outputs** - Agents 1-3 run in parallel (though sequentially in pipeline)

### Agent 1: Topology Analyst

**Input Context:** Sections 1, 2, 8 + Risk (SPOFs)  
**Focus:** Infrastructure structure and connectivity

**Analyzes:**
- Single Points of Failure (SPOFs)
  ```
  Example Finding:
  - Service: prod-api-rds
  - Issue: Single RDS instance with no Multi-AZ
  - Impact: Complete API outage if instance fails
  - Severity: CRITICAL
  ```
- Deep dependency chains
  ```
  Example Finding:
  - Chain: ALB → ASG → RDS → Cache
  - Deep chains (4+ hops) amplify latency
  - Latency observed: 450ms end-to-end
  ```
- Availability zone imbalance
  ```
  Example Finding:
  - AZ distribution: 8 in us-east-1a, 6 in 1b, 4 in 1c
  - Imbalanced → if 1a fails, load on 1b/1c overwhelms
  ```

**Output:** Topology findings used by Agent 4

### Agent 2: Behavior Scientist

**Input Context:** Sections 3, 6, 7 + Risk (AZ analysis)  
**Focus:** Performance and operational patterns

**Analyzes:**
- Traffic spike anomalies
  ```
  Example Finding:
  - Spike: P99 latency 150ms → 450ms at 2-4 PM UTC
  - Correlation: Batch jobs consume 80% of database connections
  - Symptom: Queue backlog grows to 8,000 items
  ```
- Scaling failures
  ```
  Example Finding:
  - Traffic increases 3x during peak (15k req/s vs baseline 5k)
  - ASG takes 45 seconds to add instances
  - During this time, requests queue up (connection pool exhaustion)
  ```
- Error pattern trends
  ```
  Example Finding:
  - DatabaseConnectionPoolExhausted: 5x per day
  - Pattern: Always after batch job starts (N+1 queries)
  ```

**Output:** Behavior findings used by Agent 4

### Agent 3: Cost Economist

**Input Context:** Sections 1, 3, 4, 7  
**Focus:** Spending patterns and optimization opportunities

**Analyzes:**
- Cost outliers with potential waste
  ```
  Example Finding:
  - Resource: prod-data-warehouse (Redshift)
  - Cost: $3,200/month
  - Utilization: 35% CPU, 28% Memory
  - Opportunity: Resize to smaller cluster or switch to Athena
  - Potential Savings: $1,600-2,000/month
  ```
- Usage trend analysis
  ```
  Example Finding:
  - S3 storage increasing 8% month-over-month
  - Old logs stored in STANDARD (expensive)
  - Should transition to INTELLIGENT_TIERING or delete old logs
  - Potential Savings: $280/month
  ```
- Reserved instance opportunities
  ```
  Example Finding:
  - 45 Lambda invocations/second baseline (consistent)
  - On-demand cost: $1,200/month
  - Reserved instances cost: $720/month (40% savings)
  ```

**Output:** Cost findings used by Agent 4

### Agent 4: Risk Detective

**Input Cascade:** All 8 sections + Agent 1/2/3 findings  
**Focus:** Root cause synthesis and risk prioritization

**Synthesizes:**
- Topology issues + Behavior issues + Cost issues
  ```
  Example Synthesis:
  
  Finding: Performance degradation at peak traffic
  
  Root Cause Chain:
  1. (From Agent 1) Single RDS instance (SPOF)
  2. (From Agent 2) Spike causes connection pool exhaustion
  3. (From Agent 3) Compute not sized for peak load
  
  Risk: During spike, if RDS fails, system complete loss
  Priority: CRITICAL
  ```
- Cross-domain impact analysis
  ```
  Example:
  
  Deep dependency chain (Agent 1) +
  Batch job contention (Agent 2) +
  Undersized instances (Agent 3)
  = Cascading failure risk during peak periods
  ```

**Output:** Prioritized risks for Agent 5

### Agent 5: Executive Synthesizer

**Input Cascade:** All context + All 4 agent findings  
**Focus:** Generate final, prioritized recommendations

**Produces:**
```
### Recommendation 1: Enable Multi-AZ for Prod RDS
**Priority:** CRITICAL (blocks resilience)
**Severity:** 1 of 15

**Context:**
- Issue: Single RDS instance is SPOF (Agent 1)
- Blocked by: This SPOF prevents scaling (Agent 2)
- Cost Impact: Failover means manual intervention = downtime cost
- Environment: us-east-1, prod

**Implementation:** 
- Modify RDS to Multi-AZ
- Expected downtime: 1-2 minutes during failover test
- Time to implement: 30 minutes
- Cost increase: +$840/month for redundancy

**Expected Benefit:**
- Automatic failover (2-3 min vs manual 30+ min)
- Enables confidence in Auto Scaling
- Reduces risk from 9.0 to 4.0 (risk scale 1-10)

---

### Recommendation 2: Implement Connection Pooling for Batch Jobs
**Priority:** HIGH (fixes behavior anomalies)
**Severity:** 2 of 15

**Context:**
- Issue: Batch jobs cause connection pool exhaustion (Agent 2)
- Root Cause: N+1 queries causing high connection count (Agent 2)
- Impact: All requests experience 450ms+ latency (Agent 2)
- Cost impact: Scaling inefficiency = extra instances (Agent 3)

**Implementation:**
- Add connection pool management in batch service
- Expected latency improvement: 350ms → 50ms
- Time to implement: 4 hours development + 2 hours testing

**Expected Benefit:**
- Peak latency reduced 450ms → 50ms
- Improved user experience
- Enables more efficient horizontal scaling

---

### Recommendation 3: Resize Redshift Cluster
**Priority:** MEDIUM (cost optimization)
**Severity:** 3 of 15

**Context:**
- Issue: Redshift cluster at 35% CPU, 28% memory (Agent 3)
- Current: dc2.large cluster, $3,200/month
- Alternative: dc2.medium cluster, $1,600/month
- Query performance: Will improve (less contention)

**Implementation:**
- Resize dc2.large → dc2.medium
- Downtime: 5-10 minutes (during maintenance window)
- Time to implement: 45 minutes

**Expected Benefit:**
- Cost savings: $1,600/month ($19,200/year)
- Improved performance (less contention)
- Zero functional impact
```

**Why this structure:** 5 agents find specific issues, then synthesizer creates holistic recommendations with interdependencies and priorities resolved.

---

## Workflow Pipeline Architecture

### Step-by-Step Execution Flow

#### Step 1: Request Ingestion

```python
POST /api/analyze
{
    "account_id": "123456789",
    "region": "us-east-1"
}
```

#### Step 2: Check Cache

```python
cache_key = f"analysis:{account_id}:{region}"
cached_analysis = redis.get(cache_key)
if cached_analysis and not expired(cached_analysis):
    return cached_analysis  # Fast path: 10ms
```

**Why:** Most AWS accounts don't change rapidly. Caching avoids 2+ minute LLM pipeline every request.

#### Step 3: Graph Analysis (if not cached)

```python
graph_analyzer = GraphAnalyzer(account_id, region)

# Fetch AWS data
infrastructure = graph_analyzer.fetch_aws_infrastructure()
# Returns: EC2, RDS, Lambda, S3, etc. resources

cost_data = graph_analyzer.fetch_cost_data()
# Returns: Costs per resource, pricing data

metrics = graph_analyzer.fetch_cloudwatch_metrics()
# Returns: CPU, memory, latency, error rates, traffic

# Build dependency graph
graph = graph_analyzer.build_dependency_graph(infrastructure)
# Returns: Nodes (services) + Edges (dependencies)

# Calculate centrality
centrality_scores = graph_analyzer.calculate_centrality(graph)
# Returns: Importance scores for each service
```

**Output:** Raw infrastructure data, costs, metrics, graph

#### Step 4: Context Assembly

```python
context_assembler = ContextAssembler(
    infrastructure,
    cost_data,
    metrics,
    graph,
    centrality_scores
)

# Build 8-section context package
context_package = context_assembler.assemble()

# context_package contains:
# 1. Architecture Overview
# 2. Critical Services
# 3. Cost Analysis
# 4. Anti-Patterns
# 5. Risk Assessment
# 6. Behavioral Anomalies
# 7. Historical Trends
# 8. Dependency Analysis
```

**Output:** Complete ArchitectureContextPackage

#### Step 5: Agent 1 - Topology Analysis

```python
agent_1_prompt = f"""
{TOPOLOGY_ANALYST_SYSTEM_PROMPT}

GROUNDING DATA:
{json.dumps({
    "section_1_architecture": context_package.architecture_overview,
    "section_2_critical_services": context_package.critical_services,
    "section_8_dependencies": context_package.dependency_analysis,
    "section_5_risks": context_package.risk_assessment["single_points_of_failure"]
})}

TASK: Analyze topology and identify SPOFs, deep chains, availability zone imbalances
"""

topology_findings = ollama.generate(
    model="qwen2.5-7b",
    prompt=agent_1_prompt,
    temperature=0.7,
    max_tokens=2000
)
```

**Output:** Topology findings (e.g., "Single RDS SPOF in prod", "5-hop chain identified")

#### Step 6: Agent 2 - Behavior Analysis

```python
agent_2_prompt = f"""
{BEHAVIOR_SCIENTIST_SYSTEM_PROMPT}

GROUNDING DATA:
{json.dumps({
    "section_3_costs": context_package.cost_analysis,
    "section_6_anomalies": context_package.behavioral_anomalies,
    "section_7_trends": context_package.historical_trends,
    "section_5_risks_az": context_package.risk_assessment["availability_zones"]
})}

TASK: Identify performance anomalies, scaling failures, error patterns
"""

behavior_findings = ollama.generate(model="qwen2.5-7b", prompt=agent_2_prompt)
```

**Output:** Behavior findings (e.g., "Spike to 450ms P99 at 2-4 PM UTC")

#### Step 7: Agent 3 - Cost Analysis

```python
agent_3_prompt = f"""
{COST_ECONOMIST_SYSTEM_PROMPT}

GROUNDING DATA:
{json.dumps({
    "section_1_overview": context_package.architecture_overview,
    "section_3_analysis": context_package.cost_analysis,
    "section_4_antipatterns": context_package.anti_patterns,
    "section_7_trends": context_package.historical_trends
})}

TASK: Identify cost waste, optimization opportunities, savings calculations
"""

cost_findings = ollama.generate(model="qwen2.5-7b", prompt=agent_3_prompt)
```

**Output:** Cost findings (e.g., "Redshift at 35% util → $1,600/mo savings possible")

#### Step 8: Agent 4 - Risk Synthesis

```python
agent_4_prompt = f"""
{RISK_DETECTIVE_SYSTEM_PROMPT}

GROUNDING DATA:
{json.dumps(context_package.dict())}

PREVIOUS FINDINGS:
- Topology: {topology_findings}
- Behavior: {behavior_findings}
- Cost: {cost_findings}

TASK: Synthesize into root causes and risk priorities
"""

risk_synthesis = ollama.generate(model="qwen2.5-7b", prompt=agent_4_prompt)
```

**Output:** Risk synthesis (e.g., "Root cause: SPOF + contention + undersizing")

#### Step 9: Agent 5 - Executive Synthesis

```python
agent_5_prompt = f"""
{EXECUTIVE_SYNTHESIZER_SYSTEM_PROMPT}

GROUNDING DATA:
{json.dumps(context_package.dict())}

ALL PREVIOUS FINDINGS:
- Topology: {topology_findings}
- Behavior: {behavior_findings}
- Cost: {cost_findings}
- Risks: {risk_synthesis}

TASK: Generate 10-15 prioritized, actionable recommendations with savings estimates

FORMAT EACH RECOMMENDATION:
### Recommendation [#]: [Title]
**Priority:** [CRITICAL|HIGH|MEDIUM|LOW]
**Context:** [why needed]
**Implementation:** [how to do it]
**Benefit:** [expected outcome]
**Savings:** $[monthly savings or risks reduced]
"""

final_recommendations = ollama.generate(
    model="qwen2.5-7b",
    prompt=agent_5_prompt,
    max_tokens=4000
)
```

**Output:** Final recommendations (10-15 items)

#### Step 10: Recommendation Parsing

```python
parser = RecommendationParser(final_recommendations)

recommendations = parser.parse()
# 3-strategy parsing:
# Strategy 1: Split by "### Recommendation #N" (best accuracy)
# Strategy 2: Split by any "### [Title]" 
# Strategy 3: Split by "---" delimiter

# For each recommendation:
for rec in recommendations:
    # Extract fields via regex
    rec.title = extract_regex(rec, r"^\s*###\s*Recommendation\s*\d+:\s*(.+)")
    rec.priority = extract_regex(rec, r"\*\*Priority:\*\*\s*(\w+)")
    rec.context = extract_regex(rec, r"\*\*Context:\*\*\s*(.+?)(?=\*\*|$)")
    rec.implementation = extract_regex(rec, r"\*\*Implementation:\*\*(.+?)(?=\*\*|$)")
    rec.benefits = extract_regex(rec, r"\*\*Benefit:\*\*(.+?)(?=\*\*|$)")
    rec.savings = extract_regex(rec, r"\$\d+[,\d]*")
    
    # Validate against inventory
    if not is_valid_service_in_inventory(rec.affected_service):
        rec.status = "INVALID_SERVICE"
        continue
    
    # Deduplicate
    if rec not in parsed_recommendations:
        parsed_recommendations.append(rec)
    
    # Filter zero-savings
    if rec.savings == 0 and rec.priority not in ["CRITICAL", "HIGH"]:
        continue

return parsed_recommendations  # Returns 8-15 recommendations
```

**Output:** Parsed recommendations structure

#### Step 11: Caching & Storage

```python
# Store in Redis (24-hour TTL for quick access)
redis.setex(
    key=f"analysis:{account_id}:{region}",
    time=86400,  # 24 hours
    value=json.dumps(parsed_recommendations)
)

# Store in PostgreSQL (history for trends)
analysis_history.insert({
    "account_id": account_id,
    "region": region,
    "timestamp": now(),
    "recommendations": parsed_recommendations,
    "context_package": context_package,
    "llm_findings": {
        "topology": topology_findings,
        "behavior": behavior_findings,
        "cost": cost_findings,
        "risk": risk_synthesis
    }
})
```

#### Step 12: Response Formatting

```python
response = {
    "status": "success",
    "account_id": account_id,
    "region": region,
    "analyzed_at": now(),
    "recommendations": [
        {
            "id": 1,
            "title": "Enable Multi-AZ for Prod RDS",
            "priority": "CRITICAL",
            "category": "resilience",
            "context": "Single RDS instance is SPOF...",
            "implementation": "Modify RDS to Multi-AZ...",
            "expected_benefit": "Automatic failover...",
            "estimated_savings": 840,
            "currency": "USD",
            "time_to_implement": "30 minutes",
            "affected_service": "prod-rds-main"
        },
        # ... 9-14 more recommendations
    ],
    "summary": {
        "total_recommendations": 12,
        "critical_count": 2,
        "high_count": 5,
        "medium_count": 4,
        "low_count": 1,
        "total_potential_monthly_savings": 8400,
        "risk_reduction_score": "High"
    }
}
```

---

## Prompt Templates & System Instructions

### Base System Prompt (All Agents)

```
You are an expert AWS infrastructure analyst with 10+ years of experience.

## CRITICAL INSTRUCTIONS

1. GROUNDING CONSTRAINT: You MUST ONLY make claims supported by provided context data. 
   Do NOT hallucinate or invent any data.
   
2. DATA-DRIVEN: Every finding must reference specific metrics:
   - "CPU at 85% (from CloudWatch)" not "seems high"
   - "$3,200/month waste" not "expensive"
   - "P99 latency 450ms" not "slow"

3. ACTIONABILITY: Every recommendation must be immediately implementable:
   - Include estimated time to implement
   - Specify affected resources
   - Include rollback strategy
   
4. CONTEXT IS LAW: If something is not in the provided context, do not claim it exists.
   Request data if needed, but do not guess or assume.

5. FORMAT COMPLIANCE: Follow the specified format exactly for all outputs.
```

### Agent 1: Topology Analyst - System Prompt

```
You are a cloud topology expert specializing in identifying single points of failure,
bottlenecks, and dependency chain analysis.

## Your Focus Areas

1. SINGLE POINTS OF FAILURE (SPOFs)
   - Identify services with no redundancy
   - Flag standalone RDS instances lacking Multi-AZ
   - Identify single NAT gateways, single IGWs
   
2. DEPENDENCY CHAINS
   - Identify chains longer than 4 services
   - Calculate end-to-end latency impact
   - Flag synchronous call chains
   
3. AVAILABILITY ZONE DISTRIBUTION
   - Check if instances distributed across 3+ AZs
   - Flag imbalanced distributions
   - Assess failure impact if one AZ goes down

4. RESOURCE CONCENTRATION
   - Identify if multiple critical services in one AZ
   - Assess blast radius of single AZ failure

## Output Format

For each finding:

### Finding Title
**Severity:** [CRITICAL|HIGH|MEDIUM|LOW]
**Service:** [affected service name]
**Type:** [SPOF|DeepChain|AZImbalance|Concentration]
**Evidence:** [specific data from context]
**Impact:** [what happens if this fails]
**Recommended Action:** [how to fix]
```

### Agent 2: Behavior Scientist - System Prompt

```
You are a performance anomaly detection specialist for cloud systems.

## Your Focus Areas

1. TRAFFIC ANOMALIES
   - Identify traffic spikes above baseline
   - Correlate with time patterns (daily, weekly)
   - Flag traffic patterns not meeting SLAs
   
2. PERFORMANCE DEGRADATION
   - Identify latency increases
   - Correlate with resource utilization changes
   - Calculate SLO violations

3. SCALING ISSUES
   - Identify lag between traffic spike and resource scaling
   - Flag ineffective Auto Scaling policies
   - Identify queue backlogs

4. ERROR PATTERNS
   - Identify recurring errors (e.g., connection pool exhaustion)
   - Correlate errors with behavior patterns
   - Flag root causes vs symptoms

## Output Format

For each finding:

### Anomaly: [Title]
**Type:** [Spike|Degradation|ScalingFailure|ErrorPattern]
**Frequency:** [when it occurs]
**Baseline:** [expected value] | **Observed:** [actual value]
**Affected Users:** [number/percentage]
**Root Cause:** [why it's happening]
**Recommended Action:** [mitigation]
```

### Agent 3: Cost Economist - System Prompt

```
You are an AWS cost optimization specialist with pricing expertise.

## Your Knowledge Base

- EC2 instance families and pricing (ON-DEMAND, RESERVED, SPOT)
- RDS pricing and sizing optimization
- S3 storage classes and intelligent tiering
- Data transfer costs (cross-AZ, cross-region)
- Lambda concurrent execution and duration pricing
- Elasticache vs application-level caching cost-benefit

## Your Focus Areas

1. UTILIZATION WASTE
   - Services running at <30% utilization
   - Over-sized instances for actual workload
   - Services that could be right-sized
   
2. STORAGE OPTIMIZATION
   - Identify data in expensive storage classes
   - Recommend tiering strategies
   - Calculate savings from transitions
   
3. RESERVED INSTANCE OPPORTUNITIES
   - Identify stable, predictable workloads
   - Calculate RI vs ON-DEMAND vs SPOT
   - Factor commitment discount terms

4. ARCHITECTURAL EFFICIENCY
   - Identify expensive communication (cross-AZ, cross-region)
   - Recommend service consolidation
   - Suggest alternative services (e.g., Athena vs Redshift)

## Output Format

For each optimization:

### Opportunity: [Title]
**Current State:** [service, sizing, cost]
**Identified Waste:** $[amount]/month
**Recommended Action:** [specific change]
**Expected Savings:** $[amount]/month (calculate: current - new)
**Implementation Effort:** [time estimate]
**Risk:** [any functional risks]
**Break-even:** [months of implementation cost, if any]
```

### Agent 4: Risk Detective - System Prompt

```
You are a risk synthesis specialist combining insights from topology, behavior, and cost analyses.

## Your Focus

Cross-domain root cause analysis:
- Does topology issue (SPOF) compound behavior issue (spike)?
- Does cost issue (undersizing) worsen topology risk (SPOF)?
- How do all three interact?

## Output Format

For each risk synthesis:

### Risk: [Title]
**Priority:** [CRITICAL|HIGH|MEDIUM|LOW]
**Root Cause Chain:**
1. [Topology component] - what is wrong with structure
2. [Behavior component] - what is wrong with operation
3. [Cost component] - what is wrong with resource allocation

**Combined Impact:** [what happens when all three fail together]
**Recommended Root Cause Fix:** [primary recommendation]

---

## Note on Priority Calculation

**CRITICAL** = Would cause complete service outage or customer-visible failure
**HIGH** = Degrades performance or increases failure probability significantly
**MEDIUM** = Impacts efficiency or increases operational burden
**LOW** = Nice to have, minimal current impact
```

### Agent 5: Executive Synthesizer - System Prompt

```
You are an AWS solutions architect synthesizing findings into executive recommendations.

## Your Role

Turn Agent 1-4 findings into 10-15 prioritized, immediately actionable recommendations
that balance: Resilience + Performance + Cost

## Prioritization Logic

1. CRITICAL resilience issues (SPOFs, no backups) → Recommendations 1-3
2. HIGH performance issues (blocking growth) → Recommendations 4-7
3. MEDIUM cost optimization → Recommendations 8-12
4. LOW operational improvements → Recommendations 13-15

## For Each Recommendation

Include:
- **Title** - specific, action-oriented
- **Priority** - [CRITICAL|HIGH|MEDIUM|LOW]
- **Business Context** - why this matters
- **Implementation** - exact steps to execute
- **Expected Benefit** - what improves (resilience/performance/cost)
- **Estimated Savings** - monthly cost reduction or risk reduction
- **Time to Implement** - hours/days needed
- **Affected Services** - which services change
- **Rollback Strategy** - how to undo if needed

## Output Format

### Recommendation 1: [Title]
**Priority:** [CRITICAL|HIGH|MEDIUM|LOW]
**Category:** [Resilience|Performance|Cost|Security]

**Why This Matters:**
[Business impact and urgency]

**Context:**
- [Finding from topology, behavior, cost analysis]
- [Evidence from context package]
- [How findings compound]

**What We Recommend:**
[Specific action]

**Expected Benefits:**
- [Benefit 1]
- [Benefit 2]
- [ROI if applicable]

**How to Implement:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Estimated Effort:** [time]
**Rollback:** [how to undo]
**Affected Services:** [list]
```

---

## RAG System & Knowledge Grounding

### Why RAG (Retrieval-Augmented Generation)?

```
Pure LLM without RAG:
"AWS recommends 3+ availability zones" ← LLM might hallucinate

With RAG grounding:
"AWS recommends 3+ availability zones" ← Retrieved from official AWS docs
[Cited: AWS Well-Architected Framework, Reliability Pillar]
```

### Knowledge Bases Used

#### 1. AWS Best Practices (Official)
```python
knowledge_bases = {
    "aws_well_architected_framework": {
        "reliability_pillar": [
            "Distribute workloads across AZs",
            "Implement health checks",
            "Design stateless services",
            "Use managed services for HA"
        ],
        "cost_optimization_pillar": [
            "Right-size resources based on metrics",
            "Use Reserved Instances for stable workloads",
            "Implement auto-scaling",
            "Leverage spot instances for flexible workloads"
        ]
    }
}
```

#### 2. Behavioral Simulation Data (JSONL index)
```
Knowledge base location: src/knowledge_base/BehavioralKnowledgeIndex

Indexed data:
- "What happens when RDS connection pool exhausted?" → Real examples with solutions
- "How do traffic spikes affect Auto Scaling response?" → Measured patterns
- "When does cross-AZ traffic become a cost issue?" → Threshold analysis

Example entry:
{
  "pattern": "connection_pool_exhaustion",
  "cause": "N+1 queries in batch jobs",
  "indicators": ["DatabaseConnectionPoolExhausted errors", "spike in latency"],
  "solution": "Implement query batching and connection pooling",
  "estimated_improvement": "350ms latency reduction"
}
```

#### 3. Community Summaries (GraphRAG style)
```python
# From historical analyses, aggregate patterns
community_summaries = {
    "pattern_single_rds_no_multiz": {
        "frequency": "appears in 73% of analyzed accounts",
        "avg_cost": "$840/month for Multi-AZ enablement",
        "avg_downtime_prevented": "2.3 hours/year",
        "avg_time_to_implement": "30 minutes"
    },
    "pattern_batch_contention": {
        "frequency": "appears in 58% of accounts with batch jobs",
        "avg_latency_impact": "300ms P99 increase",
        "avg_resolution_time": "4 hours development",
        "solutions_effectiveness": 94
    }
}
```

### Grounding Injection in System Prompts

```python
# When constructing Agent 5's prompt:

grounding_section = f"""
## GROUNDING & KNOWLEDGE BASE

The following context comes from:
1. **Real AWS Account Data** - from CloudFormation, CloudWatch, Pricing API
2. **AWS Official Documentation** - Well-Architected Framework
3. **Behavioral Knowledge Base** - patterns from historical analyses

### What You Know From This Account
{formatted_context_package}

### What You Know From AWS Best Practices
{aws_best_practices_relevant_to_findings}

### What You Know From Similar Accounts
{similar_patterns_from_community_summaries}

### What You DON'T Know (Do Not Guess)
- Any service not explicitly listed in inventory
- Any metric not provided in CloudWatch data
- Any assumption not grounded in provided data

If you need additional information, state clearly: "Additional data needed: [what]"
Do NOT hallucinate or assume.
"""

system_prompt = f"{BASE_SYSTEM_PROMPT}\n\n{grounding_section}"
```

### Hallucination Prevention

```python
# After LLM response, validate:

def validate_recommendation(rec, context_package):
    """Ensure recommendation is grounded in context"""
    
    errors = []
    
    # Check 1: Is affected service in inventory?
    if rec.affected_service not in context_package.service_inventory:
        errors.append(f"Service {rec.affected_service} not in inventory")
    
    # Check 2: Are metrics in provided data?
    if "CPU at 95%" in rec.context:
        found_metric = any(
            metric["cpu_utilization"] >= 90
            for metric in context_package.metrics
        )
        if not found_metric:
            errors.append("CPU utilization metric not in data")
    
    # Check 3: Is savings calculation reasonable?
    if rec.monthly_savings > context_package.total_monthly_cost:
        errors.append(f"Savings ${rec.monthly_savings} > total cost ${context_package.total_monthly_cost}")
    
    # Check 4: Is priority justified?
    if rec.priority == "CRITICAL" and not rec.affects_availability:
        errors.append("CRITICAL priority without availability impact")
    
    if errors:
        rec.status = "FAILED_VALIDATION"
        rec.validation_errors = errors
        return False
    
    rec.status = "VALID"
    return True
```

---

## Recommendation Generation & Output Formatting

### Generation Process

```
Agent 5 Output (raw LLM output):
↓
Recommendation Parser (extract structured fields)
↓
Recommendation Validator (check grounding)
↓
Deduplication (remove near-duplicates)
↓
Sorting (by priority, then by savings)
↓
JSON Response
```

### Parsing Strategy (3 Levels)

#### Strategy 1: Primary - "### Recommendation #N" Pattern

```python
import re

def strategy_1_parse(text):
    """Split by 'Recommendation #N' pattern"""
    
    # Pattern: ### Recommendation 1: ...
    pattern = r'###\s+Recommendation\s+(\d+):\s+(.+?)(?=###\s+Recommendation|\Z)'
    matches = re.finditer(pattern, text, re.DOTALL)
    
    recommendations = []
    for match in matches:
        rec_number = match.group(1)
        rec_content = match.group(2)
        recommendations.append({
            "number": rec_number,
            "content": rec_content
        })
    
    return recommendations

# Example extraction:
text = """
### Recommendation 1: Enable Multi-AZ for Prod RDS
**Priority:** CRITICAL
**Context:** Single RDS instance without failover...

### Recommendation 2: Optimize Batch Job Queries
**Priority:** HIGH
**Context:** N+1 queries causing connection pool exhaustion...
"""

recs = strategy_1_parse(text)
# Returns: [{"number": "1", "content": "..."}, {"number": "2", "content": "..."}]
```

#### Strategy 2: Secondary - Any "### [Title]" Pattern

```python
def strategy_2_parse(text):
    """Split by any ### header (more tolerant)"""
    
    pattern = r'###\s+(.+?)(?=###|\Z)'
    matches = re.finditer(pattern, text, re.DOTALL)
    
    recommendations = []
    for match in matches:
        content = match.group(1)
        # Try to extract number from content
        if "Recommendation" in content or re.search(r'\d+', content[:50]):
            recommendations.append({"content": content})
    
    return recommendations
```

#### Strategy 3: Fallback - "---" Delimiter

```python
def strategy_3_parse(text):
    """Split by --- delimiter (least accurate)"""
    
    recommendations = []
    sections = text.split("---")
    
    for section in sections:
        # Look for title and priority
        if "@@@title@@@ Pattern or high-quality content:
            if re.search(r"Recommendation|Priority", section):
                recommendations.append({"content": section.strip()})
    
    return recommendations
```

### Field Extraction via Regex

```python
def extract_fields(rec_text):
    """Extract structured fields from recommendation text"""
    
    fields = {
        "title": None,
        "priority": None,
        "category": None,
        "context": None,
        "implementation": None,
        "benefits": None,
        "savings": None,
        "time_estimate": None,
        "affected_service": None
    }
    
    # Title: ### Recommendation N: [title]
    match = re.search(r'###\s+Recommendation\s+\d+:\s*(.+?)$', rec_text, re.MULTILINE)
    if match:
        fields["title"] = match.group(1).strip()
    
    # Priority: **Priority:** [value]
    match = re.search(r'\*\*Priority:\*\*\s*(\w+)', rec_text)
    if match:
        fields["priority"] = match.group(1).strip()
    
    # Category: **Category:** [value]
    match = re.search(r'\*\*Category:\*\*\s*(.+?)(?=\*\*|$)', rec_text)
    if match:
        fields["category"] = match.group(1).strip()
    
    # Context: **Context:** [value]
    match = re.search(r'\*\*(?:Why|Context):\*\*\s*(.+?)(?=\*\*|$)', rec_text, re.DOTALL)
    if match:
        fields["context"] = match.group(1).strip()
    
    # Implementation: **Implementation:** [value] or **How To Implement:** [value]
    match = re.search(r'\*\*(?:Implementation|How To Implement):\*\*\s*(.+?)(?=\*\*|$)', rec_text, re.DOTALL)
    if match:
        fields["implementation"] = match.group(1).strip()
    
    # Benefits: **Benefits:** or **Expected Benefit:**
    match = re.search(r'\*\*(?:Benefits?|Expected Benefit):\*\*\s*(.+?)(?=\*\*|$)', rec_text, re.DOTALL)
    if match:
        fields["benefits"] = match.group(1).strip()
    
    # Savings: $[number] or [number] /month or monthly
    match = re.search(r'\\$([0-9,]+)', rec_text)
    if match:
        fields["savings"] = int(match.group(1).replace(',', ''))
    
    # Time Estimate: [number] hours|days|minutes
    match = re.search(r'(\\d+)\\s*(hours?|days?|minutes?)', rec_text)
    if match:
        fields["time_estimate"] = f"{match.group(1)} {match.group(2)}"
    
    # Affected Service: prod-api, prod-rds, etc.
    # Look for service patterns
    services = re.findall(r'(prod-\\w+|staging-\\w+|\\w+-service)', rec_text)
    if services:
        fields["affected_service"] = services[0]
    
    return fields
```

### Validation Against Inventory

```python
def validate_against_inventory(rec, inventory):
    """Ensure recommendation references real services"""
    
    if not rec.affected_service:
        return False, "No service identified"
    
    if rec.affected_service not in inventory.all_services:
        return False, f"Service {rec.affected_service} not in inventory"
    
    if rec.priority == "CRITICAL" and rec.affected_service in inventory.non_critical_services:
        return False, f"Service is not critical but marked CRITICAL priority"
    
    if rec.priority not in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        return False, f"Invalid priority: {rec.priority}"
    
    if rec.savings is None and rec.priority in ["MEDIUM", "LOW"]:
        # Cost recommendations should have savings
        return False, "Cost recommendation without savings calculation"
    
    return True, "Valid"
```

### Deduplication Logic

```python
def deduplicate_recommendations(recs):
    """Remove near-duplicate recommendations"""
    
    def similarity_score(rec1, rec2):
        """Calculate similarity (0-1)"""
        # Same title?
        if rec1.title.lower() == rec2.title.lower():
            return 0.95
        
        # Same affected service and priority?
        if (rec1.affected_service == rec2.affected_service and 
            rec1.priority == rec2.priority):
            # Check if titles are similar (levenshtein)
            from difflib import SequenceMatcher
            ratio = SequenceMatcher(None, rec1.title, rec2.title).ratio()
            return ratio * 0.9
        
        return 0
    
    deduplicated = []
    for i, rec in enumerate(recs):
        is_duplicate = False
        for dedup_rec in deduplicated:
            if similarity_score(rec, dedup_rec) > 0.8:
                is_duplicate = True
                break
        
        if not is_duplicate:
            deduplicated.append(rec)
    
    return deduplicated
```

### Final Output Structure

```json
{
  "status": "success",
  "analysis_id": "2026-03-23-123456789-us-east-1",
  "account_id": "123456789",
  "region": "us-east-1",
  "analyzed_at": "2026-03-23T15:30:00Z",
  "recommendations": [
    {
      "id": 1,
      "title": "Enable Multi-AZ for Prod RDS",
      "priority": "CRITICAL",
      "category": "Resilience",
      "context": "Single RDS instance without Multi-AZ failover. If instance fails, complete API outage.",
      "implementation": "1. Create manual snapshot\n2. Enable Multi-AZ under RDS settings\n3. Test failover\n4. Document new endpoints",
      "expected_benefits": [
        "Automatic failover in case of instance failure",
        "Automatic backups to secondary AZ",
        "Improved RPO from manual intervention to 2-3 seconds"
      ],
      "estimated_monthly_savings": 840,
      "currency": "USD",
      "time_to_implement": "30 minutes",
      "affected_service": "prod-rds-main",
      "affected_services": ["prod-rds-main", "prod-api", "prod-web"],
      "rollback_strategy": "Disable Multi-AZ in RDS settings (5 minute downtime)"
    },
    {
      "id": 2,
      "title": "Optimize Batch Job Database Queries",
      "priority": "HIGH",
      "category": "Performance",
      "context": "Batch jobs causing connection pool exhaustion due to N+1 query patterns, resulting in 450ms P99 latency spikes.",
      "implementation": "1. Audit batch job queries\n2. Implement query batching (group IDs into single query)\n3. Add connection pool management\n4. Load test with production traffic patterns",
      "expected_benefits": [
        "P99 latency: 450ms → 50ms",
        "Connection pool exhaustion errors eliminated",
        "Smoother Auto Scaling response"
      ],
      "estimated_monthly_savings": 0,
      "currency": "USD",
      "time_to_implement": "4 hours development + 2 hours testing",
      "affected_service": "batch-processor",
      "affected_services": ["batch-processor", "prod-api", "prod-rds-main"],
      "rollback_strategy": "Redeploy previous batch service version"
    }
  ],
  "summary": {
    "total_recommendations": 12,
    "by_priority": {
      "CRITICAL": 2,
      "HIGH": 5,
      "MEDIUM": 4,
      "LOW": 1
    },
    "by_category": {
      "Resilience": 2,
      "Performance": 5,
      "Cost": 4,
      "Security": 1
    },
    "total_potential_monthly_savings": 8400,
    "total_potential_annual_savings": 100800,
    "critical_resilience_issues_identified": 2,
    "estimated_total_implementation_time_hours": 32
  }
}
```

---

## Error Handling & Caching Strategy

### Cache Architecture

```
Layer 1: Redis Cache (24-hour TTL)
  Keys: analysis:{account_id}:{region}
  Value: Full recommendations + context package
  
Layer 2: PostgreSQL History DB
  Stores: Historical analyses for trend tracking
  Retention: 90 days
  
Layer 3: Local File System (for cold starts)
  Stores: Recent analyses (last 10)
  Backup in case Redis unavailable
```

### Cache Flow

```python
def get_or_analyze(account_id, region):
    """Get analysis from cache or generate new"""
    
    cache_key = f"analysis:{account_id}:{region}"
    
    # Try Redis first
    cached = redis.get(cache_key)
    if cached:
        analysis = json.loads(cached)
        analysis["source"] = "redis_cache"
        return analysis  # 10ms response
    
    # Try PostgreSQL (if older than 24h but available)
    postgres_analysis = query_latest_analysis(account_id, region)
    if postgres_analysis and not too_old(postgres_analysis):
        # Re-cache in Redis
        redis.setex(cache_key, 86400, json.dumps(postgres_analysis))
        postgres_analysis["source"] = "postgres_cache"
        return postgres_analysis  # 50ms response
    
    # Must generate new analysis (2+ minutes)
    analysis = run_full_pipeline(account_id, region)
    
    # Cache for future requests
    redis.setex(cache_key, 86400, json.dumps(analysis))
    postgres_insert(analysis)
    
    analysis["source"] = "newly_generated"
    return analysis
```

### Error Handling in Pipeline

#### Error 1: AWS API Failures
```python
def fetch_aws_infrastructure_with_retry(account_id, region):
    """Fetch with exponential backoff"""
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return cloudformation.describe_stacks()
        except ClientError as e:
            if e.response['Error']['Code'] == 'ThrottlingException':
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait_time)
                continue
            else:
                # Non-retryable error
                return {
                    "status": "error",
                    "error_type": "AWS_API_ERROR",
                    "message": str(e),
                    "account_id": account_id
                }
    
    return {"status": "error", "error_type": "MAX_RETRIES_EXCEEDED"}
```

#### Error 2: LLM Timeouts
```python
def call_llm_with_timeout(prompt, max_tokens):
    """Call LLM with timeout handling"""
    
    try:
        response = ollama.generate(
            model="qwen2.5-7b",
            prompt=prompt,
            max_tokens=max_tokens,
            timeout=120  # 2 minute timeout
        )
        return response
    except TimeoutError:
        logger.warning(f"LLM timeout after 120s")
        return {
            "status": "partial",
            "error": "timeout",
            "partial_response": "... (incomplete due to timeout)"
        }
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return {"status": "error", "error": str(e)}
```

#### Error 3: Parsing Failures
```python
def parse_with_fallback(llm_output):
    """Try multiple parsing strategies"""
    
    try:
        # Strategy 1: Primary parsing
        recs = strategy_1_parse(llm_output)
        if len(recs) >= 5:
            return recs, "strategy_1_success"
    except Exception as e:
        logger.debug(f"Strategy 1 failed: {e}")
    
    try:
        # Strategy 2: Secondary parsing
        recs = strategy_2_parse(llm_output)
        if len(recs) >= 3:
            return recs, "strategy_2_success"
    except Exception as e:
        logger.debug(f"Strategy 2 failed: {e}")
    
    try:
        # Strategy 3: Fallback parsing
        recs = strategy_3_parse(llm_output)
        if len(recs) >= 1:
            return recs, "strategy_3_fallback"
    except Exception as e:
        logger.error(f"All strategies failed: {e}")
    
    # None worked - return error
    return [], "parsing_failed"
```

#### Error 4: Recommendation Validation Failure
```python
def handle_invalid_recommendation(rec, error):
    """Handle invalid recommendations gracefully"""
    
    if "Service not in inventory" in error:
        # Skip this recommendation
        logger.warning(f"Skipping: {error}")
        return None
    
    elif "Savings > total cost" in error:
        # Reduce savings to max (account total cost)
        rec.savings = rec.savings // 1.5
        rec.note = "Savings reduced to be realistic"
        return rec
    
    elif "No service identified" in error:
        # Try to extract service from context
        rec.affected_service = extract_service_from_context(rec.context)
        if rec.affected_service:
            return rec
        else:
            return None
    
    else:
        # Unknown error - skip
        logger.error(f"Unknown validation error: {error}")
        return None
```

### Graceful Degradation

```python
def run_pipeline_with_degradation(account_id, region):
    """Run pipeline, gracefully degrade if parts fail"""
    
    result = {
        "account_id": account_id,
        "region": region,
        "recommendations": [],
        "warnings": [],
        "errors": []
    }
    
    # Step 1: Graph Analysis (CRITICAL)
    try:
        graph = analyzer.fetch_and_build()
    except Exception as e:
        result["errors"].append({"stage": "graph_analysis", "error": str(e)})
        result["recommendations"].append({
            "fallback": "Unable to analyze infrastructure",
            "reason": str(e),
            "suggested_action": "Contact AWS support or retry later"
        })
        return result
    
    # Step 2: Context Assembly (CRITICAL)
    try:
        context = assembler.assemble(graph)
    except Exception as e:
        result["errors"].append({"stage": "context_assembly", "error": str(e)})
        # Continue with partial context
        context = assembler.assemble_partial(graph)
        result["warnings"].append("Using partial context assembly")
    
    # Step 3: Agents (SEMI-CRITICAL - can skip individual agents)
    agent_findings = {}
    
    for agent_name, agent in [("topology", Agent1), ("behavior", Agent2), ...]:
        try:
            findings = agent.analyze(context)
            agent_findings[agent_name] = findings
        except TimeoutError:
            result["warnings"].append(f"Agent {agent_name} timed out, skipping")
            agent_findings[agent_name] = None
        except Exception as e:
            result["warnings"].append(f"Agent {agent_name} failed: {e}")
            agent_findings[agent_name] = None
    
    # Step 4: Final Synthesis (CRITICAL)
    try:
        findings_str = format_agent_findings(agent_findings, include_none=True)
        recommendations = synthesizer.synthesize(context, findings_str)
    except Exception as e:
        result["errors"].append({"stage": "synthesis", "error": str(e)})
        return result
    
    # Step 5: Parsing & Validation (LESS CRITICAL - can return partial)
    try:
        parsed = parser.parse(recommendations)
        validated = validator.validate_all(parsed, context)
        result["recommendations"] = validated
    except Exception as e:
        result["warnings"].append(f"Parsing failed: {e}")
        # Return unparsed recommendations
        result["recommendations"] = [{"raw": recommendations}]
    
    return result
```

---

## Performance & Timing

### Pipeline Execution Timeline

```
Request Received: T=0ms
  ↓
Cache Lookup: T=0-50ms
  → Cache HIT: Return at T=10ms ✓
  → Cache MISS: Continue
  ↓
AWS API Calls (parallel): T=50-200ms
  - Fetch CloudFormation: 80ms
  - Fetch CloudWatch metrics: 120ms
  - Fetch Pricing: 60ms
  - Fetch Cost data: 100ms
  Total: ~120ms (parallel)
  ↓
Graph Building: T=200-500ms
  - Build dependency graph: 200ms
  - Calculate centrality: 100ms
  ↓
Context Assembly: T=500-1200ms
  - Section 1 (Architecture): 50ms
  - Section 2 (Critical services): 150ms
  - Section 3 (Cost analysis): 200ms
  - Section 4 (Anti-patterns): 150ms
  - Section 5 (Risk assessment): 200ms
  - Section 6 (Anomalies): 150ms
  - Section 7 (Trends): 100ms
  - Section 8 (Dependencies): 150ms
  Total: ~1100ms
  ↓
LLM Calls (sequential): T=1200-3000ms
  - Agent 1 (Topology): 120s
  - Agent 2 (Behavior): 90s
  - Agent 3 (Cost): 100s
  - Agent 4 (Risk Synthesis): 80s
  - Agent 5 (Executive Synthesis): 110s
  Total: ~500s (8.3 min) - Can be parallelized to ~120s (2 min)
  ↓
Parsing & Validation: T=3000-3100ms
  - Parsing: 50ms
  - Validation: 50ms
  ↓
Caching & Storage: T=3100-3200ms
  - Redis: 30ms
  - PostgreSQL: 80ms
  ↓
Response Sent: T=3200ms (without LLM parallelization)
              T=2300ms (with LLM parallelization)
```

### Performance Optimization Strategies

1. **Cache First** - Most requests served from Redis in <50ms
2. **Parallel AWS Calls** - All AWS API calls parallelized
3. **Parallel Agent Execution** - Run Agents 1-3 in parallel (vs sequential)
4. **Background Processing** - PostgreSQL write happens async
5. **Streaming Responses** - Send recommendations as they parse

### Cache Hit Rates by Account

```
New accounts: 0% cache hit (cold start)
Established accounts (>1 week): 85-95% cache hit rate

Cache economics:
- Miss cost: 2-3 min (LLM inference)
- Hit cost: 10-50ms (Redis lookup + JSON parse)
- Average across all requests: 150-200ms (5% misses + 95% hits)

When to InvalidateCache:
- On-demand scalability changes (new ASG configs)
- Cost anomaly detected (spike >20%)
- Architecture changes (new services added)
- UI request with "force_refresh=true"
```

---

## Summary

This comprehensive system provides structured, grounded LLM analysis through:

1. **8-Section Context Packages** - Rich, structured context preventing hallucinations
2. **5-Agent Pipeline** - Specialized agents for topology, behavior, cost, risk, synthesis
3. **RAG Grounding** - Knowledge bases ensuring recommendations are based on AWS best practices
4. **Robust Parsing** - 3-level fallback parsing handles varied LLM output formats
5. **Validation** - Real-time verification against actual AWS inventory
6. **Caching & Performance** - 85-95% cache hit rate enables sub-second responses
7. **Error Handling** - Graceful degradation ensures partial results rather than failures

The result: **10-15 precise, actionable, cost-saving recommendations** generated in 2-3 minutes with full transparency into why each recommendation is made.

