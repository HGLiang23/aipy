"""Identity service and persistence ports."""

from typing import Protocol
from uuid import UUID

from aipy.modules.identity.domain.models import (
    AccessTokenClaims,
    RefreshTokenClaims,
    SessionRevocation,
    TokenPair,
    TokenRevocation,
    TokenSubject,
)
from aipy.shared.security.context import TenantContext


class TokenRevocationRepository(Protocol):
    """Persistence boundary for revocation and one-time refresh consumption."""

    def is_token_revoked(self, token_id: UUID) -> bool: ...

    def is_session_revoked(self, session_id: UUID) -> bool: ...

    def revoke_token(self, revocation: TokenRevocation) -> None: ...

    def consume_refresh_token(self, revocation: TokenRevocation) -> bool:
        """Atomically revoke a refresh token, returning false if already consumed."""
        ...

    def revoke_session(self, revocation: SessionRevocation) -> None: ...


class TokenService(Protocol):
    def issue_token_pair(self, subject: TokenSubject) -> TokenPair: ...

    def verify_access_token(self, token: str) -> AccessTokenClaims: ...

    def verify_refresh_token(self, token: str) -> RefreshTokenClaims: ...

    def rotate_token_pair(self, refresh_token: str, current_subject: TokenSubject) -> TokenPair: ...

    def tenant_context_from_access_token(self, token: str, request_id: str) -> TenantContext: ...

    def revoke_access_token(self, token: str, reason: str = "logout") -> None: ...

    def revoke_session(self, refresh_token: str, reason: str = "logout") -> None: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...
