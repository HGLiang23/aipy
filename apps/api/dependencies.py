"""Authentication dependencies and the JWT service singleton.

The production ``JwtTokenService`` issues/verifies real JWTs, wired to an
in-memory revocation store. A dev-only secret is used unless ``AIPY_JWT_SECRET``
is provided. Database access is provided through a lazily-built session factory.
"""

import os
from typing import Tuple
from uuid import UUID

from fastapi import Cookie, Depends, HTTPException, status
from pydantic import SecretStr

from aipy.modules.identity.domain.models import JwtTokenSettings
from aipy.modules.identity.infrastructure.jwt_tokens import JwtTokenService
from aipy.shared.config import get_settings
from aipy.shared.db import SessionFactory, make_engine, make_session_factory
from aipy.shared.security.errors import (
    InvalidTokenError,
    TokenExpiredError,
    TokenRevokedError,
)

from .repositories import authenticate, build_session
from .schemas import TenantSession

_dev_secret = os.environ.get("AIPY_JWT_SECRET", "dev-only-insecure-secret-change-me-32+chars!!")
_jwt_settings = JwtTokenSettings(
    secret_key=SecretStr(_dev_secret),
    issuer="aipy-dev",
    audience="aipy-dev",
)


class _InMemoryRevocations:
    """Minimal in-memory TokenRevocationRepository for local development."""

    def __init__(self) -> None:
        self._tokens: set[UUID] = set()
        self._sessions: set[UUID] = set()

    def is_token_revoked(self, token_id: UUID) -> bool:
        return token_id in self._tokens

    def is_session_revoked(self, session_id: UUID) -> bool:
        return session_id in self._sessions

    def revoke_token(self, revocation) -> None:
        self._tokens.add(revocation.token_id)

    def consume_refresh_token(self, revocation) -> bool:
        if revocation.token_id in self._tokens:
            return False
        self._tokens.add(revocation.token_id)
        return True

    def revoke_session(self, revocation) -> None:
        self._sessions.add(revocation.session_id)


_jwt_service = JwtTokenService(_jwt_settings, _InMemoryRevocations())


def get_jwt_service() -> JwtTokenService:
    return _jwt_service


_factory: SessionFactory | None = None


def get_session_factory() -> SessionFactory:
    """Return a cached session factory bound to the configured database."""

    global _factory
    if _factory is None:
        settings = get_settings()
        engine = make_engine(settings.database.url)
        _factory = make_session_factory(engine)
    return _factory


def require_tenant(
    access_token: str | None = Cookie(default=None),
) -> Tuple[UUID, UUID]:
    """Verify the JWT cookie and return ``(tenant_id, actor_id)``."""

    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing access token"
        )
    try:
        claims = _jwt_service.verify_access_token(access_token)
    except (InvalidTokenError, TokenExpiredError, TokenRevokedError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    return claims.tenant_id, claims.actor_id


def get_current_session(
    access_token: str | None = Cookie(default=None),
) -> TenantSession:
    tenant_id, actor_id = require_tenant(access_token)
    return build_session(get_session_factory(), tenant_id, actor_id)


__all__ = [
    "authenticate",
    "get_current_session",
    "get_jwt_service",
    "get_session_factory",
    "require_tenant",
]
