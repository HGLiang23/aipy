"""Fix missing RLS policies on role / role_permission and seed built-in roles.

Revision ID: 20260924_0012_fix_role_rls
Revises: 20260924_0011_quotas
Create Date: 2026-09-24 16:05:00

Background
----------
Migration ``20260924_0006_rbac_tables`` enabled FORCE ROW LEVEL SECURITY on both
``role`` and ``role_permission`` but never created the isolation policies. With
FORCE RLS and zero policies, PostgreSQL denies *all* access for non-superusers, so:

* ``SELECT /api/v1/roles`` always returned an empty list, and
* every ``PUT /api/v1/roles/{id}`` could never find a row to update.

That migration also seeded the built-in roles with ``INSERT ... SELECT FROM tenant``,
which silently inserted nothing because ``tenant`` is itself FORCE-RLS protected and
returned zero rows outside a tenant context.

This revision fixes both problems:

1. Creates the missing tenant-isolation policies.
2. Re-seeds the built-in roles and permissions using a direct literal tenant scan
   with RLS temporarily disabled (the same technique used by ``0011_quotas``).
3. Rebinds members that have a NULL ``role_id`` to the tenant's admin role.
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_0012_fix_role_rls"
down_revision: str | None = "20260924_0011_quotas"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_EXPR = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# (code, name, description, is_default, permission codes, data scope)
_ROLES: list[tuple[str, str, str, bool, list[str], str]] = [
    (
        "admin", "租户管理员",
        "拥有租户内全部功能权限与全量数据范围，可管理成员、角色与系统配置。", True,
        [
            "batch:view", "batch:create", "content:view", "content:create", "content:edit",
            "content:assign", "artifact:view", "artifact:edit", "artifact:compare",
            "source:view", "source:create", "source:edit", "source:collect",
            "workflow:view", "workflow:configure", "workflow:execute", "review:view",
            "review:claim", "review:approve", "review:reject", "review:reassign",
            "publication:view", "publication:preview", "publication:export",
            "model:view", "model:configure", "model:credential_manage",
            "quota:view", "quota:configure", "member:view", "member:manage",
            "role:view", "role:manage", "audit:view",
        ],
        "TENANT_ALL",
    ),
    (
        "editor", "内容编辑",
        "负责选题、写作与内容产出，可执行工作流但不能改动系统配置。", False,
        [
            "batch:view", "batch:create", "content:view", "content:create", "content:edit",
            "artifact:view", "artifact:edit", "artifact:compare",
            "source:view", "source:create", "source:edit", "source:collect",
            "workflow:view", "workflow:execute",
            "publication:view", "publication:preview",
            "model:view", "quota:view",
        ],
        "TENANT_ALL",
    ),
    (
        "reviewer", "内容审核",
        "负责人工复核与质量把关，可审批、驳回和重新分配任务。", False,
        [
            "content:view", "artifact:view", "artifact:compare", "source:view",
            "workflow:view", "review:view", "review:claim", "review:approve",
            "review:reject", "review:reassign",
            "publication:view", "publication:preview", "publication:export",
            "quota:view",
        ],
        "TENANT_ALL",
    ),
    (
        "viewer", "只读观察者",
        "只能查看内容与报表，不能执行任何写操作。", False,
        [
            "content:view", "artifact:view", "source:view",
            "workflow:view", "review:view", "publication:view", "quota:view",
        ],
        "TENANT_ALL",
    ),
]


def _with_rls_disabled(table: str, statements: list[tuple[str, dict]]) -> None:
    """Run statements with RLS temporarily disabled, then restore RLS + FORCE."""

    op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
    bind = op.get_bind()
    for sql, params in statements:
        bind.execute(sa.text(sql), params)
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. Restore the missing tenant-isolation policies ───────────────
    for table in ("role", "role_permission"):
        # Drop a stale policy if a partial earlier run left one behind.
        op.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_tenant_isolation" ON "{table}"'))

    op.execute(
        sa.text(
            f'CREATE POLICY "role_tenant_isolation" ON "role" '
            f"USING ({_TENANT_EXPR}) WITH CHECK ({_TENANT_EXPR})"
        )
    )
    # role_permission has no tenant_id column; isolate through its parent role.
    op.execute(
        sa.text(
            'CREATE POLICY "role_permission_tenant_isolation" ON "role_permission" '
            "USING (EXISTS (SELECT 1 FROM role r "
            "WHERE r.id = role_permission.role_id AND r.tenant_id = "
            "NULLIF(current_setting('app.tenant_id', true), '')::uuid)) "
            "WITH CHECK (EXISTS (SELECT 1 FROM role r "
            "WHERE r.id = role_permission.role_id AND r.tenant_id = "
            "NULLIF(current_setting('app.tenant_id', true), '')::uuid))"
        )
    )

    # ── 2. Enumerate tenants with RLS briefly disabled ─────────────────
    op.execute(sa.text('ALTER TABLE "tenant" DISABLE ROW LEVEL SECURITY'))
    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenant")).fetchall()]
    op.execute(sa.text('ALTER TABLE "tenant" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE "tenant" FORCE ROW LEVEL SECURITY'))

    # ── 3. Seed roles + permissions per tenant ────────────────────────
    for tenant_id in tenant_ids:
        for code, name, description, is_default, permissions, scope in _ROLES:
            role_id = uuid4()
            _with_rls_disabled(
                "role",
                [
                    (
                        "INSERT INTO role "
                        "(id, tenant_id, code, name, description, is_builtin, is_default, "
                        "created_at, updated_at, row_version) "
                        "VALUES (:id, :tid, :code, :name, :desc, true, :is_default, now(), now(), 0) "
                        "ON CONFLICT (tenant_id, code) DO NOTHING",
                        {
                            "id": role_id, "tid": tenant_id, "code": code,
                            "name": name, "desc": description, "is_default": is_default,
                        },
                    ),
                ],
            )

            # Resolve the actual id: ON CONFLICT may have kept an existing row.
            op.execute(sa.text('ALTER TABLE "role" DISABLE ROW LEVEL SECURITY'))
            actual_id = bind.execute(
                sa.text("SELECT id FROM role WHERE tenant_id = :tid AND code = :code"),
                {"tid": tenant_id, "code": code},
            ).scalar()
            op.execute(sa.text('ALTER TABLE "role" ENABLE ROW LEVEL SECURITY'))
            op.execute(sa.text('ALTER TABLE "role" FORCE ROW LEVEL SECURITY'))
            if actual_id is None:
                continue

            _with_rls_disabled(
                "role_permission",
                [
                    (
                        "INSERT INTO role_permission "
                        "(role_id, permission_code, data_scope) "
                        "VALUES (:rid, :perm, :scope) "
                        "ON CONFLICT (role_id, permission_code) DO NOTHING",
                        {"rid": actual_id, "perm": perm, "scope": scope},
                    )
                    for perm in permissions
                ],
            )

    # ── 4. Bind role-less members to their tenant's admin role ─────────
    _with_rls_disabled(
        "tenant_membership",
        [
            (
                "UPDATE tenant_membership m SET role_id = r.id "
                "FROM role r "
                "WHERE r.tenant_id = m.tenant_id AND r.code = 'admin' AND m.role_id IS NULL",
                {},
            ),
        ],
    )


def downgrade() -> None:
    op.execute(sa.text('DROP POLICY IF EXISTS "role_permission_tenant_isolation" ON "role_permission"'))
    op.execute(sa.text('DROP POLICY IF EXISTS "role_tenant_isolation" ON "role"'))
