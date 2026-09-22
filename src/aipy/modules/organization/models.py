"""Platform users, tenant memberships, and team persistence models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from aipy.shared.db import Base, EntityMixin, TenantEntityMixin


class AppUser(EntityMixin, Base):
    __tablename__ = "app_user"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'DISABLED', 'LOCKED')", name="status_allowed"),
        Index(
            "uq_app_user_phone_not_null",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
    )

    email: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantMembership(TenantEntityMixin, Base):
    __tablename__ = "tenant_membership"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "user_id"),
        CheckConstraint(
            "status IN ('INVITED', 'ACTIVE', 'SUSPENDED', 'LEFT')", name="status_allowed"
        ),
        Index(
            "uq_tenant_membership_member_no_not_null",
            "tenant_id",
            "member_no",
            unique=True,
            postgresql_where=text("member_no IS NOT NULL"),
        ),
        Index("ix_tenant_membership_user_status", "user_id", "status"),
        Index("ix_tenant_membership_tenant_status", "tenant_id", "status"),
    )

    user_id: Mapped[UUID] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="INVITED")
    member_no: Mapped[str | None] = mapped_column(String(64))
    job_title: Mapped[str | None] = mapped_column(String(120))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Team(TenantEntityMixin, Base):
    __tablename__ = "team"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code"),
        ForeignKeyConstraint(
            ["tenant_id", "parent_team_id"],
            ["team.tenant_id", "team.id"],
            name="fk_team_tenant_parent_team",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="status_allowed"),
        Index("ix_team_tenant_parent_team", "tenant_id", "parent_team_id"),
    )

    parent_team_id: Mapped[UUID | None] = mapped_column(nullable=True)
    code: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")


class TeamMember(TenantEntityMixin, Base):
    __tablename__ = "team_member"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "team_id", "membership_id"),
        ForeignKeyConstraint(
            ["tenant_id", "team_id"],
            ["team.tenant_id", "team.id"],
            name="fk_team_member_tenant_team",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_membership.tenant_id", "tenant_membership.id"],
            name="fk_team_member_tenant_membership",
            ondelete="CASCADE",
        ),
        Index("ix_team_member_tenant_membership", "tenant_id", "membership_id"),
    )

    team_id: Mapped[UUID] = mapped_column(nullable=False)
    membership_id: Mapped[UUID] = mapped_column(nullable=False)
    is_manager: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
