"""Authorization infrastructure: policy resolution adapters."""

from aipy.modules.authorization.infrastructure.policy_repository import (
    SqlAuthorizationPolicyRepository,
)

__all__ = ["SqlAuthorizationPolicyRepository"]
