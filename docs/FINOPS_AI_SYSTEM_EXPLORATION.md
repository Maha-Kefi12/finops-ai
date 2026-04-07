# FinOps AI System - Comprehensive Technical Overview

## Executive Summary

The FinOps AI Platform is a sophisticated AWS cost optimization system that:
- Analyzes cloud architectures through **5 specialized LLM-powered agents**
- Builds rich **context packages** with 8+ sections of architectural intelligence
- Uses **GraphRAG** for grounded LLM reasoning with behavioral data
- Generates **cost optimization recommendations** with precise savings calculations
- Provides **background analysis pipeline** with real-time progress tracking
- Serves results through **FastAPI backend** with Redis caching

---

## 1. LLM INTEGRATION ARCHITECTURE

### Primary LLM: Qwen 2.5 7B (via Ollama)

**Configuration:**
```
- Base Model: abocide/Qwen2.5-7B-Instruct-R1-forfinance
- Deployment: Ollama (local), Mistral (faster default)
- Backup: Gemini Flash API (configured via GEMINI_API_KEY)
- Endpoint: OLLAMA_URL (default: http://localhost:11434)
- Temperature: 0.2-0.3 (deterministic, fact-focused)
- Max Tokens: 2048-4096 (depending on agent)
- Timeout: 300 seconds (5 minutes)
```

**LLM Caller:** [src/llm/client.py](src/llm/client.py)
- Handles Ollama HTTP requests to `/api/chat`
- Implements health checks before calling
- Automatic fallback from Ollama to Gemini if configured
- Robust error handling with timeout protection

### 5-Agent Pipeline (Sequential Orchestration)

Each agent specializes in a specific analysis domain and builds on previous agents' outputs:

#### **Agent 1: Topology Analyst** ([src/agents/architect_agent.py](src/agents/architect_agent.py))
- **Role:** Structural AWS infrastructure risk analysis
- **Input:** Graph data + cascade analysis metrics
- **Output:** Structural findings (single point of failure, deep chains, circular dependencies)
- **LLM System Prompt:** AWS Solutions Architect perspective
- **Findings Generated:**
  - Single points of failure (centralization > 0.3)
  - Deep service chains (latency amplification)
  - Circular dependencies (retry storms)
  - Scaling mismatches (horizontal vs vertical)
- **AWS Services Referenced:** EC2, ALB, RDS, Route 53, ElastiCache, CloudWatch
- **Risk Score:** 0-1 based on structural patterns

```
Input: cascade_analysis {
  centralization_score: 0-1,
  centralization_hub: str,
  max_chain_depth: int,
  longest_chain: [str],
  cycles: [list of cycles],
  asymmetric_bottlenecks: [list]
}
```

#### **Agent 2: Behavior Scientist** ([src/agents/behavior_agent.py](src/agents/behavior_agent.py))
- **Role:** Behavioral anomalies under load
- **Input:** Monte Carlo report + cascade analysis
- **Output:** Behavioral risk findings (anomalies, overload probabilities)
- **LLM Focus:** Behavioral pattern explanation
- **Findings:** Resource overload patterns, cascade failure probabilities
- **Risk Score:** Based on anomaly severity

#### **Agent 3: Cost Economist** ([src/agents/economist_agent.py](src/agents/economist_agent.py))
- **Role:** Cost amplification and spending volatility
- **Input:** Monte Carlo scenarios + cascade analysis
- **Output:** Cost-focused findings (amplifiers, concentration, volatility)
- **Cost Analysis:**
  - Top cost amplifier nodes (>1.2× multiplication)
  - Cost concentration (Pareto 80/20 analysis)
  - Spike vs steady-state variance
  - Data transfer cost risk
- **LLM Context:** AWS billing terms, pricing models, cost allocation
- **AWS Services:** Cost Explorer, Budgets, Anomaly Detection, Savings Plans

```
Findings include:
- node_amplifications: [{node_name, cost_amplification}]
- bottleneck_nodes: [str]
- spike_volatility: float (spike_cost / steady_cost)
- estimated_data_transfer: float
```

#### **Agent 4: Risk Detective** ([src/agents/detective_agent.py](src/agents/detective_agent.py))
- **Role:** Root cause analysis combining findings from Agents 1-3
- **Input:** All previous agent outputs + cascade + MC report
- **Output:** Root cause synthesis, component-level risk breakdown
- **LLM Task:** Correlate findings to identify root causes
- **Risk Score:** Synthesized from all sources

#### **Agent 5: Executive Synthesizer** ([src/agents/synthesizer_agent.py](src/agents/synthesizer_agent.py))
- **Role:** Executive summary and final recommendations
- **Input:** All previous agent outputs
- **Output:** Verdict, financial exposure, prioritized actions
- **Verdict Levels:**
  - 🔴 HIGH RISK (>0.7): Immediate action required
  - 🟡 MODERATE RISK (0.4-0.7): Proactive optimization recommended
  - 🟢 LOW RISK (<0.4): Well-optimized
- **Financial Projection:** Annual exposure calculation based on spike frequency
- **LLM Context:** CTO/CFO audience, plain language with AWS terms

**Orchestrator:** [src/agents/orchestrator.py](src/agents/orchestrator.py)
```python
pipeline = [
  1. TopologyAnalystAgent → structural patterns
  2. BehaviorScientistAgent → behavioral anomalies
  3. CostEconomistAgent → cost amplification
  4. RiskDetectiveAgent → root cause (uses 1+2+3)
  5. ExecutiveSynthesizerAgent → verdict (uses 1+2+3+4)
]
```

---

## 2. INPUTS & CONTEXT PROVIDED TO LLM

### Input Sources (Workflow Entry Points)

**Entry Point 1: API Ingestion** ([src/api/handlers/ingest.py](src/api/handlers/ingest.py))
```
POST /api/ingest
- JSON architecture file (services + dependencies)
- Creates IngestionSnapshot in DB
- Stores raw_data for future analysis
```

**Entry Point 2: Synthetic Files** (data/synthetic/*.json)
```
- Pre-defined test architectures
- Used for demos and benchmarking
- Contains metadata + service inventory
```

**Entry Point 3: Database** (PostgreSQL)
```
- Stores Architecture, Service, Dependency records
- Retrieved by ID for analysis
- Linked to IngestionSnapshot for raw data
```

### Core Context Inputs to Each Agent

#### **1. Graph Data**
```json
{
  "metadata": {
    "name": "microservices-prod",
    "pattern": "microservices|monolith|hybrid",
    "complexity": "high|medium|low",
    "environment": "production|staging",
    "region": "us-east-1",
    "total_services": 42,
    "total_cost_monthly": 15000
  },
  "services": [
    {
      "id": "service-id",
      "name": "User Service",
      "type": "service|database|cache|queue",
      "cost_monthly": 1200,
      "attributes": {...}
    }
  ],
  "dependencies": [
    {
      "source": "service-1",
      "target": "service-2",
      "type": "calls|depends_on",
      "weight": 1.0
    }
  ]
}
```

#### **2. Cascade Analysis** (from [src/simulation/amplification.py](src/simulation/amplification.py))
```python
@dataclass
class CascadeAnalysis:
    centralization_score: float        # 0-1, how much hub concentration
    centralization_hub: str            # name of central node
    max_chain_depth: int               # longest dependency chain
    longest_chain: List[str]           # path of that chain
    cycles: List[List[str]]            # circular dependencies found
    asymmetric_bottlenecks: List       # horizontal→vertical scaling mismatches
    node_amplifications: List          # [{node_name, cost_amplification}]
    bottleneck_nodes: List[str]        # pareto analysis: top cost drivers
    dominant_pattern: str              # structural signature
```

#### **3. Monte Carlo Report** (from [src/simulation/simulator.py](src/simulation/simulator.py))
```python
@dataclass
class MonteCarloReport:
    scenario_results: List[{
        "label": "steady_state|spike|extreme",
        "traffic_multiplier": 1.0|3.0|10.0,
        "cost_mean": float,
        "cost_std": float,
        "cost_p95": float,
        "cost_p99": float,
        "overload_probability": 0-1
    }]
    # 200-500 trials per scenario to compute statistics
```

#### **4. Architecture Context Package** (from [src/analysis/context_assembler.py](src/analysis/context_assembler.py))

**8-Section Structured Package** ([ArchitectureContextPackage dataclass](src/analysis/context_assembler.py#L60)):

```python
@dataclass
class ArchitectureContextPackage:
    # SECTION 1: Architecture Overview
    architecture_name: str
    total_services: int
    total_cost_monthly: float
    service_breakdown: Dict  # {service_type: {count, cost}}
    geographic_distribution: Dict
    cross_az_dependency_count: int
    
    # SECTION 2: Critical Services (top by centrality)
    critical_services: List[Dict]
    # [{node_id, name, centrality_score, degree, cost, risk_level}]
    
    # SECTION 3: Cost Analysis
    top_expensive: List[Dict]          # highest cost services
    cost_outliers: List[Dict]          # anomalies (actual > expected)
    waste_detected: List[Dict]         # unused/idle resources
    total_waste_monthly: float         # total waste found
    
    # SECTION 4: Architectural Anti-Patterns
    anti_patterns: List[{
        name: str,                      # e.g., "N+1 query problem"
        severity: str,
        description: str,
        affected_nodes: List[str],
        recommendation: str,
        estimated_savings: float
    }]
    
    # SECTION 5: Risk Assessment
    risks: List[{
        name: str,
        severity: str,
        description: str,
        impact: str,
        affected_nodes: List[str]
    }]
    
    # SECTION 6: Behavioral Anomalies
    anomalies: List[{
        name: str,
        severity: str,
        node_id: str,
        description: str,
        evidence: List[str],
        impact: str
    }]
    
    # SECTION 7: Historical Trends
    cost_trends: Dict
    growth_trajectory: Dict
    
    # SECTION 8: Dependency Analysis
    critical_dependencies: List[{
        source: str,
        target: str,
        impact_count: int,
        description: str
    }]
    circular_dependencies: List
    orphaned_services: List[str]
    deep_chains: List[Dict]
    
    # SECTION 9: RAG-Grounded Best Practices (from knowledge base)
    rag_best_practices: List[str]
    rag_relevant_docs: List[{source, content}]
    
    # Raw data for LLM
    interesting_node_narratives: List[str]
```

---

## 3. WORKFLOW PIPELINE: API → ANALYSIS → LLM

### Complete End-to-End Flow

```
┌─ User Request ─────────────────────────────────────────┐
│                                                         │
│  POST /api/analyze                                     │
│  {                                                     │
│    architecture_file: "adtech_*.json"  OR              │
│    architecture_id: "uuid-from-db"                     │
│  }                                                     │
└─────────────────────┬─────────────────────────────────┘
                      │
                      ▼
        ┌─ STAGE 1: DATA LOADING ┐
        │                        │
        │  Load from:            │
        │  - Synthetic file      │
        │  - PostgreSQL DB       │
        │  - IngestionSnapshot   │
        │                        │
        │  Extract:             │
        │  - services[]          │
        │  - dependencies[]      │
        │  - metadata{}          │
        └──────────┬─────────────┘
                   │
                   ▼
        ┌─ STAGE 2: GRAPH BUILDING ┐
        │                          │
        │  NetworkX DiGraph:       │
        │  - Add nodes + attributes│
        │  - Add edges + weights   │
        │  - Compute centrality    │
        │  - Detect cycles         │
        └──────────┬───────────────┘
                   │
                   ▼
        ┌─ STAGE 3: SIMULATION ──────┐
        │                            │
        │  Cascade Analysis:         │
        │  - Centralization score    │
        │  - Chain depth analysis    │
        │  - Cycle detection         │
        │  - Amplification factors   │
        │                            │
        │  Monte Carlo (200 trials): │
        │  - Steady state scenario   │
        │  - 3× traffic spike        │
        │  - 10× extreme event       │
        │  - Cost + overload stats   │
        └──────────┬────────────────┘
                   │
                   ▼
        ┌─ STAGE 4: CONTEXT ASSEMBLY ┐
        │                              │
        │  GraphAnalyzer:             │
        │  - Compute node metrics      │
        │  - Identify interesting nodes│
        │  - Extract narratives        │
        │                              │
        │  ContextAssembler:           │
        │  - Build 8-section package   │
        │  - Extract anti-patterns     │
        │  - Flag waste               │
        │  - Collect RAG docs         │
        │                              │
        │  Output:                    │
        │  - ArchitectureContextPackage│
        └──────────┬──────────────────┘
                   │
                   ▼
        ┌─ STAGE 5: 5-AGENT PIPELINE ┐
        │                              │
        │  Agent 1: Topology Analyst   │
        │    → LLM call (system + user)│
        │    → Parse findings          │
        │    → Risk score              │
        │                              │
        │  Agent 2: Behavior Scientist │
        │    → Uses Agent 1 context    │
        │    → LLM call                │
        │                              │
        │  Agent 3: Cost Economist     │
        │    → Uses Agents 1+2         │
        │    → LLM call                │
        │                              │
        │  Agent 4: Risk Detective     │
        │    → Uses Agents 1+2+3       │
        │    → LLM call                │
        │                              │
        │  Agent 5: Executive Synthesizer
        │    → Uses Agents 1+2+3+4     │
        │    → Final LLM call          │
        │                              │
        │  Output:                    │
        │  - Verdict + confidence      │
        │  - Recommendations           │
        │  - Root causes               │
        │  - Risk scores               │
        └──────────┬──────────────────┘
                   │
                   ▼
        ┌─ STAGE 6: RECOMMENDATION GENERATION ┐
        │                                      │
        │  LLM Input:                         │
        │  - System prompt (Qwen 2.5 format)  │
        │  - Service inventory section        │
        │  - CloudWatch metrics section       │
        │  - Graph context section            │
        │  - Pricing data section             │
        │  - AWS best practices section       │
        │                                      │
        │  LLM Output (4000 tokens):          │
        │  ### Recommendation #1              │
        │  **Resource ID:** i-12345678        │
        │  **Service:** EC2                   │
        │  **Current Cost:** $100/mo          │
        │  **Problem:** Over-provisioned t3.2xlarge
        │  **Solution:** Downsize to t3.large │
        │  **Monthly Savings:** $45/mo        │
        │  ---                                │
        │  ### Recommendation #2              │
        │  ...                                │
        │                                      │
        │  Parser:                            │
        │  - Split by "### Recommendation #N" │
        │  - Extract fields (regex)           │
        │  - Validate resource IDs            │
        │  - Dedup by resource_id             │
        │  - Filter zero-savings cards        │
        │  - Enrich with architecture data    │
        └──────────┬──────────────────────────┘
                   │
                   ▼
        ┌─ STAGE 7: RESPONSE FORMATTING ┐
        │                                │
        │  Output:                      │
        │  {                            │
        │    verdict: str,              │
        │    risk_score: 0-1,           │
        │    agents: {detailed output}, │
        │    all_findings: [...],       │
        │    recommendations: [...],    │
        │    root_cause: str,           │
        │    timings: {agent: ms, ...}  │
        │  }                            │
        │                                │
        │  Additional:                  │
        │  - Cache results (24h Redis)  │
        │  - Save to DB                 │
        │  - Store history (90d)        │
        └────────────────────────────────┘
```

### API Endpoints in Pipeline

**[src/api/main.py](src/api/main.py)** - FastAPI App Setup
```python
app.include_router(ingest_router)        # POST /api/ingest
app.include_router(analyze_router)       # POST /api/analyze
app.include_router(recommendations_router)  # GET/POST recommendations
app.include_router(graphrag_router)      # RAG retrieval endpoints
```

**[src/api/handlers/analyze.py](src/api/handlers/analyze.py)** - Analysis Endpoint
```
POST /api/analyze
Input:
  - architecture_file: str (filename in data/synthetic/)
  - architecture_id: str (UUID from DB)
  - scenario: str (default: "spike")

Flow:
  1. Load architecture data
  2. Build NetworkX graph
  3. Run cascade analysis
  4. Run Monte Carlo simulation (async in thread)
  5. Run 5-agent orchestrator
  6. Return full report

Output:
  {
    architecture: str
    pattern: str
    baseline_cost_monthly: float
    verdict: str
    risk_score: 0-1
    agents: {
      topology_analyst: AgentOutput
      behavior_scientist: AgentOutput
      cost_economist: AgentOutput
      risk_detective: AgentOutput
      executive_synthesizer: AgentOutput
    }
    all_findings: List[Dict]
    recommendations: List[str]
    root_cause: str
    timings: {agent: int (ms), total_ms: int}
  }
```

---

## 4. CONTEXT PACKAGES & BUILDING MECHANISMS

### 8-Section Context Package Assembly

**Builder:** [src/analysis/context_assembler.py](src/analysis/context_assembler.py)

**Input:** 
- Raw graph data (JSON)
- Analysis report from GraphAnalyzer

**Process:**

```python
assembler = ContextAssembler(graph_data, analysis_report)
context_pkg = assembler.assemble()
```

**Section-by-Section Build:**

1. **OVERVIEW** (`_section1_overview`)
   - Architecture name, service count, cost
   - Service breakdown by type (EC2, RDS, etc.)
   - Geographic distribution (region/AZ)
   - Cross-AZ dependency count

2. **CRITICAL SERVICES** (`_section2_critical_services`)
   - Top services by centrality (betweenness, closeness)
   - Degree (in-degree + out-degree)
   - Current cost
   - Risk level (based on cascade analysis)

3. **COST ANALYSIS** (`_section3_cost_analysis`)
   - Top 10 most expensive services
   - Cost outliers (actual vs expected ratios)
   - Waste detection (idle/unused resources)
   - Trend analysis

4. **ANTI-PATTERNS** (`_section4_anti_patterns`)
   - N+1 query patterns
   - Missing caching opportunities
   - Unoptimized scaling
   - Resource overprovisioning

5. **RISK ASSESSMENT** (`_section5_risk_assessment`)
   - Single points of failure
   - Cascade risks
   - Scalability limits
   - Data consistency risks

6. **BEHAVIORAL ANOMALIES** (`_section6_anomalies`)
   - Overload patterns
   - Retry storms
   - Unusual traffic patterns
   - Cost spike triggers

7. **HISTORICAL TRENDS** (`_section7_trends`)
   - Cost growth trajectory
   - Traffic patterns
   - Seasonal variations
   - Projections

8. **DEPENDENCY ANALYSIS** (`_section8_dependencies`)
   - Critical dependency paths
   - Circular dependencies
   - Orphaned services
   - Deep chains (>5 hops)

9. **RAG GROUNDING** (GraphRAG Integration)
   - Best practices from knowledge base
   - Relevant documentation
   - Similar architecture patterns

### Context Package Data Flow

```
ArchitectureContextPackage (dataclass)
    ↓
    Converted to dict via asdict()
    ↓
    Formatted into LLM prompt sections:
    - service_inventory = format_services()
    - cloudwatch_metrics = format_metrics()
    - graph_context = format_graph()
    - pricing_data = format_pricing()
    - aws_best_practices = format_best_practices()
    ↓
    Injected into RECOMMENDATION_USER_PROMPT template:
    "Here is the AWS architecture to analyze:\n{service_inventory}\nMETRICS:\n{cloudwatch_metrics}..."
```

### LLM Input Construction

**[src/llm/client.py](src/llm/client.py) - `generate_recommendations()`**

```python
# 1. Build context sections
service_inventory = _build_service_inventory(raw_graph_data)
cloudwatch_metrics = _build_metrics(raw_graph_data)
graph_context = _build_graph(pkg_dict)
pricing_data = _build_pricing()
aws_best_practices = _build_best_practices(pkg_dict)

# 2. Format user prompt with all sections
user_prompt = RECOMMENDATION_USER_PROMPT.format(
    service_inventory=service_inventory,
    cloudwatch_metrics=cloudwatch_metrics,
    graph_context=graph_context,
    pricing_data=pricing_data,
    aws_best_practices=aws_best_practices,
)

# 3. Call LLM with system + user prompts
raw_response = call_llm(
    system_prompt=RECOMMENDATION_SYSTEM_PROMPT,
    user_prompt=user_prompt,
    temperature=0.2,
    max_tokens=4000
)
```

---

## 5. RAG SYSTEM & KNOWLEDGE BASE INTEGRATION

### RAG Architecture

**Components:**
- [src/rag/indexing.py](src/rag/indexing.py) - BehavioralKnowledgeIndex
- [src/rag/retrieval.py](src/rag/retrieval.py) - GraphRAGRetriever
- [src/rag/embeddings.py](src/rag/embeddings.py) - TFIDFEmbedder
- [src/rag/vector_store.py](src/rag/vector_store.py) - VectorStore
- [src/knowledge_base/aws_finops_best_practices.py](src/knowledge_base/aws_finops_best_practices.py) - Best practices docs

### Knowledge Index

**Behavioral Knowledge Index** (from data/behavioral/*.jsonl)

```python
@dataclass
class BehavioralKnowledgeIndex:
    records: List[Dict]  # Loaded from JSONL
    
    # Indexed by:
    by_architecture: Dict[str, List[Dict]]
    by_scenario: Dict[str, List[Dict]]
    by_risk_class: Dict[str, List[Dict]]
    by_pattern: Dict[str, List[Dict]]
    
    # Community summaries (GraphRAG-style)
    community_summaries: Dict[str, str]  # arch:name → summary
```

**Example Summary:**
```
"Architecture 'microservices-prod' (microservices, 42 services, 128 deps).
Baseline cost: $15,000/mo. Across 500 behavioral simulations:
mean stressed cost $28,500, mean amplification 1.9×,
risk distribution: {high: 180, moderate: 250, low: 70},
mean overload probability 45%. Dominant patterns: {deep_chain: 300}"
```

### RAG Retrieval Flow

**When LLM is called:** [src/agents/base_agent.py](src/agents/base_agent.py) - `_call_llm()`

```python
def _call_llm(system_prompt, user_prompt, ...):
    # 1. Get knowledge index
    idx = get_knowledge_index()
    
    # 2. Retrieve grounded context
    ctx = idx.retrieve_context(architecture_name)
    grounding = idx.format_grounding_prompt(ctx)
    
    # 3. Inject into system prompt
    grounded_system = system_prompt + "\n\n" + (
        "CRITICAL: You are grounded by GraphRAG index. "
        "ONLY make claims supported by ground truth. "
        "Do NOT hallucinate.\n\n" + grounding
    )
    
    # 4. Call Ollama with grounded system prompt
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL_NAME,
            "messages": [
                {"role": "system", "content": grounded_system},
                {"role": "user", "content": user_prompt}
            ]
        }
    )
```

### GraphRAG-Style Community Summaries

**Built from:** Aggregated statistics across K behavioral simulations

```python
def _build_community_summaries(self):
    # For each architecture
    for arch_name, records in self.by_architecture.items():
        stats = {
            count: len(records),
            mean_cost: sum(r['stressed_total_cost']) / len(records),
            mean_amp: sum(r['amplification_factor']) / len(records),
            risk_dist: Counter(r['risk_class'] for r in records),
            mean_overload_prob: mean([r['overload_probability'] for r in records])
        }
        # Store as summary string for LLM
        self.community_summaries[f"arch:{arch_name}"] = f"..."
```

### Best Practices Knowledge Base

**[src/knowledge_base/aws_finops_best_practices.py](src/knowledge_base/aws_finops_best_practices.py)**

```python
AWS_BEST_PRACTICES = {
    "EC2": [
        "Use Auto Scaling Groups with proper min/max settings",
        "Enable detailed monitoring via CloudWatch",
        "Use Reserved Instances for baseline capacity",
        "Switch to Spot instances for batch workloads"
    ],
    "RDS": [
        "Enable automated backups (7-35 day retention)",
        "Use Multi-AZ for production databases",
        "Enable Enhanced Monitoring",
        "Consider Aurora for read-heavy workloads"
    ],
    "S3": [
        "Enable S3 Intelligent-Tiering for automatic cost optimization",
        "Use Lifecycle policies to move old objects to Glacier",
        "Enable CloudTrail logging for compliance",
        "Use server-side encryption"
    ]
    # ... more services
}
```

**Injected into system prompt as:** Credible best practices reference

---

## 6. TEMPLATES & PROMPT PATTERNS

### System Prompts

**[src/llm/prompts.py](src/llm/prompts.py)**

#### Recommendation System Prompt
```
You are an AWS FinOps expert. Your job: analyze AWS infrastructure and 
generate 10-20 cost optimization recommendations.

CRITICAL FORMATTING RULES:
1. Start EVERY recommendation with exactly: "### Recommendation #N"
2. After each recommendation, put exactly: "---"
3. Use EXACT resource IDs from SERVICE INVENTORY
4. Show COMPLETE savings calculations

EXACT FORMAT:
### Recommendation #1
**Resource ID:** [exact-resource-id]
**Service:** RDS | EC2 | Lambda | S3 | etc
**Current Cost:** $XXX.XX/month
**Problem:** [specific metrics]
**Solution:** [exact change]
**Savings:** Current: $XXX → New: $YYY → Monthly: $ZZZ
**Implementation:** [AWS CLI command]
**Risk:** LOW | MEDIUM | HIGH
---
```

#### Recommendation User Prompt Template
```
Here is the AWS architecture to analyze:

{service_inventory}

METRICS:
{cloudwatch_metrics}

DEPENDENCIES:
{graph_context}

PRICING:
{pricing_data}

BEST PRACTICES:
{aws_best_practices}

## CRITICAL REQUIREMENTS:
✓ Generate 10-15 recommendations across DIFFERENT services
✓ Use resource IDs from SERVICE INVENTORY
✓ Include: Problem, Solution, Monthly Savings, Resource ID
✓ Format: ### Recommendation #N: [action]
```

### Agent-Specific System Prompts

**Topology Analyst:**
```
You are a senior AWS Solutions Architect analyzing infrastructure topology.
ALWAYS use real AWS service names (EC2, RDS, ALB, Lambda, ElastiCache).
Explain findings in terms a Cloud Engineer can act on.
Reference AWS console actions, CLI commands, CloudFormation parameters.
Every recommendation must include expected cost impact.
```

**Cost Economist:**
```
You are an AWS Cost Optimization specialist.
ALWAYS reference specific AWS services and billing mechanisms.
Use terms: On-Demand, Reserved Instances, Savings Plans, Spot Instances,
Cost Explorer, Cost Anomaly Detection, AWS Budgets, Cost Allocation Tags.
Explain WHY costs spike in AWS billing terms.
```

**Executive Synthesizer:**
```
You are a VP of Cloud FinOps presenting to the CTO.
Write an executive summary for non-technical executives, BUT use AWS terms.
Structure: (1) One-sentence verdict, (2) Financial exposure in dollars,
(3) Top 3 prioritized actions with savings.
Keep it under 200 words. Be direct, not academic.
```

### Prompt Context Injection

**GraphRAG Grounding:**
```
CRITICAL INSTRUCTION: You are grounded by a GraphRAG knowledge index.
You MUST only make claims supported by the ground truth data below.
Do NOT hallucinate numbers, service names, or risk levels.
If unsure, say 'insufficient data' rather than guessing.

[COMMUNITY SUMMARIES FROM INDEX]
Architecture 'xxx': ...
Pattern 'yyy': ...
```

---

## 7. RESULTS FORMATTING & DISPLAY

### Recommendation Card Output

**[src/llm/structured_output.py](src/llm/structured_output.py)**

```python
@dataclass
class Recommendation:
    num: int
    title: str
    priority: str  # P0, P1, P2
    action: str
    current_config: str
    new_config: str
    monthly_savings: float
    annual_savings: float
    performance_impact: str
    risk_assessment: str
    implementation_steps: List[str]
    monitoring_steps: List[str]
    validation_criteria: List[str]

@dataclass
class StructuredRecommendationCard:
    resource_id: str
    resource_identification: ResourceIdentification  # full ARN, service, type, region, tags
    cost_breakdown: CostBreakdown  # monthly cost, line items, trends, projections
    inefficiencies: List[Inefficiency]  # what's wrong
    recommendations: List[Recommendation]  # solutions
    total_monthly_savings: float
    total_annual_savings: float
```

### Parsing & Validation

**[src/llm/client.py](src/llm/client.py) - Parser**

```python
def _parse_all_recommendations(text: str) -> List[Dict]:
    """
    Robust parser finds ALL recommendations via 3 strategies:
    1. Split by "### Recommendation #N"
    2. Split by any "### [title]"
    3. Split by "---" delimiter
    
    Extract fields using regex:
    - resource_id: \*\*Resource ID:\*\* (.*?)
    - service: \*\*Service:\*\* (.*)
    - current_cost: \*\*Current Cost:\*\* \$([\d.,]+)
    - monthly_savings: Monthly savings: \$([\d.,]+)
    """
    # Strategy 1 (primary - most reliable)
    matches = list(re.finditer(r"###\s+Recommendation\s+#(\d+)", text, re.IGNORECASE))
    if len(matches) >= 5:
        return _extract_sections(text, matches)
    
    # Strategy 2 (fallback)
    matches = list(re.finditer(r"###\s+([^\n#]{5,100})", text))
    if len(matches) >= 5:
        return _extract_sections(text, matches)
    
    # Strategy 3 (fallback)
    sections = text.split("---")
    sections = [s.strip() for s in sections if len(s.strip()) > 100]
    if len(sections) >= 5:
        cards = []
        for i, section in enumerate(sections, 1):
            card = _parse_card_text(section, i)
            cards.append(card)
        return cards
```

### Recommendation Card Template

```
═══════════════════════════════════════════════════════════════════════
COST OPTIMIZATION RECOMMENDATION #1
═══════════════════════════════════════════════════════════════════════

RESOURCE IDENTIFICATION
───────────────────────────────────────────────────────────────────────
Resource ID: i-0a1b2c3d4e5f6g7h8
Full ARN: arn:aws:ec2:us-east-1:123456789012:instance/i-0a1b2c3d4e5f6g7h8
Service: EC2
Current Instance: t3.2xlarge
Region: us-east-1
Availability Zone: us-east-1a
Tags: Name=web-server, Environment=production, Team=platform

CURRENT COST BREAKDOWN (from CUR line items)
───────────────────────────────────────────────────────────────────────
Monthly Cost: $1,250.00

Line Items:
  - On-Demand Instances (t3.2xlarge): $1,200/mo
  - Data Transfer Out: $30/mo
  - EBS Volumes: $20/mo

Cost Trend (90-day):
  Days 1-30:  $1,250
  Days 31-60: $1,250
  Days 61-90: $1,250
Growth Rate: 0% (stable)
90-Day Projection: $3,750

INEFFICIENCIES IDENTIFIED
───────────────────────────────────────────────────────────────────────
1. ISSUE: Over-provisioned instance size
   Severity: HIGH
   Evidence:
     - Average CPU utilization 15-25% (target 60-70%)
     - Memory utilization consistently 20-30%
     - Network throughput <5% of t3.2xlarge capacity
   Root Cause:
     - Instance sized for peak load but underutilized at baseline
     - No auto-scaling configured

RECOMMENDATION
───────────────────────────────────────────────────────────────────────
#1 Downsize to t3.large + Enable Auto Scaling

Current Configuration:
  Instance Type: t3.2xlarge (8 vCPU, 32 GB RAM)
  Auto Scaling: Disabled (fixed size)
  Min/Max: N/A

New Configuration:
  Instance Type: t3.large (2 vCPU, 8 GB RAM)
  Auto Scaling: Enabled with ASG
  Min: 2 instances (redundancy)
  Max: 10 instances (spike headroom)
  Target CPU: 70%

Savings Calculation:
  Current monthly cost: $1,250
  New baseline (2× t3.large): $312.50/mo baseline
  Average during typical week: $350/mo
  Monthly savings: $900/mo
  Annual savings: $10,800

Performance Impact:
  - Initial request latency: +5-10ms during scale-up (first 60s)
  - Steady-state: Same (auto-scaling maintains target CPU)
  - Spike response: Better (scale-out prevents overload)
  - No downtime (rolling replacement via ASG)

Risk Assessment: LOW
  - Auto Scaling handles spikes automatically
  - Easy to revert (change ASG max size)
  - Monitoring: CloudWatch alarms included

Implementation Steps:
  1. Create Target Group (if not exists): aws elbv3 create-target-group ...
  2. Create Auto Scaling Group:
     aws autoscaling create-auto-scaling-group \
       --auto-scaling-group-name web-asg \
       --launch-template LaunchTemplateName=web-lt \
       --min-size 2 --max-size 10 --desired-capacity 3
  3. Create scaling policies:
     aws autoscaling put-scaling-policy \
       --auto-scaling-group-name web-asg \
       --policy-name scale-up \
       --policy-type TargetTrackingScaling \
       --target-tracking-configuration TargetValue=70.0,PredefinedMetricSpecification={PredefinedMetricType=ASGAverageCPUUtilization}
  4. Test scaling behavior
  5. Terminate old instance once traffic confirmed on ASG

Monitoring Steps:
  1. Set CloudWatch alarm: ASG GroupTerminatingInstances > 0 → PagerDuty
  2. Monitor: CPUUtilization should stay 60-80%, not spike above 90%
  3. Check: Desired capacity should scale 2-4 under normal load
  4. Alert: If scale-out lag > 3 minutes during spike

Validation Criteria:
  ✓ No errors in application logs after ASG deployment
  ✓ Request latency p95 < 500ms (same as before, slight delay during scale-up OK)
  ✓ Auto Scaling has successfully processed at least 2 scale events
  ✓ Cost monitoring confirms ~$350-400/mo baseline (before spikes)
  ✓ Team confirms performance is acceptable

═══════════════════════════════════════════════════════════════════════
SUMMARY
═══════════════════════════════════════════════════════════════════════
Total Monthly Savings: $900.00
Total Annual Savings: $10,800.00
```

### Response Caching

**[src/storage/recommendation_cache.py](src/storage/recommendation_cache.py)**

```python
# Redis cache keys
finops:rec:current:{architecture_id} → Current recommendations (24h)
finops:rec:history:{architecture_id} → Historical runs (up to 100 entries, 90d)
finops:task:{task_id} → Background task status + progress
```

### Frontend Display (React Components)

**[frontend/src/components/RecommendationCard.jsx](frontend/src/components/RecommendationCard.jsx)**

- Beautiful card design (pricing table style)
- Monthly savings badge (top-right)
- Color-coded severity badges
- Expandable details
- AWS FinOps best practices reference
- Implementation steps (collapsible)

---

## 8. COMPLETE CONFIGURATION FOR CONTEXT PACKAGES

### Environment Variables

```bash
# LLM Configuration
OLLAMA_URL=http://localhost:11434  # Qwen 2.5 7B endpoint
FINOPS_MODEL=mistral:latest        # Model name in Ollama
USE_GEMINI=false                   # Fallback to Gemini API
GEMINI_API_KEY=<key>               # Gemini API key if enabled

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/finops-db

# Redis (cache + Celery)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# AWS
AWS_REGION=us-east-1
AWS_PROFILE=default

# RAG
RAG_INDEX_DIR=data/rag_index        # Where to persist vector indices
BEHAVIORAL_DATA_PATH=data/behavioral/dataset.jsonl
```

### Default Parameters

```python
# Simulation
MONTE_CARLO_TRIALS_PER_SCENARIO = 200  # Accuracy vs speed tradeoff
SPIKE_MULTIPLIER = 3.0                  # 3× baseline for "spike" scenario
EXTREME_MULTIPLIER = 10.0               # 10× baseline for "extreme"

# LLM Generation
RECOMMENDATION_TEMPERATURE = 0.2        # Deterministic (low temp)
RECOMMENDATION_MAX_TOKENS = 4000        # Generates 10-15 recommendations
RECOMMENDATION_TIMEOUT = 300            # 5 minutes max wait

# Context Package
CONTEXT_SECTIONS = 8                    # Overview, Critical, Cost, Anti-patterns, Risk, Anomalies, Trends, Dependencies

# Caching
RECOMMENDATION_CACHE_TTL = 86400        # 24 hours
HISTORY_RETENTION = 90                  # 90 days
MAX_HISTORY_ENTRIES = 100               # Per architecture

# Background Tasks
CELERY_BEAT_SCHEDULE = {
    "collect_cur_hourly": crontab(minute=0),  # Every hour at :00
    "cleanup_cache_daily": crontab(hour=2),   # Daily at 2 AM
}
```

### Docker Compose Services

**[docker-compose.extended.yml](docker-compose.extended.yml)**

```yaml
services:
  postgres:    # Database (port 5432)
  redis:       # Cache + Celery broker (port 6379)
  ollama:      # LLM endpoint (port 11434)
  api:         # FastAPI backend (port 8000)
  worker:      # Celery worker + Beat scheduler
  frontend:    # React UI (port 5173)
```

---

## 9. KEY INTEGRATION POINTS

### Data Flow Summary

```
AWS Architecture JSON
    ↓
    [src/api/handlers/ingest.py]
    ↓
GraphAnalyzer (per-node metrics)
    ↓
ContextAssembler (8-section package)
    ↓
Service Inventory + CloudWatch Metrics + Graph Context + Pricing + Best Practices
    ↓
LLM System Prompts + User Prompts (via Ollama)
    ↓
5-Agent Pipeline (Topology → Behavior → Cost → Detective → Synthesizer)
    ↓
Recommendation Parser (extracts "### Recommendation #N" blocks)
    ↓
Recommendation Cards (resource_id + problem + solution + savings)
    ↓
Redis Cache (24h) + PostgreSQL History (90d)
    ↓
Frontend Display (React components)
```

### Critical Code Paths

1. **Recommendation Generation:**
   - [src/llm/client.py](src/llm/client.py) `generate_recommendations()`

2. **Context Assembly:**
   - [src/analysis/context_assembler.py](src/analysis/context_assembler.py) `assemble()`

3. **5-Agent Pipeline:**
   - [src/agents/orchestrator.py](src/agents/orchestrator.py) `run()`

4. **Background Tasks:**
   - [src/background/tasks.py](src/background/tasks.py) `generate_recommendations_bg()`

5. **RAG Grounding:**
   - [src/agents/base_agent.py](src/agents/base_agent.py) `_call_llm()` with GraphRAG injection

6. **API Handlers:**
   - [src/api/handlers/analyze.py](src/api/handlers/analyze.py) `analyze_architecture()`
   - [src/api/handlers/recommendations.py](src/api/handlers/recommendations.py)

---

## 10. PERFORMANCE & RELIABILITY

### Timing Breakdown (typical 42-service architecture)

```
Total pipeline: ~45-60 seconds

Stage timings:
  - Load graph data:           100 ms
  - Build NetworkX graph:      50 ms
  - Cascade analysis:          200 ms
  - Monte Carlo (200 trials):  8,000-12,000 ms (bottleneck)
  - GraphAnalyzer:            200 ms
  - ContextAssembler:         300 ms
  - 5-Agent LLM calls:        20,000-30,000 ms (depends on Ollama speed)
  - Recommendation generation: 3,000-5,000 ms
  - Parsing + validation:     100 ms
  - DB save + caching:        50 ms
```

### Caching Strategy

- **Current results:** 24-hour Redis TTL (instant reload)
- **History:** Up to 100 entries, 90-day retention
- **Task status:** Real-time polling (Celery + Redis)
- **Fallback:** PostgreSQL backup (if Redis unavailable)

### Error Handling

- **Ollama timeout:** Falls back to Gemini API (if configured)
- **Missing data:** GraphAnalyzer handles sparse graphs gracefully
- **RAG failure:** Continues without grounding (degrades gracefully)
- **Parser failures:** Multiple parsing strategies ensure at least some recommendations extracted

### Hallucination Prevention

1. **GraphRAG grounding:** System prompt explicitly forbids hallucinations
2. **Validation against inventory:** Parser checks resource IDs against actual services
3. **Zero-savings filtering:** Removes placeholder "$0.01" recommendations
4. **Deduplication:** Removes duplicate recommendations by resource_id

---

## Summary

The FinOps AI system is a **production-grade cost optimization engine** combining:

✅ **Sophisticated LLM Integration:**
- 5-agent sequential pipeline with context flow between agents
- Ollama (Qwen 2.5 7B) for deterministic, grounded analysis
- Automatic Gemini fallback for reliability

✅ **Rich Context Building:**
- 8-section architecture context packages
- GraphRAG-based behavioral knowledge indexing
- Per-node metrics + interesting narratives

✅ **Robust Workflow:**
- Simulation (cascade + Monte Carlo) for ground truth
- Multi-stage parser to extract ALL recommendations
- Redis caching for performance + PostgreSQL for durability

✅ **Production Ready:**
- Background task support (Celery)
- Progress tracking + real-time polling
- Graceful error handling + hallucination prevention
- Beautiful Card UI with drill-down details

The system generates **10-15 precise, actionable AWS cost optimization recommendations** with validated savings estimates, implementation steps, and risk assessments.

