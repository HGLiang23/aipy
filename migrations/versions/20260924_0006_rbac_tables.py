"""Add role and role_permission tables, add role_id to tenant_membership.

Revision ID: 20260924_0006_rbac_tables
Revises: 20260923_0005_table_column_comments
Create Date: 2026-09-24 12:50:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260924_0006_rbac_tables"
down_revision: Union[str, None] = "20260923_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create role table
    op.create_table(
        "role",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False, comment="角色编码，租户内唯一"),
        sa.Column("name", sa.String(120), nullable=False, comment="角色显示名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="角色描述"),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="false", comment="是否内置角色"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false", comment="是否默认角色"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_role_tenant_code"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        comment="角色：租户内定义的权限集合模板",
    )
    op.create_index("ix_role_tenant_id", "role", ["tenant_id"])

    # Create role_permission table
    op.create_table(
        "role_permission",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("permission_code", sa.String(100), nullable=False, comment="权限码"),
        sa.Column("data_scope", sa.String(50), nullable=True, server_default="TENANT_ALL", comment="数据范围"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_code", name="uq_role_permission"),
        sa.ForeignKeyConstraint(["role_id"], ["role.id"], ondelete="CASCADE"),
        comment="角色权限关联",
    )

    # Add role_id to tenant_membership
    op.add_column(
        "tenant_membership",
        sa.Column(
            "role_id",
            sa.UUID(),
            nullable=True,
            comment="关联的角色 ID",
        ),
    )
    op.create_foreign_key(
        "fk_tenant_membership_role",
        "tenant_membership",
        "role",
        ["role_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Seed built-in roles for existing tenants
    op.execute("""
        INSERT INTO role (id, tenant_id, code, name, description, is_builtin, is_default, created_at, updated_at, row_version)
        SELECT
            gen_random_uuid(),
            t.id,
            'admin',
            '租户管理员',
            '拥有租户内全部权限的管理员角色',
            true,
            false,
            now(),
            now(),
            1
        FROM tenant t
        ON CONFLICT (tenant_id, code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role (id, tenant_id, code, name, description, is_builtin, is_default, created_at, updated_at, row_version)
        SELECT
            gen_random_uuid(),
            t.id,
            'editor',
            '编辑',
            '可编辑和创建内容的普通编辑角色',
            true,
            true,
            now(),
            now(),
            1
        FROM tenant t
        ON CONFLICT (tenant_id, code) DO NOTHING
    """)

    # Seed admin role with all permissions
    op.execute("""
        INSERT INTO role_permission (role_id, permission_code, data_scope)
        SELECT r.id, perm, 'TENANT_ALL'
        FROM role r,
             unnest(ARRAY[
                 'batch:view','batch:create','content:view','content:create','content:edit',
                 'content:assign','artifact:view','artifact:edit','artifact:compare',
                 'source:view','source:create','source:edit','source:collect',
                 'workflow:view','workflow:configure','workflow:execute',
                 'review:view','review:claim','review:approve','review:reject','review:reassign',
                 'publication:view','publication:preview','publication:export',
                 'model:view','model:configure','model:credential_manage',
                 'quota:view','quota:configure',
                 'member:view','member:manage',
                 'role:view','role:manage',
                 'audit:view'
             ]) AS perm
        WHERE r.code = 'admin'
        ON CONFLICT (role_id, permission_code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permission (role_id, permission_code, data_scope)
        SELECT r.id, perm, 'CREATED_BY_ME'
        FROM role r,
             unnest(ARRAY[
                 'content:view','content:create','content:edit',
                 'artifact:view','artifact:edit',
                 'source:view','source:create',
                 'review:view','review:claim',
                 'publication:view'
             ]) AS perm
        WHERE r.code = 'editor'
        ON CONFLICT (role_id, permission_code) DO NOTHING
    """)

    # Assign admin role to existing active members
    op.execute("""
        UPDATE tenant_membership m
        SET role_id = r.id
        FROM role r
        WHERE r.tenant_id = m.tenant_id
          AND r.code = 'admin'
          AND m.status = 'ACTIVE'
          AND m.role_id IS NULL
    """)


def downgrade() -> None:
    op.drop_constraint("fk_tenant_membership_role", "tenant_membership", type_="foreignkey")
    op.drop_column("tenant_membership", "role_id")
    op.drop_table("role_permission")
    op.drop_table("role")
