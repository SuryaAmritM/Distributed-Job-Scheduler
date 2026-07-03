# Entity-Relationship Diagram

## ER Diagram

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

## Schema Design Notes

### Primary Keys
All tables use **UUID v4** primary keys for distributed-friendly ID generation without coordination.

### Foreign Keys & Cascading
| Relationship | ON DELETE |
|---|---|
| Organization → Projects | CASCADE |
| Project → Queues | CASCADE |
| Queue → Jobs | CASCADE |
| Job → Executions, Logs, Retry History | CASCADE |
| Queue → Retry Policy | SET NULL |
| Job → Worker (claim) | SET NULL |

CASCADE on job children ensures cleanup when a queue is deleted. SET NULL on worker references preserves execution history after worker deregistration.

### Indexes

| Index | Purpose |
|---|---|
| `ix_jobs_queue_status (queue_id, status)` | Fast job listing and stats per queue |
| `ix_jobs_scheduled_at (scheduled_at) WHERE status IN (...)` | Partial index for scheduler promotion |
| `ix_jobs_idempotency (idempotency_key) WHERE NOT NULL` | Unique idempotency enforcement |
| `ix_queues_poll (is_paused, priority)` | Worker queue selection |
| `ix_job_logs_job_created (job_id, created_at)` | Log retrieval per job |
| `ix_heartbeats_worker_time (worker_id, created_at)` | Heartbeat history queries |
| `ix_scheduled_next_run (next_run_at, is_active)` | Cron job promotion |

### Normalization
- **3NF** for core entities (users, orgs, projects, queues)
- **Denormalized stats** computed at query time (not stored) to avoid consistency issues
- **JSONB payload/result** for flexible job data without schema migrations per job type
- **Dead Letter Queue** as separate table (not just a status) to support DLQ-specific operations and retry tracking

### Performance Considerations
- Partial indexes reduce index size for sparse columns (`idempotency_key`, `scheduled_at`)
- `FOR UPDATE SKIP LOCKED` avoids worker contention without application-level locks
- Batch job grouping via `batch_id` avoids a separate batch table while enabling batch queries
- Heartbeat records are append-only; old records can be partitioned/archived by `created_at`
