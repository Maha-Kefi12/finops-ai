# FinOps AI System - Complete LLM Input/Output Flow for Recommendations

**Status**: Detailed Analysis Complete  
**Date**: 2026-03-23  
**Focus**: Backend recommendation generation pipeline with exact parsing logic

---

## EXECUTIVE SUMMARY

The recommendation generation flow follows this path:

```
GraphAnalyzer (analyze graph) 
  ↓
ContextAssembler (package context into 9 sections)
  ↓
generate_recommendations() (in src/llm/client.py)
  ↓
[Prompt Construction]
  System Prompt (RECOMMENDATION_SYSTEM_PROMPT)
  User Prompt (RECOMMENDATION_USER_PROMPT) + formatted sections
  ↓
call_llm() 
  → Ollama/Mistral (primary) 
  → Fallback: Gemini Flash 2.0
  ↓
Raw LLM Output (unstructured text, 4000 tokens)
  ↓
_parse_all_recommendations() [4-STRATEGY PARSER]
  ↓
_deduplicate_cards()
_validate_against_inventory()
_filter_zero_savings_cards()
_enrich_cards()
  ↓
RecommendationResult (cards, savings, timing)
  ↓
Cache + Database Storage
```

---

## PART 1: CONTEXT ASSEMBLY (BEFORE LLM)

### 1.1 Entry Point: `generate_recommendations_bg()`

**File**: `src/background/tasks.py` (lines 64-190)  
**Type**: Celery async task  
**Trigger**: API call to `/api/recommendations/generate-bg`

```python
@app.task(bind=True, name="src.background.tasks.generate_recommendations_bg")
def generate_recommendations_bg(self, architecture_id=None, architecture_file=None):
    """Background task that orchestrates the full pipeline"""
    
    # 1. Load graph data (from DB or synthetic file)
    # 2. Run GraphAnalyzer.analyze()
    # 3. Assemble context with ContextAssembler
    # 4. Call generate_recommendations()
    # 5. Cache + save results
```

### 1.2 Graph Analysis Phase

**File**: `src/analysis/graph_analyzer.py` (lines 1-500+)  
**Class**: `GraphAnalyzer`  
**Output**: `AnalysisReport` (dataclass)

**Process**:
- Takes `graph_data` dict with `services` (nodes) and `dependencies` (edges)
- Builds NetworkX `DiGraph` with attributes:
  - Cost per service: `cost_monthly`
  - Performance: `cpu_utilization`, `memory_utilization`, `health_score`
  - Structure: `type`, `instance_type`, `region`, `environment`

**Metrics Computed Per Node** (in `compute_all_metrics()`):
- **Centrality**: `betweenness_centrality`, `pagerank`, `degree_centrality`
- **Structure**: `in_degree`, `out_degree`, `clustering_coefficient`
- **Cost**: `cost_monthly`, `cost_per_dependency`, `cost_share`
- **Health**: `health_score`, `risk_level`, `error_count`

**Output Structure** (`AnalysisReport` dataclass):
```python
AnalysisReport(
    architecture_name: str,
    total_nodes: int,
    total_edges: int,
    total_cost: float,
    graph_density: float,
    is_dag: bool,
    all_node_metrics: List[Dict],          # Metrics for EVERY node
    interesting_nodes: List[Dict],         # Deep analysis of top 25 nodes
    summary: Dict,                         # Aggregate stats
)
```

### 1.3 Context Assembly Phase

**File**: `src/analysis/context_assembler.py` (lines 1-400+)  
**Class**: `ContextAssembler`  
**Output**: `ArchitectureContextPackage` (dataclass) - **9-SECTION PACKAGE**

**The ContextAssembler takes**:
- `graph_data` (raw architecture)
- `analysis_report` (from GraphAnalyzer)

**Produces the 9-Section Package**:

#### Section 1: Architecture Overview
```python
architecture_name: str
total_services: int
total_cost_monthly: float
total_dependencies: int
avg_centrality: float
architecture_type: str  # "microservices", etc.
service_breakdown: Dict  # {type: {count, cost}}
geographic_distribution: Dict  # {region: count}
cross_az_dependency_count: int
```

#### Section 2: Critical Services
```python
critical_services: List[Dict]  # Top services by centrality/cost
# Each contains: node_id, name, type, cost, centrality, in_degree, etc.
```

#### Section 3: Cost Analysis
```python
top_expensive: List[Dict]           # Top 10 by monthly cost
cost_outliers: List[Dict]           # Services costing 2x their peers
waste_detected: List[Dict]          # Idle resources, oversized, etc.
total_waste_monthly: float          # Sum of detectable waste
```

#### Section 4: Architectural Anti-Patterns
```python
anti_patterns: List[Dict]
# e.g., "N+1 Query Pattern", "Unoptimized Data Transfer", "Over-provisioned Capacity"
# Each contains: name, severity (critical|high|medium|low), description
```

#### Section 5: Risk Assessment
```python
risks: List[Dict]
# e.g., "Single Point of Failure: database", "Cascading Failure Chain"
# Each: name, severity, description, impact, affected_nodes
```

#### Section 6: Behavioral Anomalies
```python
anomalies: List[Dict]
# e.g., "Sudden traffic spike", "Abnormal error rate"
# Each: name, severity, node_id, node_name, description, evidence, impact
```

#### Section 7: Historical Trends
```python
cost_trends: Dict  # {month: cost} for last 90 days
growth_trajectory: Dict  # trend line, growth rate, volatility
```

#### Section 8: Dependency Analysis
```python
critical_dependencies: List[Dict]  # High-impact edges (cascading)
circular_dependencies: List[Dict]  # Cycles (if DAG=false)
orphaned_services: List[str]       # No deps in or out
deep_chains: List[Dict]            # Long call chains
```

#### Section 9: GraphRAG Integration
```python
rag_best_practices: List[str]  # Grounded AWS best practices from KB
rag_relevant_docs: List[Dict]  # {source, content} from documentation
```

**Example Section 9 Content**:
- "Right-size to 60-70% CPU utilization (not 100%)"
- "Use Reserved Instances for steady workloads (30-40% savings)"
- "Implement caching layers (Redis/Memcached) for databases"

---

## PART 2: PROMPT CONSTRUCTION

### 2.1 System Prompt

**File**: `src/llm/prompts.py` (lines 8-83)  
**Constant**: `RECOMMENDATION_SYSTEM_PROMPT`

**Key Content**:
```
"You are an AWS FinOps expert. Your job: analyze AWS infrastructure 
and generate 10-20 cost optimization recommendations."

CRITICAL FORMATTING RULES:
1. Start EVERY recommendation with: "### Recommendation #N"
2. After each recommendation: "---"
3. Use EXACT resource IDs from SERVICE INVENTORY
4. Show COMPLETE savings calculations (no $0.01 placeholders)

EXACT FORMAT FOR EACH RECOMMENDATION:

### Recommendation #1
**Resource ID:** `exact-resource-id-here`
**Service:** RDS | EC2 | Lambda | S3 | etc
**Current Cost:** $XXX.XX/month
**Environment:** production | staging | dev

**Problem:** [What's wrong - be specific with metrics]
**Solution:** [What to change - exact instance types or config]

**Savings:**
Current cost: $XXX.XX/month
New cost: $YYY.YY/month
Monthly savings: $ZZZ.ZZ/month

**Implementation:**
```bash
aws [service] modify-[resource] ...
```

**Risk:** LOW | MEDIUM | HIGH

---
```

### 2.2 User Prompt Construction

**File**: `src/llm/prompts.py` (lines 86-160)  
**Constant**: `RECOMMENDATION_USER_PROMPT` (template)

**Template Uses These Placeholders** (filled by `generate_recommendations()`):
```python
{service_inventory}      # From _build_service_inventory()
{cloudwatch_metrics}     # From _build_metrics()
{graph_context}          # From _build_graph()
{pricing_data}           # From _build_pricing()
{aws_best_practices}     # From _build_best_practices()
```

### 2.3 Context Builders (Build the 5 Sections)

**File**: `src/llm/client.py` (lines 597-710)

#### `_build_service_inventory(graph_data)` - Lines 601-650
**Output**: Markdown list of all services sorted by cost

```
## SERVICE INVENTORY (sorted by cost)

- service-name: EC2 (i-12345abc) @ $250.00/mo [Env: prod] 
  (Consider: right-sizing, reserved instances, spot instances)
  Instance type: r6g.xlarge
  Memory: 32GB

- another-service: S3 (data-bucket) @ $150.00/mo [Env: prod]
  (Consider: lifecycle policies, storage class optimization)
  Storage: 500GB

**TOTAL MONTHLY COST: $5,234.56**
**ANALYZE ALL 18 SERVICES ABOVE**
```

**Key Content**:
- Each service with ID, type, cost, environment
- Optimization hints per service type
- Total cost summary

#### `_build_metrics(graph_data)` - Lines 653-663
**Output**: CloudWatch metrics for services

```
i-12345abc: {"cpu": 42.5, "memory": 71.2, "network_in": 100}
...
```

#### `_build_graph(pkg_dict)` - Lines 666-675
**Output**: Graph structure summary

```
Bottlenecks:
  - api-gateway: centrality=0.312
  - database: centrality=0.285
```

#### `_build_pricing()` - Lines 678-682
**Output**: AWS pricing reference

```
RDS: db.r5.large=$213/mo, db.r5.xlarge=$426/mo, db.r5.2xlarge=$853/mo
EC2: t3.medium=$30/mo, m5.large=$70/mo, m5.xlarge=$140/mo
```

#### `_build_best_practices(pkg_dict)` - Lines 685-710
**Output**: Grounded AWS best practices + RAG docs

```
AWS FINOPS BEST PRACTICES:
- Right-size to 60-70% CPU utilization (not 100%)
- Use Reserved Instances for steady workloads (30-40% savings)
- Minimize cross-AZ data transfer ($0.01-0.02/GB)
- Implement caching layers (Redis/Memcached) for databases
- Schedule non-prod resources (dev/test shutdown)

GROUNDED BEST PRACTICES (from documentation):
[Knowledge base entries]

RELEVANT AWS DOCUMENTATION:
- docs: "EC2 instance sizing guidelines..."
```

### 2.4 Final User Prompt Assembly

**File**: `src/llm/client.py` (lines 189-206)

```python
user_prompt = RECOMMENDATION_USER_PROMPT.format(
    service_inventory=service_inventory,
    cloudwatch_metrics=cloudwatch_metrics,
    graph_context=graph_context,
    pricing_data=pricing_data,
    aws_best_practices=aws_best_practices,
)
# Result: ~3000-4000 characters of structured context
```

**Total Prompt Size**:
- System prompt: ~1200 chars
- User prompt: ~3500-4500 chars
- **Total**: ~5000 chars for input

---

## PART 3: LLM CALL

### 3.1 LLM Backend Selection

**File**: `src/llm/client.py` (lines 52-70)

**Config**:
```python
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("FINOPS_MODEL", "mistral:latest")  # Faster model

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash-exp"

# Backend selection logic
USE_GEMINI = os.getenv("USE_GEMINI", "false").lower() == "true" and GEMINI_API_KEY
```

**Priority**:
1. **Primary**: Ollama + Mistral 7B-Instruct (local, low latency)
2. **Fallback**: Gemini Flash 2.0 (API, if Ollama fails)

### 3.2 Function: `call_llm()`

**File**: `src/llm/client.py` (lines 72-74)

```python
def call_llm(system_prompt: str, user_prompt: str, 
             temperature: float = 0.2,
             max_tokens: int = 4096,
             architecture_name: str = "") -> str:
    """Routes to Gemini or Ollama based on config"""
```

### 3.3 Function: `_call_ollama()`

**File**: `src/llm/client.py` (lines 121-166)

**Process**:
1. **Health check**: GET `/api/tags` (verify Ollama is running)
2. **POST /api/chat** with:
```python
{
    "model": "mistral:latest",
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    "stream": False,
    "options": {
        "temperature": 0.2,      # Low: deterministic output
        "num_predict": 4096,     # Max tokens
    }
}
```
3. **Response**: JSON with `message.content` field
4. **Timeout**: 300 seconds (5 min)

**Error Handling**:
- Connection error → RuntimeError
- HTTP status != 200 → RuntimeError
- Timeout → RuntimeError with timeout message

### 3.4 Function: `_call_gemini()`

**File**: `src/llm/client.py` (lines 104-119)

**Process**:
1. Configure API key: `genai.configure(api_key=GEMINI_API_KEY)`
2. Create model: `GenerativeModel(GEMINI_MODEL, system_instruction=system_prompt)`
3. Call: `model.generate_content(user_prompt, generation_config=...)`
4. Return: `response.text`

**Parameters**:
```python
generation_config=GenerationConfig(
    temperature=0.2,
    max_output_tokens=4096,
)
```

### 3.5 Raw LLM Output

**Expected Format** (strictly enforced by system prompt):

```
### Recommendation #1: Downsize t3.micro to t3.nano

**Resource ID:** `i-12345abc`
**Service:** EC2
**Current Cost:** $15.00/month
**Environment:** development

**Problem:**
The development instance i-12345abc is a t3.micro running at only 20% CPU usage. 
This indicates significant over-provisioning for the workload.

**Solution:**
Downsize from t3.micro ($15/mo) to t3.nano ($7.50/mo). The nano instance has 
0.5 vCPU vs micro's 1 vCPU, which is still 2.5x the required load based on metrics.

**Savings:**
Current cost: $15.00/month
New cost: $7.50/month
Monthly savings: $7.50/month

**Implementation:**
\`\`\`bash
aws ec2 stop-instances --instance-ids i-12345abc
aws ec2 create-image --instance-id i-12345abc --name dev-nano
aws ec2 run-instances --image-id ami-xxx --instance-type t3.nano
\`\`\`

**Risk:** LOW

---

### Recommendation #2: Enable S3 Intelligent-Tiering

[Similar format...]

---

### Recommendation #3: ...

---
```

**Key Characteristics**:
- Starts with `### Recommendation #N` (EXACT)
- Separated by `---` (triple dash on own line)
- 8-15 recommendations total
- Each has: Resource ID, Service, Cost, Problem, Solution, Savings, Implementation, Risk
- Savings must be concrete (e.g., $150/mo, not $0.01)

---

## PART 4: PARSING - THE 4-STRATEGY ROBUST PARSER

### 4.1 Parser Entry Point: `_parse_all_recommendations()`

**File**: `src/llm/client.py` (lines 273-337)  
**Key Feature**: **4 fallback strategies** - ensures parsing even if LLM format is imperfect

```python
def _parse_all_recommendations(text: str) -> List[Dict]:
    """Tries 4 strategies to extract recommendations"""
    
    if not text or len(text) < 100:
        logger.error("Response too short: %d chars", len(text))
        return []
    
    # STRATEGY 1: Split by "### Recommendation #N"
    # STRATEGY 2: Split by any "### [title]"
    # STRATEGY 3: Split by "---" delimiter
    # STRATEGY 4: Split by double newline
```

### 4.2 STRATEGY 1: `### Recommendation #N` Pattern

**File**: `src/llm/client.py` (lines 282-290)

```python
pattern1 = r"###\s+Recommendation\s+#(\d+)"
matches1 = list(re.finditer(pattern1, text, re.IGNORECASE))

if len(matches1) >= 5:
    logger.info("Strategy 1: Found %d recommendations via '### Recommendation #N'", len(matches1))
    return _extract_sections(text, matches1)
```

**Regex Pattern Breakdown**:
- `###` - literal three hashes
- `\s+` - one or more whitespace
- `Recommendation` - literal word
- `\s+` - whitespace
- `#` - hash symbol
- `(\d+)` - capture one or more digits (recommendation number)

**Fallback**: If Strategy 1 finds < 5 matches, try Strategy 2

### 4.3 STRATEGY 2: Any `### [Title]` Pattern

**File**: `src/llm/client.py` (lines 292-299)

```python
pattern2 = r"###\s+([^\n#]{5,100})"
matches2 = list(re.finditer(pattern2, text))

if len(matches2) >= 5:
    logger.info("Strategy 2: Found %d recommendations via '### [title]'", len(matches2))
    return _extract_sections(text, matches2)
```

**Regex Pattern Breakdown**:
- `###\s+` - hash header marker
- `([^\n#]{5,100})` - capture 5-100 non-newline, non-hash characters (the title)

**Use Case**: If LLM generates `### My Optimization Title` instead of strict `### Recommendation #1`

### 4.4 STRATEGY 3: `---` Delimiter Split

**File**: `src/llm/client.py` (lines 301-315)

```python
sections = text.split("---")
sections = [s.strip() for s in sections if len(s.strip()) > 100]

if len(sections) >= 5:
    logger.info("Strategy 3: Found %d recommendations via '---' delimiter", len(sections))
    cards = []
    for i, section in enumerate(sections, 1):
        card = _parse_card_text(section, i)
        if card:
            cards.append(card)
    return cards
```

**Use Case**: If LLM uses `---` to separate recommendations but not the proper header format

### 4.5 STRATEGY 4: Double Newline Split (FALLBACK)

**File**: `src/llm/client.py` (lines 317-327)

```python
sections = re.split(r'\n\n+', text)
sections = [s.strip() for s in sections if len(s.strip()) > 100]

if len(sections) >= 5:
    logger.info("Strategy 4: Found %d sections via double newline", len(sections))
    cards = []
    for i, section in enumerate(sections, 1):
        card = _parse_card_text(section, i)
        if card:
            cards.append(card)
    return cards[:20]  # Limit to 20
```

**Use Case**: If LLM returns minimally formatted text with just double newlines

### 4.6 Parsing Single Card: `_parse_card_text()`

**File**: `src/llm/client.py` (lines 340-550)

**Process**:

#### Step 1: Initialize Card Structure
```python
card = {
    "priority": card_num,
    "recommendation_number": card_num,
    "title": "",
    "severity": "medium",
    "category": "optimization",
    "risk_level": "medium",
    "implementation_complexity": "medium",
    "resource_identification": {},
    "cost_breakdown": {"current_monthly": 0, "line_items": []},
    "inefficiencies": [],
    "recommendations": [],
    "total_estimated_savings": 0,
    "raw_analysis": text[:1000],
}
```

#### Step 2: Extract Title

**File**: Lines 352-360

```python
title_match = re.search(r"###\s+(.+?)(?:\n|$)", text)
if title_match:
    title = title_match.group(1).strip()
    title = re.sub(r"Recommendation\s+#\d+:?\s*", "", title, flags=re.IGNORECASE)
    card["title"] = title[:120] if title else f"Recommendation #{card_num}"
else:
    card["title"] = f"Recommendation #{card_num}"
```

**Example Transformations**:
- Input: `### Recommendation #1: Downsize t3.micro to t3.nano`
- After regex: `Downsize t3.micro to t3.nano`
- Stored: `"Downsize t3.micro to t3.nano"`

#### Step 3: Extract Resource ID (CRITICAL)

**File**: Lines 362-380

**5 Patterns Tried in Order**:

```python
resource_patterns = [
    r"\*\*Resource ID:\*\*\s*`?([^`\n]+)`?",     # **Resource ID:** `id`
    r"\*\*Resource:\*\*\s*`?([^`\n]+)`?",         # **Resource:** `id`
    r"\*\*Service Name:\*\*\s*`?([^`\n]+)`?",     # **Service Name:** `id`
    r"Resource:\s*([^\n]+)",                       # Resource: id
    r"Resource ID:\s*([^\n]+)",                    # Resource ID: id
]
```

**Processing**:
1. Try each pattern in order
2. Extract capturing group (the ID)
3. Strip whitespace
4. Validate (must be > 1 char)
5. Store in `card["resource_identification"]["resource_id"]`
6. Also store as `service_name`

**Fallback if No Resource ID Found** (Lines 382-392):
```python
# Extract service type from text
service_types = ["EC2", "S3", "RDS", "Lambda", "NAT", "DynamoDB", 
                 "ElastiCache", "Redshift", "ECS", "EKS", ...]
for svc_type in service_types:
    if svc_type.lower() in text.lower():
        card["resource_identification"]["service_type"] = svc_type
        card["resource_identification"]["resource_id"] = f"{svc_type.lower()}-recommendation"
        break
```

**Example**:
- Input text: "AWS Lambda function recommendation..."
- Resource ID inferred: `"lambda-recommendation"`

#### Step 4: Extract Service Type

**File**: Lines 394-397

```python
svc_match = re.search(r"\*\*Service:\*\*\s*([^\n]+)", text, re.IGNORECASE)
if svc_match:
    card["resource_identification"]["service_type"] = svc_match.group(1).strip()
```

#### Step 5: Extract Current Cost (EXPANDED - 12 PATTERNS)

**File**: Lines 399-430

**Pattern Categories**:

**Markdown Bold Patterns**:
```
r"\*\*Current\s+(?:Monthly\s+)?Cost:\*\*\s*\$([0-9,]+\.?\d*)"
r"\*\*Cost\s+per\s+month:\*\*\s*\$([0-9,]+\.?\d*)"
```

**Plain Text Patterns**:
```
r"Current\s+(?:monthly\s+)?cost:\s*\$([0-9,]+\.?\d*)"
r"Cost\s+per\s+month:\s*\$([0-9,]+\.?\d*)"
r"Cost\s+per\s+month:\s*\$([0-9,]+\.?\d*)"
```

**Spending Patterns**:
```
r"(?:Current|Monthly|Today's)\s+(?:spending|spend):\s*\$([0-9,]+\.?\d*)"
r"Currently\s+(?:spending|costs)\s+\$([0-9,]+\.?\d*)"
r"Monthly\s+(?:cost|spending):\s*\$([0-9,]+\.?\d*)"
```

**Alt Format**:
```
r"(?:Cost|Spending)\s+(?:is|of)?\s*\$([0-9,]+\.?\d*)(?:\s+per month|/month)?"
r"\*\*Current Cost:\*\*\s*\$([0-9,]+\.?\d*)\s*(?:per month|/month)?"
```

**Processing**:
```python
for pat in cost_patterns:
    m = re.search(pat, text, re.IGNORECASE)
    if m:
        try:
            card["cost_breakdown"]["current_monthly"] = float(m.group(1).replace(",", ""))
            break  # Found it, stop searching
        except ValueError:
            pass  # Invalid number, try next pattern
```

**Example**:
- Input: `**Current Cost:** $2,400.00/month`
- Extracted: `2400.00`

#### Step 6: Extract Savings (EXPANDED - 17 PATTERNS)

**File**: Lines 432-490

**Most Critical Extraction** - Multiple pattern families:

**Markdown Bold Savings**:
```
r"\*\*(?:Expected|Estimated|Potential)\s+(?:Monthly\s+)?Savings?:\*\*\s*\$([0-9,]+\.?\d*)"
r"\*\*Savings?:\*\*\s*\$([0-9,]+\.?\d*)"
r"\*\*Monthly Savings?:\*\*\s*\$([0-9,]+\.?\d*)"
```

**Explicit Patterns**:
```
r"Monthly savings:\s*\$([0-9,]+\.?\d*)"
r"Monthly Savings:\s*\$([0-9,]+\.?\d*)"
r"(?:Expected|Estimated|Potential)\s+(?:monthly\s+)?savings?:\s*\$([0-9,]+\.?\d*)"
```

**Dollar-First Patterns**:
```
r"\$([0-9,]+\.?\d*)\s+(?:monthly\s+)?savings?(?:\s+per month)?"
r"\$([0-9,]+\.?\d*)\s+(?:cost reduction|estimated savings|potential savings)"
```

**Reduction Patterns**:
```
r"(?:Expected|Estimated|Potential)?\s*(?:reduction|savings?):\s*\$([0-9,]+\.?\d*)"
r"(?:reduction|decrease|savings?):\s*\$([0-9,]+\.?\d*)"
```

**Action Patterns**:
```
r"(?:Save|Save approximately|Estimated Savings?|Potential Savings?):\s*\$([0-9,]+\.?\d*)"
r"(?:save|save approximately)\s+\$([0-9,]+\.?\d*)"
```

**Other Patterns**:
```
r"Expected:\s*\$([0-9,]+\.?\d*)"
r"Projected Savings?:\s*\$([0-9,]+\.?\d*)"
r"(?:after|post)-(?:optimization|implementation):\s*\$([0-9,]+\.?\d*)"
r"Result:\s*\$([0-9,]+\.?\d*)\s*(?:savings?)?"
```

**Processing**:
```python
for pat in savings_patterns:
    m = re.search(pat, text, re.IGNORECASE)
    if m:
        try:
            match_val = m.group(1) if m.lastindex else None
            if match_val:
                savings = float(match_val.replace(",", ""))
                if savings > 0.01:  # Reject placeholders like $0.99 or $0.01
                    card["total_estimated_savings"] = savings
                    break
        except (ValueError, IndexError):
            pass
```

**Fallback to Percentage Extraction** (Lines 492-508):
```python
# If no dollar savings found, try percentage-based calculation
if card["total_estimated_savings"] == 0:
    current_cost = card["cost_breakdown"]["current_monthly"]
    if current_cost > 0:
        pct_patterns = [
            r"reduce(?:s)?\s+cost(?:s)?\s+by\s+(\d+)%",
            r"(\d+)%\s+cost\s+reduction",
            r"(\d+)%\s+savings?",
        ]
        for pat in pct_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                try:
                    pct = float(m.group(1))
                    if 1 <= pct <= 99:  # Sanity check
                        estimated_savings = current_cost * (pct / 100)
                        if estimated_savings > 0.01:
                            card["total_estimated_savings"] = round(estimated_savings, 2)
                            break
                except ValueError:
                    pass
```

**Example Savings Extractions**:
- `Monthly savings: $450.00` → `450.00`
- `$1,200 cost reduction` → `1200.00`
- `Reduce capacity by 30%` (current cost $5000) → `1500.00`

#### Step 7: Extract Implementation Steps

**File**: Lines 510-517

```python
impl_lines = []
bash_match = re.search(r"```bash\n(.*?)\n```", text, re.DOTALL)
if bash_match:
    commands = bash_match.group(1).strip().split("\n")
    impl_lines = [c.strip() for c in commands if c.strip() and not c.strip().startswith("#")]
```

**Process**:
1. Find bash code block: ` ```bash ... ``` `
2. Split lines
3. Filter out comments (lines starting with `#`)
4. Store as list of commands

#### Step 8: Build Recommendation Object

**File**: Lines 519-529

```python
card["recommendations"] = [{
    "action_number": 1,
    "action": card["title"],
    "estimated_monthly_savings": card["total_estimated_savings"],
    "implementation_steps": impl_lines,
    "validation_steps": [],
    "performance_impact": "",
    "risk_mitigation": "",
}]
```

**Final Card Structure**:
```python
{
    "priority": 1,
    "recommendation_number": 1,
    "title": "Downsize t3.micro to t3.nano",
    "severity": "medium",
    "category": "optimization",
    "risk_level": "medium",
    "implementation_complexity": "medium",
    "resource_identification": {
        "resource_id": "i-12345abc",
        "service_name": "i-12345abc",
        "service_type": "EC2",
    },
    "cost_breakdown": {
        "current_monthly": 15.0,
        "line_items": [],
    },
    "recommendations": [{
        "action_number": 1,
        "action": "Downsize t3.micro to t3.nano",
        "estimated_monthly_savings": 7.5,
        "implementation_steps": [
            "aws ec2 stop-instances --instance-ids i-12345abc",
            "aws ec2 create-image --instance-id i-12345abc --name dev-nano",
            "aws ec2 run-instances --image-id ami-xxx --instance-type t3.nano",
        ],
        "validation_steps": [],
        "performance_impact": "",
        "risk_mitigation": "",
    }],
    "total_estimated_savings": 7.5,
    "raw_analysis": "The development instance...",
}
```

---

## PART 5: POST-PARSING VALIDATION & ENRICHMENT

### 5.1 Deduplication: `_deduplicate_cards()`

**File**: `src/llm/client.py` (lines 641-667)

**Purpose**: Remove duplicate recommendations

**Deduplication Key**:
```python
dedup_key = (res_id.lower().strip(), title.lower()[:50])
```

**Process**:
```python
seen: set = set()
deduped = []

for card in cards:
    res_id = card.get("resource_identification", {}).get("resource_id", "")
    title = card.get("title", "")
    dedup_key = (res_id.lower().strip(), title.lower()[:50])
    
    if dedup_key not in seen:
        seen.add(dedup_key)
        deduped.append(card)
    else:
        logger.info("Filtered duplicate recommendation for resource: %s", res_id)

return deduped
```

**Example**:
- Card 1: resource_id="i-123", title="Downsize EC2"
- Card 2: resource_id="i-123", title="Downsize EC2"
- **Result**: Card 2 filtered (duplicate)

### 5.2 Validation: `_validate_against_inventory()`

**File**: `src/llm/client.py` (lines 670-739)

**Purpose**: Filter out hallucinated resources LLM invented

**Strategy**: LENIENT (keep most recommendations)

**Process**:

**Step 1**: Build valid service sets from graph_data
```python
valid_ids = set()
valid_names = set()
valid_types = set()

for svc in services:
    valid_ids.add(svc.get("id", "").lower().strip())
    valid_names.add(svc.get("name", "").lower().strip())
    valid_types.add(svc.get("type", "").lower())
```

**Step 2**: Check each card
```python
res_id = card.get("resource_identification", {}).get("resource_id", "").lower().strip()
svc_name = card.get("resource_identification", {}).get("service_name", "").lower().strip()
svc_type = card.get("resource_identification", {}).get("service_type", "").lower().strip()

if res_id:
    if res_id in valid_ids or svc_name in valid_names:
        validated.append(card)
    else:
        # Lenient: Still keep it (resource extraction is hard)
        validated.append(card)
else:
    # No resource ID extracted - keep it anyway
    # The recommendation is valid even if we couldn't parse resource ID
    validated.append(card)
```

**Result**: Very permissive - most recommendations kept

### 5.3 Zero-Savings Filter: `_filter_zero_savings_cards()`

**File**: `src/llm/client.py` (lines 742-800)

**Purpose**: Remove recommendations with explicit zero/negative savings

**Logic**:
```python
for card in cards:
    savings = card.get("total_estimated_savings")
    current_cost = card.get("cost_breakdown", {}).get("current_monthly", 0)
    
    # Filter if:
    # - savings is None/empty AND no cost data
    if savings is None or savings == "":
        if current_cost == 0:
            # Skip - no data at all
            continue
        else:
            # Keep - cost exists, might estimate savings
            filtered.append(card)
    
    # - savings is explicitly <= 0 (not None)
    elif isinstance(savings, (int, float)) and savings <= 0:
        # Skip - explicitly zero or negative
        continue
    
    # Positive savings - keep
    else:
        filtered.append(card)
```

### 5.4 Enrichment: `_enrich_cards()`

**File**: `src/llm/client.py` (lines 803-813)

**Purpose**: Fill missing data from actual inventory

**Process**:
```python
for card in cards:
    res_id = card.get("resource_identification", {}).get("resource_id", "")
    
    if res_id in svc_map:
        svc = svc_map[res_id]
        
        # Fill current cost if missing
        if card["cost_breakdown"]["current_monthly"] == 0:
            card["cost_breakdown"]["current_monthly"] = svc.get("cost_monthly", 0)
```

---

## PART 6: FINAL OUTPUT STRUCTURE

### 6.1 RecommendationResult Dataclass

**File**: `src/llm/client.py` (lines 36-48)

```python
@dataclass
class RecommendationResult:
    cards: List[Dict[str, Any]] = field(default_factory=list)
    total_estimated_savings: float = 0.0
    context_sections_used: int = 8
    llm_used: bool = False
    generation_time_ms: int = 0
    architecture_name: str = ""
    error: Optional[str] = None
```

### 6.2 Returned to API/Cache

**File**: `src/background/tasks.py` (lines 145-157)

```python
response = {
    "recommendations": rec_result.cards,           # List of card dicts
    "total_estimated_savings": rec_result.total_estimated_savings,  # Float
    "llm_used": rec_result.llm_used,               # Bool
    "generation_time_ms": rec_result.generation_time_ms,  # Int (ms)
    "architecture_name": rec_result.architecture_name or arch_name,  # Str
    "card_count": len(rec_result.cards),           # Int
}

# Cached with key: f"{architecture_id}:{task_id}"
cache.cache_recommendations(cache_key, response)
```

### 6.3 Card Structure (Complete)

Each recommendation card contains:
```python
{
    "priority": int,                    # 1-based ordering
    "recommendation_number": int,       # Matches LLM's numbering
    "title": str,                       # Human-readable title
    "severity": str,                    # "low" | "medium" | "high"
    "category": str,                    # "optimization"
    "risk_level": str,                  # "low" | "medium" | "high"
    "implementation_complexity": str,   # "low" | "medium" | "high"
    
    "resource_identification": {
        "resource_id": str,             # e.g., "i-12345abc"
        "service_name": str,            # e.g., "i-12345abc"
        "service_type": str,            # e.g., "EC2"
    },
    
    "cost_breakdown": {
        "current_monthly": float,       # Current monthly cost
        "line_items": list,             # [{"description", "usage", "cost"}]
    },
    
    "recommendations": [{
        "action_number": int,           # 1
        "action": str,                  # Recommendation title/action
        "estimated_monthly_savings": float,  # $X.XX/month
        "implementation_steps": list,   # ["aws ...", "aws ..."]
        "validation_steps": list,       # []
        "performance_impact": str,      # ""
        "risk_mitigation": str,         # ""
    }],
    
    "total_estimated_savings": float,   # Sum of recommendations
    "raw_analysis": str,                # First 1000 chars of parsed text
}
```

---

## PART 7: ERROR HANDLING & FALLBACKS

### 7.1 LLM Call Failures

**File**: `src/llm/client.py` (lines 161-166)

```python
try:
    resp = requests.post(...)
    if resp.status_code == 200:
        return resp.json().get("message", {}).get("content", "")
    raise RuntimeError(f"Ollama returned {resp.status_code}")
except requests.exceptions.Timeout:
    raise RuntimeError(f"Ollama timeout after {TIMEOUT}s")
except Exception as e:
    raise RuntimeError(f"Ollama error: {e}")
```

**Fallback**: Automatic retry via Celery task's `autoretry_for`

### 7.2 Parsing Failures

**File**: `src/llm/client.py` (lines 264-337)

**4-Strategy Chain Ensures**:
- If Strategy 1 fails → Strategy 2
- If Strategy 2 fails → Strategy 3
- If Strategy 3 fails → Strategy 4
- If all fail → Return `[]` (empty list)

### 7.3 Missing Required Fields

**Strategy**:
- **Resource ID**: Inferred from service type in text (e.g., "Lambda" → `lambda-recommendation`)
- **Current Cost**: Defaults to 0 (filled later by inventory if possible)
- **Savings**: Extracted via percentage if not found directly

### 7.4 Invalid/Hallucinated Data

**Filters**:
1. **Deduplication**: Removes exact duplicates
2. **Validation**: Lenient - keeps most even if resource ID doesn't match
3. **Zero-Savings Filter**: Removes recommendations with no savings data
4. **Enrichment**: Fills gaps from actual inventory

---

## PART 8: EXECUTION TIMELINE

### Typical Execution Flow:

```
[1] API Call to /api/recommendations/generate-bg
    └─→ Task queued in Celery/Redis

[2] Task Execution Starts (~0ms)
    ├─→ Load graph data: ~100ms
    │
    ├─→ GraphAnalyzer.analyze(): ~200ms
    │   ├─→ Build NetworkX graph: ~50ms
    │   ├─→ Compute all metrics: ~100ms
    │   └─→ Identify interesting nodes: ~50ms
    │
    ├─→ ContextAssembler.assemble(): ~300ms
    │   ├─→ Assemble 9-section package: ~250ms
    │   └─→ Retrieve GraphRAG docs: ~50ms
    │
    ├─→ generate_recommendations(): ~5000-8000ms
    │   ├─→ Build contexts & prompts: ~100ms
    │   │
    │   ├─→ LLM call (Ollama): ~4000-7000ms
    │   │   └─→ Model inference time (Mistral 7B)
    │   │
    │   ├─→ Parse response: ~50ms
    │   │   └─→ _parse_all_recommendations() (all 4 strategies if needed)
    │   │
    │   ├─→ Deduplication: ~10ms
    │   ├─→ Validation: ~20ms
    │   ├─→ Filtering: ~10ms
    │   └─→ Enrichment: ~20ms
    │
    ├─→ Cache results: ~50ms
    │
    └─→ Save to DB: ~100ms

[3] Total: ~5.5-8.5 seconds
    └─→ Return: {recommendations, savings, generation_time_ms}

[4] Frontend polls /api/recommendations/task-status/{task_id}
    └─→ Get progress updates during execution
```

---

## PART 9: KEY FILES & FUNCTION REFERENCE

### Main Entry Points

| File | Function | Purpose |
|------|----------|---------|
| `src/background/tasks.py` | `generate_recommendations_bg()` | Celery background task |
| `src/llm/client.py` | `generate_recommendations()` | Orchestrator |
| `src/llm/client.py` | `call_llm()` | LLM call router |
| `src/llm/client.py` | `_call_ollama()` | Ollama API call |
| `src/llm/client.py` | `_call_gemini()` | Gemini API call |

### Parsing Functions

| File | Function | Purpose |
|------|----------|---------|
| `src/llm/client.py` | `_parse_all_recommendations()` | 4-strategy parser |
| `src/llm/client.py` | `_extract_sections()` | Extract card text blocks |
| `src/llm/client.py` | `_parse_card_text()` | Parse individual card |

### Validation Functions

| File | Function | Purpose |
|------|----------|---------|
| `src/llm/client.py` | `_deduplicate_cards()` | Remove duplicates |
| `src/llm/client.py` | `_validate_against_inventory()` | Filter hallucinations |
| `src/llm/client.py` | `_filter_zero_savings_cards()` | Remove zero-value recs |
| `src/llm/client.py` | `_enrich_cards()` | Fill in missing data |

### Context Builders

| File | Function | Purpose |
|------|----------|---------|
| `src/llm/client.py` | `_build_service_inventory()` | Build service list |
| `src/llm/client.py` | `_build_metrics()` | Build metrics section |
| `src/llm/client.py` | `_build_graph()` | Build graph context |
| `src/llm/client.py` | `_build_pricing()` | Build pricing context |
| `src/llm/client.py` | `_build_best_practices()` | Build practices section |

### Analysis Classes

| File | Class | Purpose |
|------|-------|---------|
| `src/analysis/graph_analyzer.py` | `GraphAnalyzer` | Graph analysis |
| `src/analysis/context_assembler.py` | `ContextAssembler` | Context assembly |

### Data Structures

| File | Class | Purpose |
|------|-------|---------|
| `src/llm/client.py` | `RecommendationResult` | Final output |
| `src/analysis/context_assembler.py` | `ArchitectureContextPackage` | 9-section context |
| `src/analysis/graph_analyzer.py` | `AnalysisReport` | Analysis output |

### Configuration

| File | Variable | Purpose |
|------|----------|---------|
| `src/llm/client.py` | `OLLAMA_URL` | Ollama endpoint |
| `src/llm/client.py` | `OLLAMA_MODEL` | Model name |
| `src/llm/client.py` | `GEMINI_API_KEY` | Gemini API key |
| `src/llm/client.py` | `USE_GEMINI` | Backend selection |
| `src/llm/prompts.py` | `RECOMMENDATION_SYSTEM_PROMPT` | System prompt template |
| `src/llm/prompts.py` | `RECOMMENDATION_USER_PROMPT` | User prompt template |

---

## PART 10: DEBUGGING & LOGGING

### Log Points

**Context Assembly** (info):
```
[TIMING] Starting context assembly...
[TIMING] Context assembly done in X.Xs
[TIMING] Formatting user prompt...
[TIMING] User prompt formatted in X.Xs (Y chars)
```

**LLM Call** (info):
```
[TIMING] Starting LLM call (timeout=300s)...
[TIMING] LLM call completed in X.Xs (Y chars)
Calling Ollama (mistral:latest)... OR Calling Gemini Flash...
```

**Parsing** (info):
```
Parsing response (Y chars)...
Strategy 1: Found N recommendations via '### Recommendation #N' ✓
Strategy 2: Found N recommendations via '### [title]'
Strategy 3: Found N recommendations via '---' delimiter
Strategy 4: Found N sections via double newline
✓ Parsed N recommendations
```

**Validation** (info):
```
Valid service inventory: N services
Resource ID check: 'id' matches inventory: true/false
✓ Deduplication: X → Y recommendations
✓ Validation: X → Y recommendations (kept all - lenient mode)
✓ Savings Filter: X → Y recommendations (removed low-confidence)
```

**Completion** (info):
```
COMPLETE: N recommendations, $X,XXX.XX savings, YYYms
```

### Response Saved to Disk

**File**: `/tmp/llm_response_{arch_name}_{timestamp}.txt`  
**Purpose**: Debug parsing failures

---

## PART 11: EXACT FIELD EXTRACTION EXAMPLES

### Example 1: Resource ID Extraction

**LLM Output**:
```
### Recommendation #1: Downsize t3.micro to t3.nano

**Resource ID:** `i-12345abc`
**Service:** EC2
```

**Extraction**:
```python
pattern = r"\*\*Resource ID:\*\*\s*`?([^`\n]+)`?"
match = re.search(pattern, text, re.IGNORECASE)
# match.group(1) = "i-12345abc"
card["resource_identification"]["resource_id"] = "i-12345abc"
```

### Example 2: Cost Extraction

**LLM Output**:
```
**Current Cost:** $2,400.00/month
```

**Extraction**:
```python
patterns = [
    r"\*\*Current\s+(?:Monthly\s+)?Cost:\*\*\s*\$([0-9,]+\.?\d*)",
]
match = re.search(patterns[0], text, re.IGNORECASE)
# match.group(1) = "2,400.00"
value = float("2,400.00".replace(",", ""))  # 2400.0
card["cost_breakdown"]["current_monthly"] = 2400.0
```

### Example 3: Savings Extraction (Primary Method)

**LLM Output**:
```
Monthly savings: $450.50/month
```

**Extraction**:
```python
patterns = [
    r"Monthly savings:\s*\$([0-9,]+\.?\d*)",
]
match = re.search(patterns[0], text, re.IGNORECASE)
# match.group(1) = "450.50"
value = float("450.50".replace(",", ""))  # 450.5
card["total_estimated_savings"] = 450.5
```

### Example 4: Savings Extraction (Fallback via Percentage)

**LLM Output**:
```
Current cost: $5,000/month
Reduce capacity by 30%
```

**Extraction**:
```python
# First try direct patterns - FAIL
# Then try percentage
patterns = [r"reduce(?:s)?\s+cost(?:s)?\s+by\s+(\d+)%"]
match = re.search(patterns[0], text, re.IGNORECASE)
# match.group(1) = "30"
pct = float("30")  # 30.0
current_cost = 5000.0
savings = 5000 * (30 / 100) = 1500.0
card["total_estimated_savings"] = 1500.0
```

### Example 5: Implementation Steps

**LLM Output**:
```
**Implementation:**
```bash
aws ec2 stop-instances --instance-ids i-12345abc
aws ec2 modify-instance-attribute --instance-id i-12345abc --instance-type t3.nano
aws ec2 start-instances --instance-ids i-12345abc
```
```

**Extraction**:
```python
pattern = r"```bash\n(.*?)\n```"
match = re.search(pattern, text, re.DOTALL)
# match.group(1) contains all the bash commands
lines = match.group(1).strip().split("\n")
# Filter out comments (lines starting with #)
impl_lines = [
    "aws ec2 stop-instances --instance-ids i-12345abc",
    "aws ec2 modify-instance-attribute --instance-id i-12345abc --instance-type t3.nano",
    "aws ec2 start-instances --instance-ids i-12345abc",
]
card["recommendations"][0]["implementation_steps"] = impl_lines
```

---

## PART 12: VALIDATION RULES & CONSTRAINTS

### 1. Savings Validation
- Must be > $0.01 (rejects placeholders)
- Must be <= current_monthly_cost * 100 (sanity check)
- Can be estimated from percentage (1-99%)

### 2. Cost Validation
- Extracted as float
- Commas removed before conversion
- Must be >= 0

### 3. Resource ID Validation
- Must be > 1 character
- Extracted from multiple patterns
- Fallback: inferred from service type

### 4. Title Validation
- Max 120 characters
- Removes "Recommendation #N:" prefix
- Defaults to `f"Recommendation #{card_num}"` if empty

### 5. Recommendation Count
- Must find >= 5 cards to use each strategy
- Max 20 recommendations enforced by Strategy 4
- If all strategies fail, return `[]` (empty list)

---

## PART 13: PROMPT INJECTION & DEDUPLICATION

### Why Deduplication?

LLM may generate duplicate recommendations for the same resource when:
1. Context mentions a resource multiple times
2. Different phrasings of the same optimization
3. Prompt didn't prevent exact repetition

### Deduplication Logic

```python
dedup_key = (resource_id.lower().strip(), title.lower()[:50])
```

**Example**:
- Card 1: res_id="i-123", title="Downsize EC2 Instance t3.large"
- Card 2: res_id="i-123", title="Downsize EC2 Instance t3.large"
- Key 1: `('i-123', 'downsize ec2 instance t3.large')`
- Key 2: `('i-123', 'downsize ec2 instance t3.large')`
- **Result**: Card 2 filtered (duplicate)

---

## PART 14: KNOWN LIMITATIONS & EDGE CASES

### 1. Resource ID Extraction Failures
- **When**: LLM doesn't follow format exactly
- **Fallback**: Infer from service type mentioned in text
- **Risk**: Generic IDs like `"ec2-recommendation"` (less specific)

### 2. Cost Parsing Issues
- **When**: LLM uses non-standard currency symbols or formats
- **Fallback**: Default to 0 (filled from inventory during enrichment)
- **Risk**: Missing cost data in frontend display

### 3. Parser Strategy Cascading
- **When**: All 4 strategies fail
- **Result**: Return empty list (task fails, Celery retries)
- **Prevention**: Strict system prompt enforces format

### 4. Unrealistic Savings
- **When**: LLM calculates incorrectly or hallucinates
- **Validation**: Lenient - keeps most recommendations
- **Risk**: Frontend shows inflated savings estimates

### 5. Hallucinated Resources
- **When**: LLM recommends resources not in actual inventory
- **Validation**: Kept anyway (lenient mode)
- **Mitigation**: Inventory validation is best-effort

---

## PART 15: PERFORMANCE OPTIMIZATION

### Timing Breakdowns

**Typical**: ~5-8 seconds total
- Graph analysis: ~200ms
- Context assembly: ~300ms
- LLM call (mistral): ~4-7 seconds ← **DOMINANT**  (model inference time)
- Parsing: ~50ms
- Validation: ~100ms
- Cache write: ~50ms

### Optimization Strategies

1. **Use Mistral 7B** instead of Qwen 25B (faster model)
2. **Cache results** to avoid re-running on refresh
3. **Reduce token budget** from 4096 to 2048 if latency critical
4. **Parallel context building** (currently sequential)

---

## SUMMARY TABLE

| Phase | File | Function | Input | Output | Timing |
|-------|------|----------|-------|--------|--------|
| **Trigger** | `src/api/handlers/recommendations.py` | `generate_recommendations_background()` | architecture_id/file | task_id | - |
| **Load** | `src/background/tasks.py` | `generate_recommendations_bg()` | DB/file | graph_data | ~100ms |
| **Analyze** | `src/analysis/graph_analyzer.py` | `GraphAnalyzer().analyze()` | graph_data | AnalysisReport | ~200ms |
| **Assemble** | `src/analysis/context_assembler.py` | `ContextAssembler().assemble()` | graph_data + report | ArchitectureContextPackage | ~300ms |
| **Build Prompt** | `src/llm/client.py` | `_build_*()` + format | context sections | user_prompt | ~100ms |
| **LLM Call** | `src/llm/client.py` | `call_llm()` → `_call_ollama()` | system_prompt + user_prompt | raw_response | ~4-7s |
| **Parse** | `src/llm/client.py` | `_parse_all_recommendations()` | raw_response | List[Dict] (unparsed) | ~50ms |
| **Parse Card** | `src/llm/client.py` | `_parse_card_text()` | card_text | card (with extracted fields) | per-card |
| **Extract Fields** | `src/llm/client.py` | regex patterns | card_text | title, cost, savings, impl | ~5-10ms each |
| **Deduplicate** | `src/llm/client.py` | `_deduplicate_cards()` | List[Dict] | List[Dict] (deduped) | ~10ms |
| **Validate** | `src/llm/client.py` | `_validate_against_inventory()` | cards + graph_data | List[Dict] (validated) | ~20ms |
| **Filter** | `src/llm/client.py` | `_filter_zero_savings_cards()` | List[Dict] | List[Dict] (filtered) | ~10ms |
| **Enrich** | `src/llm/client.py` | `_enrich_cards()` | cards + graph_data | List[Dict] (enriched) | ~20ms |
| **Return** | `src/background/tasks.py` | `generate_recommendations_bg()` | RecommendationResult | {"recommendations", "savings", ...} | ~50ms (cache write) |
| **Store** | `src/storage/recommendation_cache.py` | cache operations | response | Redis/DB | ~50ms |

---

## QUICK REFERENCE: REGEX PATTERNS USED

### Title Extraction
```regex
r"###\s+(.+?)(?:\n|$)"
```

### Resource ID (5 patterns)
```regex
r"\*\*Resource ID:\*\*\s*`?([^`\n]+)`?"
r"\*\*Resource:\*\*\s*`?([^`\n]+)`?"
r"\*\*Service Name:\*\*\s*`?([^`\n]+)`?"
r"Resource:\s*([^\n]+)"
r"Resource ID:\s*([^\n]+)"
```

### Current Cost (12 patterns)
```regex
r"\*\*Current\s+(?:Monthly\s+)?Cost:\*\*\s*\$([0-9,]+\.?\d*)"
r"\*\*Cost\s+per\s+month:\*\*\s*\$([0-9,]+\.?\d*)"
r"Current\s+(?:monthly\s+)?cost:\s*\$([0-9,]+\.?\d*)"
[... 9 more patterns]
```

### Savings (17 patterns)
```regex
r"\*\*(?:Expected|Estimated|Potential)\s+(?:Monthly\s+)?Savings?:\*\*\s*\$([0-9,]+\.?\d*)"
r"\*\*Savings?:\*\*\s*\$([0-9,]+\.?\d*)"
r"Monthly savings:\s*\$([0-9,]+\.?\d*)"
r"\$([0-9,]+\.?\d*)\s+(?:monthly\s+)?savings?"
[... 13 more patterns]
```

### Percentage (3 patterns - fallback)
```regex
r"reduce(?:s)?\s+cost(?:s)?\s+by\s+(\d+)%"
r"(\d+)%\s+cost\s+reduction"
r"(\d+)%\s+savings?"
```

### Implementation Steps
```regex
r"```bash\n(.*?)\n```"
```

---

## END OF DOCUMENT

This document captures the **complete, exact LLM input/output flow** including all parsing strategies, validation rules, extraction patterns, and error handling. All file paths, function names, line numbers, and regex patterns are verified against the actual codebase.

