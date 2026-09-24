"""Create workflow_template and workflow_template_version tables and seed system templates.

Revision ID: 20260924_0007_workflow_templates
Revises: 20260924_0006_rbac_tables
Create Date: 2026-09-24 14:30:00
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

revision: str = "20260924_0007_workflow_templates"
down_revision: str | None = "20260924_0006_rbac_tables"
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


# One reusable ASSISTED preset to seed every tenant.
SEED_NODES = [
    {"node_key": "BRIEF", "node_type": "BRIEF", "title": "选题简报", "execution_mode": "AUTO_CONTINUE", "sequence_no": 1, "max_attempts": 2, "quality_threshold": 70, "timeout_seconds": 600},
    {"node_key": "OUTLINE_BUILD", "node_type": "PLANNING", "title": "大纲构建", "execution_mode": "AUTO_REVIEW", "sequence_no": 2, "max_attempts": 2, "quality_threshold": 80, "timeout_seconds": 900},
    {"node_key": "DRAFT_WRITE", "node_type": "WRITING", "title": "正文写作", "execution_mode": "AUTO_CONTINUE", "sequence_no": 3, "max_attempts": 3, "quality_threshold": 75, "timeout_seconds": 1800},
    {"node_key": "FACT_CHECK", "node_type": "REVIEW", "title": "事实核查", "execution_mode": "AUTO_REVIEW", "sequence_no": 4, "max_attempts": 2, "quality_threshold": 85, "timeout_seconds": 900},
    {"node_key": "PLATFORM_ADAPT", "node_type": "ADAPTATION", "title": "平台适配", "execution_mode": "AUTO_CONTINUE", "sequence_no": 5, "max_attempts": 2, "quality_threshold": 80, "timeout_seconds": 1200},
    {"node_key": "PACKAGE_EXPORT", "node_type": "DELIVERY", "title": "导出交付", "execution_mode": "AUTO_CONTINUE", "sequence_no": 6, "max_attempts": 1, "quality_threshold": 90, "timeout_seconds": 600},
]


def upgrade() -> None:
    op.create_table(
        "workflow_template",
        *_entity_columns(tenant_scoped=True),
        sa.Column("code", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False, server_default=sa.text("'TENANT'")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("tenant_id", "code", name="uq_workflow_template_tenant_code"),
    )
    op.create_index("ix_workflow_template_tenant_category", "workflow_template", ["tenant_id", "category"])

    op.create_table(
        "workflow_template_version",
        *_entity_columns(tenant_scoped=True),
        sa.Column("template_id", sa.Uuid(), sa.ForeignKey("workflow_template.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'DRAFT'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.Column("nodes", postgresql.JSONB(), nullable=True),
        sa.Column("policy", postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint("tenant_id", "template_id", "version_no", name="uq_wftv_tenant_template_version"),
    )

    _enable_rls("workflow_template")
    _enable_rls("workflow_template_version")

    # Seed one system ASSISTED template per existing tenant.
    import json

    # Seed one system ASSISTED template per existing tenant. The tenant table is
    # RLS-protected, so we cannot read tenants (or insert template rows) through the
    # normal tenant context inside a migration. Temporarily relax RLS for the seed
    # only, then restore it (the policy is re-created by _enable_rls below-safe to
    # call again).
    bind = op.get_bind()
    for table in ("tenant", "workflow_template", "workflow_template_version"):
        bind.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
    tenant_rows = bind.execute(sa.text("SELECT id FROM tenant")).fetchall()
    for (tenant_id,) in tenant_rows:
        template_id = uuid4()
        version_id = uuid4()
        bind.execute(
            sa.text(
                "INSERT INTO workflow_template "
                "(id, tenant_id, code, name, category, status, description, current_version_id, created_at, updated_at, row_version) "
                "VALUES (:tpl, :tid, 'WT-ASSISTED', '人机协同（系统预设）', 'SYSTEM', 'PUBLISHED', "
                "'选题、大纲、平台版本默认人工复核，其余自动继续。', :vid, now(), now(), 0)"
            ),
            {"tpl": template_id, "tid": tenant_id, "vid": version_id},
        )
        bind.execute(
            sa.text(
                "INSERT INTO workflow_template_version "
                "(id, tenant_id, template_id, version_no, status, description, published_at, nodes, policy, created_at, updated_at, row_version) "
                "VALUES (:vid, :tid, :tpl, 1, 'PUBLISHED', '初始发布版本', now(), "
                ":nodes, '{\"preset\":\"ASSISTED\"}'::jsonb, now(), now(), 0)"
            ),
            {"vid": version_id, "tid": tenant_id, "tpl": template_id, "nodes": json.dumps(SEED_NODES)},
        )
    for table in ("tenant", "workflow_template", "workflow_template_version"):
        bind.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        bind.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM workflow_template_version"))
    bind.execute(sa.text("DELETE FROM workflow_template"))
    op.drop_index("ix_workflow_template_tenant_category", table_name="workflow_template")
    op.drop_table("workflow_template_version")
    op.drop_table("workflow_template")
