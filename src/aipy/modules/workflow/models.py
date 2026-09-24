"""Workflow template ORM models: templates and immutable published versions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aipy.shared.db import Base, TenantEntityMixin


class WorkflowTemplate(TenantEntityMixin, Base):
    """A content production workflow template a tenant can copy and customize.

    System templates are seeded per tenant with ``category = 'SYSTEM'``; tenants
    copy them into editable ``TENANT`` templates. The active version is tracked
    by ``current_version_id``.
    """

    __tablename__ = "workflow_template"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_workflow_template_tenant_code"),
        Index("ix_workflow_template_tenant_category", "tenant_id", "category"),
        {"comment": "工作流模板：租户可复制系统模板并逐节点定制"},
    )

    code: Mapped[str] = mapped_column(
        CITEXT(), nullable=False, comment="模板编码，租户内唯一（如 WT-ASSISTED）"
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False, comment="模板名称")
    category: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="TENANT",
        comment="模板类别：SYSTEM 系统内置 / TENANT 租户自定义",
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="DRAFT",
        comment="模板状态：DRAFT 草稿 / PUBLISHED 已发布 / ARCHIVED 已归档",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="模板说明")
    current_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
        comment="当前生效版本 ID（指向 workflow_template_version.id），非外键以避免循环依赖",
    )


class WorkflowTemplateVersion(TenantEntityMixin, Base):
    """An immutable, published configuration snapshot of a workflow template.

    Node-level configuration (execution mode, retries, quality thresholds, model
    routing) is stored as a JSON array in ``nodes`` to keep the MVP schema lean;
    running instances snapshot this version so later edits never affect them.
    """

    __tablename__ = "workflow_template_version"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "template_id", "version_no",
            name="uq_wftv_tenant_template_version",
        ),
        {"comment": "工作流模板版本：发布后不可变，运行实例保存版本与策略快照"},
    )

    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("workflow_template.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属模板 ID",
    )
    version_no: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="版本序号，从 1 开始递增"
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="DRAFT",
        comment="版本状态：DRAFT 草稿 / PUBLISHED 已发布",
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="版本说明")
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="发布时间"
    )
    published_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, comment="发布人用户 ID"
    )
    nodes: Mapped[list | None] = mapped_column(
        JSONB, nullable=True, comment="节点配置数组，每项为单个节点的执行与策略配置"
    )
    policy: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="解析后的策略快照（模型路由、配额、安全阈值等）"
    )
