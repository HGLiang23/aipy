"""Tenant, plan, and subscription persistence models."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from aipy.shared.db import Base, EntityMixin, TenantEntityMixin


class Plan(EntityMixin, Base):
    __tablename__ = "plan"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="status_allowed"),
        CheckConstraint("max_users >= 0", name="max_users_nonnegative"),
        CheckConstraint("max_workspaces >= 0", name="max_workspaces_nonnegative"),
        CheckConstraint("max_daily_articles >= 0", name="max_daily_articles_nonnegative"),
    )

    code: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    max_users: Mapped[int] = mapped_column(BigInteger, nullable=False, default=10)
    max_workspaces: Mapped[int] = mapped_column(BigInteger, nullable=False, default=3)
    max_daily_articles: Mapped[int] = mapped_column(BigInteger, nullable=False, default=100)


class Tenant(EntityMixin, Base):
    __tablename__ = "tenant"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')", name="status_allowed"),
        Index("ix_tenant_status", "status"),
        Index("ix_tenant_plan_id", "plan_id"),
    )

    code: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    locale: Mapped[str] = mapped_column(String(20), nullable=False, default="zh-CN")
    data_region: Mapped[str] = mapped_column(String(32), nullable=False, default="CN")
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plan.id", ondelete="RESTRICT"))
    settings_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )


class TenantSubscription(TenantEntityMixin, Base):
    __tablename__ = "tenant_subscription"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        CheckConstraint(
            "status IN ('PENDING', 'ACTIVE', 'PAST_DUE', 'CANCELLED', 'EXPIRED')",
            name="status_allowed",
        ),
        CheckConstraint("ends_at IS NULL OR ends_at > starts_at", name="valid_date_range"),
        Index(
            "uq_tenant_subscription_one_active",
            "tenant_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plan.id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
