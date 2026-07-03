# API Documentation

Base URL: `http://localhost:8000/api/v1`

Interactive docs: `http://localhost:8000/docs`

## Authentication

All endpoints except `/auth/register` and `/auth/login` require a Bearer token.

```
Authorization: Bearer <access_token>
```

### POST /auth/register
Register a new user.

**Body:**
```json
{
  "email": "user@example.com",
  "password": "password123",
  "full_name": "Jane Doe"
}
```

### POST /auth/login
Returns JWT access token.

**Body:**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

### GET /auth/me
Returns current user profile.

---

## Organizations

### POST /organizations
Create organization. Creator becomes owner.

**Body:** `{ "name": "Acme Corp", "slug": "acme" }`

### GET /organizations
List organizations for current user.

---

## Projects

### POST /organizations/{org_id}/projects
**Body:** `{ "name": "My Project", "slug": "my-project", "description": "..." }`

### GET /organizations/{org_id}/projects
List projects in organization.

### GET /projects/{project_id}
Get project details.

### PATCH /projects/{project_id}
Update project fields.

---

## Retry Policies

### POST /retry-policies
**Body:**
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

Strategies: `fixed`, `linear`, `exponential`

### GET /retry-policies
List all retry policies.

---

## Queues

### POST /projects/{project_id}/queues
**Body:**
```json
{
  "name": "default",
  "priority": 0,
  "concurrency_limit": 10,
  "retry_policy_id": "uuid",
  "rate_limit_per_minute": 100
}
```

### GET /projects/{project_id}/queues
List queues with inline statistics.

### GET /queues/{queue_id}
Get queue with stats.

### PATCH /queues/{queue_id}
Update queue configuration.

### POST /queues/{queue_id}/pause
Pause job processing for this queue.

### POST /queues/{queue_id}/resume
Resume job processing.

---

## Jobs

### POST /queues/{queue_id}/jobs
Create a single job.

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
{
  "job_type": "delayed",
  "payload": {},
  "delay_seconds": 300
}
```

**Scheduled:**
```json
{
  "job_type": "scheduled",
  "payload": {},
  "scheduled_at": "2026-07-04T10:00:00Z"
}
```

**Recurring (cron):**
```json
{
  "job_type": "recurring",
  "payload": {},
  "cron_expression": "0 */6 * * *"
}
```

**With dependency:**
```json
{
  "job_type": "immediate",
  "payload": {},
  "depends_on_job_id": "parent-job-uuid"
}
```

### POST /queues/{queue_id}/jobs/batch
Create up to 100 jobs in a batch.

**Body:**
```json
{
  "jobs": [
    { "job_type": "immediate", "payload": { "item": 1 } },
    { "job_type": "immediate", "payload": { "item": 2 } }
  ]
}
```

### GET /queues/{queue_id}/jobs
List jobs with pagination and filtering.

**Query params:** `status`, `page` (default 1), `page_size` (default 20, max 100)

### GET /jobs/{job_id}
Get job with executions, logs, and retry history.

### POST /jobs/{job_id}/cancel
Cancel a pending job.

---

## Dead Letter Queue

### GET /queues/{queue_id}/dlq
List DLQ entries. Supports pagination.

### POST /dlq/{dlq_id}/retry
Re-enqueue a failed job from DLQ.

---

## Workers

### GET /workers
List all registered workers with status and heartbeat info.

---

## Metrics

### GET /metrics
System-wide metrics.

**Response:**
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

## Error Responses

All errors return:
```json
{
  "detail": "Human-readable error message"
}
```

| Status | Meaning |
|--------|---------|
| 400 | Validation error |
| 401 | Unauthorized |
| 403 | Forbidden (RBAC) |
| 404 | Resource not found |
| 500 | Internal server error |

## Pagination

Paginated endpoints return:
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20,
  "pages": 5
}
```
