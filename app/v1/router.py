"""Aggregates the /v1 surface under a single prefix."""
from fastapi import APIRouter

from app.v1 import routes_invoices, routes_lab, routes_master, routes_meta
from app.v1.ratelimit import GlobalRateLimit

# The generous global rate limit applies to every /v1 route. It is invisible to
# a human clicking in Postman, but will catch a runaway loop -- which is exactly
# when a 429 is instructive rather than annoying.
router = APIRouter(prefix="/v1", dependencies=[GlobalRateLimit])

router.include_router(routes_meta.router)
router.include_router(routes_master.router)
router.include_router(routes_invoices.router)
router.include_router(routes_lab.router)
