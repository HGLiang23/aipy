"""Role-based access control persistence models."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from aipy.shared.db import Base, TenantEntityMixin


class Role(TenantEntityMixin, Base):
    __tablename__ = "role"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code"),
        UniqueConstraint("tenant_id", "name"),
        {"comment": "角色：租户内定义的权限集合模板，分配给成员后决定其可执行的操作"},
    )

    code: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="角色编码，租户内唯一，如 admin、editor、reviewer"
    )
    name: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="角色显示名称"
    )
    description: Mapped[str | None] = mapped_column(
        Text, comment="角色描述"
    )
    is_builtin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="是否为系统内置角色，内置角色不可删除"
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="是否为默认角色，新成员自动获得此角色"
    )

    # relationships
    permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan",
        lazy="selectin",
    )
    memberships: Mapped[list["TenantMembership"]] = relationship(
        "TenantMembership", back_populates="role",
    )


class RolePermission(Base):
    __tablename__ = "role_permission"
    __table_args__ = (
        UniqueConstraint("role_id", "permission_code"),
        {"comment": "角色权限关联：定义每个角色拥有的具体权限码"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"), nullable=False,
        comment="关联的角色 ID"
    )
    permission_code: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="权限码，格式 resource:action"
    )
    data_scope: Mapped[str | None] = mapped_column(
        String(50), default="TENANT_ALL",
        comment="该权限的数据范围，如 TENANT_ALL、TEAM、CREATED_BY_ME 等"
    )

    # relationships
    role: Mapped["Role"] = relationship("Role", back_populates="permissions")
