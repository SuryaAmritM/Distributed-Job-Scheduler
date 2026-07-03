"""Seed script for demo data. Run: python -m scripts.seed"""

import asyncio
import uuid

from sqlalchemy import select

from app.database import async_session_factory, init_db
from app.models import Organization, OrganizationMember, Project, Queue, RetryPolicy, User
from app.enums import UserRole, RetryStrategy
from app.auth import hash_password


async def seed():
    await init_db()
    async with async_session_factory() as db:
        result = await db.execute(select(User).where(User.email == "admin@example.com"))
        if result.scalar_one_or_none():
            print("Seed data already exists")
            return

        user = User(email="admin@example.com", hashed_password=hash_password("admin12345"), full_name="Admin User")
        org = Organization(name="Demo Organization", slug="demo")
        db.add_all([user, org])
        await db.flush()

        db.add(OrganizationMember(organization_id=org.id, user_id=user.id, role=UserRole.OWNER))
        project = Project(organization_id=org.id, name="Main Project", slug="main", description="Default project")
        db.add(project)
        await db.flush()

        policies = await db.execute(select(RetryPolicy))
        policy = policies.scalars().first()
        if not policy:
            policy = RetryPolicy(name="Exponential", strategy=RetryStrategy.EXPONENTIAL, max_retries=3, base_delay_seconds=30)
            db.add(policy)
            await db.flush()

        for name in ["default", "high-priority", "notifications"]:
            db.add(Queue(project_id=project.id, name=name, priority=10 if name == "high-priority" else 0, retry_policy_id=policy.id))

        await db.commit()
        print("Seed complete!")
        print("  Email: admin@example.com")
        print("  Password: admin12345")


if __name__ == "__main__":
    asyncio.run(seed())
