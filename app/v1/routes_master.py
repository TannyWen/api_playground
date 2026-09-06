"""Master data: supplier reference records, offset-paginated.

Offset/limit here and cursor pagination on the invoice search, deliberately --
those are the two styles participants will actually meet in the wild, and having
one of each makes "write a loop that drains every page" a real exercise twice.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from app import models
from app.database import get_db
from app.v1 import config, projections, schemas
from app.v1.deps import current_user

router = APIRouter(prefix="/master-data", tags=["v1: master data"])

SORTABLE = {
    "name": models.Supplier.name,
    "country": models.Supplier.country,
    "supplier_code": models.SupplierProfile.supplier_code,
    "updated_at": models.SupplierProfile.updated_at,
}


@router.get("/suppliers", response_model=schemas.SupplierMasterPage)
def list_suppliers(
    limit: int = Query(
        config.MASTER_DEFAULT_LIMIT,
        ge=1,
        le=config.MASTER_MAX_LIMIT,
        description=f"Max {config.MASTER_MAX_LIMIT}.",
    ),
    offset: int = Query(0, ge=0),
    country: Optional[str] = Query(
        None, description="Full country name, e.g. 'Finland'."
    ),
    country_code: Optional[str] = Query(
        None, min_length=2, max_length=2, description="ISO-2 code, e.g. 'FI'."
    ),
    search: Optional[str] = Query(
        None, min_length=2, max_length=60, description="Case-insensitive name match."
    ),
    status: Optional[str] = Query(None, pattern="^(active|blocked|pending)$"),
    is_preferred: Optional[bool] = None,
    sort: str = Query(
        "supplier_code",
        description="One of name, country, supplier_code, updated_at. "
        "Prefix with '-' for descending.",
    ),
    db: Session = Depends(get_db),
    _: models.User = Depends(current_user),
):
    descending = sort.startswith("-")
    key = sort.lstrip("-")
    if key not in SORTABLE:
        # A 422 naming the allowed values beats a silent fallback to default order.
        from app.v1.errors import ApiError

        raise ApiError(
            422,
            f"Unsupported sort '{sort}'.",
            details=[
                {
                    "field": "sort",
                    "issue": "unsupported_value",
                    "allowed": sorted(SORTABLE),
                }
            ],
        )

    q = (
        db.query(models.Supplier)
        .outerjoin(models.SupplierProfile)
        .options(
            joinedload(models.Supplier.profile),
            joinedload(models.Supplier.contacts),
        )
    )
    if country:
        q = q.filter(models.Supplier.country == country)
    if country_code:
        q = q.filter(models.SupplierProfile.country_code == country_code.upper())
    if search:
        q = q.filter(models.Supplier.name.ilike(f"%{search}%"))
    if status:
        q = q.filter(models.SupplierProfile.status == status)
    if is_preferred is not None:
        q = q.filter(models.SupplierProfile.is_preferred == is_preferred)

    column = SORTABLE[key]
    # Tie-break on id so paging is stable when the sort column has duplicates.
    q = q.order_by(column.desc() if descending else column.asc(), models.Supplier.id)

    total = q.distinct().count()
    rows = q.distinct().offset(offset).limit(limit).all()
    returned = len(rows)
    has_more = offset + returned < total

    return schemas.SupplierMasterPage(
        items=[projections.supplier_to_master(s) for s in rows],
        page=schemas.OffsetPage(
            limit=limit,
            offset=offset,
            total=total,
            returned=returned,
            has_more=has_more,
            next_offset=(offset + limit) if has_more else None,
        ),
    )
