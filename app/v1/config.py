"""Training-mode configuration.

Every knob is read once at import and prefixed TRAINING_. Defaults are chosen to
be safe for a live session: the disruptive behaviour is confined to the
dedicated /v1/lab/* routes, so nothing needs flipping mid-workshop.
"""
import os


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


# --- Rate limiting -----------------------------------------------------------
# Sized against the real exercises, not a guess: draining 613 invoices at
# page_size 25 costs 25 requests, and a participant may well re-run that several
# times while debugging. 300/min leaves comfortable headroom for that while
# still catching a genuine runaway `while True` (which spends thousands a
# minute) -- and a 429 is only instructive when it means "your loop is broken",
# not "you worked too fast".
RATE_LIMIT_ENABLED = _flag("TRAINING_RATE_LIMIT_ENABLED", True)
RATE_LIMIT_RPM = _int("TRAINING_RATE_LIMIT_PER_MIN", 300)

# A deliberately tight bucket, on one lab route only.
THROTTLE_LIMIT = _int("TRAINING_THROTTLE_LIMIT", 5)
THROTTLE_WINDOW_SECONDS = _int("TRAINING_THROTTLE_WINDOW_SECONDS", 30)

# --- Injected failure --------------------------------------------------------
FLAKY_ENABLED = _flag("TRAINING_FLAKY_ENABLED", True)
FLAKY_MODE = os.getenv("TRAINING_FLAKY_MODE", "counter")  # "counter" | "random"
FLAKY_EVERY_N = _int("TRAINING_FLAKY_EVERY_N", 3)
FLAKY_RATE = _float("TRAINING_FLAKY_RATE", 0.3)
# Lets the instructor force a guaranteed pass/fail on stage via X-Chaos.
CHAOS_HEADER_ENABLED = _flag("TRAINING_CHAOS_HEADER_ENABLED", True)

# --- Pagination caps ---------------------------------------------------------
# Low enough that a full extract *must* loop rather than be fetched in one call.
MASTER_DEFAULT_LIMIT = _int("TRAINING_MASTER_DEFAULT_LIMIT", 10)
MASTER_MAX_LIMIT = _int("TRAINING_MASTER_MAX_LIMIT", 50)
SEARCH_DEFAULT_PAGE_SIZE = _int("TRAINING_SEARCH_DEFAULT_PAGE_SIZE", 10)
SEARCH_MAX_PAGE_SIZE = _int("TRAINING_SEARCH_MAX_PAGE_SIZE", 25)

API_VERSION = "v1"
