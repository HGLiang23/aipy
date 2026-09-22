# Database migrations

Run the initial migration against PostgreSQL 16+:

```powershell
$env:AIPY_DATABASE_URL = "postgresql+psycopg://migration_owner:...@localhost/aipy"
alembic -c migrations/alembic.ini upgrade head
```

The migration owner and application runtime role must be different. The runtime role must be
`NOSUPERUSER NOBYPASSRLS`, must not own application tables, and receives only the DML grants
needed by the application. Role creation and credentials are deployment responsibilities, so
the migration intentionally does not create or alter roles.

RLS integration tests require both URLs and never fall back to SQLite:

```powershell
$env:AIPY_TEST_DATABASE_ADMIN_URL = "postgresql+psycopg://migration_owner:...@localhost/aipy"
$env:AIPY_TEST_DATABASE_RUNTIME_URL = "postgresql+psycopg://aipy_runtime:...@localhost/aipy"
pytest tests/integration/test_tenant_rls.py
```

Grant the runtime role `USAGE` on the application schema and the required `SELECT`, `INSERT`,
`UPDATE`, and `DELETE` privileges after migration. Every request or worker transaction must set
`app.tenant_id` with `set_config(..., true)` before tenant data is accessed.
