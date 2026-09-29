"""The board must expose actions computed by the authorization service.

These tests drive ``apps.api.repositories._allowed_actions`` with in-memory ORM
rows and a static policy, so the wiring is covered without a database: roles,
inactive tenants/actors and separation of duties all have to show up in what the
frontend receives.
"""

from uuid import UUID, uuid4

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
from aipy.shared.security.context import ActorContext, ActorType, TenantContext
from apps.api.repositories import (
    CONTENT_RESOURCE,
    REVIEW_RESOURCE,
    _allowed_actions,
)

TENANT_ID = uuid4()
ACTOR_ID = uuid4()

ALL_CONTENT_ACTIONS = [
    "view",
    "create",
    "edit",
    "assign",
    "pause",
    "resume",
    "rerun",
    "cancel",
    "export",
    "collect",
]


class StaticPolicyRepository:
    def __init__(self, policy: AuthorizationPolicy | None) -> None:
        self._policy = policy

    def get_policy(self, subject: TenantContext) -> AuthorizationPolicy | None:
        return self._policy


def policy_for(
    role: str, *, tenant_active: bool = True, actor_active: bool = True
) -> AuthorizationPolicy:
    return AuthorizationPolicy(
        tenant_active=tenant_active,
        actor_active=actor_active,
        permission_grants=tuple(
            PermissionGrant(
                permission=permission,
                data_scopes=(DataScopeGrant(scope=DataScope.TENANT_ALL),),
            )
            for permission in grants_for_role(role)
        ),
    )


def authorizer(policy: AuthorizationPolicy | None) -> AuthorizationService:
    return AuthorizationService(StaticPolicyRepository(policy))


def subject(actor_id: UUID = ACTOR_ID) -> TenantContext:
    return TenantContext(
        tenant_id=TENANT_ID,
        actor=ActorContext(actor_id=actor_id, actor_type=ActorType.USER),
        request_id="req-1",
    )


def content_run(*, created_by: UUID | None = None) -> ContentRun:
    return ContentRun(
        tenant_id=TENANT_ID,
        code="CR-1",
        seq=1,
        title="测试内容",
        brand="远山商业",
        stage_label="分段写作",
        status_label="运行中",
        tone="info",
        owner="林编辑",
        updated_at_label="刚刚",
        allowed_actions=[],
        created_by=created_by,
    )


def human_task(*, created_by: UUID | None = None) -> HumanTask:
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
        allowed_actions=[],
        created_by=created_by,
    )


def test_admin_receives_every_content_action() -> None:
    actions = _allowed_actions(
        authorizer(policy_for("租户管理员")), subject(), CONTENT_RESOURCE, content_run()
    )

    assert actions == ALL_CONTENT_ACTIONS


def test_editor_cannot_assign_content() -> None:
    actions = _allowed_actions(
        authorizer(policy_for("编辑")), subject(), CONTENT_RESOURCE, content_run()
    )

    assert "assign" not in actions
    assert actions == [
        "view",
        "create",
        "edit",
        "pause",
        "resume",
        "rerun",
        "cancel",
        "export",
        "collect",
    ]


def test_default_role_only_reads() -> None:
    actions = _allowed_actions(
        authorizer(policy_for("成员")), subject(), CONTENT_RESOURCE, content_run()
    )

    assert actions == ["view"]


@pytest.mark.parametrize(
    ("tenant_active", "actor_active"),
    [(False, True), (True, False)],
)
def test_inactive_tenant_or_actor_loses_every_action(
    tenant_active: bool, actor_active: bool
) -> None:
    actions = _allowed_actions(
        authorizer(
            policy_for("租户管理员", tenant_active=tenant_active, actor_active=actor_active)
        ),
        subject(),
        CONTENT_RESOURCE,
        content_run(),
    )

    assert actions == []


def test_missing_policy_denies_everything() -> None:
    actions = _allowed_actions(authorizer(None), subject(), CONTENT_RESOURCE, content_run())

    assert actions == []


def test_reviewer_can_claim_and_approve_a_task() -> None:
    actions = _allowed_actions(
        authorizer(policy_for("审核员")), subject(), REVIEW_RESOURCE, human_task()
    )

    assert actions == ["view", "claim", "approve", "reject", "reassign", "submit"]


def test_creator_cannot_approve_their_own_task() -> None:
    """Separation of duties must reach the frontend, not just the backend."""

    actions = _allowed_actions(
        authorizer(policy_for("审核员")),
        subject(),
        REVIEW_RESOURCE,
        human_task(created_by=ACTOR_ID),
    )

    assert "approve" not in actions
    assert "claim" in actions
