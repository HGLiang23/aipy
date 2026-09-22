"""Central, default-deny authorization service."""

from pydantic import ValidationError

from aipy.modules.authorization.domain.models import (
    AuthorizationDecision,
    AuthorizationPolicy,
    DataScope,
    DataScopeGrant,
    DenialReason,
    Permission,
    PermissionGrant,
    ResourceContext,
)
from aipy.modules.authorization.domain.ports import AuthorizationPolicyRepository
from aipy.shared.security.context import TenantContext


class AuthorizationService:
    def __init__(self, policies: AuthorizationPolicyRepository) -> None:
        self._policies = policies

    def authorize(
        self,
        subject: TenantContext,
        action: Permission | str,
        resource: ResourceContext,
    ) -> AuthorizationDecision:
        permission = self._normalize_permission(action)
        if permission is None:
            return self._deny(str(action), DenialReason.INVALID_PERMISSION)
        if subject.tenant_id != resource.tenant_id:
            return self._deny(permission.code, DenialReason.TENANT_MISMATCH)
        if permission.resource != resource.resource_type:
            return self._deny(permission.code, DenialReason.RESOURCE_TYPE_MISMATCH)

        policy = self._policies.get_policy(subject)
        if policy is None:
            return self._deny(permission.code, DenialReason.POLICY_NOT_FOUND)
        if not policy.tenant_active:
            return self._deny(permission.code, DenialReason.TENANT_INACTIVE)
        if not policy.actor_active:
            return self._deny(permission.code, DenialReason.ACTOR_INACTIVE)

        grants = tuple(
            grant for grant in policy.permission_grants if grant.permission.code == permission.code
        )
        if not grants:
            return self._deny(permission.code, DenialReason.PERMISSION_MISSING)
        if not self._workflow_state_allowed(policy, permission, resource):
            return self._deny(permission.code, DenialReason.WORKFLOW_STATE_DENIED)
        if self._violates_separation_of_duties(policy, permission, subject, resource):
            return self._deny(permission.code, DenialReason.SEPARATION_OF_DUTIES)
        if not self._data_scope_allowed(subject, resource, grants):
            return self._deny(permission.code, DenialReason.DATA_SCOPE_MISMATCH)

        return AuthorizationDecision(allowed=True, permission=permission.code)

    def allowed_actions(
        self,
        subject: TenantContext,
        actions: tuple[Permission | str, ...],
        resource: ResourceContext,
    ) -> frozenset[str]:
        return frozenset(
            decision.permission
            for action in actions
            if (decision := self.authorize(subject, action, resource)).allowed
        )

    def _workflow_state_allowed(
        self,
        policy: AuthorizationPolicy,
        permission: Permission,
        resource: ResourceContext,
    ) -> bool:
        state_rules = tuple(
            rule
            for rule in policy.workflow_state_policies
            if rule.permission.code == permission.code
        )
        if not state_rules:
            return resource.workflow_state is None
        if resource.workflow_state is None:
            return False
        return any(resource.workflow_state in rule.allowed_states for rule in state_rules)

    def _violates_separation_of_duties(
        self,
        policy: AuthorizationPolicy,
        permission: Permission,
        subject: TenantContext,
        resource: ResourceContext,
    ) -> bool:
        rules = policy.separation_of_duties
        actor_id = subject.actor_id
        if permission.code in rules.approval_permissions:
            if rules.forbid_submitter_approval and resource.submitted_by == actor_id:
                return True
            if rules.forbid_creator_approval and resource.created_by == actor_id:
                return True
        if permission.code in rules.publishing_permissions:
            if rules.forbid_editor_publish and resource.last_edited_by == actor_id:
                return True
            if rules.forbid_approver_publish and actor_id in resource.approved_by_ids:
                return True
        return False

    def _data_scope_allowed(
        self,
        subject: TenantContext,
        resource: ResourceContext,
        grants: tuple[PermissionGrant, ...],
    ) -> bool:
        return any(
            self._scope_matches(subject, resource, scope_grant)
            for permission_grant in grants
            for scope_grant in permission_grant.data_scopes
        )

    def _scope_matches(
        self,
        subject: TenantContext,
        resource: ResourceContext,
        grant: DataScopeGrant,
    ) -> bool:
        if grant.scope is DataScope.TENANT_ALL:
            return True
        if grant.scope is DataScope.WORKSPACE:
            allowed_ids = grant.workspace_ids or frozenset(subject.workspace_ids)
            return resource.workspace_id is not None and resource.workspace_id in allowed_ids
        if grant.scope is DataScope.TEAM:
            allowed_ids = grant.team_ids or frozenset(subject.team_ids)
            return resource.team_id is not None and resource.team_id in allowed_ids
        if grant.scope is DataScope.ASSIGNED:
            return resource.assigned_to == subject.actor_id
        if grant.scope is DataScope.CREATED_BY_ME:
            return resource.created_by == subject.actor_id
        if grant.scope is DataScope.CUSTOM:
            custom = grant.custom
            if custom is None:
                return False
            if custom.workspace_ids and resource.workspace_id not in custom.workspace_ids:
                return False
            if custom.team_ids and resource.team_id not in custom.team_ids:
                return False
            return not (custom.resource_ids and resource.resource_id not in custom.resource_ids)
        return False

    def _normalize_permission(self, action: Permission | str) -> Permission | None:
        if isinstance(action, Permission):
            return action
        try:
            return Permission(code=action)
        except (ValidationError, TypeError):
            return None

    def _deny(self, permission: str, reason: DenialReason) -> AuthorizationDecision:
        return AuthorizationDecision(
            allowed=False,
            permission=permission,
            denial_reason=reason,
        )
