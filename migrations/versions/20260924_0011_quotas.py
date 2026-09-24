"""Create quota policy and usage bucket tables.

Revision ID: 20260924_0011_quotas
Revises: 20260924_0010_model_routing
Create Date: 2026-09-24 15:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import SchemaItem

revision: str = "20260924_0011_quotas"
down_revision: str | None = "20260924_0010_model_routing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _entity_columns() -> list[SchemaItem]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("row_version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
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
        "quota_policy",
        *_entity_columns(),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("period_type", sa.String(length=16), nullable=False, server_default=sa.text("'MONTHLY'")),
        sa.Column("soft_limit", sa.Numeric(14, 4), nullable=True),
        sa.Column("hard_limit", sa.Numeric(14, 4), nullable=True),
        sa.Column("overage_allowed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default=sa.text("'Asia/Shanghai'")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.UniqueConstraint("tenant_id", "metric", name="uq_quota_policy_tenant_metric"),
        sa.CheckConstraint("soft_limit IS NOT NULL OR hard_limit IS NOT NULL", name="ck_quota_policy_limit_present"),
        sa.CheckConstraint("soft_limit IS NULL OR soft_limit >= 0", name="ck_quota_policy_soft_non_negative"),
        sa.CheckConstraint("hard_limit IS NULL OR hard_limit >= 0", name="ck_quota_policy_hard_non_negative"),
        sa.CheckConstraint(
            "soft_limit IS NULL OR hard_limit IS NULL OR soft_limit <= hard_limit",
            name="ck_quota_policy_soft_not_above_hard",
        ),
    )

    op.create_table(
        "quota_usage_bucket",
        *_entity_columns(),
        sa.Column("metric", sa.String(length=48), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reserved_amount", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0")),
        sa.Column("used_amount", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0")),
        sa.UniqueConstraint("tenant_id", "metric", "period_start", name="uq_quota_bucket_tenant_metric_start"),
    )
    op.create_index("ix_quota_bucket_tenant_period", "quota_usage_bucket", ["tenant_id", "period_start"])

    _enable_rls("quota_policy")
    _enable_rls("quota_usage_bucket")

    # Seed default quotas for every existing tenant. The tenant table has FORCE RLS,
    # so disable it momentarily to enumerate tenant ids, then restore.
    bind = op.get_bind()
    op.execute(sa.text('ALTER TABLE "tenant" DISABLE ROW LEVEL SECURITY'))
    tenant_ids = [row[0] for row in bind.execute(sa.text("SELECT id FROM tenant")).fetchall()]
    op.execute(sa.text('ALTER TABLE "tenant" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE "tenant" FORCE ROW LEVEL SECURITY'))

    defaults = [
        ("ARTICLES_GENERATED", 60, 120),
        ("ARTICLES_PUBLISHED", 20, 40),
        ("SOURCES_COLLECTED", 400, 800),
        ("INPUT_TOKENS", 5000000, 10000000),
        ("OUTPUT_TOKENS", 2000000, 4000000),
        ("AI_COST", 2000, 4000),
    ]
    for tenant_id in tenant_ids:
        op.execute(sa.text('ALTER TABLE "quota_policy" DISABLE ROW LEVEL SECURITY'))
        for metric, soft, hard in defaults:
            bind.execute(
                sa.text(
                    "INSERT INTO quota_policy "
                    "(id, tenant_id, metric, period_type, soft_limit, hard_limit, overage_allowed, "
                    "timezone, status, created_at, updated_at, row_version) "
                    "VALUES (gen_random_uuid(), :tid, :metric, 'MONTHLY', :soft, :hard, false, "
                    "'Asia/Shanghai', 'ACTIVE', now(), now(), 0)"
                ),
                {"tid": tenant_id, "metric": metric, "soft": soft, "hard": hard},
            )
        op.execute(sa.text('ALTER TABLE "quota_policy" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text('ALTER TABLE "quota_policy" FORCE ROW LEVEL SECURITY'))


def downgrade() -> None:
    op.drop_index("ix_quota_bucket_tenant_period", table_name="quota_usage_bucket")
    op.drop_table("quota_usage_bucket")
    op.drop_table("quota_policy")
