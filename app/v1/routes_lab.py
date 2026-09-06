"""The lab: endpoints that fail on purpose.

Kept on their own paths so injected failure can never contaminate the
pagination or flattening exercises. Both return the same payload shape as
POST /v1/invoices/search, so a working retry loop produces directly comparable
output.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.v1 import config, schemas
from app.v1.chaos import InjectChaos
from app.v1.deps import current_user
from app.v1.ratelimit import StrictRateLimit
from app.v1.routes_invoices import execute_search

router = APIRouter(prefix="/unstable", tags=["v1: lab (fails on purpose)"])


def _page(page_size: int, cursor: Optional[str]) -> schemas.InvoiceSearchRequest:
    return schemas.InvoiceSearchRequest(page_size=page_size, cursor=cursor)


@router.get(
    "/invoices",
    response_model=schemas.InvoiceSearchResponse,
    dependencies=[InjectChaos],
)
def flaky_invoices(
    request: Request,
    page_size: int = Query(
        config.SEARCH_DEFAULT_PAGE_SIZE, ge=1, le=config.SEARCH_MAX_PAGE_SIZE
    ),
    cursor: Optional[str] = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(current_user),
):
    """Fails roughly every third call, per user, with 503 + Retry-After.

    Counter mode by default rather than random, so the failure is reproducible
    per participant and independent of everyone else. `X-Chaos: fail` or
    `X-Chaos: pass` forces the outcome, for demonstrating on a projector.
    """
    return execute_search(_page(page_size, cursor), request, db)


@router.get(
    "/throttled-invoices",
    response_model=schemas.InvoiceSearchResponse,
    dependencies=[StrictRateLimit],
)
def throttled_invoices(
    request: Request,
    page_size: int = Query(
        config.SEARCH_DEFAULT_PAGE_SIZE, ge=1, le=config.SEARCH_MAX_PAGE_SIZE
    ),
    cursor: Optional[str] = None,
    db: Session = Depends(get_db),
    _: models.User = Depends(current_user),
):
    """Deliberately tight budget, so 429 + Retry-After is reachable on demand.

    A dedicated route rather than tightening the global limit, because the
    alternative means restarting the server mid-session -- and a restart drops
    everyone's in-flight requests.
    """
    return execute_search(_page(page_size, cursor), request, db)
