# AIPY

AIPY is a multi-tenant AI content workflow platform. The current repository contains the
MVP engineering skeleton only; business modules and workflow behavior are implemented in
later milestones.

## Requirements

- Python 3.12
- PostgreSQL
- Redis

## Local setup

Create and activate a Python 3.12 virtual environment, then install the project with its
development dependencies:

```powershell
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Run the API:

```powershell
python -m uvicorn apps.api.main:app --reload
```

Run a Celery worker:

```powershell
python -m celery -A apps.worker.celery_app:celery_app worker --loglevel=INFO
```

## Health endpoints

- `GET /health/live` reports whether the API process is alive.
- `GET /health/ready` reports whether application initialization is complete.

Dependency probes will be added when the database and Redis infrastructure adapters are
introduced. Until then, readiness intentionally covers application initialization only.

## Quality checks

```powershell
python -m ruff check .
python -m mypy
python -m pytest
```

Detailed architecture and delivery decisions are maintained in [`docs/`](docs/README.md).

