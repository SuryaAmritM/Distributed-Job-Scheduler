import math
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, hash_password, verify_password, create_access_token
from app.database import get_db
from app.enums import JobStatus, UserRole
from app.models import (
    DeadLetterEntry, Job, JobExecution, Organization, OrganizationMember,
    Project, Queue, RetryPolicy, User, Worker,
)
from app.schemas import (
    BatchJobCreate, DLQEntryResponse, JobCreate, JobDetailResponse, JobResponse,
    OrganizationCreate, OrganizationResponse, PaginatedResponse, ProjectCreate,
    ProjectResponse, ProjectUpdate, QueueCreate, QueueResponse, QueueStats,
    QueueUpdate, RetryPolicyCreate, RetryPolicyResponse, SystemMetrics,
    TokenResponse, UserLogin, UserRegister, UserResponse, WorkerResponse,
)
from app.services.job_service import create_job, get_queue_stats, retry_dlq_job

router = APIRouter(prefix="/api/v1")


def paginate(total: int, page: int, page_size: int) -> dict:
    return {"total": total, "page": page, "page_size": page_size, "pages": max(1, math.ceil(total / page_size))}


# ── Auth ──────────────────────────────────────────────────────────────────

@router.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    user = User(email=data.email, hashed_password=hash_password(data.password), full_name=data.full_name)
    db.add(user)
    await db.flush()

    slug_base = data.email.split("@")[0].lower().replace(".", "-")[:50]
    org = Organization(name=f"{data.full_name}'s Organization", slug=f"{slug_base}-org")
    db.add(org)
    await db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=UserRole.OWNER))
    project = Project(organization_id=org.id, name="Default Project", slug="default")
    db.add(project)
    await db.flush()

    policy = (await db.execute(select(RetryPolicy).limit(1))).scalar_one_or_none()
    db.add(Queue(project_id=project.id, name="default", retry_policy_id=policy.id if policy else None))

    return user


@router.post("/auth/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.get("/auth/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


# ── Organizations ─────────────────────────────────────────────────────────

@router.post("/organizations", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    data: OrganizationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(Organization).where(Organization.slug == data.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Slug already taken")

    org = Organization(name=data.name, slug=data.slug)
    db.add(org)
    await db.flush()
    db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=UserRole.OWNER))
    return org


@router.get("/organizations", response_model=list[OrganizationResponse])
async def list_organizations(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
    )
    return result.scalars().all()


# ── Projects ──────────────────────────────────────────────────────────────

@router.post("/organizations/{org_id}/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    org_id: uuid.UUID,
    data: ProjectCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await _check_membership(db, org_id, user.id)
    if membership.role == UserRole.VIEWER:
        raise HTTPException(403, "Viewers cannot create projects")

    project = Project(organization_id=org_id, name=data.name, slug=data.slug, description=data.description)
    db.add(project)
    await db.flush()
    return project


@router.get("/organizations/{org_id}/projects", response_model=list[ProjectResponse])
async def list_projects(
    org_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_membership(db, org_id, user.id)
    result = await db.execute(select(Project).where(Project.organization_id == org_id))
    return result.scalars().all()


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    project = await _get_project_with_access(db, project_id, user.id)
    return project


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_with_access(db, project_id, user.id, write=True)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    return project


# ── Retry Policies ────────────────────────────────────────────────────────

@router.post("/retry-policies", response_model=RetryPolicyResponse, status_code=201)
async def create_retry_policy(data: RetryPolicyCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    policy = RetryPolicy(**data.model_dump())
    db.add(policy)
    await db.flush()
    return policy


@router.get("/retry-policies", response_model=list[RetryPolicyResponse])
async def list_retry_policies(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RetryPolicy))
    return result.scalars().all()


# ── Queues ────────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/queues", response_model=QueueResponse, status_code=201)
async def create_queue(
    project_id: uuid.UUID,
    data: QueueCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_with_access(db, project_id, user.id, write=True)
    queue = Queue(project_id=project_id, **data.model_dump())
    db.add(queue)
    await db.flush()
    stats = await get_queue_stats(db, queue.id)
    return QueueResponse(**{c.name: getattr(queue, c.name) for c in queue.__table__.columns}, stats=QueueStats(**stats))


@router.get("/projects/{project_id}/queues", response_model=list[QueueResponse])
async def list_queues(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_project_with_access(db, project_id, user.id)
    result = await db.execute(
        select(Queue).where(Queue.project_id == project_id).order_by(Queue.priority.desc())
    )
    queues = result.scalars().all()
    response = []
    for q in queues:
        stats = await get_queue_stats(db, q.id)
        response.append(QueueResponse(
            id=q.id, project_id=q.project_id, name=q.name, description=q.description,
            priority=q.priority, concurrency_limit=q.concurrency_limit, is_paused=q.is_paused,
            retry_policy_id=q.retry_policy_id, rate_limit_per_minute=q.rate_limit_per_minute,
            created_at=q.created_at, stats=QueueStats(**stats),
        ))
    return response


@router.get("/queues/{queue_id}", response_model=QueueResponse)
async def get_queue(queue_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    queue = await _get_queue_with_access(db, queue_id, user.id)
    stats = await get_queue_stats(db, queue.id)
    return QueueResponse(
        id=queue.id, project_id=queue.project_id, name=queue.name, description=queue.description,
        priority=queue.priority, concurrency_limit=queue.concurrency_limit, is_paused=queue.is_paused,
        retry_policy_id=queue.retry_policy_id, rate_limit_per_minute=queue.rate_limit_per_minute,
        created_at=queue.created_at, stats=QueueStats(**stats),
    )


@router.patch("/queues/{queue_id}", response_model=QueueResponse)
async def update_queue(
    queue_id: uuid.UUID,
    data: QueueUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    queue = await _get_queue_with_access(db, queue_id, user.id, write=True)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(queue, field, value)
    stats = await get_queue_stats(db, queue.id)
    return QueueResponse(
        id=queue.id, project_id=queue.project_id, name=queue.name, description=queue.description,
        priority=queue.priority, concurrency_limit=queue.concurrency_limit, is_paused=queue.is_paused,
        retry_policy_id=queue.retry_policy_id, rate_limit_per_minute=queue.rate_limit_per_minute,
        created_at=queue.created_at, stats=QueueStats(**stats),
    )


@router.post("/queues/{queue_id}/pause")
async def pause_queue(queue_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    queue = await _get_queue_with_access(db, queue_id, user.id, write=True)
    queue.is_paused = True
    return {"status": "paused"}


@router.post("/queues/{queue_id}/resume")
async def resume_queue(queue_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    queue = await _get_queue_with_access(db, queue_id, user.id, write=True)
    queue.is_paused = False
    return {"status": "resumed"}


# ── Jobs ──────────────────────────────────────────────────────────────────

@router.post("/queues/{queue_id}/jobs", response_model=JobResponse, status_code=201)
async def create_single_job(
    queue_id: uuid.UUID,
    data: JobCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    queue = await _get_queue_with_access(db, queue_id, user.id, write=True)
    try:
        job = await create_job(
            db, queue, data.job_type, data.payload,
            priority=data.priority, scheduled_at=data.scheduled_at,
            delay_seconds=data.delay_seconds, cron_expression=data.cron_expression,
            idempotency_key=data.idempotency_key, max_retries=data.max_retries,
            depends_on_job_id=data.depends_on_job_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return job


@router.post("/queues/{queue_id}/jobs/batch", response_model=list[JobResponse], status_code=201)
async def create_batch_jobs(
    queue_id: uuid.UUID,
    data: BatchJobCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.enums import JobType

    queue = await _get_queue_with_access(db, queue_id, user.id, write=True)
    batch_id = uuid.uuid4()
    jobs = []
    for item in data.jobs:
        job = await create_job(
            db, queue, JobType.BATCH, item.payload,
            priority=item.priority, scheduled_at=item.scheduled_at,
            delay_seconds=item.delay_seconds, batch_id=batch_id,
            idempotency_key=item.idempotency_key,
        )
        jobs.append(job)
    return jobs


@router.get("/queues/{queue_id}/jobs", response_model=PaginatedResponse[JobResponse])
async def list_jobs(
    queue_id: uuid.UUID,
    status_filter: JobStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_queue_with_access(db, queue_id, user.id)
    query = select(Job).where(Job.queue_id == queue_id)
    if status_filter:
        query = query.where(Job.status == status_filter)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(
        query.order_by(Job.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return PaginatedResponse(
        items=result.scalars().all(),
        **paginate(total, page, page_size),
    )


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Job)
        .options(
            selectinload(Job.executions),
            selectinload(Job.logs),
            selectinload(Job.retry_history),
        )
        .where(Job.id == job_id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")
    await _get_queue_with_access(db, job.queue_id, user.id)
    return job


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    await _get_queue_with_access(db, job.queue_id, user.id, write=True)
    if job.status in (JobStatus.COMPLETED, JobStatus.DEAD_LETTER, JobStatus.CANCELLED):
        raise HTTPException(400, "Job cannot be cancelled")
    job.status = JobStatus.CANCELLED
    return {"status": "cancelled"}


# ── DLQ ───────────────────────────────────────────────────────────────────

@router.get("/queues/{queue_id}/dlq", response_model=PaginatedResponse[DLQEntryResponse])
async def list_dlq(
    queue_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_queue_with_access(db, queue_id, user.id)
    query = select(DeadLetterEntry).where(DeadLetterEntry.queue_id == queue_id, DeadLetterEntry.retried == False)
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0
    result = await db.execute(query.order_by(DeadLetterEntry.moved_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return PaginatedResponse(items=result.scalars().all(), **paginate(total, page, page_size))


@router.post("/dlq/{dlq_id}/retry", response_model=JobResponse)
async def retry_from_dlq(dlq_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    dlq = await db.get(DeadLetterEntry, dlq_id)
    if not dlq:
        raise HTTPException(404, "DLQ entry not found")
    await _get_queue_with_access(db, dlq.queue_id, user.id, write=True)
    try:
        job = await retry_dlq_job(db, dlq_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return job


# ── Workers ───────────────────────────────────────────────────────────────

@router.get("/workers", response_model=list[WorkerResponse])
async def list_workers(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Worker).order_by(Worker.started_at.desc()))
    return result.scalars().all()


# ── Metrics ───────────────────────────────────────────────────────────────

@router.get("/metrics", response_model=SystemMetrics)
async def system_metrics(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timedelta, timezone
    from app.enums import WorkerStatus

    status_result = await db.execute(select(Job.status, func.count(Job.id)).group_by(Job.status))
    jobs_by_status = {s.value: c for s, c in status_result.all()}

    workers_result = await db.execute(
        select(func.count(Worker.id)).where(Worker.status == WorkerStatus.ONLINE)
    )
    active_workers = workers_result.scalar() or 0

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    throughput_result = await db.execute(
        select(func.count(Job.id)).where(Job.status == JobStatus.COMPLETED, Job.completed_at >= one_hour_ago)
    )
    dlq_result = await db.execute(select(func.count(DeadLetterEntry.id)).where(DeadLetterEntry.retried == False))
    avg_result = await db.execute(
        select(func.avg(JobExecution.duration_ms)).where(JobExecution.duration_ms.isnot(None))
    )

    return SystemMetrics(
        total_jobs=sum(jobs_by_status.values()),
        jobs_by_status=jobs_by_status,
        active_workers=active_workers,
        throughput_last_hour=float(throughput_result.scalar() or 0),
        avg_duration_ms=float(avg_result.scalar() or 0),
        dlq_count=dlq_result.scalar() or 0,
    )


# ── Helpers ───────────────────────────────────────────────────────────────

async def _check_membership(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> OrganizationMember:
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id,
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(403, "Not a member of this organization")
    return membership


async def _get_project_with_access(
    db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID, write: bool = False
) -> Project:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    membership = await _check_membership(db, project.organization_id, user_id)
    if write and membership.role == UserRole.VIEWER:
        raise HTTPException(403, "Insufficient permissions")
    return project


async def _get_queue_with_access(
    db: AsyncSession, queue_id: uuid.UUID, user_id: uuid.UUID, write: bool = False
) -> Queue:
    queue = await db.get(Queue, queue_id)
    if not queue:
        raise HTTPException(404, "Queue not found")
    await _get_project_with_access(db, queue.project_id, user_id, write=write)
    return queue
