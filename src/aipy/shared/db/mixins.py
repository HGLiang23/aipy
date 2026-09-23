"""Reusable persistence columns for identity, auditing, tenancy, and locking."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Uuid, func, text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from aipy.shared.db.ids import new_uuid7


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=new_uuid7,
        comment="主键，UUIDv7（时间有序），由应用生成",
    )


class TimestampAuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间（数据库时区为 UTC）",
    )
    created_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="创建人用户 ID，系统自动创建时为空",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="最后更新时间",
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="最后更新人用户 ID，系统自动更新时为空",
    )


class OptimisticLockMixin:
    row_version: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="乐观锁版本号，每次更新自增 1，用于并发冲突检测",
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, object]:
        return {
            "version_id_col": cls.row_version,
            "version_id_generator": lambda current: 0 if current is None else current + 1,
        }


class TenantScopedMixin:
    @declared_attr
    def tenant_id(cls) -> Mapped[UUID]:
        return mapped_column(
            Uuid(as_uuid=True),
            ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
            comment="所属租户 ID，行级安全策略（RLS）的隔离依据",
        )


class EntityMixin(UUIDPrimaryKeyMixin, TimestampAuditMixin, OptimisticLockMixin):
    """Common columns for global entities."""


class TenantEntityMixin(TenantScopedMixin, EntityMixin):
    """Common columns for tenant-owned entities."""
