"""State machine guards, If-Match parsing and action authorization.

None of this needs a database: the state machine is pure and the rows are built
in memory, which is exactly why the rules live outside the repository.
"""

from uuid import uuid4

import pytest

from aipy.modules.authorization.domain.models import (
    AuthorizationPolicy,
    DataScope,
    DataScopeGrant,
    PermissionGrant,
)
from aipy.modules.authorization.infrastructure.role_catalog import grants_for_role
from aipy.modules.authorization.service import AuthorizationService
from aipy.modules.content.models import ContentRun, HumanTask
from aipy.modules.content.state_machine import (
    plan_content_transition,
    plan_task_transition,
    task_status_label,
)
from aipy.shared.security.context import ActorContext, ActorType, TenantContext
from apps.api.errors import ActionError
from apps.api.repositories import (
    CONTENT_RESOURCE,
    REVIEW_RESOURCE,
    _require_permission,
    ensure_supported,
    parse_expected_version,
)

TENANT_ID = uuid4()
ACTOR_ID = uuid4()


class StaticPolicyRepository:
    def __init__(self, policy: AuthorizationPolicy | None) -> None:
        self._policy = policy

    def get_policy(self, subject: TenantContext) -> AuthorizationPolicy | None:
        return self._policy


def policy_for(role: str) -> AuthorizationPolicy:
    return AuthorizationPolicy(
        permission_grants=tuple(
            PermissionGrant(
                permission=permission,
                data_scopes=(DataScopeGrant(scope=DataScope.TENANT_ALL),),
            )
            for permission in grants_for_role(role)
        )
    )


def authorizer(role: str) -> AuthorizationService:
    return AuthorizationService(StaticPolicyRepository(policy_for(role)))


def subject() -> TenantContext:
    return TenantContext(
        tenant_id=TENANT_ID,
        actor=ActorContext(actor_id=ACTOR_ID, actor_type=ActorType.USER),
        request_id="req-1",
    )


def content_run(status: str = "RUNNING", *, created_by=None) -> ContentRun:
    return ContentRun(
        tenant_id=TENANT_ID,
        code="CR-1",
        seq=1,
        title="测试内容",
        brand="远山商业",
        stage_label="分段写作",
        status_label="运行中",
        status=status,
        tone="info",
        owner="林编辑",
        updated_at_label="刚刚",
        allowed_actions=[],
        created_by=created_by,
    )


def human_task(status: str = "CLAIMED", *, created_by=None) -> HumanTask:
    return HumanTask(
        tenant_id=TENANT_ID,
        code="HT-1",
        seq=1,
        title="审核大纲",
        type="大纲审核",
        reason="需要人工确认",
        priority="高",
        brand="慢游计划",
        owner="已分配给你",
        due_label="今天 14:30 到期",
        status=status,
        allowed_actions=[],
        created_by=created_by,
    )


@pytest.mark.parametrize(
    ("action", "current", "expected"),
    [
        ("pause", "RUNNING", "PAUSED"),
        ("pause", "WAITING_HUMAN", "PAUSED"),
        ("resume", "PAUSED", "RUNNING"),
        ("rerun", "FAILED", "RUNNING"),
        ("rerun", "COMPLETED", "RUNNING"),
        ("cancel", "RUNNING", "CANCELLED"),
    ],
)
def test_allowed_content_transitions(action: str, current: str, expected: str) -> None:
    transition = plan_content_transition(action, current)

    assert transition is not None
    assert transition.status == expected


@pytest.mark.parametrize(
    ("action", "current"),
    [("pause", "COMPLETED"), ("resume", "RUNNING"), ("cancel", "COMPLETED"), ("rerun", "RUNNING")],
)
def test_illegal_content_transitions(action: str, current: str) -> None:
    assert plan_content_transition(action, current) is None


def test_transition_carries_display_fields() -> None:
    transition = plan_content_transition("pause", "RUNNING")

    assert transition is not None
    assert (transition.label, transition.tone) == ("已暂停", "warning")


@pytest.mark.parametrize(
    ("action", "current", "status", "decision"),
    [
        ("claim", "OPEN", "CLAIMED", None),
        ("reassign", "CLAIMED", "OPEN", None),
        ("approve", "CLAIMED", "COMPLETED", "APPROVE"),
        ("reject", "CLAIMED", "COMPLETED", "REJECT"),
        ("submit", "CLAIMED", "COMPLETED", "EDIT_AND_APPROVE"),
    ],
)
def test_task_transitions(action: str, current: str, status: str, decision: str | None) -> None:
    transition = plan_task_transition(action, current)

    assert transition is not None
    assert (transition.status, transition.decision) == (status, decision)


def test_finished_task_cannot_be_approved_again() -> None:
    assert plan_task_transition("approve", "COMPLETED") is None


def test_task_status_label_is_chinese() -> None:
    assert task_status_label("CLAIMED") == "处理中"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ('"CR-20260724-018-v3"', 3),
        ('W/"CR-20260724-018-v12"', 12),
        ("*", None),
        (None, None),
    ],
)
def test_if_match_parsing(header: str | None, expected: int | None) -> None:
    assert parse_expected_version(header) == expected


def test_malformed_if_match_is_a_client_error() -> None:
    with pytest.raises(ActionError) as excinfo:
        parse_expected_version('"not-an-etag"')

    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "invalid_precondition"


def test_unsupported_action_is_rejected_before_any_lookup() -> None:
    with pytest.raises(ActionError) as excinfo:
        ensure_supported("export", CONTENT_RESOURCE)

    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "unsupported_action"


def test_viewer_cannot_pause_a_run() -> None:
    with pytest.raises(ActionError) as excinfo:
        _require_permission(authorizer("成员"), subject(), CONTENT_RESOURCE, "pause", content_run())

    assert excinfo.value.status_code == 403
    assert excinfo.value.code == "permission_missing"


def test_editor_can_pause_a_run() -> None:
    _require_permission(authorizer("编辑"), subject(), CONTENT_RESOURCE, "pause", content_run())


def test_creator_cannot_approve_their_own_task() -> None:
    """Separation of duties must block the write, not just hide the button."""

    with pytest.raises(ActionError) as excinfo:
        _require_permission(
            authorizer("审核员"),
            subject(),
            REVIEW_RESOURCE,
            "approve",
            human_task(created_by=ACTOR_ID),
        )

    assert excinfo.value.status_code == 403
    assert excinfo.value.code == "separation_of_duties"
