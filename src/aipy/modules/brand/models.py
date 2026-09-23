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
        {"comment": "工作区：租户下的内容协作空间，品牌与内容任务均归属于某个工作区"},
    )

    code: Mapped[str] = mapped_column(CITEXT(), nullable=False, comment="工作区编码，租户内唯一")
    name: Mapped[str] = mapped_column(String(160), nullable=False, comment="工作区名称")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        comment="状态：ACTIVE 启用 / ARCHIVED 已归档",
    )
    default_brand_id: Mapped[UUID | None] = mapped_column(
        nullable=True, comment="默认品牌 ID，新建内容时作为默认品牌"
    )
    created_by_membership_id: Mapped[UUID] = mapped_column(
        nullable=False, comment="创建者对应的租户成员 ID"
    )


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
        {"comment": "品牌：内容生产所遵循的品牌设定，含口吻规范与禁用词"},
    )

    workspace_id: Mapped[UUID] = mapped_column(nullable=False, comment="所属工作区 ID")
    name: Mapped[str] = mapped_column(
        String(160), nullable=False, comment="品牌名称，同一工作区内唯一"
    )
    description: Mapped[str | None] = mapped_column(Text, comment="品牌描述")
    tone_guideline: Mapped[str | None] = mapped_column(
        Text, comment="品牌口吻规范，供生成内容时约束语气风格"
    )
    prohibited_terms: Mapped[list[str]] = mapped_column(
        ARRAY(String()),
        nullable=False,
        default=list,
        comment="禁用词列表，生成内容时禁止出现",
    )
    default_language: Mapped[str] = mapped_column(
        String(20), nullable=False, default="zh-CN", comment="品牌默认输出语言"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", comment="状态：ACTIVE 启用 / INACTIVE 停用"
    )
