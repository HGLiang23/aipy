"""HTTP middleware package.

Both the local branch (``middleware.py`` module) and the remote branch
(``middleware/`` package) defined request-id middleware under the same import
name ``apps.api.middleware``. Python resolves that name to this package, so the
module form is dead. To keep ``from .middleware import RequestIdMiddleware`` and
``REQUEST_ID_STATE_KEY`` working, re-export them here.
"""

from .request_id import REQUEST_ID_HEADER, RequestIDMiddleware

# Canonical key used to stash the id on ``request.state``; matches what
# ``RequestIDMiddleware`` writes (``request.state.request_id``).
REQUEST_ID_STATE_KEY = "request_id"

# Alias expected by the application wiring (apps.api.main / dependencies).
RequestIdMiddleware = RequestIDMiddleware

__all__ = [
    "REQUEST_ID_HEADER",
    "REQUEST_ID_STATE_KEY",
    "RequestIdMiddleware",
    "RequestIDMiddleware",
]
