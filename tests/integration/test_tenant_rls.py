"""PostgreSQL-only integration checks for tenant RLS.

Required environment:

* ``AIPY_TEST_DATABASE_ADMIN_URL`` points to the migrated database using the
  migration owner (or another role able to create fixture rows).
* ``AIPY_TEST_DATABASE_RUNTIME_URL`` points to the same database using the
  application runtime role. That role must have DML grants, must not own the
  tables, and must be non-superuser without ``BYPASSRLS``.

The test is skipped when either URL is absent. A configured non-PostgreSQL URL
is rejected; SQLite is never used as a substitute for RLS testing.

Before running this module, apply the Alembic migration and grant the runtime
role ``SELECT, INSERT, UPDATE, DELETE`` on the migrated tables. The migration
owner and runtime role must resolve to different PostgreSQL roles.
"""

import os
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import DBAPIError

from aipy.shared.db import new_uuid7

ADMIN_URL = os.getenv("AIPY_TEST_DATABASE_ADMIN_URL")
RUNTIME_URL = os.getenv("AIPY_TEST_DATABASE_RUNTIME_URL")

pytestmark = pytest.mark.skipif(
    not ADMIN_URL or not RUNTIME_URL,
    reason=(
        "requires migrated PostgreSQL URLs for an admin/migration role and a distinct "
        "non-BYPASSRLS runtime role"
    ),
)

RLS_TABLES = (
    "tenant",
    "tenant_subscription",
    "tenant_membership",
    "team",
    "team_member",
    "workspace",
    "brand",
)


def _postgres_engine(url: str | None) -> Engine:
    assert url is not None
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise AssertionError("RLS integration tests require PostgreSQL; SQLite is unsupported")
    return create_engine(url, pool_pre_ping=True)


def _set_tenant(connection: Connection, tenant_id: UUID) -> None:
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def _insert_tenant_fixture(
    connection: Connection,
    *,
    tenant_id: UUID,
    plan_id: UUID,
    team_id: UUID,
    suffix: str,
) -> None:
    _set_tenant(connection, tenant_id)
    connection.execute(
        text(
            """
            INSERT INTO tenant (
                id, code, name, status, timezone, locale, data_region, plan_id
            ) VALUES (
                :id, :code, :name, 'ACTIVE', 'Asia/Shanghai', 'zh-CN', 'CN', :plan_id
            )
            """
        ),
        {
            "id": tenant_id,
            "code": f"rls-{suffix}",
            "name": f"RLS tenant {suffix}",
            "plan_id": plan_id,
        },
    )
    connection.execute(
        text(
            """
            INSERT INTO team (id, tenant_id, code, name, status)
            VALUES (:id, :tenant_id, :code, :name, 'ACTIVE')
            """
        ),
        {
            "id": team_id,
            "tenant_id": tenant_id,
            "code": f"team-{suffix}",
            "name": f"Team {suffix}",
        },
    )


def test_runtime_role_is_tenant_isolated_for_reads_and_writes() -> None:
    admin_engine = _postgres_engine(ADMIN_URL)
    runtime_engine = _postgres_engine(RUNTIME_URL)
    plan_id = new_uuid7()
    tenant_a = new_uuid7()
    tenant_b = new_uuid7()
    team_a = new_uuid7()
    team_b = new_uuid7()
    rejected_team = new_uuid7()
    rejected_child_team = new_uuid7()
    suffix = plan_id.hex
    schema_ready = False

    try:
        with admin_engine.begin() as admin:
            migrated = admin.scalar(text("SELECT to_regclass('public.team') IS NOT NULL"))
            assert migrated, "run `alembic -c migrations/alembic.ini upgrade head` first"
            schema_ready = True

            rls_settings = admin.execute(
                text(
                    """
                    SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relname = ANY(:table_names)
                    ORDER BY c.relname
                    """
                ),
                {"table_names": list(RLS_TABLES)},
            ).all()
            assert {row.relname for row in rls_settings} == set(RLS_TABLES)
            assert all(row.relrowsecurity and row.relforcerowsecurity for row in rls_settings)

            admin.execute(
                text(
                    """
                    INSERT INTO plan (
                        id, code, name, status, max_users, max_workspaces,
                        max_daily_articles
                    ) VALUES (:id, :code, 'RLS test', 'ACTIVE', 10, 3, 100)
                    """
                ),
                {"id": plan_id, "code": f"rls-plan-{suffix}"},
            )
            _insert_tenant_fixture(
                admin,
                tenant_id=tenant_a,
                plan_id=plan_id,
                team_id=team_a,
                suffix=f"a-{suffix}",
            )
            _insert_tenant_fixture(
                admin,
                tenant_id=tenant_b,
                plan_id=plan_id,
                team_id=team_b,
                suffix=f"b-{suffix}",
            )

        with runtime_engine.begin() as runtime:
            runtime_user = runtime.scalar(text("SELECT current_user"))
            role = runtime.execute(
                text(
                    """
                    SELECT r.rolsuper,
                           r.rolbypassrls,
                           r.oid = c.relowner AS owns_team,
                           has_table_privilege(current_user, 'team', 'SELECT')
                               AS has_select,
                           has_table_privilege(current_user, 'team', 'INSERT')
                               AS has_insert
                    FROM pg_roles r
                    CROSS JOIN pg_class c
                    WHERE r.rolname = current_user
                      AND c.oid = 'public.team'::regclass
                    """
                )
            ).one()
            assert not role.rolsuper
            assert not role.rolbypassrls
            assert not role.owns_team
            assert role.has_select
            assert role.has_insert

            with admin_engine.connect() as admin:
                assert admin.scalar(text("SELECT current_user")) != runtime_user

            _set_tenant(runtime, tenant_a)
            assert runtime.scalars(text("SELECT id FROM tenant ORDER BY id")).all() == [tenant_a]
            assert runtime.scalars(text("SELECT id FROM team ORDER BY id")).all() == [team_a]

            with pytest.raises(DBAPIError) as rls_error, runtime.begin_nested():
                runtime.execute(
                    text(
                        """
                            INSERT INTO team (id, tenant_id, code, name, status)
                            VALUES (:id, :tenant_id, :code, 'Rejected', 'ACTIVE')
                            """
                    ),
                    {
                        "id": rejected_team,
                        "tenant_id": tenant_b,
                        "code": f"rejected-{suffix}",
                    },
                )
            assert "row-level security" in str(rls_error.value).lower()

            # RLS permits this tenant_id, but the composite FK must reject a
            # parent team that belongs to another tenant.
            with pytest.raises(DBAPIError), runtime.begin_nested():
                runtime.execute(
                    text(
                        """
                        INSERT INTO team (
                            id, tenant_id, parent_team_id, code, name, status
                        ) VALUES (
                            :id, :tenant_id, :parent_team_id, :code, 'Rejected child', 'ACTIVE'
                        )
                        """
                    ),
                    {
                        "id": rejected_child_team,
                        "tenant_id": tenant_a,
                        "parent_team_id": team_b,
                        "code": f"rejected-child-{suffix}",
                    },
                )

        # SET LOCAL must not survive transaction completion or pooled
        # connection reuse. Missing context is fail-closed, not an error.
        with runtime_engine.begin() as runtime:
            assert runtime.scalar(text("SELECT count(*) FROM tenant")) == 0
            assert runtime.scalar(text("SELECT count(*) FROM team")) == 0

            _set_tenant(runtime, tenant_b)
            assert runtime.scalars(text("SELECT id FROM tenant ORDER BY id")).all() == [tenant_b]
            assert runtime.scalars(text("SELECT id FROM team ORDER BY id")).all() == [team_b]
    finally:
        if schema_ready:
            with admin_engine.begin() as admin:
                for tenant_id in (tenant_a, tenant_b):
                    _set_tenant(admin, tenant_id)
                    admin.execute(text("DELETE FROM team WHERE tenant_id = :id"), {"id": tenant_id})
                    admin.execute(text("DELETE FROM tenant WHERE id = :id"), {"id": tenant_id})
                admin.execute(text("DELETE FROM plan WHERE id = :id"), {"id": plan_id})
        runtime_engine.dispose()
        admin_engine.dispose()
