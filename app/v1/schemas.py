"""Request and response models for the /v1 training surface.

Two deliberate properties, both teaching material:

* `extra="forbid"` on every request body. The most common real mistake is
  putting a parameter at the wrong nesting level; forbidding extras means the
  422 names the offending key instead of silently ignoring it.
* Money is typed `Decimal`, which Pydantic v2 serialises to a JSON *string*.
  Left unhandled, pandas infers `object` dtype and `.sum()` concatenates. That
  is the single most valuable lesson in the flattening block, so it stays.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.v1 import config

Strict = ConfigDict(extra="forbid")
FromAttrs = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Connection / meta
# ---------------------------------------------------------------------------
class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class PingOut(BaseModel):
    status: str = "ok"
    api_version: str = config.API_VERSION
    server_time: datetime
    auth_required: bool = False
    next_step: str
    # Answers "is the new version actually deployed and running" without
    # needing Kudu or the portal: app_version is bumped by hand per change,
    # git_commit is read straight from .git (null if not present in this
    # deploy), and process_started_at / uptime_seconds change on every real
    # restart -- so even an unbumped version is caught by a fresh uptime.
    app_version: str
    git_commit: Optional[str] = None
    process_started_at: datetime
    uptime_seconds: int


class RateLimitOut(BaseModel):
    limit: int
    remaining: int
    resets_in_seconds: int


class WhoAmIOut(BaseModel):
    authenticated: bool = True
    username: str
    user_id: int
    token_expires_at: Optional[datetime] = None
    token_expires_in_seconds: Optional[int] = None
    server_time: datetime
    rate_limit: RateLimitOut


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
class OffsetPage(BaseModel):
    limit: int
    offset: int
    total: int
    returned: int
    has_more: bool
    next_offset: Optional[int] = None


class VendorOut(BaseModel):
    vendor_number: str
    vendor_name: str
    vendor_address: str
    vendor_post_code: str
    vendor_country: str
    vendor_group: str
    vendor_tax_number: Optional[str] = None
    created_at: datetime


class VendorPage(BaseModel):
    items: List[VendorOut]
    page: OffsetPage


class AccountOut(BaseModel):
    account_number: str
    account_name: str
    account_group_number: str
    account_group_name: str
    account_set_id: str
    account_set_name: str


class AccountPage(BaseModel):
    items: List[AccountOut]
    page: OffsetPage


# ---------------------------------------------------------------------------
# Invoice search -- request
# ---------------------------------------------------------------------------
class InvoiceFilters(BaseModel):
    model_config = Strict

    vendor_number: Optional[List[str]] = Field(None, min_length=1, max_length=25)
    account_number: Optional[List[str]] = Field(
        None,
        min_length=1,
        max_length=25,
        description="Match invoices with at least one posting on any of these accounts.",
    )
    accounting_date_from: Optional[date] = None
    accounting_date_to: Optional[date] = None

    @model_validator(mode="after")
    def _check_ranges(self):
        if (
            self.accounting_date_from
            and self.accounting_date_to
            and self.accounting_date_to < self.accounting_date_from
        ):
            raise ValueError("accounting_date_to must be on or after accounting_date_from")
        return self


class InvoiceSearchRequest(BaseModel):
    model_config = Strict

    filters: InvoiceFilters = Field(default_factory=InvoiceFilters)
    page_size: int = Field(
        config.SEARCH_DEFAULT_PAGE_SIZE,
        ge=1,
        le=config.SEARCH_MAX_PAGE_SIZE,
        description=(
            f"Maximum {config.SEARCH_MAX_PAGE_SIZE}. Larger values are rejected -- "
            "follow next_cursor in a loop instead of asking for everything at once."
        ),
    )
    cursor: Optional[str] = Field(
        None,
        max_length=512,
        description="Pass back the next_cursor from the previous response. Omit for page 1.",
    )

    @model_validator(mode="after")
    def _blank_cursor_means_first_page(self):
        # An empty string is what a templating tool sends for an unset variable
        # (Postman's {{next_cursor}} before anything has populated it). Treating
        # that as "start from the beginning" is friendlier, and more defensible,
        # than a validation error about a field the caller never meant to set.
        if self.cursor is not None and not self.cursor.strip():
            self.cursor = None
        return self


# ---------------------------------------------------------------------------
# Invoice search -- response
# ---------------------------------------------------------------------------
class PostingOut(BaseModel):
    account_number: str
    line_amount: Decimal


class LineItemOut(BaseModel):
    line_item: int
    purchasing_line_description: str
    quantity: int
    postings: List[PostingOut]


class InvoiceOut(BaseModel):
    invoice_number: str
    # A reference, not embedded master data -- resolving vendor_number to a
    # name/address is what GET /v1/master-data/vendors is for. Same idea as a
    # real ERP extract: transactional data carries keys, not copies.
    vendor_number: str
    accounting_date: date
    line_items: List[LineItemOut]


class CursorPage(BaseModel):
    page_size: int
    returned: int
    cursor: Optional[str] = None
    next_cursor: Optional[str] = None
    has_more: bool
    # Present on the first page only, and named "estimated" so nobody builds a
    # contract on it. After page 1 it is null, which removes the shortcut of
    # deriving a page count and forces a real drain loop.
    estimated_total: Optional[int] = None


class SearchMeta(BaseModel):
    request_id: str
    generated_at: datetime
    elapsed_ms: int
    filters_applied: int


class InvoiceSearchResponse(BaseModel):
    data: List[InvoiceOut]
    page: CursorPage
    meta: SearchMeta
