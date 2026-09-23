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
        {"comment": "套餐定义：约束单个租户可用的成员数、工作区数与每日内容产额"},
    )

    code: Mapped[str] = mapped_column(
        CITEXT(), nullable=False, unique=True, comment="套餐编码，全局唯一"
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="套餐名称")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", comment="状态：ACTIVE 启用 / INACTIVE 停用"
    )
    max_users: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=10, comment="租户最大成员数上限"
    )
    max_workspaces: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=3, comment="租户最大工作区数上限"
    )
    max_daily_articles: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=100, comment="每日最大内容产出篇数"
    )


class Tenant(EntityMixin, Base):
    __tablename__ = "tenant"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')", name="status_allowed"),
        Index("ix_tenant_status", "status"),
        Index("ix_tenant_plan_id", "plan_id"),
        {"comment": "租户：平台的独立业务空间，是所有业务数据行级隔离的边界"},
    )

    code: Mapped[str] = mapped_column(
        CITEXT(), nullable=False, unique=True, comment="租户编码，全局唯一，用于登录时定位租户"
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False, comment="租户名称")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        comment="状态：ACTIVE 正常 / SUSPENDED 已暂停 / CLOSED 已关闭",
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Shanghai",
        comment="租户默认时区，用于时间展示与定时调度",
    )
    locale: Mapped[str] = mapped_column(
        String(20), nullable=False, default="zh-CN", comment="默认语言区域，如 zh-CN"
    )
    data_region: Mapped[str] = mapped_column(
        String(32), nullable=False, default="CN", comment="数据存储区域标识"
    )
    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan.id", ondelete="RESTRICT"), comment="关联的套餐 ID"
    )
    settings_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="租户配置版本号，配置变更后自增以失效相关缓存",
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
        {"comment": "租户订阅：记录租户与套餐的订阅周期、宽限期，同一租户最多一条生效中记录"},
    )

    plan_id: Mapped[UUID] = mapped_column(
        ForeignKey("plan.id", ondelete="RESTRICT"), comment="订阅的套餐 ID"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        comment=(
            "状态：PENDING 待生效 / ACTIVE 生效中 / PAST_DUE 已逾期 / "
            "CANCELLED 已取消 / EXPIRED 已过期"
        ),
    )
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="订阅开始时间"
    )
    ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="订阅结束时间，为空表示不限期"
    )
    grace_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="宽限期截止时间，逾期后仍可访问的截止时点"
    )
