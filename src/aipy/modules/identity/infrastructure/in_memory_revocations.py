"""Process-local revocation store for single-worker runs.

Only suitable for ``local``/``test`` environments: the state disappears on
restart and is not shared between API replicas.
"""

from uuid import UUID

from aipy.modules.identity.domain.models import SessionRevocation, TokenRevocation


class InMemoryTokenRevocations:
    def __init__(self) -> None:
        self._tokens: set[UUID] = set()
        self._sessions: set[UUID] = set()

    def is_token_revoked(self, token_id: UUID) -> bool:
        return token_id in self._tokens

    def is_session_revoked(self, session_id: UUID) -> bool:
        return session_id in self._sessions

    def revoke_token(self, revocation: TokenRevocation) -> None:
        self._tokens.add(revocation.token_id)

    def consume_refresh_token(self, revocation: TokenRevocation) -> bool:
        if revocation.token_id in self._tokens:
            return False
        self._tokens.add(revocation.token_id)
        return True

    def revoke_session(self, revocation: SessionRevocation) -> None:
        self._sessions.add(revocation.session_id)
