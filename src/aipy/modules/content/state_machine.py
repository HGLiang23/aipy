"""Workflow state transitions for content runs and human tasks.

The rules follow ``docs/02-workflow-state-machine.md`` (sections 4.2 and 8):
every transition is driven by the machine-readable ``status`` column, guarded by
the state it starts from, and applied together with the caller's
``expected_version`` so concurrent writers cannot silently overwrite each other.

This module is deliberately pure - it never touches the database - so the whole
matrix can be unit-tested without a session.
"""

from dataclasses import dataclass
from enum import StrEnum

TERMINAL_CONTENT_STATUSES = frozenset({"COMPLETED", "CANCELLED"})


class ContentStatus(StrEnum):
    DRAFT = "DRAFT"
    RUNNING = "RUNNING"
    WAITING_HUMAN = "WAITING_HUMAN"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskStatus(StrEnum):
    OPEN = "OPEN"
    CLAIMED = "CLAIMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TaskDecision(StrEnum):
    APPROVE = "APPROVE"
    EDIT_AND_APPROVE = "EDIT_AND_APPROVE"
    REJECT = "REJECT"
    REQUEST_REWORK = "REQUEST_REWORK"
    SKIP = "SKIP"


# action -> (states it may start from, resulting state)
CONTENT_TRANSITIONS: dict[str, tuple[frozenset[ContentStatus], ContentStatus]] = {
    "pause": (
        frozenset({ContentStatus.RUNNING, ContentStatus.WAITING_HUMAN}),
        ContentStatus.PAUSED,
    ),
    "resume": (frozenset({ContentStatus.PAUSED}), ContentStatus.RUNNING),
    "rerun": (
        frozenset({ContentStatus.FAILED, ContentStatus.COMPLETED}),
        ContentStatus.RUNNING,
    ),
    "cancel": (
        frozenset(
            {
                ContentStatus.DRAFT,
                ContentStatus.RUNNING,
                ContentStatus.WAITING_HUMAN,
                ContentStatus.PAUSED,
                ContentStatus.FAILED,
            }
        ),
        ContentStatus.CANCELLED,
    ),
}

TASK_TRANSITIONS: dict[str, tuple[frozenset[TaskStatus], TaskStatus]] = {
    "claim": (frozenset({TaskStatus.OPEN}), TaskStatus.CLAIMED),
    "reassign": (
        frozenset({TaskStatus.OPEN, TaskStatus.CLAIMED}),
        TaskStatus.OPEN,
    ),
    "submit": (frozenset({TaskStatus.CLAIMED}), TaskStatus.COMPLETED),
    "approve": (frozenset({TaskStatus.OPEN, TaskStatus.CLAIMED}), TaskStatus.COMPLETED),
    "reject": (frozenset({TaskStatus.OPEN, TaskStatus.CLAIMED}), TaskStatus.COMPLETED),
}

# action -> decision recorded on the human task
TASK_DECISIONS: dict[str, TaskDecision] = {
    "approve": TaskDecision.APPROVE,
    "submit": TaskDecision.EDIT_AND_APPROVE,
    "reject": TaskDecision.REJECT,
}

# status -> (Chinese label shown on the board, tone used by the frontend)
CONTENT_DISPLAY: dict[ContentStatus, tuple[str, str]] = {
    ContentStatus.DRAFT: ("草稿", "neutral"),
    ContentStatus.RUNNING: ("运行中", "info"),
    ContentStatus.WAITING_HUMAN: ("等待人工", "warning"),
    ContentStatus.PAUSED: ("已暂停", "warning"),
    ContentStatus.FAILED: ("需要处理", "danger"),
    ContentStatus.COMPLETED: ("已完成", "success"),
    ContentStatus.CANCELLED: ("已取消", "neutral"),
}

TASK_DISPLAY: dict[TaskStatus, tuple[str, str]] = {
    TaskStatus.OPEN: ("待领取", "warning"),
    TaskStatus.CLAIMED: ("处理中", "info"),
    TaskStatus.COMPLETED: ("已处理", "success"),
    TaskStatus.CANCELLED: ("已撤销", "neutral"),
    TaskStatus.EXPIRED: ("已超时", "danger"),
}


@dataclass(frozen=True)
class Transition:
    """What an action does to a row: new status plus its display fields."""

    status: str
    label: str
    tone: str
    decision: str | None = None


def _content_status(value: str) -> ContentStatus | None:
    try:
        return ContentStatus(value)
    except ValueError:
        return None


def _task_status(value: str) -> TaskStatus | None:
    try:
        return TaskStatus(value)
    except ValueError:
        return None


def plan_content_transition(action: str, current_status: str) -> Transition | None:
    """Return the transition for ``action``, or ``None`` when it is not allowed."""

    transition = CONTENT_TRANSITIONS.get(action)
    current = _content_status(current_status)
    if transition is None or current is None or current not in transition[0]:
        return None
    target = transition[1]
    label, tone = CONTENT_DISPLAY[target]
    return Transition(status=target.value, label=label, tone=tone)


def plan_task_transition(action: str, current_status: str) -> Transition | None:
    transition = TASK_TRANSITIONS.get(action)
    current = _task_status(current_status)
    if transition is None or current is None or current not in transition[0]:
        return None
    target = transition[1]
    label, tone = TASK_DISPLAY[target]
    decision = TASK_DECISIONS.get(action)
    return Transition(
        status=target.value,
        label=label,
        tone=tone,
        decision=decision.value if decision is not None else None,
    )


def content_status_label(status: str) -> tuple[str, str]:
    """Display label and tone for a content run status."""

    resolved = _content_status(status)
    if resolved is None:
        return (status, "neutral")
    return CONTENT_DISPLAY[resolved]


def task_status_label(status: str) -> str:
    """Display label for a human task status."""

    resolved = _task_status(status)
    if resolved is None:
        return status
    return TASK_DISPLAY[resolved][0]
