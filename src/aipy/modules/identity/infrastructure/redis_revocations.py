"""Redis-backed token revocation store for multi-worker deployments.

Every key carries a TTL derived from the token's own expiry, so the store stays
bounded without a sweeper job. ``consume_refresh_token`` relies on ``SET NX`` to
make refresh-token replay impossible across concurrent requests.
"""

from datetime import UTC, datetime
from uuid import UUID

from redis import Redis

from aipy.modules.identity.domain.models import SessionRevocation, TokenRevocation

MIN_TTL_SECONDS = 60


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _ttl(expires_at: datetime, now: datetime) -> int:
    """Seconds to keep an entry, never shorter than one minute."""

    remaining = (_as_utc(expires_at) - now).total_seconds()
    return max(int(remaining), MIN_TTL_SECONDS)


class RedisTokenRevocations:
    def __init__(self, client: Redis, *, prefix: str = "aipy:rev") -> None:
        self._client = client
        self._prefix = prefix

    def is_token_revoked(self, token_id: UUID) -> bool:
        return bool(self._client.exists(self._token_key(token_id)))

    def is_session_revoked(self, session_id: UUID) -> bool:
        return bool(self._client.exists(self._session_key(session_id)))

    def revoke_token(self, revocation: TokenRevocation) -> None:
        ttl = _ttl(revocation.expires_at, datetime.now(UTC))
        self._client.setex(self._token_key(revocation.token_id), ttl, revocation.reason)

    def consume_refresh_token(self, revocation: TokenRevocation) -> bool:
        ttl = _ttl(revocation.expires_at, datetime.now(UTC))
        return bool(
            self._client.set(
                self._token_key(revocation.token_id),
                revocation.reason,
                nx=True,
                ex=ttl,
            )
        )

    def revoke_session(self, revocation: SessionRevocation) -> None:
        ttl = _ttl(revocation.expires_at, datetime.now(UTC))
        self._client.setex(self._session_key(revocation.session_id), ttl, revocation.reason)

    def _token_key(self, token_id: UUID) -> str:
        return f"{self._prefix}:token:{token_id}"

    def _session_key(self, session_id: UUID) -> str:
        return f"{self._prefix}:session:{session_id}"
