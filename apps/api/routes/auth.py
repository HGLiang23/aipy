"""Authentication routes.

Paths follow the frontend contract exactly:
- ``POST /api/v1/auth/login`` issues a JWT cookie and returns the session
- ``GET  /api/v1/me`` returns the session for the authenticated caller
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..dependencies import (
    authenticate,
    get_current_session,
    get_jwt_service,
    get_session_factory,
)
from ..repositories import build_session
from ..schemas import LoginCommand, TenantSession

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TenantSession)
def login(command: LoginCommand, response: Response) -> TenantSession:
    subject = authenticate(get_session_factory(), command.email, command.password)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
        )

    token_pair = get_jwt_service().issue_token_pair(subject)
    max_age = int((token_pair.access_expires_at - datetime.now(UTC)).total_seconds())
    response.set_cookie(
        key="access_token",
        value=token_pair.access_token,
        httponly=True,
        samesite="lax",
        path="/",
        max_age=max_age,
    )
    return build_session(get_session_factory(), subject.tenant_id, subject.actor_id)


@router.get("/me", response_model=TenantSession)
def get_session(session: TenantSession = Depends(get_current_session)) -> TenantSession:
    return session
