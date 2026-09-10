"""Master data: vendors and the chart of accounts, both offset-paginated.

Offset/limit here and cursor pagination on the invoice search, deliberately --
those are the two styles participants will actually meet in the wild, and
having one of each makes "write a loop that drains every page" a real
exercise twice.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.v1 import config, projections, schemas
from app.v1.deps import current_user

router = APIRouter(prefix="/master-data", tags=["v1: master data"])

VENDOR_SORTABLE = {
    "vendor_number": models.Vendor.vendor_number,
    "vendor_name": models.Vendor.vendor_name,
    "vendor_country": models.Vendor.vendor_country,
}


@router.get("/vendors", response_model=schemas.VendorPage)
def list_vendors(
    limit: int = Query(
        config.MASTER_DEFAULT_LIMIT,
        ge=1,
        le=config.MASTER_MAX_LIMIT,
        description=f"Max {config.MASTER_MAX_LIMIT}.",
    ),
    offset: int = Query(0, ge=0),
    vendor_country: Optional[str] = Query(None, description="Full country name."),
    vendor_group: Optional[str] = Query(None),
    search: Optional[str] = Query(
        None, min_length=2, max_length=60, description="Case-insensitive name match."
    ),
    sort: str = Query(
        "vendor_number",
        description="One of vendor_number, vendor_name, vendor_country. "
        "Prefix with '-' for descending.",
    ),
    db: Session = Depends(get_db),
    _: models.User = Depends(current_user),
):
    descending = sort.startswith("-")
    key = sort.lstrip("-")
    if key not in VENDOR_SORTABLE:
        from app.v1.errors import ApiError

        raise ApiError(
            422,
            f"Unsupported sort '{sort}'.",
            details=[
                {"field": "sort", "issue": "unsupported_value", "allowed": sorted(VENDOR_SORTABLE)}
            ],
        )

    q = db.query(models.Vendor)
    if vendor_country:
        q = q.filter(models.Vendor.vendor_country == vendor_country)
    if vendor_group:
        q = q.filter(models.Vendor.vendor_group == vendor_group)
    if search:
        q = q.filter(models.Vendor.vendor_name.ilike(f"%{search}%"))

    column = VENDOR_SORTABLE[key]
    q = q.order_by(column.desc() if descending else column.asc(), models.Vendor.id)

    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    returned = len(rows)
    has_more = offset + returned < total

    return schemas.VendorPage(
        items=[projections.vendor_to_out(v) for v in rows],
        page=schemas.OffsetPage(
            limit=limit,
            offset=offset,
            total=total,
            returned=returned,
            has_more=has_more,
            next_offset=(offset + limit) if has_more else None,
        ),
    )


ACCOUNT_SORTABLE = {
    "account_number": models.Account.account_number,
    "account_name": models.Account.account_name,
    "account_group_number": models.Account.account_group_number,
}


@router.get("/accounts", response_model=schemas.AccountPage)
def list_accounts(
    limit: int = Query(
        config.MASTER_DEFAULT_LIMIT,
        ge=1,
        le=config.MASTER_MAX_LIMIT,
        description=f"Max {config.MASTER_MAX_LIMIT}.",
    ),
    offset: int = Query(0, ge=0),
    account_group_number: Optional[str] = Query(None),
    sort: str = Query(
        "account_number",
        description="One of account_number, account_name, account_group_number. "
        "Prefix with '-' for descending.",
    ),
    db: Session = Depends(get_db),
    _: models.User = Depends(current_user),
):
    descending = sort.startswith("-")
    key = sort.lstrip("-")
    if key not in ACCOUNT_SORTABLE:
        from app.v1.errors import ApiError

        raise ApiError(
            422,
            f"Unsupported sort '{sort}'.",
            details=[
                {
                    "field": "sort",
                    "issue": "unsupported_value",
                    "allowed": sorted(ACCOUNT_SORTABLE),
                }
            ],
        )

    q = db.query(models.Account)
    if account_group_number:
        q = q.filter(models.Account.account_group_number == account_group_number)

    column = ACCOUNT_SORTABLE[key]
    q = q.order_by(column.desc() if descending else column.asc(), models.Account.id)

    total = q.count()
    rows = q.offset(offset).limit(limit).all()
    returned = len(rows)
    has_more = offset + returned < total

    return schemas.AccountPage(
        items=[projections.account_to_out(a) for a in rows],
        page=schemas.OffsetPage(
            limit=limit,
            offset=offset,
            total=total,
            returned=returned,
            has_more=has_more,
            next_offset=(offset + limit) if has_more else None,
        ),
    )
