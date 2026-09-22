"""Application-side identifier generation."""

from uuid import UUID

from uuid6 import uuid7


def new_uuid7() -> UUID:
    """Return a time-ordered UUIDv7 for database primary keys."""

    return uuid7()
