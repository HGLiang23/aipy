"""Add the ``material_file`` table that backs manual uploads.

Revision ID: 20260928_0009
Revises: 20260925_0008
Create Date: 2026-09-28

``POST /api/v1/materials/upload`` stores the uploaded bytes here so the library can
hand the original file back on download. The stack has no object store, so the bytes
live in a tenant-scoped table: RLS then protects them exactly like every other
content row and there is no shared volume to provision.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import SchemaItem

revision: str = "20260928_0009"
down_revision: str | None = "20260925_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entity_columns() -> list[SchemaItem]:
    """``TenantEntityMixin`` columns, comments included so ``alembic check`` agrees."""

    return [
        sa.Column("id", sa.Uuid(), nullable=False, comment="主键，UUIDv7（时间有序），由应用生成"),
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
            "created_by", sa.Uuid(), nullable=True, comment="创建人用户 ID，系统自动创建时为空"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="最后更新时间",
        ),
        sa.Column(
            "updated_by", sa.Uuid(), nullable=True, comment="最后更新人用户 ID，系统自动更新时为空"
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
        "material_file",
        *_entity_columns(),
        sa.Column("material_id", sa.Uuid(), nullable=False, comment="关联的素材 ID"),
        sa.Column(
            "filename",
            sa.String(length=255),
            nullable=False,
            comment="上传时的原始文件名",
        ),
        sa.Column(
            "content_type",
            sa.String(length=128),
            nullable=False,
            comment="上传时的 MIME 类型，用于下载响应头",
        ),
        sa.Column("byte_size", sa.Integer(), nullable=False, comment="文件字节数"),
        sa.Column("data", sa.LargeBinary(), nullable=False, comment="文件的原始字节内容"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint("tenant_id", "material_id", name="uq_material_file_material"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "material_id"],
            ["material.tenant_id", "material.id"],
            ondelete="CASCADE",
        ),
        comment="素材原件：人工上传文件的字节内容，供下载与后续解析",
    )
    op.create_foreign_key(
        "fk_material_file_tenant_id_tenant",
        "material_file",
        "tenant",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    _enable_rls("material_file")


def downgrade() -> None:
    op.execute(sa.text('DROP POLICY IF EXISTS "material_file_tenant_isolation" ON "material_file"'))
    op.execute(sa.text('ALTER TABLE "material_file" DISABLE ROW LEVEL SECURITY'))
    op.drop_table("material_file")
