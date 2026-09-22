"""PyJWT access and rotating refresh token implementation."""

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Literal, overload
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError as PyJwtInvalidTokenError
from pydantic import ValidationError

from aipy.modules.identity.domain.models import (
    AccessTokenClaims,
    JwtTokenSettings,
    RefreshTokenClaims,
    SessionRevocation,
    TokenPair,
    TokenRevocation,
    TokenSubject,
    TokenType,
)
from aipy.modules.identity.domain.ports import TokenRevocationRepository
from aipy.shared.security.context import ActorContext, TenantContext
from aipy.shared.security.errors import InvalidTokenError, TokenExpiredError, TokenRevokedError


def _utc_now() -> datetime:
    return datetime.now(UTC)


class JwtTokenService:
    def __init__(
        self,
        settings: JwtTokenSettings,
        revocations: TokenRevocationRepository,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._settings = settings
        self._revocations = revocations
        self._clock = clock

    def issue_token_pair(self, subject: TokenSubject) -> TokenPair:
        now = self._now()
        access_expires_at = now + self._settings.access_token_ttl
        refresh_expires_at = now + self._settings.refresh_token_ttl

        access_claims = AccessTokenClaims(
            **subject.model_dump(),
            issuer=self._settings.issuer,
            audience=self._settings.audience,
            token_id=uuid4(),
            issued_at=now,
            expires_at=access_expires_at,
        )
        refresh_claims = RefreshTokenClaims(
            issuer=self._settings.issuer,
            audience=self._settings.audience,
            tenant_id=subject.tenant_id,
            actor_id=subject.actor_id,
            actor_type=subject.actor_type,
            session_id=subject.session_id,
            token_id=uuid4(),
            issued_at=now,
            expires_at=refresh_expires_at,
        )
        return TokenPair(
            access_token=self._encode(access_claims),
            refresh_token=self._encode(refresh_claims),
            access_expires_at=access_expires_at,
            refresh_expires_at=refresh_expires_at,
        )

    def verify_access_token(self, token: str) -> AccessTokenClaims:
        claims = self._decode(token, AccessTokenClaims, TokenType.ACCESS)
        self._require_not_revoked(claims.token_id, claims.session_id)
        return claims

    def verify_refresh_token(self, token: str) -> RefreshTokenClaims:
        claims = self._decode(token, RefreshTokenClaims, TokenType.REFRESH)
        self._require_not_revoked(claims.token_id, claims.session_id)
        return claims

    def rotate_token_pair(self, refresh_token: str, current_subject: TokenSubject) -> TokenPair:
        claims = self.verify_refresh_token(refresh_token)
        if (
            claims.tenant_id != current_subject.tenant_id
            or claims.actor_id != current_subject.actor_id
            or claims.actor_type != current_subject.actor_type
            or claims.session_id != current_subject.session_id
        ):
            raise InvalidTokenError("Refresh token does not match the current identity")

        consumed = self._revocations.consume_refresh_token(
            TokenRevocation(
                token_id=claims.token_id,
                session_id=claims.session_id,
                expires_at=claims.expires_at,
                reason="refresh_rotation",
            )
        )
        if not consumed:
            raise TokenRevokedError("Refresh token has already been used")
        return self.issue_token_pair(current_subject)

    def tenant_context_from_access_token(self, token: str, request_id: str) -> TenantContext:
        claims = self.verify_access_token(token)
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
            request_id=request_id,
        )

    def revoke_access_token(self, token: str, reason: str = "logout") -> None:
        claims = self._decode(token, AccessTokenClaims, TokenType.ACCESS)
        self._revocations.revoke_token(
            TokenRevocation(
                token_id=claims.token_id,
                session_id=claims.session_id,
                expires_at=claims.expires_at,
                reason=reason,
            )
        )

    def revoke_session(self, refresh_token: str, reason: str = "logout") -> None:
        claims = self._decode(refresh_token, RefreshTokenClaims, TokenType.REFRESH)
        self._revocations.revoke_session(
            SessionRevocation(
                session_id=claims.session_id,
                expires_at=claims.expires_at,
                reason=reason,
            )
        )

    def _encode(self, claims: AccessTokenClaims | RefreshTokenClaims) -> str:
        payload: dict[str, Any] = {
            "iss": claims.issuer,
            "aud": claims.audience,
            "sub": str(claims.actor_id),
            "tenant_id": str(claims.tenant_id),
            "actor_type": claims.actor_type.value,
            "sid": str(claims.session_id),
            "jti": str(claims.token_id),
            "token_type": claims.token_type.value,
            "iat": int(claims.issued_at.timestamp()),
            "exp": int(claims.expires_at.timestamp()),
        }
        if isinstance(claims, AccessTokenClaims):
            payload.update(
                {
                    "role_ids": [str(item) for item in claims.role_ids],
                    "team_ids": [str(item) for item in claims.team_ids],
                    "workspace_ids": [str(item) for item in claims.workspace_ids],
                }
            )
        return jwt.encode(
            payload,
            self._settings.secret_key.get_secret_value(),
            algorithm=self._settings.algorithm,
        )

    @overload
    def _decode(
        self,
        token: str,
        claim_type: type[AccessTokenClaims],
        expected_type: Literal[TokenType.ACCESS],
    ) -> AccessTokenClaims: ...

    @overload
    def _decode(
        self,
        token: str,
        claim_type: type[RefreshTokenClaims],
        expected_type: Literal[TokenType.REFRESH],
    ) -> RefreshTokenClaims: ...

    def _decode(
        self,
        token: str,
        claim_type: type[AccessTokenClaims] | type[RefreshTokenClaims],
        expected_type: TokenType,
    ) -> AccessTokenClaims | RefreshTokenClaims:
        if not token:
            raise InvalidTokenError("Token must not be empty")
        try:
            payload = jwt.decode(
                token,
                self._settings.secret_key.get_secret_value(),
                algorithms=[self._settings.algorithm],
                issuer=self._settings.issuer,
                audience=self._settings.audience,
                options={
                    "require": ["iss", "aud", "sub", "tenant_id", "sid", "jti", "iat", "exp"],
                    "verify_exp": False,
                    "verify_iat": False,
                },
            )
            if payload.get("token_type") != expected_type.value:
                raise InvalidTokenError("Unexpected token type")
            claims = claim_type.model_validate(self._normalize_payload(payload))
        except InvalidTokenError:
            raise
        except (PyJwtInvalidTokenError, ValidationError, TypeError, ValueError) as exc:
            raise InvalidTokenError("Token is invalid") from exc

        now = self._now()
        if claims.expires_at <= now - self._settings.clock_skew:
            raise TokenExpiredError("Token has expired")
        if claims.issued_at > now + self._settings.clock_skew:
            raise InvalidTokenError("Token was issued in the future")
        return claims

    def _normalize_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized.update(
            {
                "issuer": payload.get("iss"),
                "audience": payload.get("aud"),
                "actor_id": payload.get("sub"),
                "session_id": payload.get("sid"),
                "token_id": payload.get("jti"),
                "issued_at": payload.get("iat"),
                "expires_at": payload.get("exp"),
            }
        )
        for key in ("iss", "aud", "sub", "sid", "jti", "iat", "exp"):
            normalized.pop(key, None)
        return normalized

    def _require_not_revoked(self, token_id: UUID, session_id: UUID) -> None:
        if self._revocations.is_token_revoked(token_id):
            raise TokenRevokedError("Token has been revoked")
        if self._revocations.is_session_revoked(session_id):
            raise TokenRevokedError("Session has been revoked")

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now.astimezone(UTC)
