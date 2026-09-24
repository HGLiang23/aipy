"""Audit trail ORM model.

``AuditEvent`` is append-only by contract: the application may only INSERT and
SELECT. The migration revokes UPDATE/DELETE from the runtime DB role so the
guarantee holds even if application code tries to mutate a row.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Index, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from aipy.shared.db import Base, TenantEntityMixin


class AuditEvent(TenantEntityMixin, Base):
    """A single immutable record of a tenant-scoped operation."""

    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_event_tenant_occurred", "tenant_id", "occurred_at"),
        Index(
            "ix_audit_event_tenant_resource",
            "tenant_id", "resource_type", "resource_id", "occurred_at",
        ),
        Index("ix_audit_event_trace", "trace_id"),
        {"comment": "操作审计：关键操作的只追加记录，保留操作者、对象版本、前后差异和请求链路"},
    )

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), comment="事件发生时间"
    )
    actor_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="USER", comment="操作者类型：USER / SYSTEM / PLATFORM"
    )
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, comment="操作者用户 ID，系统事件为空"
    )
    actor_label: Mapped[str | None] = mapped_column(
        String(160), nullable=True, comment="操作者显示名快照，避免成员改名后审计失真"
    )
    action: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="动作标识，如 member.update / role.update / workflow.publish"
    )
    resource_type: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="资源类型，如 member / role / workflow_template"
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="资源标识（通常为资源主键或业务编码）"
    )
    resource_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, comment="资源版本 ID（如发布版本），无版本时为 NULL"
    )
    request_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="请求链路 ID，用于关联同一次请求的多条审计"
    )
    trace_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="分布式追踪 ID"
    )
    ip_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="客户端 IP 的哈希，避免明文存储敏感网络信息"
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="客户端 User-Agent"
    )
    reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="操作原因，高风险动作必填"
    )
    result: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SUCCESS", comment="操作结果：SUCCESS / FAILURE / DENIED"
    )
    before_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="变更前数据快照（已脱敏）"
    )
    after_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="变更后数据快照（已脱敏）"
    )
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, comment="附加元数据"
    )
