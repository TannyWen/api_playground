"""Request-id plumbing.

App-wide, but it only ever adds a response *header*, so no response body is
touched. Having the id on request.state means the id in a `meta` block and the
id in an error envelope come from the same source.
"""
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

HEADER = "X-Request-Id"


def new_request_id() -> str:
    return f"req_{secrets.token_hex(4)}"


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Honour a caller-supplied id so a participant can correlate their own
        # logs with the server's; mint one otherwise.
        request.state.request_id = request.headers.get(HEADER) or new_request_id()
        response = await call_next(request)
        response.headers[HEADER] = request.state.request_id
        return response
