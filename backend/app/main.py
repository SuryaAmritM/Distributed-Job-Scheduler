import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.database import init_db
from app.models import RetryPolicy
from app.enums import RetryStrategy
from app.database import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed_default_retry_policies():
    async with async_session_factory() as db:
        from sqlalchemy import select
        result = await db.execute(select(RetryPolicy).limit(1))
        if result.scalar_one_or_none():
            return
        defaults = [
            RetryPolicy(name="Fixed 60s", strategy=RetryStrategy.FIXED, max_retries=3, base_delay_seconds=60),
            RetryPolicy(name="Linear Backoff", strategy=RetryStrategy.LINEAR, max_retries=5, base_delay_seconds=30),
            RetryPolicy(name="Exponential Backoff", strategy=RetryStrategy.EXPONENTIAL, max_retries=5, base_delay_seconds=60, multiplier=2.0),
        ]
        for p in defaults:
            db.add(p)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_default_retry_policies()
    logger.info("Database initialized")
    yield


app = FastAPI(
    title="Distributed Job Scheduler",
    description="Production-inspired distributed job scheduling platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
async def health():
    return {"status": "healthy"}
