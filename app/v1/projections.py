"""Turn ORM rows into /v1 response objects.

Kept separate from the routes so the shape of the payload is defined in exactly
one place, and so the nesting the workshop flattens is easy to reason about:

    invoice -> line_items[] -> allocations[]
    invoice -> supplier -> address
"""
from datetime import datetime

from app import models
from app.v1 import schemas

PAYMENT_TERM_DAYS = {
    "IMMEDIATE": 0,
    "NET15": 15,
    "NET30": 30,
    "NET45": 45,
    "NET60": 60,
}


def _payment_terms(code: str | None) -> schemas.PaymentTermsOut:
    code = code or "NET30"
    return schemas.PaymentTermsOut(code=code, days=PAYMENT_TERM_DAYS.get(code, 30))


def supplier_to_master(supplier: models.Supplier) -> schemas.SupplierMasterOut:
    """Full master-data record. Tolerates a supplier with no profile row.

    That tolerance matters for any database seeded before the profile table
    existed -- it degrades to blanks rather than raising a 500.
    """
    p = supplier.profile
    return schemas.SupplierMasterOut(
        supplier_code=p.supplier_code if p else f"SUP-{supplier.id:06d}",
        name=supplier.name,
        country=supplier.country,
        country_code=p.country_code if p else "",
        tax_id=p.vat_number if p else None,
        duns=p.duns if p else None,
        status=p.status if p else "active",
        is_preferred=bool(p.is_preferred) if p else False,
        default_currency=p.default_currency if p else "EUR",
        payment_terms=_payment_terms(p.payment_terms if p else None),
        address=schemas.AddressOut(
            line1=p.address_line1 if p else None,
            city=p.address_city if p else None,
            postal_code=p.address_postal_code if p else None,
            country_code=p.country_code if p else None,
        ),
        contacts=[
            schemas.ContactOut(
                name=c.full_name,
                role=c.role,
                email=c.email,
                phone=c.phone,
                is_primary=bool(c.is_primary),
            )
            # Primary contact first, then a stable order, so saved responses are
            # byte-comparable between runs.
            for c in sorted(supplier.contacts, key=lambda c: (not c.is_primary, c.id))
        ],
        created_at=supplier.created_at or datetime.utcnow(),
        updated_at=p.updated_at if p else None,
    )


def _invoice_supplier(supplier: models.Supplier) -> schemas.InvoiceSupplierOut:
    """The supplier fields embedded in an invoice.

    Deliberately a subset of the master record. Comparing the two is a workshop
    exercise about why embedded copies drift from the master source.
    """
    p = supplier.profile
    return schemas.InvoiceSupplierOut(
        supplier_code=p.supplier_code if p else f"SUP-{supplier.id:06d}",
        name=supplier.name,
        country=supplier.country,
        country_code=p.country_code if p else "",
        tax_id=p.vat_number if p else None,
        address=schemas.AddressOut(
            line1=p.address_line1 if p else None,
            city=p.address_city if p else None,
            postal_code=p.address_postal_code if p else None,
            country_code=p.country_code if p else None,
        ),
    )


def _allocations(item: models.InvoiceLineItem) -> list[schemas.AllocationOut]:
    return [
        schemas.AllocationOut(
            cost_center=a.cost_center,
            cost_center_name=a.cost_center_name,
            gl_account=a.gl_account,
            project_code=a.project_code,
            percentage=a.percentage,
            amount=a.amount,
        )
        for a in sorted(item.allocations, key=lambda a: a.id)
    ]


def invoice_to_out(
    invoice: models.Invoice,
    include_supplier: bool = True,
    include_line_items: bool = True,
    include_allocations: bool = True,
) -> schemas.InvoiceOut:
    line_items = None
    if include_line_items:
        line_items = [
            schemas.InvoiceLineOut(
                # line_number is derived, not stored: a stable ordinal within the
                # invoice, so flattened output is reproducible.
                line_number=n,
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                line_total=item.line_total,
                allocations=_allocations(item) if include_allocations else None,
            )
            for n, item in enumerate(
                sorted(invoice.line_items, key=lambda i: i.id), start=1
            )
        ]

    return schemas.InvoiceOut(
        invoice_id=invoice.id,
        invoice_number=invoice.invoice_number,
        status=invoice.status,
        currency=invoice.currency,
        issue_date=invoice.issue_date,
        due_date=invoice.due_date,
        total_amount=invoice.total_amount,
        notes=invoice.notes,
        created_at=invoice.created_at or datetime.utcnow(),
        supplier=_invoice_supplier(invoice.supplier) if include_supplier else None,
        line_items=line_items,
    )
