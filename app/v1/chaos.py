"""Deliberate, controllable failure injection.

Confined to the /v1/lab/* routes so the error-handling exercises can never
contaminate the pagination or flattening ones.

Determinism, in priority order:
  1. X-Chaos: fail|pass       -- guaranteed outcome, for demoing on stage
  2. counter mode (default)   -- every Nth call per principal fails, reliably
  3. random mode              -- genuinely nondeterministic, if you want it
"""
import random
import threading
from collections import defaultdict

from fastapi import Depends, Request

from app.v1 import config
from app.v1.deps import principal
from app.v1.errors import ApiError

_CALLS: dict[str, int] = defaultdict(int)
_LOCK = threading.Lock()

RETRY_AFTER_SECONDS = 2


def reset_all() -> None:
    """Clear every call counter. Used by tests."""
    with _LOCK:
        _CALLS.clear()


def _next_index(key: str) -> int:
    with _LOCK:
        _CALLS[key] += 1
        return _CALLS[key]


def _unavailable(reason: str) -> ApiError:
    # 503, not 500: this failure is transient and *should* be retried, which is
    # precisely the distinction the exercise is teaching.
    return ApiError(
        503,
        "The invoice export service is temporarily unavailable. "
        "This failure is injected on purpose -- retry the same request.",
        details=[{"field": None, "issue": "chaos_injected", "message": reason}],
        headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
    )


def maybe_fail(request: Request, who: str = Depends(principal)) -> None:
    if config.CHAOS_HEADER_ENABLED:
        forced = (request.headers.get("X-Chaos") or "").strip().lower()
        if forced == "fail":
            raise _unavailable("forced by X-Chaos: fail")
        if forced == "pass":
            return

    if not config.FLAKY_ENABLED:
        return

    if config.FLAKY_MODE == "random":
        if random.random() < config.FLAKY_RATE:
            raise _unavailable(f"mode=random rate={config.FLAKY_RATE}")
        return

    every_n = max(2, config.FLAKY_EVERY_N)
    index = _next_index(f"flaky:{who}")
    if index % every_n == 0:
        raise _unavailable(
            f"mode=counter every_n={every_n} call_index={index} principal={who}"
        )


InjectChaos = Depends(maybe_fail)
