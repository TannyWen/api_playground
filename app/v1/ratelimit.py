"""In-process sliding-window rate limiting.

A sliding window rather than a token bucket, because it yields an exact and
honest Retry-After -- which is what makes the backoff exercise land.

Single-process only: with multiple gunicorn workers each keeps its own window,
so the effective limit multiplies. That is why the deployment pins one worker,
and it is an honest talking point about why real rate limiting needs shared
state such as Redis.
"""
import math
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, Request, Response

from app.v1 import config
from app.v1.deps import principal
from app.v1.errors import ApiError

_WINDOWS: dict[str, deque] = defaultdict(deque)
_LOCK = threading.Lock()


def _consume(key: str, limit: int, window: int) -> tuple[bool, int, int]:
    """Try to record a hit. Returns (allowed, remaining, seconds_until_reset)."""
    now = time.monotonic()
    with _LOCK:
        hits = _WINDOWS[key]
        cutoff = now - window
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= limit:
            retry_after = max(1, math.ceil(hits[0] + window - now))
            return False, 0, retry_after

        hits.append(now)
        reset_in = max(1, math.ceil(hits[0] + window - now))
        return True, limit - len(hits), reset_in


def peek(key: str, limit: int, window: int) -> tuple[bool, int, int]:
    """Report window state *without* consuming a hit.

    Used by /v1/whoami so that asking about your budget does not spend it.
    """
    now = time.monotonic()
    with _LOCK:
        hits = _WINDOWS.get(key)
        if not hits:
            return True, limit, window
        cutoff = now - window
        live = [t for t in hits if t > cutoff]
        remaining = max(0, limit - len(live))
        reset_in = max(1, math.ceil(live[0] + window - now)) if live else window
        return remaining > 0, remaining, reset_in


def reset_all() -> None:
    """Clear every window. Used by tests; harmless in production."""
    with _LOCK:
        _WINDOWS.clear()


def rate_limit(bucket: str, limit: int, window_seconds: int):
    """Build a dependency enforcing `limit` requests per `window_seconds`."""

    def dependency(
        request: Request,
        response: Response,
        who: str = Depends(principal),
    ) -> None:
        if not config.RATE_LIMIT_ENABLED:
            return

        allowed, remaining, reset_in = _consume(
            f"{bucket}:{who}", limit, window_seconds
        )
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_in),
        }

        if not allowed:
            raise ApiError(
                429,
                f"Rate limit exceeded: {limit} requests per {window_seconds}s for "
                f"'{who}' on {request.url.path}. Read the Retry-After header and "
                f"sleep that many seconds before retrying.",
                details=[
                    {
                        "field": None,
                        "issue": "rate_limit",
                        "limit": limit,
                        "window_seconds": window_seconds,
                        "retry_after_seconds": reset_in,
                    }
                ],
                headers={**headers, "Retry-After": str(reset_in)},
            )

        # Successful responses carry the budget too, so participants can watch it
        # drain without ever having to be blocked.
        response.headers.update(headers)

    return dependency


# The generous global bucket, applied to every /v1 route.
GlobalRateLimit = Depends(rate_limit("global", config.RATE_LIMIT_RPM, 60))

# The deliberately tight bucket, applied to one lab route only.
StrictRateLimit = Depends(
    rate_limit("throttled", config.THROTTLE_LIMIT, config.THROTTLE_WINDOW_SECONDS)
)
