from datetime import datetime
from typing import Any, Generic, Optional, TypeVar
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.enums import (
    ExecutionStatus, JobStatus, JobType, LogLevel, RetryStrategy,
    UserRole, WorkerStatus,
)

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


class ErrorResponse(BaseModel):
    detail: str
    code: Optional[str] = None


# Auth
class UserRegister(BaseModel):
    email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)


class UserLogin(BaseModel):
    email: str = Field(pattern=r"^[^@]+@[^@]+\.[^@]+$")
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime


# Organization
class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime


# Project
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    is_active: bool
    created_at: datetime


# Retry Policy
class RetryPolicyCreate(BaseModel):
    name: str
    strategy: RetryStrategy
    max_retries: int = Field(default=3, ge=0, le=20)
    base_delay_seconds: int = Field(default=60, ge=1)
    max_delay_seconds: int = Field(default=3600, ge=1)
    multiplier: float = Field(default=2.0, ge=1.0)


class RetryPolicyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    strategy: RetryStrategy
    max_retries: int
    base_delay_seconds: int
    max_delay_seconds: int
    multiplier: float


# Queue
class QueueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    priority: int = Field(default=0, ge=0, le=100)
    concurrency_limit: int = Field(default=10, ge=1, le=1000)
    retry_policy_id: Optional[uuid.UUID] = None
    rate_limit_per_minute: Optional[int] = Field(default=None, ge=1)


class QueueUpdate(BaseModel):
    description: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=0, le=100)
    concurrency_limit: Optional[int] = Field(default=None, ge=1, le=1000)
    retry_policy_id: Optional[uuid.UUID] = None
    rate_limit_per_minute: Optional[int] = None
    is_paused: Optional[bool] = None


class QueueStats(BaseModel):
    total_jobs: int = 0
    queued: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    dead_letter: int = 0
    throughput_per_hour: float = 0.0


class QueueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: Optional[str]
    priority: int
    concurrency_limit: int
    is_paused: bool
    retry_policy_id: Optional[uuid.UUID]
    rate_limit_per_minute: Optional[int]
    created_at: datetime
    stats: Optional[QueueStats] = None


# Job
class JobCreate(BaseModel):
    job_type: JobType
    payload: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0, le=100)
    scheduled_at: Optional[datetime] = None
    delay_seconds: Optional[int] = Field(default=None, ge=0)
    cron_expression: Optional[str] = None
    idempotency_key: Optional[str] = None
    max_retries: Optional[int] = Field(default=None, ge=0, le=20)
    depends_on_job_id: Optional[uuid.UUID] = None


class BatchJobCreate(BaseModel):
    jobs: list[JobCreate] = Field(min_length=1, max_length=100)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    queue_id: uuid.UUID
    batch_id: Optional[uuid.UUID]
    job_type: JobType
    status: JobStatus
    priority: int
    payload: dict
    result: Optional[dict]
    error_message: Optional[str]
    scheduled_at: Optional[datetime]
    cron_expression: Optional[str]
    retry_count: int
    claimed_by_worker_id: Optional[uuid.UUID]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime


class JobExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    worker_id: Optional[uuid.UUID]
    attempt_number: int
    status: ExecutionStatus
    started_at: datetime
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    error_message: Optional[str]
    result: Optional[dict]


class JobLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    level: LogLevel
    message: str
    created_at: datetime


class RetryHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    attempt_number: int
    error_message: Optional[str]
    retry_after_seconds: int
    retried_at: datetime


class JobDetailResponse(JobResponse):
    executions: list[JobExecutionResponse] = []
    logs: list[JobLogResponse] = []
    retry_history: list[RetryHistoryResponse] = []


class DLQEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    queue_id: uuid.UUID
    failure_reason: str
    final_error: Optional[str]
    total_attempts: int
    moved_at: datetime
    retried: bool


# Worker
class WorkerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    hostname: str
    pid: int
    status: WorkerStatus
    concurrency: int
    active_jobs: int
    total_jobs_processed: int
    last_heartbeat_at: Optional[datetime]
    started_at: datetime


# Metrics
class SystemMetrics(BaseModel):
    total_jobs: int
    jobs_by_status: dict[str, int]
    active_workers: int
    throughput_last_hour: float
    avg_duration_ms: float
    dlq_count: int
