"""Add content body, export artifacts, and material collection links.

Revision ID: 20260925_0008
Revises: 20260925_0007
Create Date: 2026-09-25

Closes the ``export`` / ``collect`` action gap: ``content_run`` gains a
``content`` body (written back by the worker) and ``exported_at`` stamp; the
``export`` action persists a ``content_export`` artifact; ``collect`` links
relevant ``material`` rows through ``content_run_material``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

revision: str = "20260925_0008"
down_revision: str | None = "20260925_0007"
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
    op.add_column(
        "content_run",
        sa.Column("content", sa.Text(), nullable=True, comment="生成的正文内容，由工作流执行回写"),
    )
    op.add_column(
        "content_run",
        sa.Column(
            "exported_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="最近一次导出时间，导出动作成功后写入",
        ),
    )

    # ``content_run_material`` below references ``(tenant_id, id)`` on both
    # ``content_run`` and ``material``. Revision 0002 declared only the primary key
    # on ``id``, and PostgreSQL rejects a composite foreign key unless the
    # referenced column list carries a matching unique constraint.
    for table in ("content_run", "material"):
        op.create_unique_constraint(f"uq_{table}_tenant_id_id", table, ["tenant_id", "id"])

    op.create_table(
        "content_export",
        *_entity_columns(),
        sa.Column("run_id", sa.Uuid(), nullable=False, comment="关联的内容任务 ID"),
        sa.Column(
            "run_code",
            postgresql.CITEXT(),
            nullable=False,
            comment="关联任务编码，便于阅读与排查",
        ),
        sa.Column(
            "format",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'markdown'"),
            comment="产物格式：markdown / docx",
        ),
        sa.Column("title", sa.String(length=255), nullable=False, comment="导出标题"),
        sa.Column("payload", sa.Text(), nullable=False, comment="导出成品正文（markdown 源）"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.Index("ix_content_export_tenant_run", "tenant_id", "run_id"),
        comment="内容导出产物：每次导出生成一条记录，保存可下载的成品文本",
    )
    op.create_foreign_key(
        "fk_content_export_tenant_id_tenant",
        "content_export",
        "tenant",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        None,
        "content_export",
        "content_run",
        ["run_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "content_run_material",
        *_entity_columns(),
        sa.Column("run_id", sa.Uuid(), nullable=False, comment="内容任务 ID"),
        sa.Column("material_id", sa.Uuid(), nullable=False, comment="素材 ID"),
        sa.UniqueConstraint("tenant_id", "id"),
        sa.UniqueConstraint(
            "tenant_id", "run_id", "material_id", name="uq_content_run_material_run_material"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["content_run.tenant_id", "content_run.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "material_id"],
            ["material.tenant_id", "material.id"],
            ondelete="CASCADE",
        ),
        comment="内容任务与素材的关联：采集动作写入，记录该任务引用的参考来源",
    )
    op.create_foreign_key(
        "fk_content_run_material_tenant_id_tenant",
        "content_run_material",
        "tenant",
        ["tenant_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    _enable_rls("content_export")
    _enable_rls("content_run_material")


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP POLICY IF EXISTS "
            '"content_run_material_tenant_isolation" ON "content_run_material"'
        )
    )
    op.execute(
        sa.text('DROP POLICY IF EXISTS "content_export_tenant_isolation" ON "content_export"')
    )
    op.execute(sa.text('ALTER TABLE "content_run_material" DISABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE "content_export" DISABLE ROW LEVEL SECURITY'))

    op.drop_table("content_run_material")
    op.drop_table("content_export")
    for table in ("content_run", "material"):
        op.drop_constraint(f"uq_{table}_tenant_id_id", table, type_="unique")
    op.drop_column("content_run", "exported_at")
    op.drop_column("content_run", "content")
