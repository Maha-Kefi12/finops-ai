# FinOps AI System - Besoins Fonctionnels & Non-Fonctionnels

## BESOINS FONCTIONNELS (BF)

### 1. **Ingestion des Données AWS**

#### BF1.1 - Parser CUR (Cost and Usage Report)
- **Description:** Ingérer les fichiers CUR depuis S3 ou système de fichiers local
- **Données Traitées:** 
  - ProductCode, UsageType, ResourceId, UnblendedCost, UsageAmount
  - Tags AWS (Name, Environment, etc.)
  - Périodes de facturation
- **Format d'entrée:** CSV gzip ou CSV brut
- **Format de sortie:** JSON structuré avec mapping produit → type interne
- **Fallback:** AWS Cost Explorer API si S3 indisponible
- **Taille support:** Fichiers > 100MB

#### BF1.2 - Collecte Métriques CloudWatch
- **Ressources suportées:**
  - EC2: CPU, Network I/O, Disk I/O, Memory (via agent)
  - RDS: Database CPU, Connections, Latency, Throughput
  - ElastiCache: CPU, Network, Evictions, Replication lag
  - ELB/ALB: Request count, Response time, HTTP errors
  - Lambda: Duration, Errors, Invocations
  - S3: Objects count, Storage size, Request metrics
- **Fenêtre temporelle:** 30 jours lookback
- **Granularité:** Agrégations P50, P95, P99
- **Statut de collecte:** Success, Timeout (fallback en cache), No data
- **Fréquence:** À la demande + caching hebdomadaire

#### BF1.3 - Transformation CUR
- **12 règles d'inférence de dépendances:**
  1. EC2 ↔ Security Groups
  2. EC2 ↔ Subnet ↔ VPC
  3. RDS ↔ Enhanced Monitoring
  4. ALB → Target Groups → EC2
  5. EBS Volume ↔ EC2 (snapshots)
  6. Lambda ↔ VPC (si attaché)
  7. S3 ↔ Lifecycle policies
  8. CloudFront ↔ S3 (origins)
  9. RDS ↔ Read replicas
  10. NAT Gateway ↔ Subnets
  11. VPC Endpoints ↔ Services
  12. API Gateway ↔ Lambda/Backend
- **Calcul de corrélation:** Pearson correlation (> 0.75 threshold)
- **Risk Scoring:** 0-100% basé sur variance métrique
- **Détection d'anomalies:**
  - Ressources orphelines (0% utilisation)
  - Pics de coûts non expliqués
  - Cross-region transfer anormal
  - Anti-patterns (pas de caching, single-AZ, etc.)

---

### 2. **Stockage et Représentation du Graphe**

#### BF2.1 - Neo4j Graph Storage
- **Types de nœuds:** Compute, Database, Storage, Network, Security, Monitoring
- **Types d'edges:** USES, DEPENDS_ON, IN, HAS_METRIC, etc.
- **Opérations Cypher:**
  - Insérer/Mettre à jour ressources (MERGE)
  - Détecter clusters de dépendance (MATCH avec traversée multi-hop)
  - Calculer blast radius (impact cascade)
  - Détecter Single Points of Failure
  - Tracer data flows
- **Contraintes:** PRIMARY KEY sur resource_id, UNIQUE sur (account, region, resource)
- **Indexes:** cost, cpu_utilization, last_updated
- **Persistence:** Snapshots hebdomadaires
- **Backup:** Automatique Neo4j (cloud snapshots)

#### BF2.2 - PostgreSQL Persistance
- **Objectifs:** Snapshots historiques de recommandations
- **Schéma:**
  - `recommendations`: id, resource_id, action, savings, created_at, status
  - `architecture_snapshots`: snapshot_id, timestamp, resources_json, graph_json
  - `validation_logs`: proposal_id, validation_result, metrics_used, timestamp
- **Requêtes:** Historique recommandations, trends coûts, audit trails

---

### 3. **Système de Recommandations Deux-Tiers**

#### BF3.1 - Tier 1: Engine Recommandations Déterministes
- **Pattern Detection (20 patterns minimum):**
  - EC2 Rightsizing: CPU < 40% + Memory < 60% → downsize
  - EC2 Termination: CPU < 10% + Network < 1 Mbps → terminate
  - RDS Rightsizing: DB CPU < 40% + Connections < 50% max
  - Storage Class Migration: S3 infrequent access policy
  - EBS GP2 → GP3 Migration (latency improvement)
  - Multi-AZ Disable: For non-critical databases
  - Lifecycle Policies: Archiving after 90 days
- **Metrics Driving:** Chaque pattern basé sur seuils CloudWatch réels
- **Confidence Level:** 0.9-1.0 (déterministe)
- **Source Marker:** source = "engine"
- **Output Format:** FullRecommendationCard avec source="engine_backed"

#### BF3.2 - Tier 2: LLM-Proposed Intelligence
- **Génération:** Contexte enrichi + rag best practices
- **Capabilities:**
  - Cross-resource patterns (caching, VPC endpoints)
  - Architectural insights (disaster recovery gap)
  - Graviton migrations (efficiency)
  - Advanced networking (NAT optimization)
- **Confidence:** LLM self-estimate (0-1.0)
- **Validation:** Re-check contre CloudWatch metrics
- **Promotion:** Si validation passe → source="engine_backed", engine_confidence=0.8
- **Rejet:** Si fail validation → validation_status="rejected"
- **Conflit:** Si overlaps engine rec → downgraded, is_downgraded_due_to_conflict=true

#### BF3.3 - Schema de Recommandation
- **Champs obligatoires:**
  - id (UUID)
  - source (ENGINE_BACKED | LLM_PROPOSED)
  - action (20 enums, pas d'invention)
  - resource_id (doit exister dans graph)
  - estimated_monthly_savings (calcul déterministe)
  - engine_confidence ou llm_confidence
  - validation_status (PENDING, VALIDATED, REJECTED, CONFLICT)
- **Champs contextuels:**
  - justification (doit citer metrics réelles)
  - graph_context (blast_radius, dependencies, SPOF)
  - conflicting_rec_ids (si conflit)
- **Métriques:** CPU, memory, network, latency P95, error_rate, IOPS

#### BF3.4 - Conflict Resolution
- **Princip:** ENGINE TOUJOURS GAGNANT
- **Logique:**
  - Si engine.action == "terminate" ET llm.action == "downsize" → llm.downgrade()
  - Store conflicting_rec_ids bidirectional
  - Mark is_downgraded_due_to_conflict=true
- **Output pour user:** Afficher raison du conflit clairement

---

### 4. **LLM Integration**

#### BF4.1 - Dual LLM Call Pipeline
- **Call #1: Narrative Pass (Qwen 2.5 7B)**
  - Input: 4 engine-backed recs + metrics
  - Task: Polish "why_it_matters" + "full_analysis" fields
  - Constraint: Numbers/IDs NEVER modified
  - Output: Enriched narrative
  - Fallback: Template text si timeout
  - Timeout: 30 minutes avec retry
- **Call #2: Proposal Generation (Mistral 7B ou Claude)**
  - Input: Full architecture context + RAG context + 20 action enums
  - Task: Generate novel cross-resource recommendations
  - Constraint: Metrics citations + JSON valid + confidence estimate
  - Output: JSON array de LLM proposals
  - Timeout: 30 minutes avec retry (3x)
  - Fallback: Skip si toujours timeout

#### BF4.2 - LLM Output Validation
- **Constraints:**
  - Action must be from [20 enums], pas invented
  - resource_id must exist dans architecture
  - Metrics cited must match CloudWatch reality
  - JSON structure valide
- **Validation process:**
  - Re-extract CloudWatch metrics pour resource
  - Check contre thresholds (CPU < 40%, etc.)
  - Apply conflict resolution
  - Separate validated vs rejected vs conflict

#### BF4.3 - RAG (Retrieval-Augmented Generation)
- **Knowledge Base:** 50MB FinOps PDFs
  - AWS Well-Architected Framework
  - FinOps Framework 2025
  - AWS Cost Optimization Guide
  - Tools docs (Finout, Flexera, Fig.io)
- **Embedding:** Generate embeddings pour chunks
- **Retrieval:** Top-5 documents relevants par query
- **Integration:** Augmenter LLM prompt avec best practices
- **Indexing:** Vector store (Pinecone / Weaviate)

---

### 5. **API REST**

#### BF5.1 - Endpoint: POST /api/ingest
```
Input:  { cur_source: "s3://...", org_id: "123" }
Output: { pipeline_id, status: "FETCH_CUR" }
Response: 7-stage pipeline progress (FETCH, PARSE, COLLECT_CLOUDWATCH, TRANSFORM, STORE_NEO4J, STORE_POSTGRES, DONE)
```

#### BF5.2 - Endpoint: POST /api/analyze
```
Input:  { architecture_id, focus_area: "cost|performance|resilience", include_rag: true }
Output: {
  analysis: { executive_summary, findings[] },
  recommendations: [{ id, source, action, savings, confidence, ... }],
  graph_analysis: { tier_structure, critical_paths, resilience_score }
}
```

#### BF5.3 - Endpoint: POST /api/recommendations
```
Input:  { architecture_id }
Output: {
  validated_recommendations: [],    # source="engine" ou "engine_backed" promu
  ai_suggested_ideas: []            # source="llm_proposed" (pending/rejected/conflict)
}
```

#### BF5.4 - Endpoint: GET /api/docs
```
Output: { documents: [{ id, title, summary, sections[] }] }
```

#### BF5.5 - Endpoint: GET /api/ingest/status?pipeline_id=X
```
Output: { stage, progress: 0-100, details, errors }
```

#### BF5.6 - Endpoint: POST /api/validate-llm-proposal
```
Input:  { proposal: { resource_id, action, ... } }
Output: { validation_status, metrics_used, reason_if_rejected }
```

---

### 6. **Frontend Interface**

#### BF6.1 - PipelinePage (Ingestion UI)
- **7-stage progress bar** (FETCH → PARSE → COLLECT_CLOUDWATCH → TRANSFORM → STORE_NEO4J → STORE_POSTGRES → DONE)
- **Live timing** chaqu étape
- **Service summary** ("47 resources: 32 EC2, 8 RDS, ...")
- **JSON viewers** (raw input vs transformed output)
- **Neo4j status indicator** (Online/Disconnected)
- **Error handling** (timeout, S3 access denied, etc.)

#### BF6.2 - AnalysisPage (Recommendations UI)
- **Tab 1: ✅ Validated Recommendations**
  - Source badge (⚙️ Engine | 🔍 AI-Validated)
  - engine_confidence 0.9-1.0
  - Metrics that triggered rec
  - Implementation steps
  - Risk: "LOW - 2 dependents"
- **Tab 2: 💡 AI Suggested Ideas**
  - Source badge 🤖 AI Proposed
  - llm_confidence 0-1.0
  - Validation status (✅ Pending | ❌ Rejected | ⚠️ Conflict)
  - Rejection reason si rejected
  - Conflict explanation si conflict
  - User action buttons: "Review" | "Implement anyway"
- **Summary Card:**
  - Trusted Savings Potential ($X/mo)
  - Exploratory Ideas (+$Y/mo)
  - Total Potential ($X+Y/mo)
  - Confidence level narrative

#### BF6.3 - Resource Deep-Dive
- **Tableau interactif:**
  - Colonnes: ID | Type | Cost | CPU% | Memory% | Dependencies | Suggested Action
  - Tri/filtres: by type, cost, utilization
  - Click row: voir détails + graph impact cascading

#### BF6.4 - Dependency Graph Visualization
- **Nodes:** Services (couleur par type)
- **Edges:** Dépendances (épaisseur par criticité)
- **Click edge:** Afficher cost de transfer cross-AZ ou latency
- **Highlight path:** si user click resource, show all dependents

#### BF6.5 - Best Practices Browser
- **Side panel:** PDFs FinOps digérés
- **Search:** "How to optimize RDS?"
- **Snippets:** Cas d'usage relevants + AWS pricing examples

---

## BESOINS NON-FONCTIONNELS (BNF)

### 1. **Performance**

#### BNF1.1 - Temps de Réponse Pipeline
- **Ingestion complète:** < 5 minutes (pour 50 ressources, 30 jours data)
  - CUR parse: < 1 min
  - CloudWatch collect: < 2 min (avec fallback sur cache)
  - Transformation: < 30s
  - Neo4j store: < 1 min
- **Analysis API:** < 2 secondes
- **Graph queries:** < 500ms (Cypher avec indexes)
- **LLM calls:** 30 secondes max (with retry)

#### BNF1.2 - Latency Metrics
- **Frontend:** < 3 secondes pour charger AnalysisPage
- **API response:** 200ms median, 1s p99
- **Database queries:** < 100ms per query (PostgreSQL)

#### BNF1.3 - Throughput
- **Support concurrent pipelines:** 5+ simultanément
- **Concurrent analysis requests:** 10+
- **LLM querying:** 2 parallel calls max (resource constraint)
- **Database:** 100+ QPS (PostgreSQL)

---

### 2. **Scalabilité**

#### BNF2.1 - Horizontal Scaling
- **Stateless API servers:** N × FastAPI instances (load balanced)
- **Neo4j:** Cluster support (read replicas pour queries)
- **PostgreSQL:** Connection pooling (PgBouncer), replication ready
- **Message Queue:** Optional (for async pipeline stages)

#### BNF2.2 - Data Volume
- **Resources:** Supporter 1000+ ressources AWS
- **Graph edges:** 5000+ relationships
- **Time series:** 24 mois historique (rolling window)
- **Recommendations:** 10000+ stored (pagination)

#### BNF2.3 - Storage
- **Neo4j:** 50GB database (initial), 200GB+ with history
- **PostgreSQL:** 100GB+ (snapshots, logs)
- **S3:** Unbounded (CUR files, backups)
- **Vector store:** 100GB+ embeddings (50 PDFs × indices)

---

### 3. **Disponibilité & Résilience**

#### BNF3.1 - SLA
- **API availability:** 99.5% uptime
- **Critical data:** No data loss (encrypted backups)
- **Graceful degradation:** Works with partial data (metrics timeout)

#### BNF3.2 - Failover & Fallback
- **CloudWatch timeout:** Fallback sur cache (7 jours)
- **LLM timeout:** Fallback sur template narratives (keep original text)
- **Neo4j down:** PostgreSQL data access (denormalized copy)
- **S3 unavailable:** Local CUR file upload alternative
- **API failure:** Queue requests, retry avec exponential backoff

#### BNF3.3 - Data Backup & Recovery
- **Neo4j:** Daily snapshots (S3)
- **PostgreSQL:** Point-in-time recovery (WAL archiving)
- **RTO:** < 1 hour
- **RPO:** < 15 minutes

---

### 4. **Sécurité**

#### BNF4.1 - Authentication & Authorization
- **API auth:** OAuth2 / API keys avec rate limiting
- **Multi-tenancy:** Isolation par org_id (row-level security)
- **Audit logs:** Toutes les recommandations + modifications
- **User roles:** Admin, Analyst, Viewer

#### BNF4.2 - Secrets Management
- **AWS credentials:** AWS Secrets Manager (rotation 90 jours)
- **LLM API keys:** Encrypted in KMS
- **Database passwords:** Secrets Manager with parameter store
- **HTTPS:** All API calls, TLS 1.2+

#### BNF4.3 - Data Protection
- **Encryption at rest:** PostgreSQL + Neo4j (AES-256)
- **Encryption in transit:** TLS for all external calls
- **Sensitive data:** No PII stored (resource IDs only)
- **GDPR:** Data retention policies (24 mois max)

#### BNF4.4 - Compliance
- **Audit trail:** Immutable logs (CloudTrail)
- **Access logs:** Who accessed what, when
- **Recommendation approval:** Before implementation (audit)
- **Cost validation:** Certified by AWS Compute Optimizer

---

### 5. **Observabilité & Monitoring**

#### BNF5.1 - Logging
- **Levels:** DEBUG, INFO, WARNING, ERROR
- **Structured logs:** JSON (timestamp, level, service, request_id, error_stack)
- **Destinations:** CloudWatch, ELK stack, S3 (archiving)
- **Retention:** 90 jours (hot), 1 year (archive)

#### BNF5.2 - Metrics
- **Application metrics:**
  - Pipeline duration (per stage)
  - API response time (p50, p95, p99)
  - LLM call latency
  - Validation pass/fail ratio
- **Business metrics:**
  - Recommendations generated (per day)
  - Estimated savings (per month)
  - Recommendations implemented (tracking)
- **Infrastructure metrics:**
  - Database CPU, memory, connections
  - Neo4j query time, cache hit ratio
  - API error rate, 5xx count

#### BNF5.3 - Alerting
- **Critical:** Database down, API error rate > 5%, LLM service down
- **Warning:** Pipeline > 10 min, API p99 > 5s, Validation failed > 30%
- **Channels:** PagerDuty, Slack, Email

#### BNF5.4 - Tracing
- **Distributed tracing:** X-Ray (AWS) or Jaeger
- **Request propagation:** trace_id across microservices
- **Sampling:** 10% production, 100% dev/staging

---

### 6. **Maintenabilité & Architecture**

#### BNF6.1 - Code Quality
- **Language:** Python 3.11+ (type hints recommended)
- **Testing:** Unit tests (90%+ coverage), integration tests
- **CI/CD:** GitHub Actions (lint, test, security scan, deploy)
- **Code review:** Mandatory for main branch
- **Documentation:** Docstrings, README, architecture diagrams

#### BNF6.2 - Dependency Management
- **Python:** requirements.txt with pinned versions
- **Node.js:** package-lock.json for frontend stability
- **Security:** Regular dependency scanning (Snyk, WhiteSource)

#### BNF6.3 - Deployment
- **Containerization:** Docker images (Python API, frontend)
- **Orchestration:** Docker Compose (dev) | Kubernetes (prod)
- **GitOps:** ArgoCD for declarative deployments
- **Versioning:** Semantic versioning (git tags)
- **Rollback:** Blue/green deployments, quick rollback

#### BNF6.4 - Configuration Management
- **Environment variables:** .env file (dev), Secrets Manager (prod)
- **Feature flags:** Enable/disable LLM, RAG, specific detectors
- **A/B testing:** Support for recommendation algorithm variants

---

### 7. **Compatibilité & Interopérabilité**

#### BNF7.1 - Cloud Support
- **AWS:** Primary (EC2, RDS, S3, Lambda, etc.)
- **Multi-region:** Support for us-east-1, eu-west-1, ap-southeast-1
- **API compatibility:** AWS SDK v3 (boto3 for Python)
- **CUR format:** Standard AWS CUR (2024 schema)

#### BNF7.2 - Browser Support
- **Desktop:** Chrome, Firefox, Safari, Edge (latest 2 versions)
- **Mobile:** Responsive design (tablet-ready)
- **Accessibility:** WCAG 2.1 AA compliance

#### BNF7.3 - API Versioning
- **Versioning:** /api/v1, /api/v2 (backward compat)
- **Deprecation:** Announce 6 months before removal

---

### 8. **Testabilité**

#### BNF8.1 - Unit Testing
- **Coverage:** > 90% (critical paths 100%)
- **Frameworks:** pytest (Python), Jest (Node)
- **Mocking:** Mock CloudWatch, S3, LLM calls
- **Speed:** < 30 seconds total

#### BNF8.2 - Integration Testing
- **Real services:** LocalStack for AWS, Docker compose
- **Scenario testing:** Full pipeline (CUR → Neo4j → LLM → recommendations)
- **Regression:** Ensure past fixes stay fixed

#### BNF8.3 - Load Testing
- **Tool:** k6 or Apache JMeter
- **Scenarios:**
  - 5 concurrent ingestion pipelines
  - 100 concurrent API requests
  - Sustain for 10 minutes
- **Acceptance criteria:** p99 < 5s, error rate < 1%

#### BNF8.4 - Security Testing
- **OWASP Top 10:** Scan for SQL injection, XSS, CSRF
- **Dependency scanning:** Regular security updates
- **Pen testing:** Quarterly external assessment

---

### 9. **Support & Documentation**

#### BNF9.1 - Documentation
- **API docs:** OpenAPI/Swagger
- **Architecture:** C4 diagrams (context, container, component)
- **Runbook:** How to deploy, scale, debug, incident response
- **Troubleshooting:** Common issues + resolution

#### BNF9.2 - Support SLA
- **Critical bugs:** 1-hour response, 4-hour fix
- **Feature requests:** 2-week turnaround
- **User onboarding:** Documentation + video tutorials

---

## Tableau Récapitulatif

| Catégorie | BF/BNF | Requirement | Acceptance Criteria |
|-----------|--------|-------------|-------------------|
| Ingestion | BF1.1 | Parse CUR | 100% line items extracted |
| Ingestion | BF1.2 | Collect CloudWatch | 95%+ metrics availability |
| Ingestion | BF1.3 | Transform + infer | 12 inference rules applied |
| Storage | BF2.1 | Neo4j graph | 50+ nodes, 190+ edges |
| Recomm. | BF3.1 | Engine patterns | 20+ patterns, 0.9-1.0 confidence |
| Recomm. | BF3.2 | LLM proposals | Cross-resource insights, validated metrics |
| API | BF5.1-6 | REST endpoints | All 6 endpoints working, JSON compliant |
| Frontend | BF6.1-5 | UI tabs | 2 tabs (trusted + ideas), responsive |
| Perf | BNF1.1 | Pipeline < 5min | 47 resources in 3-5 minutes |
| Perf | BNF1.2 | API response | p99 < 1 second |
| Scale | BNF2.1 | Horizontal scale | 5+ concurrent pipelines |
| Avail | BNF3.1 | SLA | 99.5% uptime |
| Sec | BNF4.1 | Auth | OAuth2 + API keys |
| Obs | BNF5.1 | Logging | CloudWatch + structured JSON |
| Test | BNF8.1 | Unit coverage | > 90% coverage |

---

## Priorisation (MVP → Phase 2 → Phase 3)

### MVP (Livré - V1 + V2 + V3)
- ✅ CUR ingestion + CloudWatch collection
- ✅ Neo4j graph + dependency inference (12 rules)
- ✅ Engine pattern detection (20 patterns)
- ✅ LLM proposal generation + validation
- ✅ Conflict resolution
- ✅ API + PipelinePage + AnalysisPage

### Phase 2 (Prochaines itérations)
- Kubernetes deployment
- Advanced RAG (semantic search, PDF extraction OCR)
- Cost forecasting (ML time series)
- Recommendation approval workflow
- Implementation webhook integration

### Phase 3 (Long-term)
- Multi-cloud (GCP, Azure)
- FinOps maturity scoring
- Chargeback models
- BI dashboards integration (Tableau, Looker)
- Custom detector plugins
