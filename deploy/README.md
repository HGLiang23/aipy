# Local deployment

The Compose project provides PostgreSQL 16, Redis 7, and MinIO with persistent named
volumes and health checks. Application containers are optional so developers can run the
API and worker on the host while keeping dependencies in containers.

## Configure

Create `deploy/.env` from `deploy/.env.example` and replace every placeholder password.
The file is ignored by Git. Production credentials must come from the deployment
platform's secret manager rather than an environment file committed to this repository.

## Start infrastructure

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d
```

## Start the complete application

The `application` profile runs the database migration once, then starts the API and
Celery worker:

```powershell
docker compose --env-file deploy/.env -f deploy/compose.yaml --profile application up -d --build
```

The API is available at `http://localhost:8000`; the MinIO console is available at
`http://localhost:9001` with the credentials from `deploy/.env`.

Use `scripts/dev/infrastructure.ps1` for the same common operations from PowerShell.
The script intentionally does not delete named volumes.

