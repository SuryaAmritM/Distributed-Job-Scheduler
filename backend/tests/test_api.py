import pytest
from httpx import AsyncClient

from app.services.job_service import calculate_retry_delay
from app.enums import RetryStrategy
from app.models import RetryPolicy


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    res = await client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    res = await client.post("/api/v1/auth/register", json={
        "email": "user@test.com", "password": "password123", "full_name": "User",
    })
    assert res.status_code == 201

    res = await client.post("/api/v1/auth/login", json={
        "email": "user@test.com", "password": "password123",
    })
    assert res.status_code == 200
    assert "access_token" in res.json()


@pytest.mark.asyncio
async def test_create_immediate_job(client: AsyncClient, auth_headers):
    res = await client.post(
        f"/api/v1/queues/{auth_headers['queue_id']}/jobs",
        json={"job_type": "immediate", "payload": {"action": "test"}},
        headers=auth_headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "queued"
    assert data["job_type"] == "immediate"


@pytest.mark.asyncio
async def test_create_delayed_job(client: AsyncClient, auth_headers):
    res = await client.post(
        f"/api/v1/queues/{auth_headers['queue_id']}/jobs",
        json={"job_type": "delayed", "payload": {}, "delay_seconds": 60},
        headers=auth_headers,
    )
    assert res.status_code == 201
    assert res.json()["status"] == "scheduled"


@pytest.mark.asyncio
async def test_idempotency(client: AsyncClient, auth_headers):
    body = {"job_type": "immediate", "payload": {}, "idempotency_key": "unique-key-1"}
    res1 = await client.post(f"/api/v1/queues/{auth_headers['queue_id']}/jobs", json=body, headers=auth_headers)
    res2 = await client.post(f"/api/v1/queues/{auth_headers['queue_id']}/jobs", json=body, headers=auth_headers)
    assert res1.json()["id"] == res2.json()["id"]


@pytest.mark.asyncio
async def test_queue_pause_resume(client: AsyncClient, auth_headers):
    qid = auth_headers["queue_id"]
    res = await client.post(f"/api/v1/queues/{qid}/pause", headers=auth_headers)
    assert res.status_code == 200

    res = await client.get(f"/api/v1/queues/{qid}", headers=auth_headers)
    assert res.json()["is_paused"] is True

    res = await client.post(f"/api/v1/queues/{qid}/resume", headers=auth_headers)
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_list_jobs_pagination(client: AsyncClient, auth_headers):
    for _ in range(3):
        await client.post(
            f"/api/v1/queues/{auth_headers['queue_id']}/jobs",
            json={"job_type": "immediate", "payload": {}},
            headers=auth_headers,
        )
    res = await client.get(f"/api/v1/queues/{auth_headers['queue_id']}/jobs?page=1&page_size=2", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data["items"]) == 2
    assert data["total"] >= 3


def test_retry_delay_fixed():
    policy = RetryPolicy(strategy=RetryStrategy.FIXED, base_delay_seconds=60, max_delay_seconds=3600, multiplier=2.0)
    assert calculate_retry_delay(policy, 1) == 60
    assert calculate_retry_delay(policy, 3) == 60


def test_retry_delay_exponential():
    policy = RetryPolicy(strategy=RetryStrategy.EXPONENTIAL, base_delay_seconds=60, max_delay_seconds=3600, multiplier=2.0)
    assert calculate_retry_delay(policy, 1) == 60
    assert calculate_retry_delay(policy, 2) == 120
    assert calculate_retry_delay(policy, 3) == 240


def test_retry_delay_linear():
    policy = RetryPolicy(strategy=RetryStrategy.LINEAR, base_delay_seconds=30, max_delay_seconds=3600, multiplier=2.0)
    assert calculate_retry_delay(policy, 2) == 60
    assert calculate_retry_delay(policy, 4) == 120
