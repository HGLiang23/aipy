"""Credential masking helpers.

The raw secret must never be persisted or returned. We keep only:

* a **masked preview** for display (``sk-…a1b2``), and
* a **SHA-256 fingerprint** for rotation detection.

Neither can be reversed into the original secret.
"""

import hashlib


def fingerprint(secret: str) -> str:
    """Return a stable, non-reversible SHA-256 hex digest of the secret."""

    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def mask(secret: str) -> str:
    """Return a display-only masked preview that never exposes the middle."""

    value = secret.strip()
    if len(value) <= 8:
        return "…" + value[-2:] if value else "…"
    return f"{value[:3]}…{value[-4:]}"
