"""Authorization persistence ports."""

from typing import Protocol

from aipy.modules.authorization.domain.models import AuthorizationPolicy
from aipy.shared.security.context import TenantContext


class AuthorizationPolicyRepository(Protocol):
    def get_policy(self, subject: TenantContext) -> AuthorizationPolicy | None:
        """Return the current server-side policy for this actor and tenant."""
        ...
