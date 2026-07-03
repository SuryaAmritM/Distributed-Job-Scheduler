# Design Decisions

## 1. PostgreSQL as the Job Broker

**Decision:** Use PostgreSQL with `FOR UPDATE SKIP LOCKED` instead of Redis/RabbitMQ as the primary job queue.

**Rationale:**
- Single source of truth — no dual-write problem between message broker and database
- ACID guarantees for atomic claiming and state transitions
- Rich querying for dashboard, metrics, and job history
- Simpler operational footprint for an assignment scope

**Trade-off:** Lower peak throughput than dedicated message brokers (Redis, Kafka). Mitigated by horizontal worker scaling and partial indexes. For >10K jobs/sec, a hybrid approach (Redis for queueing, PG for state) would be preferred.

## 2. Separate Worker Process

**Decision:** Workers run as an independent process, not inside the API server.

**Rationale:**
- Independent scaling — add workers without scaling API
- Fault isolation — a crashing job handler doesn't take down the API
- Graceful shutdown — workers drain active jobs before exiting
- Production pattern used by Celery, Sidekiq, BullMQ

**Trade-off:** Additional deployment unit. Docker Compose makes this manageable.

## 3. Sync SQL in Worker, Async in API

**Decision:** API uses async SQLAlchemy; worker uses sync sessions with thread pool for concurrent execution.

**Rationale:**
- Job execution is CPU/IO-bound and benefits from threads
- Atomic claim SQL is simpler with sync sessions
- Avoids event-loop blocking from `time.sleep` in job handlers

**Trade-off:** Two database access patterns in one codebase. Acceptable given clear process boundaries.

## 4. UUID Primary Keys

**Decision:** UUID v4 for all primary keys.

**Rationale:**
- Safe for distributed ID generation (API and workers can create records)
- No ID enumeration attacks on public APIs
- Merge-friendly across environments

**Trade-off:** Larger indexes (16 bytes vs 8), no natural ordering. Mitigated by `created_at` indexes for time-based queries.

## 5. JSONB for Job Payloads

**Decision:** Store job input/output as JSONB rather than typed columns.

**Rationale:**
- Jobs are user-defined; payload schemas vary per use case
- No migration needed for new job types
- PostgreSQL JSONB supports indexing if needed later

**Trade-off:** No schema validation at DB level. Validated at API layer via Pydantic.

## 6. Retry Policy as Separate Entity

**Decision:** Retry policies are reusable entities referenced by queues, not embedded config.

**Rationale:**
- Multiple queues can share the same policy
- Policies can be updated centrally
- Clean separation of queue config vs retry behavior

## 7. Dead Letter Queue as Dedicated Table

**Decision:** DLQ entries live in a separate `dead_letter_queue` table, not just a job status.

**Rationale:**
- DLQ has unique fields (failure_reason, original_payload snapshot, retried flag)
- Supports DLQ-specific queries without filtering all failed jobs
- Retry-from-DLQ is an explicit operation with audit trail

## 8. Polling over WebSockets for Dashboard

**Decision:** Dashboard uses HTTP polling (3–5s intervals) instead of WebSockets.

**Rationale:**
- Simpler implementation; no connection management
- Sufficient for monitoring use case
- Works behind standard load balancers without sticky sessions

**Trade-off:** Higher latency for live updates (~3s). WebSocket support listed as bonus; polling is a pragmatic default.

## 9. JWT Authentication

**Decision:** Stateless JWT tokens, no server-side session store.

**Rationale:**
- API is stateless and horizontally scalable
- Standard pattern for REST APIs
- Simple frontend integration

**Trade-off:** Cannot revoke tokens before expiry. Mitigated by short-ish expiry (24h default) and future token blocklist via Redis if needed.

## 10. Role-Based Access Control

**Decision:** Four roles — owner, admin, member, viewer — at the organization level.

**Rationale:**
- Covers typical team structures
- Viewers can monitor without mutating
- Members can enqueue jobs; admins manage queues

**Trade-off:** No per-project or per-queue ACLs. Would add complexity; org-level RBAC is sufficient for MVP.

## 11. Idempotency via Unique Key

**Decision:** Optional `idempotency_key` with a unique partial index.

**Rationale:**
- Prevents duplicate job creation from client retries
- Industry standard (Stripe, AWS APIs)
- Partial index keeps index small (only non-null keys)

## 12. Job Dependencies

**Decision:** Simple `depends_on_job_id` FK; dependent jobs stay in `scheduled` until parent completes.

**Rationale:**
- Covers basic workflow ordering without a full DAG engine
- Easy to understand and debug

**Trade-off:** No multi-parent dependencies or complex DAGs. A `job_dependencies` junction table would be needed for that.
