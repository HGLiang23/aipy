"""Create the append-only audit_event table.

Revision ID: 20260924_0008_audit_event
Revises: 20260924_0007_workflow_templates
Create Date: 2026-09-24 14:55:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

revision: str = "20260924_0008_audit_event"
down_revision: str | None = "20260924_0007_workflow_templates"
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


def upgrade() -> None:
    op.create_table(
        "audit_event",
        *_entity_columns(tenant_scoped=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_type", sa.String(length=16), nullable=False, server_default=sa.text("'USER'")),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_label", sa.String(length=160), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("resource_version_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=False, server_default=sa.text("'SUCCESS'")),
        sa.Column("before_data", postgresql.JSONB(), nullable=True),
        sa.Column("after_data", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
    )
    op.create_index("ix_audit_event_tenant_occurred", "audit_event", ["tenant_id", "occurred_at"])
    op.create_index(
        "ix_audit_event_tenant_resource", "audit_event",
        ["tenant_id", "resource_type", "resource_id", "occurred_at"],
    )
    op.create_index("ix_audit_event_trace", "audit_event", ["trace_id"])

    # RLS isolation by tenant.
    expression = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
    op.execute(sa.text('ALTER TABLE "audit_event" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text('ALTER TABLE "audit_event" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            'CREATE POLICY "audit_event_tenant_isolation" ON "audit_event" '
            f"USING ({expression}) WITH CHECK ({expression})"
        )
    )

    # Append-only enforcement. A trigger fires for every role (including the table
    # owner and superusers), which REVOKE alone cannot guarantee.
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION audit_event_block_mutation() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'audit_event is append-only: % is not permitted', TG_OP;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER audit_event_no_update
            BEFORE UPDATE OR DELETE ON audit_event
            FOR EACH ROW EXECUTE FUNCTION audit_event_block_mutation();
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS audit_event_no_update ON audit_event"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS audit_event_block_mutation()"))
    op.drop_index("ix_audit_event_trace", table_name="audit_event")
    op.drop_index("ix_audit_event_tenant_resource", table_name="audit_event")
    op.drop_index("ix_audit_event_tenant_occurred", table_name="audit_event")
    op.drop_table("audit_event")
