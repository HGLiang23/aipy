"""Content production ORM models: workflow runs, human tasks, and materials."""

from sqlalchemy import Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from aipy.shared.db import Base, TenantEntityMixin


class ContentRun(TenantEntityMixin, Base):
    """A content production workflow run (the unit shown in the content board)."""

    __tablename__ = "content_run"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_content_run_tenant_code"),
        Index("ix_content_run_tenant_seq", "tenant_id", "seq"),
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
    tone: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="info",
        comment=(
            "前端展示色调：info 信息 / success 成功 / warning 警告 / danger 异常 / neutral 中性"
        ),
    )
    owner: Mapped[str] = mapped_column(String(120), nullable=False, comment="负责人显示名")
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
