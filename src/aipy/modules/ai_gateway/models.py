"""AI governance ORM models: providers, model catalog, and tenant credentials.

Security contract for credentials: the raw secret is NEVER persisted or returned.
Only a masked preview (e.g. ``sk-…a1b2``) and a SHA-256 fingerprint are stored so
the UI can show "which key" without ever exposing it. Rotation is implementable by
comparing the new fingerprint against the stored one.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from aipy.shared.db import Base, EntityMixin, TenantEntityMixin


class ModelProvider(EntityMixin, Base):
    """A global LLM/provider vendor (e.g. OpenAI-compatible, Anthropic, Qwen)."""

    __tablename__ = "model_provider"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="status_allowed"),
        {"comment": "模型供应商：全局定义的服务商，如 OpenAI 兼容、Anthropic、通义千问"},
    )

    code: Mapped[str] = mapped_column(
        CITEXT(), nullable=False, unique=True, comment="供应商编码，全局唯一（如 openai-compatible）"
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="供应商名称")
    api_style: Mapped[str] = mapped_column(
        String(32), nullable=False, default="OPENAI_COMPATIBLE",
        comment="接口风格：OPENAI_COMPATIBLE / ANTHROPIC / GEMINI / CUSTOM",
    )
    base_url: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="默认 API 基础地址，BYOK 时可被租户覆盖"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE", comment="状态：ACTIVE 启用 / DISABLED 停用"
    )


class ModelDefinition(EntityMixin, Base):
    """A concrete model offered by a provider, with versioned pricing."""

    __tablename__ = "model_definition"
    __table_args__ = (
        UniqueConstraint("provider_id", "model_code", name="uq_model_definition_provider_code"),
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="status_allowed"),
        Index("ix_model_definition_provider", "provider_id"),
        {"comment": "模型定义：某供应商下的具体模型及其能力与价格（价格按有效期版本化）"},
    )

    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_provider.id", ondelete="RESTRICT"), nullable=False, comment="所属供应商 ID"
    )
    model_code: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="供应商标识下的模型编码，如 gpt-4o-mini"
    )
    display_name: Mapped[str] = mapped_column(String(160), nullable=False, comment="展示名称")
    capability_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="CHAT", comment="能力类型：CHAT / EMBEDDING / RERANK"
    )
    context_window: Mapped[int] = mapped_column(
        Integer, nullable=False, default=8192, comment="上下文窗口 token 上限"
    )
    supports_structured_output: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否支持结构化输出（JSON Schema）"
    )
    input_price_per_million: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=0, comment="输入价格（每百万 token）"
    )
    output_price_per_million: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=0, comment="输出价格（每百万 token）"
    )
    currency_code: Mapped[str] = mapped_column(
        String(8), nullable=False, default="CNY", comment="计价货币"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE", comment="状态：ACTIVE 启用 / DISABLED 停用"
    )


class TenantModelCredential(TenantEntityMixin, Base):
    """A tenant's credential reference for a provider (platform-managed or BYOK).

    The secret itself is not stored here: ``secret_masked`` holds a display-only
    preview and ``secret_fingerprint`` a SHA-256 digest used for rotation checks.
    A real deployment resolves the raw secret from a secrets manager via
    ``credential_ref``.
    """

    __tablename__ = "tenant_model_credential"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_id", "name", name="uq_tmc_tenant_provider_name"),
        CheckConstraint("ownership_type IN ('PLATFORM', 'BYOK')", name="ownership_allowed"),
        CheckConstraint("status IN ('ACTIVE', 'INVALID', 'REVOKED')", name="status_allowed"),
        Index("ix_tmc_tenant_provider", "tenant_id", "provider_id"),
        {"comment": "租户模型凭证：引用平台托管或租户自有（BYOK）密钥，密钥只写不读"},
    )

    provider_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_provider.id", ondelete="RESTRICT"), nullable=False, comment="关联供应商 ID"
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False, comment="凭证名称，租户内可读")
    ownership_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="BYOK",
        comment="归属类型：PLATFORM 平台托管 / BYOK 租户自有",
    )
    secret_masked: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="密钥掩码预览（仅展示，如 sk-…a1b2），不存明文"
    )
    secret_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="密钥 SHA-256 指纹，用于轮换检测，不可逆推明文"
    )
    credential_ref: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="密钥管理器引用（如 vault://...），真实调用时解析明文"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE",
        comment="状态：ACTIVE 有效 / INVALID 验证失败 / REVOKED 已吊销",
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="最近一次验证通过时间"
    )
    last_verify_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="最近一次验证结果说明"
    )


class ModelRoutePolicy(TenantEntityMixin, Base):
    """A per-task-type routing policy: primary model plus bounded fallbacks."""

    __tablename__ = "model_route_policy"
    __table_args__ = (
        UniqueConstraint("tenant_id", "task_type", name="uq_mrp_tenant_task_type"),
        CheckConstraint("status IN ('ACTIVE', 'DISABLED')", name="status_allowed"),
        {"comment": "模型路由策略：按任务类型配置主模型、降级模型、预算与超时"},
    )

    task_type: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="任务类型标识，如 BRIEF / OUTLINE_BUILD / DRAFT_WRITE"
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False, comment="策略名称")
    daily_cost_limit: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True, comment="该任务类型每日成本上限，为空表示不限制"
    )
    per_call_timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, comment="单次调用超时秒数"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE", comment="状态：ACTIVE 启用 / DISABLED 停用"
    )


class ModelRouteCandidate(TenantEntityMixin, Base):
    """An ordered candidate model within a routing policy (priority 1 = primary)."""

    __tablename__ = "model_route_candidate"
    __table_args__ = (
        UniqueConstraint("tenant_id", "policy_id", "priority", name="uq_mrc_tenant_policy_priority"),
        {"comment": "模型路由候选：一条策略下的主模型与降级模型，按 priority 升序尝试"},
    )

    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_route_policy.id", ondelete="CASCADE"), nullable=False, comment="所属策略 ID"
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="优先级，从 1 开始，1 为主模型"
    )
    model_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_definition.id", ondelete="RESTRICT"), nullable=False, comment="候选模型 ID"
    )
    credential_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("tenant_model_credential.id", ondelete="RESTRICT"),
        nullable=True, comment="使用的租户凭证 ID，为空表示使用平台托管凭证",
    )
    temperature: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), nullable=False, default=Decimal("0.70"), comment="采样温度 0.00-1.00"
    )
    max_output_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2048, comment="单次最大输出 token 数"
    )
    allowed_for_publish: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否允许用于对外发布的高质量节点"
    )
