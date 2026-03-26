# FinOps AI System: Implemented Architecture and Workflow Details

## 1. Purpose of This Document

This document explains the architecture currently implemented in FinOps AI, with a detailed view of:

- End-to-end workflow
- GraphRAG role and data flow
- Neo4j responsibility
- PostgreSQL responsibility
- Why these databases are separated
- Supporting components (Redis, Celery, API, frontend)

It is written for developers and operators who need to understand how recommendations are produced, stored, and served reliably.

---

## 2. High-Level Architecture

The system is built as a hybrid graph-analytics and LLM recommendation platform.

Core layers:

1. Data ingestion and graph construction
2. Graph analytics and context assembly
3. Recommendation generation (deterministic engine + LLM)
4. Persistence and history governance
5. API delivery to frontend
6. Scheduled refresh pipeline (hourly)

Main runtime services:

- FastAPI backend (request handling and orchestration)
- Celery worker (background jobs)
- Celery beat (hourly scheduler)
- Neo4j (graph topology and relationships)
- PostgreSQL (recommendation/report persistence and queryable history)
- Redis (task state and cache)
- Frontend (analysis and recommendation UI)

---

## 3. End-to-End Workflow

### 3.1 Ingestion and Topology Availability

Input comes from either:

- AWS live discovery pipeline, or
- Synthetic architecture files (for controlled scenarios)

The pipeline builds service nodes and dependency edges, then stores graph topology in Neo4j. Snapshot-like payloads may also be persisted for recovery and replay.

### 3.2 Deep Analysis and Context Assembly

When analysis runs, the backend:

1. Loads graph data from the latest completed source.
2. Executes graph analytics (centrality, dependency, blast radius, SPOF, etc.).
3. Assembles a rich context package (architecture, costs, anti-patterns, risk, behavior, trends, dependencies, best-practices grounding).

This context package is the foundation for grounded recommendation generation.

### 3.3 Recommendation Generation

Recommendation generation is hybrid:

- Deterministic engine for structural/cost-aware signals
- LLM for synthesis, explanation, and additional opportunities

Key behaviors implemented:

- Strict parsing and normalization of LLM outputs
- Card-shape parity between engine and LLM outputs
- Deduplication logic
- Zero-savings and low-quality filtering
- Final recommendation card set suitable for UI rendering

### 3.4 Persistence and Retrieval

Completed recommendation runs are persisted in PostgreSQL in `recommendation_results`.

Read paths provide:

- Latest recommendation snapshot (`/analyze/recommendations/last`)
- Recommendation history (`/analyze/recommendations/history`)

Current retention behavior is intentionally strict: keep latest completed non-empty snapshot per architecture selector, removing older completed rows until the next hourly refresh produces a new latest snapshot.

### 3.5 Frontend Delivery

The analysis UI loads stored latest recommendations (not forced regeneration on page open). The carousel renders recommendation cards and a structured summary. This prevents churn and keeps display consistent with persisted state.

### 3.6 Hourly Refresh

Celery beat triggers hourly tasks that refresh data and recommendation state. This provides predictable cadence and decouples expensive generation from user navigation events.

---

## 4. GraphRAG in This System

GraphRAG here means retrieval and grounding from graph-informed context rather than free-form LLM prompting.

GraphRAG pipeline in practice:

1. Build graph representation (services, dependencies, topology signals)
2. Compute graph-derived features (criticality, dependency count, blast radius, risk)
3. Merge cost and behavior metadata
4. Assemble a structured context package
5. Inject context into recommendation prompts
6. Parse and validate outputs back against inventory and schema

Why GraphRAG matters:

- Reduces hallucinations by grounding in real topology and cost evidence
- Improves prioritization by considering dependency impact, not only local savings
- Produces recommendations that are explainable through graph context

---

## 5. Neo4j Responsibility

Neo4j is the system of record for graph topology and traversal-heavy questions.

Primary responsibilities:

- Store services as nodes and dependencies as edges
- Support graph-centric reads for analytics and risk reasoning
- Enable relationship-aware metrics (centrality, path/dependency impacts)
- Feed graph context into analysis and recommendation generation

Why Neo4j is the right fit:

- Native graph model represents infrastructure dependency networks naturally
- Graph traversals and path reasoning are first-class operations
- Better operational semantics for relationship-heavy workloads than relational joins over deep edge chains

What Neo4j is not used for:

- Long-term recommendation history and run metadata
- API response-oriented run snapshots
- General transactional reporting

---

## 6. PostgreSQL Responsibility

PostgreSQL stores persisted run artifacts and operational history.

Primary responsibilities:

- Persist recommendation run results (`recommendation_results`)
- Persist LLM pipeline reports (`llm_reports`)
- Persist ingestion snapshots and status metadata
- Serve latest/history queries for UI and API consumers
- Support retention and cleanup policies

Why PostgreSQL is the right fit:

- Strong consistency and transactional guarantees for run-state persistence
- Efficient querying, ordering, and filtering for history APIs
- Mature tooling for backup, migrations, and operational visibility
- Well-suited for structured records and lifecycle metadata

What PostgreSQL is not used for:

- Primary graph traversal and graph-native dependency analytics

---

## 7. Why Neo4j and PostgreSQL Are Separated

Separation is deliberate and architectural, not accidental.

### 7.1 Different Data Shapes

- Neo4j: relationship-first data (nodes/edges/path queries)
- PostgreSQL: record-first data (runs, snapshots, status, payload metadata)

### 7.2 Different Query Profiles

- Neo4j: traversal, neighborhood, centrality-style reasoning
- PostgreSQL: filtering, pagination, sorting, retention, API history responses

### 7.3 Performance and Maintainability

Splitting storage avoids forcing one database to do jobs it is not optimized for. It keeps each subsystem simpler and improves predictability under load.

### 7.4 Clear Operational Boundaries

Each persistence layer has clear ownership:

- Graph correctness and topology in Neo4j
- Run correctness and history governance in PostgreSQL

This also reduces blast radius for schema changes and makes debugging easier.

---

## 8. Redis and Celery Roles

### Redis

Used for:

- Background task status and progress state
- Short-lived cache for recommendation responses

Redis is ephemeral and speed-oriented. It is not the authoritative store for long-lived recommendation history.

### Celery Worker + Beat

Used for:

- Async/background processing of expensive workflows
- Hourly scheduled execution (beat)
- Decoupling user request latency from heavy analysis operations

This keeps UI responsiveness stable and enables regular pipeline refresh independent of user interaction.

---

## 9. API and Frontend Interaction Model

API model:

- Request analysis/recommendation execution
- Read latest stored snapshot
- Read history list (subject to retention policy)
- Read task status for background operations

Frontend model:

- Display latest persisted recommendation state
- Avoid implicit regeneration on page load
- Show card-level details plus summary
- Depend on hourly pipeline updates for canonical refresh

This avoids stale/duplicated UX behavior and makes state transitions easier to reason about.

---

## 10. Reliability and Quality Controls Implemented

Key controls currently implemented include:

- Parsing hardening for LLM outputs
- Normalization so LLM cards match engine schema
- Duplicate suppression and card filtering
- Zero-savings handling improvements
- Keep-latest retention for recommendation results
- Filtering of empty completed runs from latest/history reads

These controls improve trustworthiness and consistency of recommendations shown to users.

---

## 11. Practical Summary

In short:

- Neo4j answers topology and dependency questions.
- PostgreSQL preserves recommendation/report run history and serves API retrieval.
- Redis/Celery handle speed and scheduling concerns.
- GraphRAG ties graph evidence to LLM generation so recommendations stay grounded.
- Storage separation exists to optimize correctness, performance, and operational clarity.

This architecture is designed for production-like behavior: deterministic where needed, explainable in outputs, and stable in persistence.
