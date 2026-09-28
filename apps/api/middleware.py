"""Cross-cutting HTTP middleware."""

from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_STATE_KEY = "request_id"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Give every request an id, reused from the caller when supplied.

    The id lands on ``request.state`` (so authorization contexts can carry it)
    and on the response header, which is what makes a client-reported error
    traceable in logs.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = incoming or uuid4().hex
        setattr(request.state, REQUEST_ID_STATE_KEY, request_id)

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
