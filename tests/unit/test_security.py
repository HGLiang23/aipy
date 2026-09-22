from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from aipy.modules.identity import (
    JwtTokenService,
    JwtTokenSettings,
    PwdlibPasswordHasher,
    TokenSubject,
)
from aipy.modules.identity.domain.models import SessionRevocation, TokenRevocation
from aipy.shared.security.context import ActorType
from aipy.shared.security.errors import TokenExpiredError, TokenRevokedError


def uid(value: int) -> UUID:
    return UUID(int=value)


class FakeTokenRevocationRepository:
    def __init__(self) -> None:
        self.revoked_tokens: dict[UUID, TokenRevocation] = {}
        self.revoked_sessions: dict[UUID, SessionRevocation] = {}

    def is_token_revoked(self, token_id: UUID) -> bool:
        return token_id in self.revoked_tokens

    def is_session_revoked(self, session_id: UUID) -> bool:
        return session_id in self.revoked_sessions

    def revoke_token(self, revocation: TokenRevocation) -> None:
        self.revoked_tokens[revocation.token_id] = revocation

    def consume_refresh_token(self, revocation: TokenRevocation) -> bool:
        if revocation.token_id in self.revoked_tokens:
            return False
        self.revoked_tokens[revocation.token_id] = revocation
        return True

    def revoke_session(self, revocation: SessionRevocation) -> None:
        self.revoked_sessions[revocation.session_id] = revocation


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> MutableClock:
    return MutableClock(datetime(2026, 7, 24, 8, 0, tzinfo=UTC))


@pytest.fixture
def revocations() -> FakeTokenRevocationRepository:
    return FakeTokenRevocationRepository()


@pytest.fixture
def token_service(
    clock: MutableClock,
    revocations: FakeTokenRevocationRepository,
) -> JwtTokenService:
    return JwtTokenService(
        JwtTokenSettings(
            secret_key="test-secret-that-is-at-least-thirty-two-characters",
            issuer="aipy-test",
            audience="aipy-api",
            access_token_ttl=timedelta(minutes=15),
            refresh_token_ttl=timedelta(days=7),
            clock_skew=timedelta(0),
        ),
        revocations,
        clock=clock,
    )


@pytest.fixture
def subject() -> TokenSubject:
    return TokenSubject(
        tenant_id=uid(1),
        actor_id=uid(2),
        actor_type=ActorType.USER,
        session_id=uid(3),
        role_ids=(uid(4),),
        team_ids=(uid(5),),
        workspace_ids=(uid(6),),
    )


def test_access_token_builds_trusted_tenant_context(
    token_service: JwtTokenService,
    subject: TokenSubject,
) -> None:
    pair = token_service.issue_token_pair(subject)

    context = token_service.tenant_context_from_access_token(pair.access_token, "request-1")

    assert context.tenant_id == subject.tenant_id
    assert context.actor_id == subject.actor_id
    assert context.role_ids == subject.role_ids
    assert context.team_ids == subject.team_ids
    assert context.workspace_ids == subject.workspace_ids
    assert context.request_id == "request-1"


def test_access_token_expiry_uses_injected_clock(
    token_service: JwtTokenService,
    subject: TokenSubject,
    clock: MutableClock,
) -> None:
    pair = token_service.issue_token_pair(subject)
    clock.now += timedelta(minutes=16)

    with pytest.raises(TokenExpiredError):
        token_service.verify_access_token(pair.access_token)


def test_refresh_rotation_is_one_time_and_uses_current_memberships(
    token_service: JwtTokenService,
    subject: TokenSubject,
) -> None:
    pair = token_service.issue_token_pair(subject)
    updated_subject = subject.model_copy(update={"team_ids": (uid(50),)})

    rotated = token_service.rotate_token_pair(pair.refresh_token, updated_subject)
    rotated_claims = token_service.verify_access_token(rotated.access_token)

    assert rotated_claims.team_ids == (uid(50),)
    with pytest.raises(TokenRevokedError):
        token_service.rotate_token_pair(pair.refresh_token, updated_subject)


def test_revoked_session_invalidates_access_and_refresh_tokens(
    token_service: JwtTokenService,
    subject: TokenSubject,
) -> None:
    pair = token_service.issue_token_pair(subject)

    token_service.revoke_session(pair.refresh_token)

    with pytest.raises(TokenRevokedError):
        token_service.verify_access_token(pair.access_token)
    with pytest.raises(TokenRevokedError):
        token_service.verify_refresh_token(pair.refresh_token)


def test_pwdlib_adapter_hashes_and_verifies_passwords() -> None:
    hasher = PwdlibPasswordHasher()

    password_hash = hasher.hash("correct horse battery staple")

    assert password_hash != "correct horse battery staple"
    assert hasher.verify("correct horse battery staple", password_hash)
    assert not hasher.verify("wrong password", password_hash)
