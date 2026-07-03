# Distributed Job Scheduler — Assignment Submission

**Project:** Production-inspired distributed job scheduling platform  
**Stack:** FastAPI · PostgreSQL/SQLite · SQLAlchemy · React · TypeScript  
**Repository layout:** `backend/` · `frontend/` · `docs/` · `docker-compose.yml`

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Requirements Coverage](#2-requirements-coverage)
3. [Source Code & Setup Instructions](#3-source-code--setup-instructions)
4. [Architecture Diagram](#4-architecture-diagram)
5. [ER Diagram & Database Design](#5-er-diagram--database-design)
6. [API Documentation](#6-api-documentation)
7. [Design Decisions & Trade-offs](#7-design-decisions--trade-offs)
8. [Automated Tests](#8-automated-tests)
9. [Bonus Features](#9-bonus-features)

---

## 1. Executive Summary

This project implements a **distributed job scheduling platform** capable of reliably executing asynchronous background jobs across multiple workers. It includes:

- JWT authentication with organization/project management and RBAC
- Configurable job queues (priority, concurrency, retry policy, pause/resume, statistics)
- Five job types: immediate, delayed, scheduled, recurring (cron), and batch
- A standalone worker service that polls queues, atomically claims jobs, executes concurrently, sends heartbeats, and supports graceful shutdown
- Full job lifecycle management with retries and Dead Letter Queue (DLQ)
- Three retry strategies: fixed delay, linear backoff, exponential backoff
- Execution logs, retry history, worker assignment, timestamps, and metrics
- A React dashboard for queue health, job inspection, worker monitoring, and throughput visualization

---

## 2. Requirements Coverage

| Requirement | Status | Implementation |
|-------------|--------|----------------|
| Authentication & project management | ✅ | JWT auth, orgs, projects, RBAC |
| Queue configuration | ✅ | Priority, concurrency, retry policy, pause/resume, stats |
| Job types (immediate, delayed, scheduled, cron, batch) | ✅ | REST APIs with validation |
| Worker service | ✅ | Poll, atomic claim, concurrent exec, heartbeats, graceful shutdown |
| Job lifecycle | ✅ | Queued → Scheduled → Claimed → Running → Completed/Failed/DLQ |
| Retry strategies | ✅ | Fixed, linear, exponential backoff |
| Execution logs & metrics | ✅ | Job logs, retry history, executions, metrics API |
| Web dashboard | ✅ | React dashboard with live polling |
| Database design | ✅ | 14 normalized tables with indexes and FK constraints |
| REST APIs | ✅ | Validation, auth, pagination, filtering, error handling |
| Atomic job claiming | ✅ | `FOR UPDATE SKIP LOCKED` (PostgreSQL) |
| Automated tests | ✅ | 10 pytest tests for critical paths |

---

## 3. Source Code & Setup Instructions

### 3.1 Project Structure

```
Codity assignment/
├── backend/
│   ├── app/
│   │   ├── api/routes.py       # REST API endpoints
│   │   ├── services/
│   │   │   └── job_service.py  # Job creation, retry, DLQ logic
│   │   ├── worker/main.py      # Worker polling & execution
│   │   ├── models.py           # SQLAlchemy ORM (14 tables)
│   │   ├── schemas.py          # Pydantic request/response models
│   │   ├── auth.py             # JWT & password hashing
│   │   ├── enums.py            # Status/type enumerations
│   │   ├── database.py         # DB session management
│   │   ├── config.py           # Environment settings
│   │   └── main.py             # FastAPI application entry
│   ├── tests/
│   │   ├── conftest.py         # Test fixtures
│   │   └── test_api.py         # API & retry strategy tests
│   ├── scripts/seed.py         # Demo data seeder
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/              # Dashboard, Queues, Jobs, Workers, Login
│   │   ├── api.ts              # API client
│   │   └── App.tsx             # Router & layout
│   ├── package.json
│   └── Dockerfile
├── docs/                       # Individual doc files (also in this document)
├── docker-compose.yml
└── README.md
```

### 3.2 Prerequisites

- **Docker path:** Docker & Docker Compose
- **Local path:** Python 3.12+, Node.js 20+, PostgreSQL 16+ (or SQLite for quick local dev)

### 3.3 Option A — Docker (Recommended)

```bash
# From project root
docker compose up --build

# Seed demo data (in a second terminal)
docker compose exec api python -m scripts.seed
```

| Service   | URL                          |
|-----------|------------------------------|
| API       | http://localhost:8000        |
| API Docs  | http://localhost:8000/docs   |
| Dashboard | http://localhost:5173        |

**Demo login:** `admin@example.com` / `admin12345`

### 3.4 Option B — Local Development (Windows PowerShell)

**Backend API:**
```powershell
cd backend
pip install -r requirements.txt

# SQLite (no PostgreSQL needed) — .env file is pre-configured
python -m scripts.seed
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Worker (separate terminal):**
```powershell
cd backend
python -m app.worker.main
```

**Frontend (separate terminal):**
```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in.

### 3.5 Option C — Local with PostgreSQL

```powershell
cd backend
pip install -r requirements.txt

$env:DATABASE_URL = "postgresql+asyncpg://scheduler:scheduler@localhost:5432/job_scheduler"
$env:DATABASE_URL_SYNC = "postgresql://scheduler:scheduler@localhost:5432/job_scheduler"

python -m scripts.seed
python -m uvicorn app.main:app --reload
```

### 3.6 Run Tests

```powershell
cd backend
python -m pytest -v
```

Expected: **10 passed**

---

## 4. Architecture Diagram

### 4.1 High-Level System Architecture

```
┌──────────────┐     REST/JSON      ┌──────────────┐
│   React      │◄──────────────────►│   FastAPI    │
│  Dashboard   │     JWT Auth      │     API      │
└──────────────┘                    └──────┬───────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
              ┌─────▼─────┐         ┌──────▼──────┐        ┌──────▼──────┐
              │ PostgreSQL │         │    Redis    │        │   Worker    │
              │  (primary) │         │  (optional) │        │   Service   │
              └───────────┘         └─────────────┘        └─────────────┘
```

### 4.2 Component Diagram (Mermaid)

```mermaid
flowchart TB
    subgraph Client Layer
        UI[React Dashboard]
    end

    subgraph Control Plane
        API[FastAPI API Server]
    end

    subgraph Data Plane
        W1[Worker 1]
        W2[Worker 2]
        WN[Worker N]
    end

    subgraph Storage
        PG[(PostgreSQL)]
        RD[(Redis - optional)]
    end

    UI -->|REST + JWT| API
    API --> PG
    W1 --> PG
    W2 --> PG
    WN --> PG
    API -.-> RD
    W1 -.-> RD
```

### 4.3 Control Plane vs Data Plane

| Layer | Component | Responsibility |
|-------|-----------|----------------|
| **Control Plane** | FastAPI API | Auth, validation, job enqueue, queue config, metrics, DLQ retry |
| **Data Plane** | Worker Service | Poll queues, atomic claim, execute jobs, heartbeats, retry/DLQ routing |
| **Storage** | PostgreSQL | Source of truth, atomic claims, audit trail |
| **Client** | React Dashboard | Visualization, job management, live status (polling) |

### 4.4 Job Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> Queued: immediate job
    [*] --> Scheduled: delayed / scheduled / cron
    Scheduled --> Queued: time reached / dependency met
    Queued --> Claimed: worker claims (SKIP LOCKED)
    Claimed --> Running: execution starts
    Running --> Completed: success
    Running --> Scheduled: retry with backoff
    Running --> DeadLetter: max retries exceeded
    Completed --> Scheduled: recurring cron reschedule
    Queued --> Cancelled: user cancel
    DeadLetter --> Queued: manual DLQ retry
```

### 4.5 Atomic Job Claiming Flow

Workers prevent duplicate execution using PostgreSQL row-level locking:

1. Promote scheduled jobs whose `scheduled_at` has passed → `queued`
2. Find queues that are **not paused** and **under concurrency limit**
3. Select highest-priority, oldest eligible job
4. Atomically `UPDATE` status to `claimed` with `FOR UPDATE SKIP LOCKED`

This is the same pattern used by Sidekiq, Celery (DB broker), and Faktory.

### 4.6 Deployment Topology (Production)

- **API:** 2+ replicas behind a load balancer (stateless)
- **Workers:** N replicas, scaled by queue depth
- **PostgreSQL:** Primary + read replica for metrics queries
- **Redis:** Optional for distributed rate limiting and pub/sub

---

## 5. ER Diagram & Database Design

### 5.1 Entity-Relationship Diagram

```mermaid
erDiagram
    USERS ||--o{ ORGANIZATION_MEMBERS : "belongs to"
    ORGANIZATIONS ||--o{ ORGANIZATION_MEMBERS : "has"
    ORGANIZATIONS ||--o{ PROJECTS : "owns"
    PROJECTS ||--o{ QUEUES : "contains"
    RETRY_POLICIES ||--o{ QUEUES : "configures"
    QUEUES ||--o{ JOBS : "holds"
    JOBS ||--o{ JOB_EXECUTIONS : "has"
    JOBS ||--o{ JOB_LOGS : "logs"
    JOBS ||--o{ RETRY_HISTORY : "tracks"
    JOBS ||--o| DEAD_LETTER_QUEUE : "may enter"
    JOBS ||--o| SCHEDULED_JOBS : "cron template"
    JOBS ||--o| JOBS : "depends on"
    WORKERS ||--o{ JOB_EXECUTIONS : "runs"
    WORKERS ||--o{ WORKER_HEARTBEATS : "pulses"
    WORKERS ||--o{ JOBS : "claims"

    USERS {
        uuid id PK
        string email UK
        string hashed_password
        string full_name
        boolean is_active
        timestamp created_at
    }

    ORGANIZATIONS {
        uuid id PK
        string name
        string slug UK
        timestamp created_at
    }

    ORGANIZATION_MEMBERS {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK
        enum role
    }

    PROJECTS {
        uuid id PK
        uuid organization_id FK
        string name
        string slug
        boolean is_active
    }

    RETRY_POLICIES {
        uuid id PK
        string name
        enum strategy
        int max_retries
        int base_delay_seconds
        int max_delay_seconds
        float multiplier
    }

    QUEUES {
        uuid id PK
        uuid project_id FK
        string name
        int priority
        int concurrency_limit
        boolean is_paused
        uuid retry_policy_id FK
        int rate_limit_per_minute
    }

    JOBS {
        uuid id PK
        uuid queue_id FK
        uuid batch_id
        enum job_type
        enum status
        int priority
        jsonb payload
        jsonb result
        string idempotency_key
        timestamp scheduled_at
        string cron_expression
        int retry_count
        uuid claimed_by_worker_id FK
        uuid depends_on_job_id FK
    }

    JOB_EXECUTIONS {
        uuid id PK
        uuid job_id FK
        uuid worker_id FK
        int attempt_number
        enum status
        timestamp started_at
        timestamp completed_at
        int duration_ms
    }

    RETRY_HISTORY {
        uuid id PK
        uuid job_id FK
        int attempt_number
        string error_message
        int retry_after_seconds
        timestamp retried_at
    }

    JOB_LOGS {
        uuid id PK
        uuid job_id FK
        uuid execution_id FK
        enum level
        string message
        jsonb metadata
        timestamp created_at
    }

    WORKERS {
        uuid id PK
        string hostname
        int pid
        enum status
        int concurrency
        int active_jobs
        int total_jobs_processed
        timestamp last_heartbeat_at
    }

    WORKER_HEARTBEATS {
        uuid id PK
        uuid worker_id FK
        int active_jobs
        float cpu_percent
        float memory_mb
        timestamp created_at
    }

    DEAD_LETTER_QUEUE {
        uuid id PK
        uuid job_id FK UK
        uuid queue_id FK
        string failure_reason
        string final_error
        int total_attempts
        jsonb original_payload
        boolean retried
    }

    SCHEDULED_JOBS {
        uuid id PK
        uuid job_id FK UK
        uuid queue_id FK
        string cron_expression
        timestamp next_run_at
        boolean is_active
    }
```

### 5.2 Tables Summary (14 entities)

| Table | Purpose |
|-------|---------|
| `users` | User accounts |
| `organizations` | Top-level tenant |
| `organization_members` | RBAC membership (owner/admin/member/viewer) |
| `projects` | Projects within an organization |
| `retry_policies` | Reusable retry configuration |
| `queues` | Job queues with priority, concurrency, pause state |
| `jobs` | Job records with payload, status, scheduling info |
| `job_executions` | Per-attempt execution records |
| `retry_history` | Retry audit trail |
| `job_logs` | Structured execution logs |
| `workers` | Registered worker processes |
| `worker_heartbeats` | Heartbeat time-series |
| `dead_letter_queue` | Permanently failed jobs |
| `scheduled_jobs` | Cron/recurring job scheduler index |

### 5.3 Primary Keys

All tables use **UUID v4** primary keys — safe for distributed ID generation without coordination between API and workers.

### 5.4 Foreign Keys & Cascading

| Relationship | ON DELETE |
|---|---|
| Organization → Projects | CASCADE |
| Project → Queues | CASCADE |
| Queue → Jobs | CASCADE |
| Job → Executions, Logs, Retry History | CASCADE |
| Queue → Retry Policy | SET NULL |
| Job → Worker (claim reference) | SET NULL |

- **CASCADE** on job children ensures cleanup when a queue is deleted.
- **SET NULL** on worker references preserves execution history after worker deregistration.

### 5.5 Indexes

| Index | Purpose |
|---|---|
| `ix_jobs_queue_status (queue_id, status)` | Fast job listing and per-queue stats |
| `ix_jobs_scheduled_at (scheduled_at) WHERE status IN (...)` | Partial index for scheduler promotion |
| `ix_jobs_idempotency (idempotency_key) WHERE NOT NULL` | Unique idempotency enforcement |
| `ix_queues_poll (is_paused, priority)` | Worker queue selection |
| `ix_job_logs_job_created (job_id, created_at)` | Log retrieval per job |
| `ix_heartbeats_worker_time (worker_id, created_at)` | Heartbeat history queries |
| `ix_scheduled_next_run (next_run_at, is_active)` | Cron job promotion |

### 5.6 Normalization

- **3NF** for core entities (users, organizations, projects, queues)
- **Computed stats** at query time (not stored) to avoid consistency issues
- **JSONB payloads** for flexible job data without per-type schema migrations
- **DLQ as separate table** (not just a status flag) for DLQ-specific operations and retry tracking

### 5.7 Performance Considerations

- Partial indexes reduce size for sparse columns (`idempotency_key`, `scheduled_at`)
- `FOR UPDATE SKIP LOCKED` avoids worker contention without application-level locks
- `batch_id` on jobs groups batch submissions without a separate batch table
- Heartbeat records are append-only; archivable by `created_at`

---

## 6. API Documentation

**Base URL:** `http://localhost:8000/api/v1`  
**Interactive docs:** `http://localhost:8000/docs`  
**Auth header:** `Authorization: Bearer <access_token>`

### 6.1 Authentication

#### POST `/auth/register`
Register a new user. Auto-creates organization, project, and default queue.

```json
{
  "email": "user@example.com",
  "password": "password123",
  "full_name": "Jane Doe"
}
```

#### POST `/auth/login`
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```
**Response:** `{ "access_token": "eyJ...", "token_type": "bearer" }`

#### GET `/auth/me`
Returns current user profile. Requires auth.

---

### 6.2 Organizations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/organizations` | Create org (creator becomes owner) |
| GET | `/organizations` | List user's organizations |

**Create body:** `{ "name": "Acme Corp", "slug": "acme" }`

---

### 6.3 Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/organizations/{org_id}/projects` | Create project |
| GET | `/organizations/{org_id}/projects` | List projects |
| GET | `/projects/{project_id}` | Get project |
| PATCH | `/projects/{project_id}` | Update project |

---

### 6.4 Retry Policies

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/retry-policies` | Create policy |
| GET | `/retry-policies` | List policies |

**Strategies:** `fixed` · `linear` · `exponential`

```json
{
  "name": "Exponential Backoff",
  "strategy": "exponential",
  "max_retries": 5,
  "base_delay_seconds": 60,
  "max_delay_seconds": 3600,
  "multiplier": 2.0
}
```

---

### 6.5 Queues

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/projects/{project_id}/queues` | Create queue |
| GET | `/projects/{project_id}/queues` | List queues with stats |
| GET | `/queues/{queue_id}` | Get queue with stats |
| PATCH | `/queues/{queue_id}` | Update configuration |
| POST | `/queues/{queue_id}/pause` | Pause processing |
| POST | `/queues/{queue_id}/resume` | Resume processing |

**Queue stats included in responses:**
`total_jobs`, `queued`, `running`, `completed`, `failed`, `dead_letter`, `throughput_per_hour`

---

### 6.6 Jobs

#### POST `/queues/{queue_id}/jobs` — Create job

**Immediate:**
```json
{
  "job_type": "immediate",
  "payload": { "action": "send_email", "to": "user@example.com" },
  "priority": 0,
  "idempotency_key": "optional-unique-key"
}
```

**Delayed:**
```json
{ "job_type": "delayed", "payload": {}, "delay_seconds": 300 }
```

**Scheduled:**
```json
{ "job_type": "scheduled", "payload": {}, "scheduled_at": "2026-07-04T10:00:00Z" }
```

**Recurring (cron):**
```json
{ "job_type": "recurring", "payload": {}, "cron_expression": "0 */6 * * *" }
```

**With dependency:**
```json
{ "job_type": "immediate", "payload": {}, "depends_on_job_id": "parent-job-uuid" }
```

#### POST `/queues/{queue_id}/jobs/batch`
Create up to 100 jobs. All share a `batch_id`.

#### GET `/queues/{queue_id}/jobs`
List jobs. Query params: `status`, `page`, `page_size`

#### GET `/jobs/{job_id}`
Job detail with executions, logs, and retry history.

#### POST `/jobs/{job_id}/cancel`
Cancel a pending job.

---

### 6.7 Dead Letter Queue

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/queues/{queue_id}/dlq` | List DLQ entries (paginated) |
| POST | `/dlq/{dlq_id}/retry` | Re-enqueue failed job |

---

### 6.8 Workers & Metrics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/workers` | List workers with heartbeat info |
| GET | `/metrics` | System-wide metrics |
| GET | `/health` | Health check (no auth) |

**Metrics response:**
```json
{
  "total_jobs": 1500,
  "jobs_by_status": { "completed": 1200, "queued": 50, "running": 5 },
  "active_workers": 3,
  "throughput_last_hour": 245.0,
  "avg_duration_ms": 1523.5,
  "dlq_count": 12
}
```

---

### 6.9 Error Responses & Pagination

**Errors:** `{ "detail": "Human-readable message" }`

| Status | Meaning |
|--------|---------|
| 400 | Validation error |
| 401 | Unauthorized |
| 403 | Forbidden (RBAC) |
| 404 | Not found |
| 500 | Internal server error |

**Pagination:** `{ "items": [], "total": 100, "page": 1, "page_size": 20, "pages": 5 }`

---

## 7. Design Decisions & Trade-offs

### 7.1 PostgreSQL as the Job Broker
**Decision:** Use PostgreSQL with `FOR UPDATE SKIP LOCKED` instead of Redis/RabbitMQ.  
**Why:** Single source of truth, ACID guarantees, rich querying for dashboard/metrics.  
**Trade-off:** Lower peak throughput than dedicated brokers; acceptable for this scope.

### 7.2 Separate Worker Process
**Decision:** Workers run independently from the API server.  
**Why:** Independent scaling, fault isolation, graceful shutdown, production-standard pattern.  
**Trade-off:** Extra deployment unit (managed via Docker Compose).

### 7.3 Async API, Sync Worker
**Decision:** FastAPI uses async SQLAlchemy; worker uses sync sessions + thread pool.  
**Why:** Job handlers block on I/O; sync SQL simplifies atomic claim logic.  
**Trade-off:** Two DB access patterns, separated by process boundary.

### 7.4 UUID Primary Keys
**Decision:** UUID v4 everywhere.  
**Why:** Distributed-safe ID generation, no enumeration attacks.  
**Trade-off:** Larger indexes; mitigated by `created_at` indexes.

### 7.5 JSONB Job Payloads
**Decision:** Flexible JSONB for job input/output.  
**Why:** User-defined schemas, no migration per job type.  
**Trade-off:** No DB-level schema validation (validated via Pydantic at API layer).

### 7.6 Retry Policy as Separate Entity
**Decision:** Reusable `retry_policies` table referenced by queues.  
**Why:** Share policies across queues, update centrally.

### 7.7 Dead Letter Queue as Dedicated Table
**Decision:** Separate `dead_letter_queue` table, not just a status flag.  
**Why:** DLQ-specific fields, explicit retry operation, audit trail.

### 7.8 Polling over WebSockets (Dashboard)
**Decision:** HTTP polling every 3–5 seconds.  
**Why:** Simpler, works behind load balancers, sufficient for monitoring.  
**Trade-off:** ~3s update latency vs real-time.

### 7.9 JWT Authentication
**Decision:** Stateless JWT, no server-side sessions.  
**Why:** Horizontally scalable API, standard REST pattern.  
**Trade-off:** Cannot revoke tokens before expiry without a blocklist.

### 7.10 Role-Based Access Control
**Decision:** Four roles at org level — owner, admin, member, viewer.  
**Why:** Covers typical team structures without per-queue ACL complexity.

### 7.11 Idempotency Keys
**Decision:** Optional `idempotency_key` with unique partial index.  
**Why:** Prevents duplicate jobs from client retries (Stripe/AWS pattern).

### 7.12 Job Dependencies
**Decision:** Simple `depends_on_job_id` FK.  
**Why:** Basic workflow ordering without a full DAG engine.  
**Trade-off:** Single parent only; multi-parent needs a junction table.

---

## 8. Automated Tests

### 8.1 How to Run

```powershell
cd backend
python -m pytest -v
```

### 8.2 Test Suite (10 tests)

| Test | What it verifies |
|------|------------------|
| `test_health` | API health endpoint returns 200 |
| `test_register_and_login` | User registration and JWT login flow |
| `test_create_immediate_job` | Immediate job created with `queued` status |
| `test_create_delayed_job` | Delayed job created with `scheduled` status |
| `test_idempotency` | Duplicate idempotency key returns same job ID |
| `test_queue_pause_resume` | Queue pause/resume toggles `is_paused` |
| `test_list_jobs_pagination` | Job listing respects page size and total count |
| `test_retry_delay_fixed` | Fixed retry: delay = base_delay always |
| `test_retry_delay_exponential` | Exponential: 60s → 120s → 240s |
| `test_retry_delay_linear` | Linear: delay = base × attempt number |

### 8.3 Test Infrastructure

- **Framework:** pytest + pytest-asyncio + httpx AsyncClient
- **Database:** In-memory SQLite (isolated per test run)
- **Fixtures:** Pre-seeded user, org, project, queue, retry policy with JWT token

### 8.4 Critical Paths Covered

- Authentication (register, login, token)
- Job creation (immediate, delayed)
- Idempotent job submission
- Queue lifecycle (pause/resume)
- Pagination
- All three retry delay calculations

---

## 9. Bonus Features

| Feature | Implementation |
|---------|----------------|
| Workflow dependencies | `depends_on_job_id` on jobs; promoted when parent completes |
| Rate limiting | `rate_limit_per_minute` config per queue |
| Role-based access control | owner / admin / member / viewer at org level |

---

## Appendix — Quick Demo Walkthrough

1. Start services (Docker or local — see Section 3)
2. Open http://localhost:5173
3. Login: `admin@example.com` / `admin12345`
4. Go to **Jobs** → click **Enqueue Job**
5. Watch status change: `queued` → `running` → `completed`
6. Click **Details** to see execution logs and timing
7. Check **Workers** page for active worker and heartbeat
8. Check **Dashboard** for throughput and status charts

To test failure/retry, use payload:
```json
{ "should_fail": true, "error_message": "Simulated failure", "duration_seconds": 0.1 }
```

---

*End of submission document.*
