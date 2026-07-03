import asyncio
import logging
import os
import signal
import socket
import time
import uuid
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import sync_session_factory
from app.enums import ExecutionStatus, JobStatus, JobType, LogLevel, WorkerStatus
from app.models import DeadLetterEntry, Job, JobExecution, JobLog, Queue, RetryHistory, ScheduledJob, Worker, WorkerHeartbeat
from app.services.job_service import calculate_retry_delay, promote_scheduled_jobs

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("worker")


def add_log(db: Session, job_id: uuid.UUID, message: str, level: LogLevel = LogLevel.INFO, execution_id=None):
    db.add(JobLog(job_id=job_id, message=message, level=level, execution_id=execution_id))


def complete_job_sync(db: Session, job: Job, execution: JobExecution, result: dict | None = None):
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

    add_log(db, job.id, "Job completed successfully", LogLevel.INFO, execution.id)

    if job.job_type == JobType.RECURRING and job.cron_expression:
        cron = croniter(job.cron_expression, now)
        next_run = cron.get_next(datetime).replace(tzinfo=timezone.utc)
        job.status = JobStatus.SCHEDULED
        job.scheduled_at = next_run
        job.next_run_at = next_run
        job.retry_count = 0
        job.completed_at = None
        job.result = None

        sched = db.query(ScheduledJob).filter(ScheduledJob.job_id == job.id).first()
        if sched:
            sched.next_run_at = next_run
            sched.last_run_at = now


def handle_failure_sync(db: Session, job: Job, queue: Queue, execution: JobExecution, error: str):
    policy = queue.retry_policy
    max_retries = job.max_retries if job.max_retries is not None else (policy.max_retries if policy else 3)

    job.retry_count += 1
    execution.status = ExecutionStatus.FAILED
    execution.completed_at = datetime.now(timezone.utc)
    execution.error_message = error
    if execution.started_at:
        execution.duration_ms = int((execution.completed_at - execution.started_at).total_seconds() * 1000)

    if job.retry_count <= max_retries and policy:
        delay = calculate_retry_delay(policy, job.retry_count)
        job.status = JobStatus.SCHEDULED
        job.scheduled_at = datetime.now(timezone.utc) + __import__("datetime").timedelta(seconds=delay)
        job.error_message = error
        job.claimed_by_worker_id = None
        job.claimed_at = None

        db.add(RetryHistory(
            job_id=job.id, attempt_number=job.retry_count,
            error_message=error, retry_after_seconds=delay,
        ))
        add_log(db, job.id, f"Retry {job.retry_count}/{max_retries} in {delay}s: {error}", LogLevel.WARNING, execution.id)
    else:
        job.status = JobStatus.DEAD_LETTER
        job.error_message = error
        job.completed_at = datetime.now(timezone.utc)
        job.claimed_by_worker_id = None
        db.add(DeadLetterEntry(
            job_id=job.id, queue_id=queue.id, failure_reason="Max retries exceeded",
            final_error=error, total_attempts=job.retry_count, original_payload=job.payload,
        ))
        add_log(db, job.id, f"Moved to DLQ after {job.retry_count} attempts", LogLevel.ERROR, execution.id)


class JobWorker:
    def __init__(self):
        self.worker_id: uuid.UUID | None = None
        self.concurrency = int(os.environ.get("WORKER_CONCURRENCY", settings.worker_concurrency))
        self.poll_interval = float(os.environ.get("WORKER_POLL_INTERVAL", settings.worker_poll_interval))
        self.running = True
        self.active_tasks: set[asyncio.Task] = set()
        self.semaphore = asyncio.Semaphore(self.concurrency)

    def register_worker(self, db: Session) -> Worker:
        worker = Worker(hostname=socket.gethostname(), pid=os.getpid(), status=WorkerStatus.ONLINE, concurrency=self.concurrency)
        db.add(worker)
        db.commit()
        db.refresh(worker)
        self.worker_id = worker.id
        logger.info("Worker registered: %s", self.worker_id)
        return worker

    def send_heartbeat(self, db: Session):
        if not self.worker_id:
            return
        worker = db.get(Worker, self.worker_id)
        if worker:
            worker.last_heartbeat_at = datetime.now(timezone.utc)
            worker.active_jobs = len(self.active_tasks)
            db.add(WorkerHeartbeat(worker_id=self.worker_id, active_jobs=len(self.active_tasks)))
            db.commit()

    def claim_job_atomic(self, db: Session) -> uuid.UUID | None:
        if "sqlite" in settings.database_url_sync:
            return self._claim_job_sqlite(db)

        db.execute(text("""
            UPDATE jobs SET status = 'queued', updated_at = NOW()
            WHERE status = 'scheduled' AND scheduled_at <= NOW() AND job_type != 'recurring'
        """))
        db.execute(text("""
            UPDATE jobs j SET status = 'queued', scheduled_at = NOW(), updated_at = NOW()
            FROM jobs parent WHERE j.depends_on_job_id = parent.id
            AND j.status = 'scheduled' AND parent.status = 'completed'
        """))
        db.commit()

        result = db.execute(
            text("""
                WITH eligible AS (
                    SELECT q.id FROM queues q
                    WHERE q.is_paused = false
                    AND (SELECT COUNT(*) FROM jobs j2 WHERE j2.queue_id = q.id
                         AND j2.status IN ('claimed','running')) < q.concurrency_limit
                ),
                candidate AS (
                    SELECT j.id FROM jobs j
                    JOIN eligible e ON j.queue_id = e.id
                    WHERE j.status IN ('queued','retrying')
                       OR (j.status = 'scheduled' AND j.scheduled_at <= NOW())
                    ORDER BY j.priority DESC, j.created_at ASC
                    LIMIT 1 FOR UPDATE OF j SKIP LOCKED
                )
                UPDATE jobs SET status = 'claimed', claimed_by_worker_id = :wid,
                    claimed_at = NOW(), updated_at = NOW()
                FROM candidate WHERE jobs.id = candidate.id
                RETURNING jobs.id
            """),
            {"wid": str(self.worker_id)},
        )
        row = result.fetchone()
        db.commit()
        return uuid.UUID(str(row[0])) if row else None

    def _claim_job_sqlite(self, db: Session) -> uuid.UUID | None:
        now = datetime.now(timezone.utc)
        for job in db.query(Job).filter(
            Job.status == JobStatus.SCHEDULED,
            Job.scheduled_at <= now,
            Job.job_type != JobType.RECURRING,
        ).all():
            job.status = JobStatus.QUEUED

        for job in db.query(Job).filter(Job.status == JobStatus.SCHEDULED, Job.depends_on_job_id.isnot(None)).all():
            parent = db.get(Job, job.depends_on_job_id)
            if parent and parent.status == JobStatus.COMPLETED:
                job.status = JobStatus.QUEUED
                job.scheduled_at = now

        db.commit()

        queues = db.query(Queue).filter(Queue.is_paused == False).all()
        for queue in queues:
            active = db.query(Job).filter(
                Job.queue_id == queue.id,
                Job.status.in_([JobStatus.CLAIMED, JobStatus.RUNNING]),
            ).count()
            if active >= queue.concurrency_limit:
                continue

            job = (
                db.query(Job)
                .filter(
                    Job.queue_id == queue.id,
                    Job.status.in_([JobStatus.QUEUED, JobStatus.RETRYING]),
                )
                .order_by(Job.priority.desc(), Job.created_at.asc())
                .with_for_update(skip_locked=True)
                .first()
            )
            if job:
                job.status = JobStatus.CLAIMED
                job.claimed_by_worker_id = self.worker_id
                job.claimed_at = now
                db.commit()
                return job.id
        return None

    async def execute_job(self, job_id: uuid.UUID):
        async with self.semaphore:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._run_job_sync, job_id)

    def _run_job_sync(self, job_id: uuid.UUID):
        with sync_session_factory() as db:
            job = db.get(Job, job_id)
            if not job or job.status != JobStatus.CLAIMED:
                return
            queue = db.query(Queue).options(joinedload(Queue.retry_policy)).filter(Queue.id == job.queue_id).first()
            if not queue:
                return

            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            attempt = job.retry_count + 1
            execution = JobExecution(
                job_id=job.id, worker_id=self.worker_id, attempt_number=attempt,
                status=ExecutionStatus.RUNNING, started_at=job.started_at,
            )
            db.add(execution)
            db.commit()
            db.refresh(execution)
            add_log(db, job.id, f"Execution attempt {attempt} started", LogLevel.INFO, execution.id)
            db.commit()

            try:
                result = self._process_payload(job.payload)
                complete_job_sync(db, job, execution, result)
                worker = db.get(Worker, self.worker_id)
                if worker:
                    worker.total_jobs_processed += 1
                db.commit()
                logger.info("Job %s completed", job_id)
            except Exception as e:
                logger.exception("Job %s failed", job_id)
                handle_failure_sync(db, job, queue, execution, str(e))
                db.commit()

    def _process_payload(self, payload: dict) -> dict:
        duration = payload.get("duration_seconds", 0.1)
        if payload.get("should_fail"):
            raise RuntimeError(payload.get("error_message", "Simulated failure"))
        time.sleep(min(duration, 5))
        return {"processed_at": datetime.now(timezone.utc).isoformat(), "status": "ok"}

    async def poll_loop(self):
        with sync_session_factory() as db:
            self.register_worker(db)
        last_hb = time.monotonic()

        while self.running:
            try:
                if time.monotonic() - last_hb >= settings.worker_heartbeat_interval:
                    with sync_session_factory() as db:
                        self.send_heartbeat(db)
                    last_hb = time.monotonic()

                with sync_session_factory() as db:
                    job_id = self.claim_job_atomic(db)

                if job_id:
                    task = asyncio.create_task(self.execute_job(job_id))
                    self.active_tasks.add(task)
                    task.add_done_callback(self.active_tasks.discard)
                else:
                    await asyncio.sleep(self.poll_interval)
            except Exception:
                logger.exception("Poll error")
                await asyncio.sleep(self.poll_interval)

    def shutdown(self):
        self.running = False
        with sync_session_factory() as db:
            if self.worker_id:
                w = db.get(Worker, self.worker_id)
                if w:
                    w.status = WorkerStatus.DRAINING
                    db.commit()

    def finalize(self):
        with sync_session_factory() as db:
            if self.worker_id:
                w = db.get(Worker, self.worker_id)
                if w:
                    w.status = WorkerStatus.OFFLINE
                    w.stopped_at = datetime.now(timezone.utc)
                    db.commit()


async def main():
    worker = JobWorker()
    try:
        await worker.poll_loop()
    except KeyboardInterrupt:
        worker.shutdown()
    finally:
        if worker.active_tasks:
            await asyncio.gather(*worker.active_tasks, return_exceptions=True)
        worker.finalize()


if __name__ == "__main__":
    asyncio.run(main())
