"""XML rendering for the invoice endpoints only.

Every other /v1 route stays JSON. This exists specifically because the two
invoice endpoints (POST /v1/invoices/search, GET /v1/invoices/{number})
were asked to speak XML instead -- a deliberate point of contrast: two
endpoints in the same API, two different wire formats, same underlying
data and the same error envelope underneath (errors on these routes are
still JSON -- see app/v1/errors.py, untouched by this module).
"""
import xml.etree.ElementTree as ET
from datetime import date

from app.v1 import schemas


def _add_scalar(parent: ET.Element, tag: str, value) -> ET.Element:
    """Append <tag>value</tag>. None becomes an empty element, e.g. <cursor/>."""
    el = ET.SubElement(parent, tag)
    if value is None:
        pass
    elif isinstance(value, bool):
        el.text = "true" if value else "false"
    elif isinstance(value, date):
        # Covers datetime too -- datetime is a subclass of date.
        el.text = value.isoformat()
    else:
        el.text = str(value)
    return el


def _posting_to_xml(parent: ET.Element, posting: schemas.PostingOut) -> None:
    item = ET.SubElement(parent, "item")
    _add_scalar(item, "account_number", posting.account_number)
    _add_scalar(item, "line_amount", posting.line_amount)


def _line_item_to_xml(parent: ET.Element, line: schemas.LineItemOut) -> None:
    item = ET.SubElement(parent, "item")
    _add_scalar(item, "line_item", line.line_item)
    _add_scalar(item, "purchasing_line_description", line.purchasing_line_description)
    _add_scalar(item, "quantity", line.quantity)
    postings_el = ET.SubElement(item, "postings")
    for posting in line.postings:
        _posting_to_xml(postings_el, posting)


def _invoice_fields_to_xml(parent: ET.Element, invoice: schemas.InvoiceOut) -> None:
    _add_scalar(parent, "invoice_number", invoice.invoice_number)
    _add_scalar(parent, "vendor_number", invoice.vendor_number)
    _add_scalar(parent, "accounting_date", invoice.accounting_date)
    line_items_el = ET.SubElement(parent, "line_items")
    for line in invoice.line_items:
        _line_item_to_xml(line_items_el, line)


def _to_string(root: ET.Element) -> str:
    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def invoice_to_xml(invoice: schemas.InvoiceOut) -> str:
    """GET /v1/invoices/{invoice_number} -- one invoice, as XML."""
    root = ET.Element("invoice")
    _invoice_fields_to_xml(root, invoice)
    return _to_string(root)


def search_response_to_xml(response: schemas.InvoiceSearchResponse) -> str:
    """POST /v1/invoices/search -- the full envelope (data/page/meta), as XML."""
    root = ET.Element("invoice_search_response")

    data_el = ET.SubElement(root, "data")
    for invoice in response.data:
        item = ET.SubElement(data_el, "item")
        _invoice_fields_to_xml(item, invoice)

    page_el = ET.SubElement(root, "page")
    _add_scalar(page_el, "page_size", response.page.page_size)
    _add_scalar(page_el, "returned", response.page.returned)
    _add_scalar(page_el, "cursor", response.page.cursor)
    _add_scalar(page_el, "next_cursor", response.page.next_cursor)
    _add_scalar(page_el, "has_more", response.page.has_more)
    _add_scalar(page_el, "estimated_total", response.page.estimated_total)

    meta_el = ET.SubElement(root, "meta")
    _add_scalar(meta_el, "request_id", response.meta.request_id)
    _add_scalar(meta_el, "generated_at", response.meta.generated_at)
    _add_scalar(meta_el, "elapsed_ms", response.meta.elapsed_ms)
    _add_scalar(meta_el, "filters_applied", response.meta.filters_applied)

    return _to_string(root)
