"""Shared /v1 dependencies."""
from fastapi import Request

from app.auth import require_token
from app.security import decode_access_token

# Re-exported so routes read as `user: User = Depends(current_user)` -- and,
# unlike the legacy routes, actually *use* the returned User.
current_user = require_token


def principal(request: Request) -> str:
    """Who is this request attributed to, for rate limiting and chaos counters?

    Decodes the bearer token without raising, so unauthenticated routes such as
    /v1/ping still get a stable key (the client IP). Per-principal keys matter:
    keying on IP alone would make one participant's runaway loop throttle the
    whole room, since an office network shares an egress address.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            return decode_access_token(auth[7:].strip())
        except Exception:
            pass
    client = request.client
    return f"ip:{client.host if client else 'unknown'}"
