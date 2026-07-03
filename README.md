# Distributed Job Scheduler

A production-inspired distributed job scheduling platform with REST APIs, PostgreSQL persistence, worker-based execution, and a React dashboard.

## Architecture

```
┌──────────────┐     REST/JSON      ┌──────────────┐
│   React      │◄──────────────────►│   FastAPI    │
│  Dashboard   │                    │     API      │
└──────────────┘                    └──────┬───────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                      │
              ┌─────▼─────┐         ┌──────▼──────┐        ┌──────▼──────┐
              │ PostgreSQL │         │    Redis    │        │   Worker    │
              │  (primary) │         │  (optional) │        │   Service   │
              └───────────┘         └─────────────┘        └─────────────┘
```

## Quick Start (Docker)

```bash
docker compose up --build
```

| Service  | URL                        |
|----------|----------------------------|
| API      | http://localhost:8000      |
| API Docs | http://localhost:8000/docs |
| Dashboard| http://localhost:5173      |

### Seed Demo Data

```bash
docker compose exec api python -m scripts.seed
```

Login: `admin@example.com` / `admin12345`

## Local Development

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16+
- Redis 7+ (optional)

### Backend

```bash
cd backend
pip install -r requirements.txt

# Set environment
export DATABASE_URL=postgresql+asyncpg://scheduler:scheduler@localhost:5432/job_scheduler
export DATABASE_URL_SYNC=postgresql://scheduler:scheduler@localhost:5432/job_scheduler

python -m scripts.seed
uvicorn app.main:app --reload
```

### Worker

```bash
cd backend
python -m app.worker.main
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
pytest -v
```

## Features

- **Authentication** — JWT-based auth with organization/project RBAC
- **Queue Management** — Priority, concurrency limits, pause/resume, statistics
- **Job Types** — Immediate, delayed, scheduled, recurring (cron), batch
- **Worker Service** — Atomic job claiming (`FOR UPDATE SKIP LOCKED`), concurrent execution, heartbeats, graceful shutdown
- **Job Lifecycle** — Queued → Scheduled → Claimed → Running → Completed/Failed → DLQ
- **Retry Strategies** — Fixed delay, linear backoff, exponential backoff
- **Observability** — Execution logs, retry history, worker assignment, metrics API
- **Dashboard** — Queue health, job explorer, worker monitor, live polling updates

## Bonus Features Implemented

- Workflow dependencies (`depends_on_job_id`)
- Rate limiting configuration per queue
- Role-based access control (owner/admin/member/viewer)

## Documentation

- [Architecture Diagram](docs/architecture.md)
- [ER Diagram](docs/er-diagram.md)
- [API Documentation](docs/api.md)
- [Design Decisions](docs/design-decisions.md)

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── api/          # REST route handlers
│   │   ├── services/     # Business logic
│   │   ├── worker/       # Worker polling & execution
│   │   ├── models.py     # SQLAlchemy ORM models
│   │   └── main.py       # FastAPI application
│   ├── tests/
│   └── scripts/seed.py
├── frontend/             # React dashboard
├── docs/                 # Architecture, ER, API, design docs
└── docker-compose.yml
```
