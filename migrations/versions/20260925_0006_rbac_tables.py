"""Create RBAC tables (role, role_permission, membership_role).

Revision ID: 20260925_0006
Revises: 20260923_0005
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

revision: str = "20260925_0006"
down_revision: str | None = "20260923_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_columns() -> list[SchemaItem]:
    """Shared tenant-owned columns, mirroring ``TenantEntityMixin``."""

    return [
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            comment="主键，UUIDv7（时间有序），由应用生成",
        ),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            nullable=False,
            comment="所属租户 ID，行级安全策略（RLS）的隔离依据",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="创建时间（数据库时区为 UTC）",
        ),
        sa.Column(
            "created_by",
            sa.Uuid(),
            nullable=True,
            comment="创建人用户 ID，系统自动创建时为空",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="最后更新时间",
        ),
        sa.Column(
            "updated_by",
            sa.Uuid(),
            nullable=True,
            comment="最后更新人用户 ID，系统自动更新时为空",
        ),
        sa.Column(
            "row_version",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
            comment="乐观锁版本号，每次更新自增 1，用于并发冲突检测",
        ),
        sa.PrimaryKeyConstraint("id"),
    ]


def _enable_rls(table: str) -> None:
    expression = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{table}_tenant_isolation" ON "{table}" '
            f"USING ({expression}) WITH CHECK ({expression})"
        )
    )


def upgrade() -> None:
    op.create_table(
        "role",
        *_tenant_columns(),
        sa.Column(
            "code",
            postgresql.CITEXT(),
            nullable=False,
            comment="角色编码，租户内唯一，系统预置为 admin/editor/reviewer/member",
        ),
        sa.Column("name", sa.String(length=64), nullable=False, comment="角色名称"),
        sa.Column("description", sa.String(length=255), nullable=True, comment="角色用途说明"),
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="是否为系统预置角色，预置角色不允许删除",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
            comment="状态：ACTIVE 启用 / INACTIVE 停用，停用后其权限不再生效",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_role_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_role_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_role_tenant_id_code"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name=op.f("ck_role_status_allowed")),
        comment="角色：租户内可分配给成员的权限集合，系统预置角色不允许删除",
    )

    op.create_table(
        "role_permission",
        *_tenant_columns(),
        sa.Column("role_id", sa.Uuid(), nullable=False, comment="关联的角色 ID"),
        sa.Column(
            "permission_code",
            sa.String(length=64),
            nullable=False,
            comment="权限码，格式 resource:action，如 content:approve",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["role.tenant_id", "role.id"],
            name="fk_role_permission_tenant_role",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_role_permission_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_role_permission_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "role_id",
            "permission_code",
            name="uq_role_permission_tenant_id_role_id_permission_code",
        ),
        comment="角色权限：角色与权限码的多对多关联，权限码格式为 resource:action",
    )
    op.create_index("ix_role_permission_tenant_role", "role_permission", ["tenant_id", "role_id"])

    op.create_table(
        "membership_role",
        *_tenant_columns(),
        sa.Column("membership_id", sa.Uuid(), nullable=False, comment="关联的租户成员 ID"),
        sa.Column("role_id", sa.Uuid(), nullable=False, comment="关联的角色 ID"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_membership.tenant_id", "tenant_membership.id"],
            name="fk_membership_role_tenant_membership",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["role.tenant_id", "role.id"],
            name="fk_membership_role_tenant_role",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_membership_role_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_membership_role_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "membership_id",
            "role_id",
            name="uq_membership_role_tenant_id_membership_id_role_id",
        ),
        comment="成员角色：租户成员与角色的多对多关联，一人多角色时权限取并集",
    )
    op.create_index(
        "ix_membership_role_tenant_membership",
        "membership_role",
        ["tenant_id", "membership_id"],
    )

    _enable_rls("role")
    _enable_rls("role_permission")
    _enable_rls("membership_role")


def downgrade() -> None:
    op.drop_index("ix_membership_role_tenant_membership", table_name="membership_role")
    op.drop_table("membership_role")
    op.drop_index("ix_role_permission_tenant_role", table_name="role_permission")
    op.drop_table("role_permission")
    op.drop_table("role")
