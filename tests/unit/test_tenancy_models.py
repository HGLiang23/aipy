"""Database-independent checks for the initial tenancy ORM contract."""

from typing import cast

from sqlalchemy import ForeignKeyConstraint, Table, UniqueConstraint

from aipy.modules.brand.models import Brand, Workspace
from aipy.modules.organization.models import AppUser, Team, TeamMember, TenantMembership
from aipy.modules.tenancy.models import Plan, Tenant, TenantSubscription
from aipy.shared.db import Base, new_uuid7

TENANT_SCOPED_MODELS = (
    TenantSubscription,
    TenantMembership,
    Team,
    TeamMember,
    Workspace,
    Brand,
)


def test_uuid_factory_returns_uuid7() -> None:
    first = new_uuid7()
    second = new_uuid7()

    assert first.version == 7
    assert second.version == 7
    assert first < second


def test_initial_model_set_is_registered() -> None:
    assert {
        "app_user",
        "brand",
        "plan",
        "team",
        "team_member",
        "tenant",
        "tenant_membership",
        "tenant_subscription",
        "workspace",
    } <= set(Base.metadata.tables)


def test_entities_expose_audit_and_optimistic_lock_columns() -> None:
    for model in (Plan, Tenant, AppUser, *TENANT_SCOPED_MODELS):
        columns = cast(Table, model.__table__).columns
        assert {"id", "created_at", "created_by", "updated_at", "updated_by"} <= set(columns.keys())
        assert "row_version" in columns
        assert model.__mapper__.version_id_col is columns.row_version


def test_tenant_entities_have_composite_identity_constraint() -> None:
    for model in TENANT_SCOPED_MODELS:
        table = cast(Table, model.__table__)
        columns = table.columns
        assert "tenant_id" in columns
        unique_column_sets = {
            tuple(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, UniqueConstraint)
        }
        assert ("tenant_id", "id") in unique_column_sets


def test_tenant_child_references_are_composite() -> None:
    expected = {
        "team": {("tenant_id", "parent_team_id")},
        "team_member": {
            ("tenant_id", "team_id"),
            ("tenant_id", "membership_id"),
        },
        "workspace": {
            ("tenant_id", "created_by_membership_id"),
            ("tenant_id", "default_brand_id"),
        },
        "brand": {("tenant_id", "workspace_id")},
    }

    for table_name, required_column_sets in expected.items():
        table = Base.metadata.tables[table_name]
        composite_foreign_keys = {
            tuple(constraint.columns.keys())
            for constraint in table.constraints
            if isinstance(constraint, ForeignKeyConstraint) and len(constraint.columns) > 1
        }
        assert required_column_sets <= composite_foreign_keys


def test_global_identity_tables_are_not_tenant_scoped() -> None:
    for model in (Plan, AppUser):
        assert "tenant_id" not in model.__table__.columns

    assert "tenant_id" not in Tenant.__table__.columns
    assert str(AppUser.__table__.columns.email.type).upper() == "CITEXT"
