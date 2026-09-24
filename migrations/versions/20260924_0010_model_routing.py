"""Create model routing policy and candidate tables.

Revision ID: 20260924_0010_model_routing
Revises: 20260924_0009_model_credentials
Create Date: 2026-09-24 15:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import SchemaItem

revision: str = "20260924_0010_model_routing"
down_revision: str | None = "20260924_0009_model_credentials"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entity_columns(*, tenant_scoped: bool = False) -> list[SchemaItem]:
    columns: list[SchemaItem] = [sa.Column("id", sa.Uuid(), nullable=False)]
    if tenant_scoped:
        columns.append(sa.Column("tenant_id", sa.Uuid(), nullable=False))
    columns.extend(
        [
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("created_by", sa.Uuid(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_by", sa.Uuid(), nullable=True),
            sa.Column("row_version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        ]
    )
    return columns


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
        "model_route_policy",
        *_entity_columns(tenant_scoped=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("daily_cost_limit", sa.Numeric(12, 4), nullable=True),
        sa.Column("per_call_timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.UniqueConstraint("tenant_id", "task_type", name="uq_mrp_tenant_task_type"),
    )

    op.create_table(
        "model_route_candidate",
        *_entity_columns(tenant_scoped=True),
        sa.Column("policy_id", sa.Uuid(), sa.ForeignKey("model_route_policy.id", ondelete="CASCADE"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("model_definition_id", sa.Uuid(), sa.ForeignKey("model_definition.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("credential_id", sa.Uuid(), sa.ForeignKey("tenant_model_credential.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=False, server_default=sa.text("0.70")),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default=sa.text("2048")),
        sa.Column("allowed_for_publish", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("tenant_id", "policy_id", "priority", name="uq_mrc_tenant_policy_priority"),
    )

    _enable_rls("model_route_policy")
    _enable_rls("model_route_candidate")


def downgrade() -> None:
    op.drop_table("model_route_candidate")
    op.drop_table("model_route_policy")
