"""Login brute-force protection.

Two implementations back :class:`LoginLockout`: a process-local one for
single-worker runs and a Redis one that survives restarts and is shared by every
API replica. Both keep the lock bounded by ``window`` so a locked account
recovers on its own.
"""

from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import cast

from redis import Redis


class InMemoryLoginLockout:
    def __init__(self, max_attempts: int, window: timedelta) -> None:
        self._max_attempts = max_attempts
        self._window = window
        self._attempts: dict[str, int] = {}
        self._locked_until: dict[str, datetime] = {}
        self._guard = Lock()

    def is_locked(self, key: str) -> bool:
        with self._guard:
            self._forget_expired(key)
            return key in self._locked_until

    def record_failure(self, key: str) -> None:
        with self._guard:
            self._forget_expired(key)
            attempts = self._attempts.get(key, 0) + 1
            if attempts >= self._max_attempts:
                self._attempts.pop(key, None)
                self._locked_until[key] = datetime.now(UTC) + self._window
            else:
                self._attempts[key] = attempts

    def reset(self, key: str) -> None:
        with self._guard:
            self._attempts.pop(key, None)
            self._locked_until.pop(key, None)

    def _forget_expired(self, key: str) -> None:
        deadline = self._locked_until.get(key)
        if deadline is not None and deadline <= datetime.now(UTC):
            self._locked_until.pop(key, None)


class RedisLoginLockout:
    def __init__(
        self,
        client: Redis,
        max_attempts: int,
        window: timedelta,
        *,
        prefix: str = "aipy:login",
    ) -> None:
        self._client = client
        self._max_attempts = max_attempts
        self._window = window
        self._prefix = prefix

    def is_locked(self, key: str) -> bool:
        return bool(self._client.exists(self._lock_key(key)))

    def record_failure(self, key: str) -> None:
        window_seconds = max(int(self._window.total_seconds()), 1)
        attempts = cast("int", self._client.incr(self._attempt_key(key)))
        if attempts == 1:
            self._client.expire(self._attempt_key(key), window_seconds)
        if attempts >= self._max_attempts:
            self._client.setex(self._lock_key(key), window_seconds, "locked")
            self._client.delete(self._attempt_key(key))

    def reset(self, key: str) -> None:
        self._client.delete(self._attempt_key(key), self._lock_key(key))

    def _attempt_key(self, key: str) -> str:
        return f"{self._prefix}:attempts:{key}"

    def _lock_key(self, key: str) -> str:
        return f"{self._prefix}:locked:{key}"
