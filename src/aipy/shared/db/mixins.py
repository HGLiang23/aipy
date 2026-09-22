"""Reusable persistence columns for identity, auditing, tenancy, and locking."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Uuid, func, text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from aipy.shared.db.ids import new_uuid7


class UUIDPrimaryKeyMixin:
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid7)


class TimestampAuditMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class OptimisticLockMixin:
    row_version: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
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
        )


class EntityMixin(UUIDPrimaryKeyMixin, TimestampAuditMixin, OptimisticLockMixin):
    """Common columns for global entities."""


class TenantEntityMixin(TenantScopedMixin, EntityMixin):
    """Common columns for tenant-owned entities."""
