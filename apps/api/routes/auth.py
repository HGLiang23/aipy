"""Authentication routes.

Paths follow the frontend contract exactly:
- ``POST /api/v1/auth/login`` issues a JWT cookie pair and returns the session
- ``POST /api/v1/auth/refresh`` rotates the pair using the refresh cookie
- ``POST /api/v1/auth/logout`` revokes both tokens and clears the cookies
- ``GET  /api/v1/me`` returns the session for the authenticated caller

The refresh cookie is scoped to ``/api/v1/auth`` so it is never sent on ordinary
API calls; only the short-lived access cookie is.
"""

from contextlib import suppress
from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status

from aipy.modules.identity.domain.models import (
    RefreshTokenClaims,
    TokenPair,
    TokenSubject,
)
from aipy.modules.identity.domain.ports import LoginLockout
from aipy.shared.config import AppSettings
from aipy.shared.security.errors import (
    InvalidTokenError,
    TokenExpiredError,
    TokenRevokedError,
)

from ..dependencies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    get_current_session,
    get_jwt_service,
    get_login_lockout,
    get_session_factory,
    require_refresh_claims,
)
from ..repositories import authenticate, build_session
from ..schemas import LoginCommand, TenantSession

router = APIRouter(tags=["auth"])

REFRESH_COOKIE_PATH = "/api/v1/auth"

_TOKEN_ERRORS = (InvalidTokenError, TokenExpiredError, TokenRevokedError)


def _cookie_max_age(expires_at: datetime) -> int:
    return max(int((expires_at - datetime.now(UTC)).total_seconds()), 1)


def _set_auth_cookies(response: Response, pair: TokenPair, *, secure: bool) -> None:
    response.set_cookie(
        key=ACCESS_COOKIE,
        value=pair.access_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=_cookie_max_age(pair.access_expires_at),
    )
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=pair.refresh_token,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=_cookie_max_age(pair.refresh_expires_at),
    )


def _clear_auth_cookies(response: Response) -> None:
    """Expire both cookies on ``response``.

    ``httponly``/``samesite`` are repeated to mirror how the cookies were issued;
    a browser matches a deletion on (name, domain, path) alone, but sending the
    same attributes keeps the resulting ``Set-Cookie`` headers self-consistent.
    """

    response.delete_cookie(key=ACCESS_COOKIE, path="/", httponly=True, samesite="lax")
    response.delete_cookie(
        key=REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True, samesite="lax"
    )


def _lockout_key(email: str) -> str:
    """Normalise the email so casing cannot be used to get a fresh attempt budget."""

    return email.strip().lower()


def _reject_locked(lockout: LoginLockout, email: str) -> None:
    if lockout.is_locked(_lockout_key(email)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many failed login attempts",
        )


@router.post("/auth/login", response_model=TenantSession)
def login(
    request: Request,
    command: LoginCommand,
    response: Response,
) -> TenantSession:
    settings: AppSettings = request.app.state.settings
    lockout = get_login_lockout()
    _reject_locked(lockout, command.email)

    subject = authenticate(get_session_factory(), command.email, command.password)
    if subject is None:
        lockout.record_failure(_lockout_key(command.email))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
        )
    lockout.reset(_lockout_key(command.email))

    token_pair = get_jwt_service().issue_token_pair(subject)
    _set_auth_cookies(response, token_pair, secure=settings.cookie_secure)

    session = build_session(get_session_factory(), subject.tenant_id, subject.actor_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="tenant or workspace is unavailable",
        )
    return session


@router.post("/auth/refresh", response_model=TenantSession)
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    claims: RefreshTokenClaims = Depends(require_refresh_claims),
) -> TenantSession:
    """Rotate the token pair; the presented refresh token is single-use."""

    settings: AppSettings = request.app.state.settings
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="missing refresh token"
        )
    subject = TokenSubject(
        tenant_id=claims.tenant_id,
        actor_id=claims.actor_id,
        actor_type=claims.actor_type,
        session_id=claims.session_id,
    )
    try:
        token_pair = get_jwt_service().rotate_token_pair(refresh_token, subject)
    except _TOKEN_ERRORS as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    _set_auth_cookies(response, token_pair, secure=settings.cookie_secure)

    session = build_session(get_session_factory(), subject.tenant_id, subject.actor_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="tenant or workspace is unavailable",
        )
    return session


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    access_token: str | None = Cookie(default=None, alias=ACCESS_COOKIE),
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
) -> Response:
    """Revoke both tokens and clear the cookies. Idempotent by design."""

    service = get_jwt_service()
    if access_token:
        # An already-expired token needs no revocation; failing loudly here would
        # make logout unusable for anyone whose session went stale.
        with suppress(*_TOKEN_ERRORS):
            service.revoke_access_token(access_token, reason="logout")
    if refresh_token:
        with suppress(*_TOKEN_ERRORS):
            service.revoke_session(refresh_token, reason="logout")

    # The deletion must land on the object that is actually returned: FastAPI only
    # merges headers set on an injected ``Response`` when the handler returns a
    # plain value. Returning ``Response(...)`` replaces it, and the caller would
    # keep both cookies.
    cleared = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(cleared)
    return cleared


@router.get("/me", response_model=TenantSession)
def get_session(session: TenantSession = Depends(get_current_session)) -> TenantSession:
    return session
