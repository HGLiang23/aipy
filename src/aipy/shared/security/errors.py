"""Stable security errors independent of HTTP and framework concerns."""

from collections.abc import Mapping
from typing import Any, ClassVar


class SecurityError(Exception):
    """Base error carrying a stable machine-readable code."""

    code: ClassVar[str] = "SECURITY_ERROR"

    def __init__(
        self,
        detail: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.metadata = dict(metadata or {})


class AuthenticationError(SecurityError):
    code = "AUTHENTICATION_REQUIRED"


class InvalidCredentialsError(AuthenticationError):
    code = "INVALID_CREDENTIALS"


class InvalidTokenError(AuthenticationError):
    code = "INVALID_TOKEN"


class TokenExpiredError(AuthenticationError):
    code = "TOKEN_EXPIRED"


class TokenRevokedError(AuthenticationError):
    code = "TOKEN_REVOKED"


class AuthorizationDeniedError(SecurityError):
    code = "AUTHORIZATION_DENIED"

    def __init__(
        self,
        detail: str = "The requested action is not allowed",
        *,
        reason: str | None = None,
    ) -> None:
        super().__init__(detail, metadata={"reason": reason} if reason else None)
