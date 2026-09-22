"""Workspace and brand persistence models."""

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from aipy.shared.db import Base, TenantEntityMixin


class Workspace(TenantEntityMixin, Base):
    __tablename__ = "workspace"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
        ForeignKeyConstraint(
            ["tenant_id", "created_by_membership_id"],
            ["tenant_membership.tenant_id", "tenant_membership.id"],
            name="fk_workspace_tenant_creator_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "default_brand_id"],
            ["brand.tenant_id", "brand.id"],
            name="fk_workspace_tenant_default_brand",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint("status IN ('ACTIVE', 'ARCHIVED')", name="status_allowed"),
        Index("ix_workspace_tenant_status", "tenant_id", "status"),
        Index(
            "ix_workspace_tenant_creator_membership",
            "tenant_id",
            "created_by_membership_id",
        ),
        Index("ix_workspace_tenant_default_brand", "tenant_id", "default_brand_id"),
    )

    code: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    default_brand_id: Mapped[UUID | None] = mapped_column(nullable=True)
    created_by_membership_id: Mapped[UUID] = mapped_column(nullable=False)


class Brand(TenantEntityMixin, Base):
    __tablename__ = "brand"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id",
            "workspace_id",
            "name",
            name="uq_brand_tenant_workspace_name",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "workspace_id"],
            ["workspace.tenant_id", "workspace.id"],
            name="fk_brand_tenant_workspace",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="status_allowed"),
        Index("ix_brand_tenant_workspace_status", "tenant_id", "workspace_id", "status"),
    )

    workspace_id: Mapped[UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    tone_guideline: Mapped[str | None] = mapped_column(Text)
    prohibited_terms: Mapped[list[str]] = mapped_column(
        ARRAY(String()), nullable=False, default=list
    )
    default_language: Mapped[str] = mapped_column(String(20), nullable=False, default="zh-CN")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
