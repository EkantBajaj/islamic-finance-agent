# 🏦 Barakah AI — Shariah-Compliant Transaction Intelligence Agent

> **Prototype Design Document & Codebase** — Demonstrating production-grade AI system design for the **AI Engineer L3 (Senior)** role at [Barakah](https://barakah.ai)

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Test Status](https://img.shields.io/badge/tests-74%20passed-green.svg)](https://github.com/EkantBajaj/islamic-finance-agent)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 1. What This Is

This is a Shariah-compliant transaction intelligence agent that demonstrates how I would build Barakah's core AI pipeline. It ingests bank transactions and autonomously categorizes them, screens for Shariah compliance, detects recurring payments, generates financial insights, and calculates Zakat obligations.

The system is structured as a production-grade asynchronous pipeline that standardizes transaction data, routes them through a LangGraph orchestration flow, and guarantees resilience via caching, PII sanitization, and circuit breakers with fallback modes.

---

## 2. Design Decisions — What & Why

| Decision | What (Prototype) | Why | What (Production) |
|----------|-------------------|-----|--------------------|
| **LLM Provider** | Claude Haiku via direct API | Fastest, cheapest for classification tasks. Temperature=0 for deterministic categorization. | Same, but with Anthropic's Batch API for bulk processing. Add model routing (Haiku for categorization, Sonnet for insights). |
| **Agentic Framework** | LangGraph | Explicit state machine > magic chains. Each agent has clear inputs/outputs. Supports parallel fan-out natively. Better than CrewAI for structured pipelines (vs. autonomous agents). | Same. LangGraph's checkpointing enables pipeline resume on failure — critical for batch processing millions of transactions. |
| **Data Architecture** | Medallion (raw→map→core→pfm→profile) in PostgreSQL | Matches Barakah's actual architecture. Each layer is independently queryable. Clear data lineage for audit. | Same pattern, but with dedicated schemas per layer. Add dbt for transformation orchestration. Move PFM/Profile layers to a read-optimized store (e.g., ClickHouse). |
| **Categorization Strategy** | 3-tier: MCC→Rules→LLM | MCC codes are instant and free. Rules engine catches 70% of cases. LLM only for the remaining 30% = massive cost savings. | Add a 4th tier: fine-tuned small model (distilled from Claude) for the highest-volume ambiguous cases. LLM becomes the last resort. |
| **Shariah Screening** | Deterministic blocklist + LLM verification | Blocklist is auditable and explainable. LLM handles gray areas. Two-tier = high recall + reasonable precision. | Add Shariah Advisory Board review queue for `review` status transactions. Human-in-the-loop for edge cases. Formal audit trail for CBUAE. |
| **Caching** | Redis with 24h TTL for LLM responses | Same merchant + description = same category. Cache hit rate ~60-70% in practice. | Add cache warming for known merchants. Bloom filter for cache existence checks. |
| **Circuit Breaker** | In-process Python implementation | Simple, no external dependencies. Good enough for single-instance prototype. | Replace with resilience4j-style library or service mesh (Istio) circuit breaking for multi-instance deployments. |
| **Database** | PostgreSQL 16 with Alembic migrations | Battle-tested, excellent JSON support, free. Alembic for Python-native migrations. | Same DB. Switch to Flyway migrations (Barakah uses JVM stack). Add read replicas. Connection pooling via PgBouncer. |
| **Frontend** | Vanilla JS + Vite | Fast to build. Demonstrates the pipeline visually without framework overhead. | React/Next.js with proper state management. Mobile-first responsive design. |
| **Auth** | JWT with hardcoded demo token | Prototype simplification — no auth server needed. | OAuth 2.0 with PKCE. Integration with Barakah's IAM. RDS IAM authentication for DB. |
| **Observability** | Structured logging (structlog) | Queryable JSON logs. Every decision includes model version, prompt version, confidence score. | Add OpenTelemetry tracing, Prometheus metrics, Grafana dashboards. Datadog or similar APM. |
| **PII Handling** | Regex-based sanitization before LLM calls | Strips card numbers, IBANs, emails before any data leaves the system. | Add Microsoft Presidio or AWS Comprehend for ML-based PII detection. Formal DLP policy. |

---

## 3. What I Deliberately Didn't Build (And Why)

| Omitted | Reason | Production Approach |
|---------|--------|--------------------|
| **Evaluation framework** | Adds significant complexity; not demonstrable in a prototype | Braintrust/Langsmith with golden datasets; CI-gated eval runs (see Versioning & Evals section) |
| **Fine-tuned models** | Requires labeled data + training infrastructure | Distill Claude into smaller models for high-volume classification tasks |
| **Multi-tenancy** | Single-user prototype | Row-level security in PostgreSQL, tenant-scoped caching |
| **Real open-banking integration** | Requires Lean/Plaid API keys and bank partnerships | Webhook-based ingestion from open-banking providers |
| **Kubernetes deployment** | Docker-compose is sufficient for demo | Helm charts, HPA autoscaling, blue-green deployments |
| **Rate limiting & throttling** | Single-user, no abuse risk | Token bucket per-account rate limiter, API gateway (Kong/AWS API Gateway) |
| **Formal Shariah audit trail** | Requires legal/compliance review | Immutable audit log with decision provenance for CBUAE regulatory compliance |

---

## 4. Architecture Diagram

```mermaid
graph TB
    subgraph "Client Layer"
        UI["Web Dashboard<br/>(React/Next.js)"]
    end

    subgraph "API Gateway"
        API["FastAPI Server<br/>REST + WebSocket"]
        AUTH["Auth Middleware<br/>(JWT)"]
    end

    subgraph "Agentic AI Pipeline"
        ORCH["Orchestrator Agent<br/>(LangGraph)"]
        CAT["Categorization Agent"]
        SHARIAH["Shariah Screening Agent"]
        RECUR["Recurrence Detection Agent"]
        INSIGHT["Insight Generation Agent"]
        ZAKAT["Zakat Calculation Agent"]
    end

    subgraph "Data Layer (Medallion)"
        RAW["Raw Layer<br/>(Ingested Transactions)"]
        MAP["Map Layer<br/>(Normalized + Enriched)"]
        CORE["Core Layer<br/>(Categorized + Screened)"]
        PFM["PFM Layer<br/>(Insights + Aggregations)"]
        PROFILE["Profile Layer<br/>(User Financial Profile)"]
    end

    subgraph "Infrastructure"
        PG["PostgreSQL"]
        REDIS["Redis<br/>(Cache + Queue)"]
        LLM["LLM Provider<br/>(Claude API)"]
    end

    UI --> API
    API --> AUTH
    AUTH --> ORCH
    ORCH --> CAT
    ORCH --> SHARIAH
    ORCH --> RECUR
    ORCH --> INSIGHT
    ORCH --> ZAKAT
    CAT --> LLM
    SHARIAH --> LLM
    INSIGHT --> LLM
    ORCH --> RAW
    CAT --> MAP
    SHARIAH --> CORE
    RECUR --> CORE
    INSIGHT --> PFM
    ZAKAT --> PROFILE
    RAW --> PG
    MAP --> PG
    CORE --> PG
    PFM --> PG
    PROFILE --> PG
    ORCH --> REDIS
```

---

## 5. Quick Start

### 1. Build infrastructure
Run local PostgreSQL and Redis containers:
```bash
docker compose up -d postgres redis
```

### 2. Configure Environment variables
Copy variables and configure local settings:
```bash
cp .env.example .env
```
Inside `.env`:
```ini
DATABASE_URL=postgresql+asyncpg://barakah:barakah_dev@localhost:5435/barakah_agent
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
ENVIRONMENT=development
# optional (defaults to dynamic mocks if key is empty)
# ANTHROPIC_API_KEY=your-api-key
```

### 3. Run migrations and seed data
Sync dependencies, apply Alembic database schema definitions, and seed transactions:
```bash
uv sync
uv run python scripts/seed_transactions.py
```

### 4. Launch terminal dashboard demo
```bash
# Run animation stages slowly (presentation mode)
uv run python scripts/demo.py --slow

# Run animation stages quickly
uv run python scripts/demo.py
```

### 5. Start development API server
```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 6. API Reference

All HTTP routes are exposed under `/api/v1` prefix. You can view the fully interactive OpenAPI schema documentation at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Primary API Contracts
- **`GET /api/v1/health`**: Dependency latency diagnostics (PostgreSQL, Redis, LLM configs).
- **`POST /api/v1/transactions/ingest`**: Accepts raw transactions, creates Raw records in DB, starts asynchronous LangGraph background pipeline, and returns `ws_channel`.
- **`GET /api/v1/transactions/{account_id}`**: Returns enriched transaction feed with category/Shariah status filtering.
- **`GET /api/v1/zakat/{account_id}`**: Performs gold Nisab threshold obligation assessments.
- **`GET /api/v1/insights/{account_id}`**: Retrieves generated financial and compliance advice alerts.
- **`GET /api/v1/profile/{account_id}`**: Returns compliance score and RFM metrics.
- **`WebSocket /ws/pipeline/{pipeline_id}`**: Streams step event states (e.g. stage started/completed) to frontend client connection listeners.

---

## 7. Versioning & Eval Strategy

In production AI systems, **model changes** and **prompt changes** represent two independent axes of change. Barakah AI implements a registry tracking these configurations separately for absolute traceability.

Each agent tracks:
- `model`: E.g. `claude-3-haiku-20240307`
- `model_version`: Internal config tag
- `prompt_version`: Template identifier (e.g., `cat-v3`)
- `prompt_hash`: A SHA-256 hash of the prompt template loaded at startup.
- `fallback_model`: The fallback engine used on failure.

For Shariah auditing (e.g., Central Bank audit logs), this allows tracing every decision back to the exact prompt template and model instructions that generated it. While evaluation frameworks (Golden datasets, Langsmith/Braintrust eval pipelines) are omitted from this prototype, they represent the critical next step in staging/production rollouts.
