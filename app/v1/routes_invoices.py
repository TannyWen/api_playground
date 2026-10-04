"""Invoice extraction: POST because the filter belongs in the body.

This is the GET-vs-POST lesson made concrete. A realistic extraction filter --
a list of vendor numbers, a date range, a set of GL accounts -- does not fit
comfortably or safely in a URL. So the parameters move into the body, and the
request stays a read: it returns 200, creates nothing, and can be repeated.

Pagination is keyset (WHERE id > last_id ORDER BY id) rather than offset, and
the response deliberately omits a total, so the only correct way to extract
everything is to follow next_cursor until it comes back null.

These two routes are also the only ones on /v1 that respond in XML rather
than JSON (see xml_render.py) -- a deliberate point of contrast: same data,
same error envelope (errors here are still the standard JSON envelope,
untouched), different wire format on success. Every other /v1 route,
including the /unstable/* lab routes that reuse execute_search() below,
stays JSON.
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy.orm import Session, joinedload

from app import models
from app.database import get_db
from app.v1 import projections, schemas, xml_render
from app.v1.cursor import InvalidCursor, decode_cursor, encode_cursor
from app.v1.deps import current_user
from app.v1.errors import ApiError
from app.v1.middleware import get_request_id

router = APIRouter(prefix="/invoices", tags=["v1: invoices"])


def _base_query(db: Session):
    return db.query(models.Invoice).options(
        joinedload(models.Invoice.vendor),
        joinedload(models.Invoice.line_items).joinedload(
            models.InvoiceLineItem.postings
        ).joinedload(models.Posting.account),
    )


def _apply_filters(q, f: schemas.InvoiceFilters, db: Session):
    applied = 0
    if f.vendor_number:
        vendor_ids = [
            vid
            for (vid,) in db.query(models.Vendor.id).filter(
                models.Vendor.vendor_number.in_(f.vendor_number)
            )
        ]
        # An unmatched code yields an empty page rather than an error: "no rows"
        # is a legitimate answer, and telling the two apart is a workshop point.
        q = q.filter(models.Invoice.vendor_id.in_(vendor_ids or [-1]))
        applied += 1
    if f.account_number:
        matching_invoice_ids = (
            db.query(models.Invoice.id)
            .join(models.InvoiceLineItem)
            .join(models.Posting)
            .join(models.Account)
            .filter(models.Account.account_number.in_(f.account_number))
            .distinct()
        )
        ids = [iid for (iid,) in matching_invoice_ids]
        q = q.filter(models.Invoice.id.in_(ids or [-1]))
        applied += 1
    if f.accounting_date_from:
        q = q.filter(models.Invoice.accounting_date >= f.accounting_date_from)
        applied += 1
    if f.accounting_date_to:
        q = q.filter(models.Invoice.accounting_date <= f.accounting_date_to)
        applied += 1
    return q, applied


def execute_search(
    payload: schemas.InvoiceSearchRequest, request: Request, db: Session
) -> schemas.InvoiceSearchResponse:
    """The search itself, independent of routing.

    Shared with the /v1/unstable/* lab routes so the retry exercises return the
    exact same payload shape as the real endpoint.
    """
    started = time.perf_counter()

    if payload.cursor:
        try:
            last_id = decode_cursor(payload.cursor)
        except InvalidCursor as exc:
            # 400, not 422: the value is well-typed, its *content* is wrong.
            raise ApiError(
                400,
                str(exc),
                code="invalid_cursor",
                details=[{"field": "cursor", "issue": "undecodable"}],
            ) from exc
    else:
        last_id = None

    q, filters_applied = _apply_filters(_base_query(db), payload.filters, db)

    # Only the first page carries a count, and it is named "estimated" so nobody
    # builds a contract on it. From page 2 it is null, which removes the shortcut
    # of computing a page count and forces a genuine drain loop.
    estimated_total = q.count() if last_id is None else None

    if last_id is not None:
        q = q.filter(models.Invoice.id > last_id)

    # Fetch one extra row to learn whether another page exists, without a
    # second COUNT query.
    rows = q.order_by(models.Invoice.id).limit(payload.page_size + 1).all()
    has_more = len(rows) > payload.page_size
    rows = rows[: payload.page_size]

    data = [projections.invoice_to_out(inv) for inv in rows]

    return schemas.InvoiceSearchResponse(
        data=data,
        page=schemas.CursorPage(
            page_size=payload.page_size,
            returned=len(rows),
            cursor=payload.cursor,
            next_cursor=encode_cursor(rows[-1].id) if (rows and has_more) else None,
            has_more=has_more,
            estimated_total=estimated_total,
        ),
        meta=schemas.SearchMeta(
            request_id=get_request_id(request),
            generated_at=datetime.now(timezone.utc),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
            filters_applied=filters_applied,
        ),
    )


@router.post(
    "/search",
    response_class=Response,
    responses={
        200: {
            "description": "Invoice search results, as XML (not JSON).",
            "content": {
                "application/xml": {
                    "example": (
                        "<invoice_search_response>\n"
                        "  <data>\n"
                        "    <item>\n"
                        "      <invoice_number>INV-2025-001</invoice_number>\n"
                        "      <vendor_number>V-0795</vendor_number>\n"
                        "      <accounting_date>2025-01-17</accounting_date>\n"
                        "      <line_items>...</line_items>\n"
                        "    </item>\n"
                        "  </data>\n"
                        "  <page>...</page>\n"
                        "  <meta>...</meta>\n"
                        "</invoice_search_response>"
                    )
                }
            },
        }
    },
)
def search_invoices(
    payload: schemas.InvoiceSearchRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: models.User = Depends(current_user),
):
    """Same request shape as always (a JSON filter body) -- but the response
    is XML, not JSON. See xml_render.search_response_to_xml for the shape.
    """
    result = execute_search(payload, request, db)
    return Response(content=xml_render.search_response_to_xml(result), media_type="application/xml")


@router.get(
    "/{invoice_number}",
    response_class=Response,
    responses={
        200: {
            "description": "One fully-expanded invoice, as XML (not JSON).",
            "content": {
                "application/xml": {
                    "example": (
                        "<invoice>\n"
                        "  <invoice_number>INV-2025-001</invoice_number>\n"
                        "  <vendor_number>V-0795</vendor_number>\n"
                        "  <accounting_date>2025-01-17</accounting_date>\n"
                        "  <line_items>\n"
                        "    <item>\n"
                        "      <line_item>1</line_item>\n"
                        "      <purchasing_line_description>Office furniture</purchasing_line_description>\n"
                        "      <quantity>47</quantity>\n"
                        "      <postings>...</postings>\n"
                        "    </item>\n"
                        "  </line_items>\n"
                        "</invoice>"
                    )
                }
            },
        }
    },
)
def get_invoice(
    invoice_number: str = Path(
        ...,
        description="The business key, e.g. INV-2025-014 -- not the surrogate id.",
    ),
    db: Session = Depends(get_db),
    _: models.User = Depends(current_user),
):
    """One fully-expanded invoice, addressed by its business key, as XML.

    Addressing by invoice_number rather than a surrogate id is deliberate: it
    is the key a finance person would actually quote. A 404 here still comes
    back as the standard JSON error envelope -- only the success body is XML.
    """
    invoice = (
        _base_query(db)
        .filter(models.Invoice.invoice_number == invoice_number)
        .first()
    )
    if not invoice:
        raise ApiError(
            404,
            f"No invoice with number '{invoice_number}'.",
            details=[{"field": "invoice_number", "issue": "not_found"}],
        )
    result = projections.invoice_to_out(invoice)
    return Response(content=xml_render.invoice_to_xml(result), media_type="application/xml")
