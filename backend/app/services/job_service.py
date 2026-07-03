from datetime import datetime, timedelta, timezone
import math
import uuid

from croniter import croniter
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ExecutionStatus, JobStatus, JobType, LogLevel, RetryStrategy
from app.models import (
    DeadLetterEntry, Job, JobExecution, JobLog, Queue, RetryHistory,
    RetryPolicy, ScheduledJob,
)


def calculate_retry_delay(policy: RetryPolicy, attempt: int) -> int:
    base = policy.base_delay_seconds
    if policy.strategy == RetryStrategy.FIXED:
        delay = base
    elif policy.strategy == RetryStrategy.LINEAR:
        delay = base * attempt
    else:
        delay = int(base * (policy.multiplier ** (attempt - 1)))
    return min(delay, policy.max_delay_seconds)


async def add_job_log(
    db: AsyncSession,
    job_id: uuid.UUID,
    message: str,
    level: LogLevel = LogLevel.INFO,
    execution_id: uuid.UUID | None = None,
) -> None:
    db.add(JobLog(job_id=job_id, message=message, level=level, execution_id=execution_id))


async def get_queue_stats(db: AsyncSession, queue_id: uuid.UUID) -> dict:
    result = await db.execute(
        select(Job.status, func.count(Job.id))
        .where(Job.queue_id == queue_id)
        .group_by(Job.status)
    )
    counts = {status.value: 0 for status in JobStatus}
    for status, count in result.all():
        counts[status.value] = count

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    throughput_result = await db.execute(
        select(func.count(Job.id)).where(
            Job.queue_id == queue_id,
            Job.status == JobStatus.COMPLETED,
            Job.completed_at >= one_hour_ago,
        )
    )
    throughput = throughput_result.scalar() or 0

    return {
        "total_jobs": sum(counts.values()),
        "queued": counts.get("queued", 0) + counts.get("scheduled", 0),
        "running": counts.get("running", 0) + counts.get("claimed", 0),
        "completed": counts.get("completed", 0),
        "failed": counts.get("failed", 0) + counts.get("retrying", 0),
        "dead_letter": counts.get("dead_letter", 0),
        "throughput_per_hour": float(throughput),
    }


async def create_job(
    db: AsyncSession,
    queue: Queue,
    job_type: JobType,
    payload: dict,
    priority: int = 0,
    scheduled_at: datetime | None = None,
    delay_seconds: int | None = None,
    cron_expression: str | None = None,
    idempotency_key: str | None = None,
    max_retries: int | None = None,
    depends_on_job_id: uuid.UUID | None = None,
    batch_id: uuid.UUID | None = None,
) -> Job:
    if idempotency_key:
        existing = await db.execute(
            select(Job).where(Job.idempotency_key == idempotency_key)
        )
        job = existing.scalar_one_or_none()
        if job:
            return job

    now = datetime.now(timezone.utc)
    status = JobStatus.QUEUED
    next_run_at = None

    if job_type == JobType.DELAYED and delay_seconds is not None:
        scheduled_at = now + timedelta(seconds=delay_seconds)
        status = JobStatus.SCHEDULED
    elif job_type == JobType.SCHEDULED and scheduled_at:
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        status = JobStatus.SCHEDULED
    elif job_type == JobType.RECURRING and cron_expression:
        if not croniter.is_valid(cron_expression):
            raise ValueError(f"Invalid cron expression: {cron_expression}")
        cron = croniter(cron_expression, now)
        next_run_at = cron.get_next(datetime).replace(tzinfo=timezone.utc)
        scheduled_at = next_run_at
        status = JobStatus.SCHEDULED

    if depends_on_job_id:
        dep = await db.get(Job, depends_on_job_id)
        if dep and dep.status != JobStatus.COMPLETED:
            status = JobStatus.SCHEDULED
            scheduled_at = None

    job = Job(
        queue_id=queue.id,
        batch_id=batch_id,
        job_type=job_type,
        status=status,
        priority=priority or queue.priority,
        payload=payload,
        scheduled_at=scheduled_at,
        cron_expression=cron_expression,
        next_run_at=next_run_at,
        idempotency_key=idempotency_key,
        max_retries=max_retries,
        depends_on_job_id=depends_on_job_id,
    )
    db.add(job)
    await db.flush()

    if job_type == JobType.RECURRING and cron_expression and next_run_at:
        db.add(ScheduledJob(
            job_id=job.id,
            queue_id=queue.id,
            cron_expression=cron_expression,
            next_run_at=next_run_at,
        ))

    await add_job_log(db, job.id, f"Job created with type {job_type.value}")
    return job


async def promote_scheduled_jobs(db: AsyncSession) -> int:
    """Move scheduled jobs whose time has come to queued status."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(Job)
        .where(
            Job.status == JobStatus.SCHEDULED,
            Job.scheduled_at <= now,
            Job.job_type != JobType.RECURRING,
            or_(Job.depends_on_job_id.is_(None), Job.depends_on_job_id.isnot(None)),
        )
        .values(status=JobStatus.QUEUED, updated_at=now)
        .returning(Job.id)
    )
    promoted = result.fetchall()

    for dep_check in promoted:
        job = await db.get(Job, dep_check[0])
        if job and job.depends_on_job_id:
            parent = await db.get(Job, job.depends_on_job_id)
            if not parent or parent.status != JobStatus.COMPLETED:
                job.status = JobStatus.SCHEDULED
                continue

    dep_result = await db.execute(
        select(Job).where(
            Job.status == JobStatus.SCHEDULED,
            Job.depends_on_job_id.isnot(None),
        )
    )
    for job in dep_result.scalars():
        parent = await db.get(Job, job.depends_on_job_id)
        if parent and parent.status == JobStatus.COMPLETED:
            job.status = JobStatus.QUEUED
            job.scheduled_at = now

    return len(promoted)


async def handle_job_failure(
    db: AsyncSession,
    job: Job,
    queue: Queue,
    execution: JobExecution,
    error: str,
) -> None:
    policy = queue.retry_policy
    max_retries = job.max_retries if job.max_retries is not None else (
        policy.max_retries if policy else 3
    )

    job.retry_count += 1
    execution.status = ExecutionStatus.FAILED
    execution.completed_at = datetime.now(timezone.utc)
    execution.error_message = error
    if execution.started_at:
        execution.duration_ms = int(
            (execution.completed_at - execution.started_at).total_seconds() * 1000
        )

    if job.retry_count <= max_retries and policy:
        delay = calculate_retry_delay(policy, job.retry_count)
        job.status = JobStatus.RETRYING
        job.scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        job.error_message = error
        job.claimed_by_worker_id = None
        job.claimed_at = None

        db.add(RetryHistory(
            job_id=job.id,
            attempt_number=job.retry_count,
            error_message=error,
            retry_after_seconds=delay,
        ))
        await add_job_log(
            db, job.id,
            f"Retry {job.retry_count}/{max_retries} scheduled in {delay}s: {error}",
            LogLevel.WARNING,
            execution.id,
        )
        job.status = JobStatus.SCHEDULED
    else:
        job.status = JobStatus.DEAD_LETTER
        job.error_message = error
        job.completed_at = datetime.now(timezone.utc)
        job.claimed_by_worker_id = None

        db.add(DeadLetterEntry(
            job_id=job.id,
            queue_id=queue.id,
            failure_reason="Max retries exceeded",
            final_error=error,
            total_attempts=job.retry_count,
            original_payload=job.payload,
        ))
        await add_job_log(
            db, job.id,
            f"Moved to dead letter queue after {job.retry_count} attempts",
            LogLevel.ERROR,
            execution.id,
        )


async def complete_job(
    db: AsyncSession,
    job: Job,
    execution: JobExecution,
    result: dict | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    job.status = JobStatus.COMPLETED
    job.result = result
    job.completed_at = now
    job.claimed_by_worker_id = None

    execution.status = ExecutionStatus.COMPLETED
    execution.completed_at = now
    execution.result = result
    if execution.started_at:
        execution.duration_ms = int((now - execution.started_at).total_seconds() * 1000)

    await add_job_log(db, job.id, "Job completed successfully", LogLevel.INFO, execution.id)

    if job.job_type == JobType.RECURRING and job.cron_expression:
        cron = croniter(job.cron_expression, now)
        next_run = cron.get_next(datetime).replace(tzinfo=timezone.utc)
        job.status = JobStatus.SCHEDULED
        job.scheduled_at = next_run
        job.next_run_at = next_run
        job.retry_count = 0
        job.completed_at = None
        job.result = None

        sched = await db.execute(
            select(ScheduledJob).where(ScheduledJob.job_id == job.id)
        )
        scheduled = sched.scalar_one_or_none()
        if scheduled:
            scheduled.next_run_at = next_run
            scheduled.last_run_at = now


async def retry_dlq_job(db: AsyncSession, dlq_id: uuid.UUID) -> Job:
    dlq = await db.get(DeadLetterEntry, dlq_id)
    if not dlq or dlq.retried:
        raise ValueError("DLQ entry not found or already retried")

    job = await db.get(Job, dlq.job_id)
    if not job:
        raise ValueError("Job not found")

    job.status = JobStatus.QUEUED
    job.retry_count = 0
    job.error_message = None
    job.completed_at = None
    job.claimed_by_worker_id = None
    dlq.retried = True

    await add_job_log(db, job.id, "Job retried from dead letter queue")
    return job
