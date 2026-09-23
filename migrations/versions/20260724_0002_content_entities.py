"""Create content production tables (content_run, human_task, material).

Revision ID: 20260724_0002
Revises: 20260724_0001
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

revision: str = "20260724_0002"
down_revision: str | None = "20260724_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entity_columns(*, tenant_scoped: bool = False) -> list[SchemaItem]:
    columns: list[SchemaItem] = [
        sa.Column("id", sa.Uuid(), nullable=False),
    ]
    if tenant_scoped:
        columns.append(sa.Column("tenant_id", sa.Uuid(), nullable=False))
    columns.extend(
        [
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("row_version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        ]
    )
    return columns


def _enable_rls(table: str, *, tenant_column: str = "tenant_id") -> None:
    expression = f"{tenant_column} = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
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
        "content_run",
        *_entity_columns(tenant_scoped=True),
        sa.Column("code", postgresql.CITEXT(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=False),
        sa.Column("stage_label", sa.String(length=64), nullable=False),
        sa.Column("status_label", sa.String(length=64), nullable=False),
        sa.Column("tone", sa.String(length=16), nullable=False, server_default=sa.text("'info'")),
        sa.Column("owner", sa.String(length=120), nullable=False),
        sa.Column("updated_at_label", sa.String(length=64), nullable=False),
        sa.Column(
            "allowed_actions",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_content_run_tenant_code"),
    )
    op.create_index("ix_content_run_tenant_seq", "content_run", ["tenant_id", "seq"])

    op.create_table(
        "human_task",
        *_entity_columns(tenant_scoped=True),
        sa.Column("code", postgresql.CITEXT(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "priority",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'普通'"),
        ),
        sa.Column("brand", sa.String(length=120), nullable=False),
        sa.Column("owner", sa.String(length=120), nullable=False),
        sa.Column("due_label", sa.String(length=64), nullable=False),
        sa.Column(
            "allowed_actions",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_human_task_tenant_code"),
    )
    op.create_index("ix_human_task_tenant_seq", "human_task", ["tenant_id", "seq"])

    op.create_table(
        "material",
        *_entity_columns(tenant_scoped=True),
        sa.Column("code", postgresql.CITEXT(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("trust_label", sa.String(length=32), nullable=False),
        sa.Column(
            "tone",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'neutral'"),
        ),
        sa.Column("updated_at_label", sa.String(length=64), nullable=False),
        sa.Column(
            "allowed_actions",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_material_tenant_code"),
    )
    op.create_index("ix_material_tenant_seq", "material", ["tenant_id", "seq"])

    _enable_rls("content_run")
    _enable_rls("human_task")
    _enable_rls("material")


def downgrade() -> None:
    op.drop_index("ix_material_tenant_seq", table_name="material")
    op.drop_table("material")
    op.drop_index("ix_human_task_tenant_seq", table_name="human_task")
    op.drop_table("human_task")
    op.drop_index("ix_content_run_tenant_seq", table_name="content_run")
    op.drop_table("content_run")
