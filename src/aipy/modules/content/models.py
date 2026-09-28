"""Content production ORM models: workflow runs, human tasks, and materials."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from aipy.shared.db import Base, TenantEntityMixin

CONTENT_STATUSES = (
    "DRAFT",
    "RUNNING",
    "WAITING_HUMAN",
    "PAUSED",
    "FAILED",
    "COMPLETED",
    "CANCELLED",
)
HUMAN_TASK_STATUSES = ("OPEN", "CLAIMED", "COMPLETED", "CANCELLED", "EXPIRED")
HUMAN_TASK_DECISIONS = (
    "APPROVE",
    "EDIT_AND_APPROVE",
    "REJECT",
    "REQUEST_REWORK",
    "SKIP",
)


class ContentRun(TenantEntityMixin, Base):
    """A content production workflow run (the unit shown in the content board)."""

    __tablename__ = "content_run"
    __table_args__ = (
        # ``content_run_material`` references ``(tenant_id, id)``, and PostgreSQL
        # only accepts a composite foreign key when the referenced column list has
        # a matching unique constraint. ``id`` alone is the primary key, which is
        # not enough for the two-column reference.
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code", name="uq_content_run_tenant_code"),
        Index("ix_content_run_tenant_seq", "tenant_id", "seq"),
        CheckConstraint(
            "status IN ('DRAFT', 'RUNNING', 'WAITING_HUMAN', 'PAUSED', 'FAILED', "
            "'COMPLETED', 'CANCELLED')",
            name="status_allowed",
        ),
        {"comment": "内容任务：内容生产流程的一次执行实例，对应内容看板上的一行"},
    )

    code: Mapped[str] = mapped_column(
        CITEXT(),
        nullable=False,
        comment="任务编码，租户内唯一，对外作为 API 的 id 暴露（如 CR-20260724-018）",
    )
    seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="租户内递增序号，用于列表稳定排序"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="内容标题")
    brand: Mapped[str] = mapped_column(String(120), nullable=False, comment="所属品牌名称")
    stage_label: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="当前所处阶段的中文文案，如“分段写作”"
    )
    status_label: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="当前状态的中文文案，如“运行中”“等待人工”"
    )
    status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="RUNNING",
        comment="执行状态，状态机唯一事实源：DRAFT / RUNNING / WAITING_HUMAN / "
        "PAUSED / FAILED / COMPLETED / CANCELLED；status_label 仅用于展示",
    )
    tone: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="info",
        comment=(
            "前端展示色调：info 信息 / success 成功 / warning 警告 / danger 异常 / neutral 中性"
        ),
    )
    owner: Mapped[str] = mapped_column(String(120), nullable=False, comment="负责人显示名")
    content: Mapped[str | None] = mapped_column(
        Text, comment="生成的正文内容，由工作流执行（content.run.execute）回写；未执行时为空"
    )
    exported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="最近一次导出时间，导出动作成功后写入"
    )
    updated_at_label: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="最近更新的相对时间展示文案，如“2 分钟前”"
    )
    allowed_actions: Mapped[list[str]] = mapped_column(
        ARRAY(String()),
        nullable=False,
        default=list,
        comment="当前状态下前端允许的操作列表，如 view / pause / approve / reject / export / rerun",
    )


class HumanTask(TenantEntityMixin, Base):
    """A human-in-the-loop task awaiting an editor/reviewer action."""

    __tablename__ = "human_task"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_human_task_tenant_code"),
        Index("ix_human_task_tenant_seq", "tenant_id", "seq"),
        CheckConstraint(
            "status IN ('OPEN', 'CLAIMED', 'COMPLETED', 'CANCELLED', 'EXPIRED')",
            name="status_allowed",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('APPROVE', 'EDIT_AND_APPROVE', 'REJECT', "
            "'REQUEST_REWORK', 'SKIP')",
            name="decision_allowed",
        ),
        {"comment": "人工任务：流程中需要人工介入的待办，如大纲审核、事实核查、异常处理"},
    )

    code: Mapped[str] = mapped_column(
        CITEXT(), nullable=False, comment="任务编码，租户内唯一（如 HT-201）"
    )
    seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="租户内递增序号，用于列表稳定排序"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="任务标题")
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="任务类型，如“大纲审核”“事实核查”“异常处理”"
    )
    reason: Mapped[str] = mapped_column(
        Text, nullable=False, comment="触发该人工任务的原因说明，供处理人判断"
    )
    priority: Mapped[str] = mapped_column(
        String(16), nullable=False, default="普通", comment="优先级文案：普通 / 高"
    )
    brand: Mapped[str] = mapped_column(String(120), nullable=False, comment="所属品牌名称")
    owner: Mapped[str] = mapped_column(
        String(120), nullable=False, comment="处理人展示文案，如“已分配给你”“团队任务”"
    )
    due_label: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="截止时间展示文案，如“今天 14:30 到期”"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="OPEN",
        comment="任务状态：OPEN 待领取 / CLAIMED 已领取 / COMPLETED 已处理 / "
        "CANCELLED 已撤销 / EXPIRED 已超时",
    )
    decision: Mapped[str | None] = mapped_column(
        String(24),
        comment="处理结论：APPROVE / EDIT_AND_APPROVE / REJECT / REQUEST_REWORK / SKIP，"
        "未处理时为空",
    )
    assignee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), comment="当前处理人用户 ID，领取或转派时写入"
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="领取租约到期时间，到期后可被他人重新领取"
    )
    allowed_actions: Mapped[list[str]] = mapped_column(
        ARRAY(String()),
        nullable=False,
        default=list,
        comment="允许的操作列表，如 approve / reject / reassign / submit / claim",
    )


class Material(TenantEntityMixin, Base):
    """A retrieved source / reference material in the library."""

    __tablename__ = "material"
    __table_args__ = (
        # Referenced by ``content_run_material`` and ``material_file`` as
        # ``(tenant_id, id)``; see the note on ``ContentRun``.
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "code", name="uq_material_tenant_code"),
        Index("ix_material_tenant_seq", "tenant_id", "seq"),
        {"comment": "素材：检索到的可引用来源资料，供内容生成时引用与核查"},
    )

    code: Mapped[str] = mapped_column(
        CITEXT(), nullable=False, comment="素材编码，租户内唯一（如 MAT-301）"
    )
    seq: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="租户内递增序号，用于列表稳定排序"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="素材标题")
    summary: Mapped[str] = mapped_column(Text, nullable=False, comment="素材摘要")
    source: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="来源标识，如域名或“人工上传”"
    )
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="素材类型，如 PDF / 网页 / DOCX / XLSX"
    )
    trust_label: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="可信度标签，如“高可信”“官方来源”“内部资料”“待复核”"
    )
    tone: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="neutral",
        comment=(
            "前端展示色调：info 信息 / success 成功 / warning 警告 / danger 异常 / neutral 中性"
        ),
    )
    updated_at_label: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="最近更新的相对时间展示文案，如“今天 10:16”"
    )
    allowed_actions: Mapped[list[str]] = mapped_column(
        ARRAY(String()),
        nullable=False,
        default=list,
        comment="允许的操作列表，如 view / edit",
    )


class ContentExport(TenantEntityMixin, Base):
    """An exported artifact produced by the ``export`` action on a content run."""

    __tablename__ = "content_export"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        Index("ix_content_export_tenant_run", "tenant_id", "run_id"),
        {"comment": "内容导出产物：每次导出生成一条记录，保存可下载的成品文本（如 markdown）"},
    )

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("content_run.id", ondelete="CASCADE"), comment="关联的内容任务 ID"
    )
    run_code: Mapped[str] = mapped_column(
        CITEXT(), nullable=False, comment="关联任务编码，便于阅读与排查"
    )
    format: Mapped[str] = mapped_column(
        String(16), nullable=False, default="markdown", comment="产物格式：markdown / docx"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="导出标题")
    payload: Mapped[str] = mapped_column(
        Text, nullable=False, comment="导出成品正文（markdown 源）"
    )


class ContentRunMaterial(TenantEntityMixin, Base):
    """Link between a content run and a source material collected for it."""

    __tablename__ = "content_run_material"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint(
            "tenant_id", "run_id", "material_id", name="uq_content_run_material_run_material"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "run_id"],
            ["content_run.tenant_id", "content_run.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "material_id"],
            ["material.tenant_id", "material.id"],
            ondelete="CASCADE",
        ),
        {"comment": "内容任务与素材的关联：采集动作写入，记录该任务引用的参考来源"},
    )

    run_id: Mapped[UUID] = mapped_column(nullable=False, comment="内容任务 ID")
    material_id: Mapped[UUID] = mapped_column(nullable=False, comment="素材 ID")


class MaterialFile(TenantEntityMixin, Base):
    """The original bytes behind an uploaded material.

    Files are stored in the database rather than on the local disk: the API has no
    object store, and keeping the bytes in a tenant-scoped table means RLS protects
    them exactly like every other row and there is no shared volume to provision.
    """

    __tablename__ = "material_file"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id"),
        UniqueConstraint("tenant_id", "material_id", name="uq_material_file_material"),
        ForeignKeyConstraint(
            ["tenant_id", "material_id"],
            ["material.tenant_id", "material.id"],
            ondelete="CASCADE",
        ),
        {"comment": "素材原件：人工上传文件的字节内容，供下载与后续解析"},
    )

    material_id: Mapped[UUID] = mapped_column(nullable=False, comment="关联的素材 ID")
    filename: Mapped[str] = mapped_column(String(255), nullable=False, comment="上传时的原始文件名")
    content_type: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="上传时的 MIME 类型，用于下载响应头"
    )
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False, comment="文件字节数")
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, comment="文件的原始字节内容")
