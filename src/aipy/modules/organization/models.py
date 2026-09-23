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
        {"comment": "平台用户：登录账号，跨租户全局唯一，不直接承载租户业务数据"},
    )

    email: Mapped[str] = mapped_column(
        CITEXT(), nullable=False, unique=True, comment="登录邮箱，大小写不敏感，全局唯一"
    )
    phone: Mapped[str | None] = mapped_column(
        String(32), comment="手机号，非空时全局唯一，可用于登录或通知"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="密码哈希（Argon2），永不返回给客户端"
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, comment="用户显示名称")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="ACTIVE",
        comment="状态：ACTIVE 正常 / DISABLED 已禁用 / LOCKED 已锁定",
    )
    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否启用多因素认证"
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="最近一次登录成功时间"
    )


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
        {"comment": "租户成员：平台用户在某个租户下的成员身份，是用户进入该租户的唯一入口"},
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="RESTRICT"), comment="关联的平台用户 ID"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="INVITED",
        comment="状态：INVITED 已邀请 / ACTIVE 正常 / SUSPENDED 已停用 / LEFT 已退出",
    )
    member_no: Mapped[str | None] = mapped_column(
        String(64), comment="租户内成员编号，非空时租户内唯一，用于对外展示"
    )
    job_title: Mapped[str | None] = mapped_column(String(120), comment="职位名称")
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="加入租户的时间，未加入时为空"
    )


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
        {"comment": "团队：租户内支持父子层级的组织单元，用于授权与数据范围划分"},
    )

    parent_team_id: Mapped[UUID | None] = mapped_column(
        nullable=True, comment="上级团队 ID，为空表示顶层团队"
    )
    code: Mapped[str] = mapped_column(CITEXT(), nullable=False, comment="团队编码，租户内唯一")
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="团队名称")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", comment="状态：ACTIVE 启用 / INACTIVE 停用"
    )


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
        {"comment": "团队成员：团队与租户成员的多对多关联关系"},
    )

    team_id: Mapped[UUID] = mapped_column(nullable=False, comment="关联的团队 ID")
    membership_id: Mapped[UUID] = mapped_column(nullable=False, comment="关联的租户成员 ID")
    is_manager: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否为该团队的负责人"
    )
