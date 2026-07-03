import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.models import Base, Organization, OrganizationMember, Project, Queue, RetryPolicy, User
from app.enums import RetryStrategy, UserRole
from app.auth import hash_password
from app.database import get_db

TEST_DB = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(db_session):
    user = User(email="test@example.com", hashed_password=hash_password("password123"), full_name="Test User")
    org = Organization(name="Test Org", slug="test-org")
    db_session.add_all([user, org])
    await db_session.flush()

    db_session.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=UserRole.OWNER))
    project = Project(organization_id=org.id, name="Test Project", slug="test-project")
    db_session.add(project)
    await db_session.flush()

    policy = RetryPolicy(name="Test Fixed", strategy=RetryStrategy.FIXED, max_retries=2, base_delay_seconds=1)
    db_session.add(policy)
    await db_session.flush()

    queue = Queue(project_id=project.id, name="default", retry_policy_id=policy.id)
    db_session.add(queue)
    await db_session.commit()

    from app.auth import create_access_token
    token = create_access_token({"sub": str(user.id)})

    return {
        "Authorization": f"Bearer {token}",
        "queue_id": str(queue.id),
        "project_id": str(project.id),
        "org_id": str(org.id),
    }
