"""Argon2id password hashing adapter."""

from pwdlib import PasswordHash


class PwdlibPasswordHasher:
    def __init__(self, password_hash: PasswordHash | None = None) -> None:
        self._password_hash = password_hash or PasswordHash.recommended()

    def hash(self, password: str) -> str:
        if not password:
            raise ValueError("password must not be empty")
        return self._password_hash.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        if not password or not password_hash:
            return False
        return self._password_hash.verify(password, password_hash)
