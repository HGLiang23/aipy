"""Create initial tenant, organization, workspace, and brand tables.

Revision ID: 20260724_0001
Revises: None
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import SchemaItem

revision: str = "20260724_0001"
down_revision: str | None = None
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
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS citext"))

    op.create_table(
        "plan",
        *_entity_columns(),
        sa.Column("code", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("max_users", sa.BigInteger(), nullable=False),
        sa.Column("max_workspaces", sa.BigInteger(), nullable=False),
        sa.Column("max_daily_articles", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name=op.f("ck_plan_status_allowed")),
        sa.CheckConstraint("max_users >= 0", name=op.f("ck_plan_max_users_nonnegative")),
        sa.CheckConstraint("max_workspaces >= 0", name=op.f("ck_plan_max_workspaces_nonnegative")),
        sa.CheckConstraint(
            "max_daily_articles >= 0", name=op.f("ck_plan_max_daily_articles_nonnegative")
        ),
        sa.UniqueConstraint("code", name="uq_plan_code"),
    )

    op.create_table(
        "tenant",
        *_entity_columns(),
        sa.Column("code", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("locale", sa.String(length=20), nullable=False),
        sa.Column("data_region", sa.String(length=32), nullable=False),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("settings_version", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')",
            name=op.f("ck_tenant_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["plan.id"], name="fk_tenant_plan_id_plan", ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("code", name="uq_tenant_code"),
    )
    op.create_index("ix_tenant_status", "tenant", ["status"])
    op.create_index("ix_tenant_plan_id", "tenant", ["plan_id"])

    op.create_table(
        "tenant_subscription",
        *_entity_columns(tenant_scoped=True),
        sa.Column("plan_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'PAST_DUE', 'CANCELLED', 'EXPIRED')",
            name=op.f("ck_tenant_subscription_status_allowed"),
        ),
        sa.CheckConstraint(
            "ends_at IS NULL OR ends_at > starts_at",
            name=op.f("ck_tenant_subscription_valid_date_range"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_tenant_subscription_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plan.id"],
            name="fk_tenant_subscription_plan_id_plan",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_subscription_tenant_id_id"),
    )
    op.create_index(
        "uq_tenant_subscription_one_active",
        "tenant_subscription",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "app_user",
        *_entity_columns(),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED', 'LOCKED')",
            name=op.f("ck_app_user_status_allowed"),
        ),
        sa.UniqueConstraint("email", name="uq_app_user_email"),
    )
    op.create_index(
        "uq_app_user_phone_not_null",
        "app_user",
        ["phone"],
        unique=True,
        postgresql_where=sa.text("phone IS NOT NULL"),
    )

    op.create_table(
        "tenant_membership",
        *_entity_columns(tenant_scoped=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("member_no", sa.String(length=64), nullable=True),
        sa.Column("job_title", sa.String(length=120), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('INVITED', 'ACTIVE', 'SUSPENDED', 'LEFT')",
            name=op.f("ck_tenant_membership_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_tenant_membership_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name="fk_tenant_membership_user_id_app_user",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_membership_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership_tenant_id_user_id"),
    )
    op.create_index(
        "uq_tenant_membership_member_no_not_null",
        "tenant_membership",
        ["tenant_id", "member_no"],
        unique=True,
        postgresql_where=sa.text("member_no IS NOT NULL"),
    )
    op.create_index("ix_tenant_membership_user_status", "tenant_membership", ["user_id", "status"])
    op.create_index(
        "ix_tenant_membership_tenant_status", "tenant_membership", ["tenant_id", "status"]
    )

    op.create_table(
        "team",
        *_entity_columns(tenant_scoped=True),
        sa.Column("parent_team_id", sa.Uuid(), nullable=True),
        sa.Column("code", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name=op.f("ck_team_status_allowed")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_team_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_team_id"],
            ["team.tenant_id", "team.id"],
            name="fk_team_tenant_parent_team",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_team_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_team_tenant_id_code"),
    )
    op.create_index("ix_team_tenant_parent_team", "team", ["tenant_id", "parent_team_id"])

    op.create_table(
        "team_member",
        *_entity_columns(tenant_scoped=True),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("is_manager", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_team_member_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "team_id"],
            ["team.tenant_id", "team.id"],
            name="fk_team_member_tenant_team",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_membership.tenant_id", "tenant_membership.id"],
            name="fk_team_member_tenant_membership",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_team_member_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "team_id",
            "membership_id",
            name="uq_team_member_tenant_id_team_id_membership_id",
        ),
    )
    op.create_index(
        "ix_team_member_tenant_membership", "team_member", ["tenant_id", "membership_id"]
    )

    op.create_table(
        "workspace",
        *_entity_columns(tenant_scoped=True),
        sa.Column("code", postgresql.CITEXT(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("default_brand_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_membership_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ARCHIVED')", name=op.f("ck_workspace_status_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_workspace_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_membership_id"],
            ["tenant_membership.tenant_id", "tenant_membership.id"],
            name="fk_workspace_tenant_creator_membership",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_workspace_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_workspace_tenant_id_code"),
    )
    op.create_index("ix_workspace_tenant_status", "workspace", ["tenant_id", "status"])
    op.create_index(
        "ix_workspace_tenant_creator_membership",
        "workspace",
        ["tenant_id", "created_by_membership_id"],
    )
    op.create_index(
        "ix_workspace_tenant_default_brand",
        "workspace",
        ["tenant_id", "default_brand_id"],
    )

    op.create_table(
        "brand",
        *_entity_columns(tenant_scoped=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tone_guideline", sa.Text(), nullable=True),
        sa.Column("prohibited_terms", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("default_language", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')", name=op.f("ck_brand_status_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenant.id"],
            name="fk_brand_tenant_id_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workspace_id"],
            ["workspace.tenant_id", "workspace.id"],
            name="fk_brand_tenant_workspace",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_brand_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id", "workspace_id", "name", name="uq_brand_tenant_workspace_name"
        ),
    )
    op.create_index(
        "ix_brand_tenant_workspace_status", "brand", ["tenant_id", "workspace_id", "status"]
    )

    op.create_foreign_key(
        "fk_workspace_tenant_default_brand",
        "workspace",
        "brand",
        ["tenant_id", "default_brand_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )

    # Runtime roles must be non-superuser, non-owner, and must not have BYPASSRLS.
    # Deployment grants are environment-specific and intentionally not created here.
    _enable_rls("tenant", tenant_column="id")
    for table in (
        "tenant_subscription",
        "tenant_membership",
        "team",
        "team_member",
        "workspace",
        "brand",
    ):
        _enable_rls(table)


def downgrade() -> None:
    op.drop_constraint("fk_workspace_tenant_default_brand", "workspace", type_="foreignkey")
    op.drop_table("brand")
    op.drop_table("workspace")
    op.drop_table("team_member")
    op.drop_table("team")
    op.drop_table("tenant_membership")
    op.drop_table("app_user")
    op.drop_table("tenant_subscription")
    op.drop_table("tenant")
    op.drop_table("plan")
    # citext can be shared by other schemas; downgrades intentionally leave the extension installed.
