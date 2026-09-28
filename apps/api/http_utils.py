"""HTTP helpers shared by the route modules."""

import re
from urllib.parse import quote

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def attachment_header(filename: str) -> str:
    """Build a ``Content-Disposition`` value that survives a non-ASCII title.

    HTTP header values are latin-1, so a Chinese filename has to travel in the
    ``filename*`` parameter (RFC 5987) with an ASCII fallback for old clients.
    """

    fallback = _UNSAFE.sub("_", filename).strip("_") or "download"
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"
