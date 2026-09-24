"""Quota policy and usage bucket ORM models.

MVP scope: configuration (``QuotaPolicy``) plus a usage summary projection
(``QuotaUsageBucket``). The reservation ledger (``quota_reservation`` /
``quota_ledger``) is intentionally deferred — the bucket is a rebuildable
projection, so it can be introduced later without a data migration.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from aipy.shared.db import Base, TenantEntityMixin

QUOTA_METRICS = (
    "ARTICLES_GENERATED",
    "ARTICLES_PUBLISHED",
    "SOURCES_COLLECTED",
    "INPUT_TOKENS",
    "OUTPUT_TOKENS",
    "AI_COST",
    "MAX_CONCURRENT_RUNS",
)

QUOTA_PERIOD_TYPES = ("DAILY", "MONTHLY", "ROLLING_30D")


class QuotaPolicy(TenantEntityMixin, Base):
    """A tenant's soft/hard limit for one metric over a recurring period."""

    __tablename__ = "quota_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", "metric", name="uq_quota_policy_tenant_metric"),
        CheckConstraint("soft_limit IS NOT NULL OR hard_limit IS NOT NULL", name="limit_present"),
        CheckConstraint("soft_limit IS NULL OR soft_limit >= 0", name="soft_non_negative"),
        CheckConstraint("hard_limit IS NULL OR hard_limit >= 0", name="hard_non_negative"),
        CheckConstraint(
            "soft_limit IS NULL OR hard_limit IS NULL OR soft_limit <= hard_limit",
            name="soft_not_above_hard",
        ),
        {"comment": "配额策略：租户某指标的软/硬上限，超出软限告警、超出硬限阻断"},
    )

    metric: Mapped[str] = mapped_column(
        String(48), nullable=False,
        comment="指标：ARTICLES_GENERATED/ARTICLES_PUBLISHED/SOURCES_COLLECTED/INPUT_TOKENS/OUTPUT_TOKENS/AI_COST/MAX_CONCURRENT_RUNS",
    )
    period_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MONTHLY", comment="周期类型：DAILY / MONTHLY / ROLLING_30D"
    )
    soft_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True, comment="软上限，触达后告警但不阻断"
    )
    hard_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 4), nullable=True, comment="硬上限，触达后阻断相关操作"
    )
    overage_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否允许超额（超额后仅计费不阻断）"
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Asia/Shanghai",
        comment="计算周期边界所用时区，实际存储时间仍为 UTC",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE", comment="状态：ACTIVE 生效 / DISABLED 停用"
    )


class QuotaUsageBucket(TenantEntityMixin, Base):
    """A rebuildable usage summary for one metric within one period."""

    __tablename__ = "quota_usage_bucket"
    __table_args__ = (
        UniqueConstraint("tenant_id", "metric", "period_start", name="uq_quota_bucket_tenant_metric_start"),
        Index("ix_quota_bucket_tenant_period", "tenant_id", "period_start"),
        {"comment": "配额用量桶：按指标与周期汇总的已用/预占用量，账本为真相源、桶可重建"},
    )

    metric: Mapped[str] = mapped_column(String(48), nullable=False, comment="指标")
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="周期开始时间（UTC）"
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="周期结束时间（UTC，不含）"
    )
    reserved_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=0, comment="已预占但未结算的用量"
    )
    used_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 4), nullable=False, default=0, comment="已结算用量"
    )
