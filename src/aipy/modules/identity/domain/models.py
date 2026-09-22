"""Identity value objects."""

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from aipy.shared.security.context import ActorType


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenSubject(BaseModel):
    """Current identity data used when issuing a token pair."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: UUID
    actor_id: UUID
    actor_type: ActorType
    session_id: UUID
    role_ids: tuple[UUID, ...] = ()
    team_ids: tuple[UUID, ...] = ()
    workspace_ids: tuple[UUID, ...] = ()


class AccessTokenClaims(TokenSubject):
    issuer: str
    audience: str
    token_id: UUID
    token_type: Literal[TokenType.ACCESS] = TokenType.ACCESS
    issued_at: datetime
    expires_at: datetime


class RefreshTokenClaims(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issuer: str
    audience: str
    tenant_id: UUID
    actor_id: UUID
    actor_type: ActorType
    session_id: UUID
    token_id: UUID
    token_type: Literal[TokenType.REFRESH] = TokenType.REFRESH
    issued_at: datetime
    expires_at: datetime


class TokenPair(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime


class JwtTokenSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    secret_key: SecretStr
    issuer: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_ttl: timedelta = timedelta(minutes=15)
    refresh_token_ttl: timedelta = timedelta(days=14)
    clock_skew: timedelta = timedelta(seconds=30)

    @field_validator("secret_key")
    @classmethod
    def secret_must_be_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT secret_key must contain at least 32 characters")
        return value

    @field_validator("access_token_ttl", "refresh_token_ttl")
    @classmethod
    def ttl_must_be_positive(cls, value: timedelta) -> timedelta:
        if value <= timedelta(0):
            raise ValueError("token TTL must be positive")
        return value

    @field_validator("clock_skew")
    @classmethod
    def clock_skew_must_not_be_negative(cls, value: timedelta) -> timedelta:
        if value < timedelta(0):
            raise ValueError("clock_skew must not be negative")
        return value


class TokenRevocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    token_id: UUID
    session_id: UUID
    expires_at: datetime
    reason: str = Field(min_length=1, max_length=128)


class SessionRevocation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: UUID
    expires_at: datetime
    reason: str = Field(min_length=1, max_length=128)
