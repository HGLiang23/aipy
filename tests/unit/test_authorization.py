from uuid import UUID

import pytest

from aipy.modules.authorization import (
    AuthorizationPolicy,
    AuthorizationService,
    CustomScopeConstraint,
    DataScope,
    DataScopeGrant,
    DenialReason,
    Permission,
    PermissionGrant,
    ResourceContext,
    SeparationOfDutiesPolicy,
    WorkflowStatePolicy,
)
from aipy.shared.security.context import ActorContext, ActorType, TenantContext
from aipy.shared.security.errors import AuthorizationDeniedError


def uid(value: int) -> UUID:
    return UUID(int=value)


TENANT_ID = uid(1)
ACTOR_ID = uid(2)
WORKSPACE_ID = uid(3)
TEAM_ID = uid(4)
RESOURCE_ID = uid(5)
VIEW = Permission(code="content:view")
APPROVE = Permission(code="review:approve")
PUBLISH = Permission(code="publication:publish")


class FakeAuthorizationPolicyRepository:
    def __init__(self, policy: AuthorizationPolicy | None = None) -> None:
        self.policy = policy
        self.subjects: list[TenantContext] = []

    def get_policy(self, subject: TenantContext) -> AuthorizationPolicy | None:
        self.subjects.append(subject)
        return self.policy


@pytest.fixture
def subject() -> TenantContext:
    return TenantContext(
        tenant_id=TENANT_ID,
        actor=ActorContext(
            actor_id=ACTOR_ID,
            actor_type=ActorType.USER,
            role_ids=(uid(10),),
            workspace_ids=(WORKSPACE_ID,),
            team_ids=(TEAM_ID,),
            session_id=uid(11),
        ),
        request_id="request-1",
    )


def resource(**updates: object) -> ResourceContext:
    values: dict[str, object] = {
        "tenant_id": TENANT_ID,
        "resource_type": "content",
        "resource_id": RESOURCE_ID,
        "workspace_id": WORKSPACE_ID,
        "team_id": TEAM_ID,
        "assigned_to": ACTOR_ID,
        "created_by": ACTOR_ID,
    }
    values.update(updates)
    return ResourceContext.model_validate(values)


def policy_for(
    permission: Permission,
    scope: DataScopeGrant,
    *,
    workflow_states: frozenset[str] | None = None,
    duties: SeparationOfDutiesPolicy | None = None,
) -> AuthorizationPolicy:
    workflow_policies = ()
    if workflow_states is not None:
        workflow_policies = (
            WorkflowStatePolicy(permission=permission, allowed_states=workflow_states),
        )
    return AuthorizationPolicy(
        permission_grants=(PermissionGrant(permission=permission, data_scopes=(scope,)),),
        workflow_state_policies=workflow_policies,
        separation_of_duties=duties or SeparationOfDutiesPolicy(),
    )


def test_authorization_defaults_to_deny_without_policy(subject: TenantContext) -> None:
    service = AuthorizationService(FakeAuthorizationPolicyRepository())

    decision = service.authorize(subject, VIEW, resource())

    assert not decision.allowed
    assert decision.denial_reason is DenialReason.POLICY_NOT_FOUND
    with pytest.raises(AuthorizationDeniedError):
        decision.require_allowed()


def test_cross_tenant_resource_is_denied_before_policy_lookup(subject: TenantContext) -> None:
    repository = FakeAuthorizationPolicyRepository(
        policy_for(VIEW, DataScopeGrant(scope=DataScope.TENANT_ALL))
    )
    service = AuthorizationService(repository)

    decision = service.authorize(subject, VIEW, resource(tenant_id=uid(999)))

    assert decision.denial_reason is DenialReason.TENANT_MISMATCH
    assert repository.subjects == []


def test_permission_resource_type_must_match(subject: TenantContext) -> None:
    repository = FakeAuthorizationPolicyRepository(
        policy_for(VIEW, DataScopeGrant(scope=DataScope.TENANT_ALL))
    )
    service = AuthorizationService(repository)

    decision = service.authorize(subject, VIEW, resource(resource_type="publication"))

    assert decision.denial_reason is DenialReason.RESOURCE_TYPE_MISMATCH
    assert repository.subjects == []


@pytest.mark.parametrize(
    ("scope", "resource_updates"),
    [
        (DataScopeGrant(scope=DataScope.TENANT_ALL), {}),
        (DataScopeGrant(scope=DataScope.WORKSPACE), {"workspace_id": WORKSPACE_ID}),
        (DataScopeGrant(scope=DataScope.TEAM), {"team_id": TEAM_ID}),
        (DataScopeGrant(scope=DataScope.ASSIGNED), {"assigned_to": ACTOR_ID}),
        (DataScopeGrant(scope=DataScope.CREATED_BY_ME), {"created_by": ACTOR_ID}),
        (
            DataScopeGrant(
                scope=DataScope.CUSTOM,
                custom=CustomScopeConstraint(
                    workspace_ids=frozenset({WORKSPACE_ID}),
                    team_ids=frozenset({TEAM_ID}),
                    resource_ids=frozenset({RESOURCE_ID}),
                ),
            ),
            {
                "workspace_id": WORKSPACE_ID,
                "team_id": TEAM_ID,
                "resource_id": RESOURCE_ID,
            },
        ),
    ],
)
def test_all_supported_data_scopes_can_authorize(
    subject: TenantContext,
    scope: DataScopeGrant,
    resource_updates: dict[str, object],
) -> None:
    service = AuthorizationService(FakeAuthorizationPolicyRepository(policy_for(VIEW, scope)))

    decision = service.authorize(subject, VIEW, resource(**resource_updates))

    assert decision.allowed


def test_data_scope_mismatch_is_denied(subject: TenantContext) -> None:
    scope = DataScopeGrant(scope=DataScope.TEAM, team_ids=frozenset({uid(700)}))
    service = AuthorizationService(FakeAuthorizationPolicyRepository(policy_for(VIEW, scope)))

    decision = service.authorize(subject, VIEW, resource())

    assert decision.denial_reason is DenialReason.DATA_SCOPE_MISMATCH


def test_workflow_state_requires_an_explicit_allowed_state(subject: TenantContext) -> None:
    scope = DataScopeGrant(scope=DataScope.TENANT_ALL)
    service = AuthorizationService(
        FakeAuthorizationPolicyRepository(
            policy_for(VIEW, scope, workflow_states=frozenset({"DRAFT", "PAUSED"}))
        )
    )

    allowed = service.authorize(subject, VIEW, resource(workflow_state="DRAFT"))
    denied = service.authorize(subject, VIEW, resource(workflow_state="COMPLETED"))

    assert allowed.allowed
    assert denied.denial_reason is DenialReason.WORKFLOW_STATE_DENIED


def test_workflow_resource_without_state_policy_is_denied(subject: TenantContext) -> None:
    scope = DataScopeGrant(scope=DataScope.TENANT_ALL)
    service = AuthorizationService(FakeAuthorizationPolicyRepository(policy_for(VIEW, scope)))

    decision = service.authorize(subject, VIEW, resource(workflow_state="DRAFT"))

    assert decision.denial_reason is DenialReason.WORKFLOW_STATE_DENIED


def test_state_constrained_permission_requires_resource_state(subject: TenantContext) -> None:
    scope = DataScopeGrant(scope=DataScope.TENANT_ALL)
    service = AuthorizationService(
        FakeAuthorizationPolicyRepository(
            policy_for(VIEW, scope, workflow_states=frozenset({"DRAFT"}))
        )
    )

    decision = service.authorize(subject, VIEW, resource())

    assert decision.denial_reason is DenialReason.WORKFLOW_STATE_DENIED


def test_submitter_cannot_approve_own_content(subject: TenantContext) -> None:
    scope = DataScopeGrant(scope=DataScope.TENANT_ALL)
    service = AuthorizationService(FakeAuthorizationPolicyRepository(policy_for(APPROVE, scope)))

    decision = service.authorize(
        subject,
        APPROVE,
        resource(
            resource_type="review",
            created_by=uid(100),
            submitted_by=ACTOR_ID,
        ),
    )

    assert decision.denial_reason is DenialReason.SEPARATION_OF_DUTIES


def test_last_editor_cannot_publish(subject: TenantContext) -> None:
    scope = DataScopeGrant(scope=DataScope.TENANT_ALL)
    service = AuthorizationService(FakeAuthorizationPolicyRepository(policy_for(PUBLISH, scope)))

    decision = service.authorize(
        subject,
        PUBLISH,
        resource(resource_type="publication", last_edited_by=ACTOR_ID),
    )

    assert decision.denial_reason is DenialReason.SEPARATION_OF_DUTIES


def test_distinct_approver_and_publisher_can_be_required(subject: TenantContext) -> None:
    scope = DataScopeGrant(scope=DataScope.TENANT_ALL)
    duties = SeparationOfDutiesPolicy(forbid_approver_publish=True)
    service = AuthorizationService(
        FakeAuthorizationPolicyRepository(policy_for(PUBLISH, scope, duties=duties))
    )

    decision = service.authorize(
        subject,
        PUBLISH,
        resource(
            resource_type="publication",
            last_edited_by=uid(101),
            approved_by_ids=frozenset({ACTOR_ID}),
        ),
    )

    assert decision.denial_reason is DenialReason.SEPARATION_OF_DUTIES


def test_missing_permission_is_denied(subject: TenantContext) -> None:
    repository = FakeAuthorizationPolicyRepository(
        policy_for(VIEW, DataScopeGrant(scope=DataScope.TENANT_ALL))
    )
    service = AuthorizationService(repository)

    decision = service.authorize(subject, "content:edit", resource())

    assert decision.denial_reason is DenialReason.PERMISSION_MISSING
