"""Add workflow state columns to content_run and human_task.

Revision ID: 20260925_0007
Revises: 20260925_0006
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0007"
down_revision: str | None = "20260925_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The boards used to carry Chinese display labels only. The machine-readable
# status becomes the single source of truth for transitions, so existing rows are
# back-filled from the label they already show.
CONTENT_STATUS_BACKFILL = """
UPDATE content_run SET status = CASE status_label
    WHEN '运行中' THEN 'RUNNING'
    WHEN '等待人工' THEN 'WAITING_HUMAN'
    WHEN '已完成' THEN 'COMPLETED'
    WHEN '需要处理' THEN 'FAILED'
    WHEN '已暂停' THEN 'PAUSED'
    WHEN '已取消' THEN 'CANCELLED'
    ELSE 'RUNNING'
END
"""

HUMAN_TASK_STATUS_BACKFILL = """
UPDATE human_task SET status = CASE
    WHEN owner = '已分配给你' THEN 'CLAIMED'
    ELSE 'OPEN'
END
"""


def upgrade() -> None:
    op.add_column(
        "content_run",
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default=sa.text("'RUNNING'"),
            comment="执行状态，状态机唯一事实源：DRAFT / RUNNING / WAITING_HUMAN / "
            "PAUSED / FAILED / COMPLETED / CANCELLED；status_label 仅用于展示",
        ),
    )
    op.create_check_constraint(
        op.f("ck_content_run_status_allowed"),
        "content_run",
        "status IN ('DRAFT', 'RUNNING', 'WAITING_HUMAN', 'PAUSED', 'FAILED', "
        "'COMPLETED', 'CANCELLED')",
    )
    op.execute(sa.text(CONTENT_STATUS_BACKFILL))

    op.add_column(
        "human_task",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'OPEN'"),
            comment="任务状态：OPEN 待领取 / CLAIMED 已领取 / COMPLETED 已处理 / "
            "CANCELLED 已撤销 / EXPIRED 已超时",
        ),
    )
    op.add_column(
        "human_task",
        sa.Column(
            "decision",
            sa.String(length=24),
            nullable=True,
            comment="处理结论：APPROVE / EDIT_AND_APPROVE / REJECT / REQUEST_REWORK / "
            "SKIP，未处理时为空",
        ),
    )
    op.add_column(
        "human_task",
        sa.Column(
            "assignee_id",
            sa.Uuid(),
            nullable=True,
            comment="当前处理人用户 ID，领取或转派时写入",
        ),
    )
    op.add_column(
        "human_task",
        sa.Column(
            "lease_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="领取租约到期时间，到期后可被他人重新领取",
        ),
    )
    op.create_check_constraint(
        op.f("ck_human_task_status_allowed"),
        "human_task",
        "status IN ('OPEN', 'CLAIMED', 'COMPLETED', 'CANCELLED', 'EXPIRED')",
    )
    op.create_check_constraint(
        op.f("ck_human_task_decision_allowed"),
        "human_task",
        "decision IS NULL OR decision IN ('APPROVE', 'EDIT_AND_APPROVE', 'REJECT', "
        "'REQUEST_REWORK', 'SKIP')",
    )
    op.execute(sa.text(HUMAN_TASK_STATUS_BACKFILL))


def downgrade() -> None:
    op.execute(sa.text("UPDATE human_task SET status = 'OPEN'"))
    op.drop_constraint("ck_human_task_decision_allowed", "human_task", type_="check")
    op.drop_constraint("ck_human_task_status_allowed", "human_task", type_="check")
    op.drop_column("human_task", "lease_expires_at")
    op.drop_column("human_task", "assignee_id")
    op.drop_column("human_task", "decision")
    op.drop_column("human_task", "status")

    op.drop_constraint("ck_content_run_status_allowed", "content_run", type_="check")
    op.drop_column("content_run", "status")
