# AIPY

AIPY is a multi-tenant AI content workflow platform. The repository contains a working
vertical slice: tenant-scoped content runs, the human review queue, and the source
library, each with a real write path - create, run, export and download included.

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

Apply migrations and load the demo tenant:

```powershell
python scripts/seed_dev.py
```

Run the API:

```powershell
python -m uvicorn apps.api.main:app --reload
```

Run a Celery worker:

```powershell
python -m celery -A apps.worker.celery_app:celery_app worker --loglevel=INFO
```

The demo login is `editor@example.com` / `demo-password`.

## Health endpoints

- `GET /health/live` reports whether the API process is alive.
- `GET /health/ready` runs a `SELECT 1` against PostgreSQL and a `PING` against Redis, and
  answers `503 not_ready` when either fails. Both are registered by default; pass an
  explicit `readiness_checks` mapping to `create_app` to replace them (tests do this).

## API surface

`openapi/openapi.yaml` is a hand-maintained contract draft and is not generated from the
app. The authoritative route list is whatever `create_app().openapi()` returns; see
`docs/adr/` for the decisions behind each group.

- `POST /api/v1/auth/{login,refresh,logout}`, `GET /api/v1/me`
- `GET|POST /api/v1/workflow-runs`, `GET /api/v1/workflow-runs/counts`
- `GET /api/v1/workflow-runs/{id}`, `POST .../{id}/actions`
- `GET .../{id}/exports`, `GET .../{id}/exports/{export_id}/download`
- `POST .../{id}/materials/{material_id}`
- `GET /api/v1/human-tasks`, `GET /api/v1/human-tasks/counts`, `POST .../{id}/actions`
- `GET|POST /api/v1/materials`, `POST /api/v1/materials/upload`, `GET .../{id}/file`

## Quality checks

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest
```

Detailed architecture and delivery decisions are maintained in [`docs/`](docs/README.md).

