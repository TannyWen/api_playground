import logging
import os

from fastapi import FastAPI

from app.database import Base, engine
from app.v1.errors import install_v1_error_handlers
from app.v1.middleware import RequestIdMiddleware
from app.v1.router import router as v1_router
from app.version import __version__

log = logging.getLogger("app.main")

Base.metadata.create_all(bind=engine)


def _auto_seed_enabled() -> bool:
    """Should this boot wipe and deterministically rebuild all data?

    An explicit AUTO_SEED_ON_START always wins, in either direction. Absent
    that, default ON when WEBSITE_SITE_NAME is present -- an environment
    variable Azure App Service sets on every instance automatically, with
    nothing to configure -- and OFF everywhere else, so a fresh deploy is
    self-contained with zero App Settings, while local dev keeps its
    existing, faster, opt-in seeding via run_api.ps1 / manage.py.
    """
    explicit = os.getenv("AUTO_SEED_ON_START")
    if explicit is not None:
        return explicit.strip().lower() in ("1", "true", "yes", "on")
    return bool(os.getenv("WEBSITE_SITE_NAME"))


# Every process start wipes and deterministically rebuilds the entire
# dataset -- including workshop participant accounts, from the same fixed
# seed every time. This is what removes the "did a restart wipe my data"
# question entirely: a restart is supposed to reset to the same known-good
# state, not something to work around. See manage.auto_seed_on_start.
if _auto_seed_enabled():
    import manage

    try:
        manage.auto_seed_on_start()
    except Exception:
        log.exception("auto-seed failed at startup")

app = FastAPI(
    title="Procurement Invoice API",
    description=(
        "A teaching API for procurement invoices, backed by SQLite. "
        "Start at `GET /v1/ping`, then `POST /v1/auth/token` "
        "(form-encoded, not JSON) for a bearer token."
    ),
    version=__version__,
)

# Adds an X-Request-Id response header to every request.
app.add_middleware(RequestIdMiddleware)

install_v1_error_handlers(app)

app.include_router(v1_router)
