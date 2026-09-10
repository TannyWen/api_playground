"""Turn ORM rows into /v1 response objects.

Kept separate from the routes so the shape of the payload is defined in
exactly one place, and so the nesting the workshop flattens is easy to
reason about:

    invoice -> line_items[] -> postings[]

vendor_number and account_number travel on the transactional data as plain
references -- resolving them to a name/address is what the two master-data
endpoints are for.
"""
from app import models
from app.v1 import schemas


def vendor_to_out(vendor: models.Vendor) -> schemas.VendorOut:
    return schemas.VendorOut(
        vendor_number=vendor.vendor_number,
        vendor_name=vendor.vendor_name,
        vendor_address=vendor.vendor_address,
        vendor_post_code=vendor.vendor_post_code,
        vendor_country=vendor.vendor_country,
        vendor_group=vendor.vendor_group,
        vendor_tax_number=vendor.vendor_tax_number,
        created_at=vendor.created_at,
    )


def account_to_out(account: models.Account) -> schemas.AccountOut:
    return schemas.AccountOut(
        account_number=account.account_number,
        account_name=account.account_name,
        account_group_number=account.account_group_number,
        account_group_name=account.account_group_name,
        account_set_id=account.account_set_id,
        account_set_name=account.account_set_name,
    )


def _postings(line_item: models.InvoiceLineItem) -> list[schemas.PostingOut]:
    return [
        schemas.PostingOut(
            account_number=p.account.account_number,
            line_amount=p.line_amount,
        )
        for p in sorted(line_item.postings, key=lambda p: p.id)
    ]


def invoice_to_out(invoice: models.Invoice) -> schemas.InvoiceOut:
    return schemas.InvoiceOut(
        invoice_number=invoice.invoice_number,
        vendor_number=invoice.vendor.vendor_number,
        accounting_date=invoice.accounting_date,
        line_items=[
            schemas.LineItemOut(
                line_item=li.line_item,
                purchasing_line_description=li.purchasing_line_description,
                quantity=li.quantity,
                postings=_postings(li),
            )
            for li in sorted(invoice.line_items, key=lambda li: li.line_item)
        ],
    )
