"""Authentication dependencies and the JWT / revocation singletons.

Revocation and lockout state is process-local in ``local``/``test`` and Redis-backed
everywhere else, so multi-replica deployments share it. The JWT signing key comes
from ``AIPY_JWT__SECRET_KEY``; outside local/test a missing key is a hard error.
"""

from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import Cookie, Depends, HTTPException, Request, status
from redis import Redis

from aipy.modules.authorization.infrastructure.policy_repository import (
    SqlAuthorizationPolicyRepository,
)
from aipy.modules.authorization.service import AuthorizationService
from aipy.modules.identity.domain.models import (
    AccessTokenClaims,
    JwtTokenSettings,
    RefreshTokenClaims,
)
from aipy.modules.identity.domain.ports import LoginLockout, TokenRevocationRepository
from aipy.modules.identity.infrastructure.in_memory_revocations import InMemoryTokenRevocations
from aipy.modules.identity.infrastructure.jwt_tokens import JwtTokenService
from aipy.modules.identity.infrastructure.login_lockout import (
    InMemoryLoginLockout,
    RedisLoginLockout,
)
from aipy.modules.identity.infrastructure.redis_revocations import RedisTokenRevocations
from aipy.shared.config import get_settings, jwt_secret
from aipy.shared.db import SessionFactory, make_engine, make_session_factory
from aipy.shared.security.context import ActorContext, TenantContext
from aipy.shared.security.errors import (
    InvalidTokenError,
    TokenExpiredError,
    TokenRevokedError,
)

from .middleware import REQUEST_ID_STATE_KEY
from .repositories import build_session
from .schemas import TenantSession

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


@lru_cache(maxsize=1)
def _redis_client(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)


@lru_cache(maxsize=1)
def get_revocations() -> TokenRevocationRepository:
    settings = get_settings()
    if settings.uses_shared_state:
        return RedisTokenRevocations(_redis_client(settings.redis.url))
    return InMemoryTokenRevocations()


@lru_cache(maxsize=1)
def get_login_lockout() -> LoginLockout:
    settings = get_settings()
    max_attempts = settings.security.login_max_attempts
    window = settings.security.login_lockout
    if settings.uses_shared_state:
        return RedisLoginLockout(_redis_client(settings.redis.url), max_attempts, window)
    return InMemoryLoginLockout(max_attempts, window)


@lru_cache(maxsize=1)
def get_jwt_service() -> JwtTokenService:
    settings = get_settings()
    token_settings = JwtTokenSettings(
        secret_key=jwt_secret(settings),
        issuer=settings.jwt.issuer,
        audience=settings.jwt.audience,
        access_token_ttl=settings.jwt.access_token_ttl,
        refresh_token_ttl=settings.jwt.refresh_token_ttl,
    )
    return JwtTokenService(token_settings, get_revocations())


_factory: SessionFactory | None = None


def get_session_factory() -> SessionFactory:
    """Return a cached session factory bound to the configured database."""

    global _factory
    if _factory is None:
        settings = get_settings()
        engine = make_engine(settings.database.url)
        _factory = make_session_factory(engine)
    return _factory


@lru_cache(maxsize=1)
def get_authorization_service() -> AuthorizationService:
    return AuthorizationService(SqlAuthorizationPolicyRepository(get_session_factory()))


def get_request_id(request: Request) -> str:
    """Return the id assigned by ``RequestIdMiddleware``."""

    value = getattr(request.state, REQUEST_ID_STATE_KEY, "")
    return value if isinstance(value, str) and value else uuid4().hex


def require_claims(
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
) -> AccessTokenClaims:
    """Verify the access cookie and return its claims."""

    if not access_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing access token")
    try:
        return get_jwt_service().verify_access_token(access_token)
    except (InvalidTokenError, TokenExpiredError, TokenRevokedError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def require_tenant(claims: AccessTokenClaims = Depends(require_claims)) -> tuple[UUID, UUID]:
    """Verify the JWT cookie and return ``(tenant_id, actor_id)``."""

    return claims.tenant_id, claims.actor_id


def get_tenant_context(
    request: Request,
    claims: AccessTokenClaims = Depends(require_claims),
) -> TenantContext:
    """Build the trusted authorization subject from verified claims."""

    return TenantContext(
        tenant_id=claims.tenant_id,
        actor=ActorContext(
            actor_id=claims.actor_id,
            actor_type=claims.actor_type,
            role_ids=claims.role_ids,
            team_ids=claims.team_ids,
            workspace_ids=claims.workspace_ids,
            session_id=claims.session_id,
        ),
        request_id=get_request_id(request),
    )


def require_refresh_claims(
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> RefreshTokenClaims:
    """Verify the refresh cookie without consuming it."""

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing refresh token"
        )
    try:
        return get_jwt_service().verify_refresh_token(refresh_token)
    except (InvalidTokenError, TokenExpiredError, TokenRevokedError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


def get_current_session(
    claims: AccessTokenClaims = Depends(require_claims),
) -> TenantSession:
    session = build_session(get_session_factory(), claims.tenant_id, claims.actor_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="tenant or workspace is unavailable",
        )
    return session


__all__ = [
    "ACCESS_COOKIE",
    "REFRESH_COOKIE",
    "get_authorization_service",
    "get_current_session",
    "get_jwt_service",
    "get_login_lockout",
    "get_request_id",
    "get_revocations",
    "get_session_factory",
    "get_tenant_context",
    "require_claims",
    "require_refresh_claims",
    "require_tenant",
]
