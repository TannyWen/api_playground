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

from app.models import InvoiceStatus
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
class PaymentTermsOut(BaseModel):
    code: str
    days: int


class AddressOut(BaseModel):
    line1: Optional[str] = None
    city: Optional[str] = None
    postal_code: Optional[str] = None
    country_code: Optional[str] = None


class ContactOut(BaseModel):
    name: str
    role: str
    email: str
    phone: Optional[str] = None
    is_primary: bool


class SupplierMasterOut(BaseModel):
    supplier_code: str
    name: str
    # Both representations, on purpose: `country` is the full name, while
    # `country_code` is the ISO-2 code. Reconciling them is a workshop exercise.
    country: str
    country_code: str
    tax_id: Optional[str] = None
    duns: Optional[str] = None
    status: str
    is_preferred: bool
    default_currency: str
    payment_terms: PaymentTermsOut
    address: AddressOut
    contacts: List[ContactOut]
    created_at: datetime
    updated_at: Optional[datetime] = None


class OffsetPage(BaseModel):
    limit: int
    offset: int
    total: int
    returned: int
    has_more: bool
    next_offset: Optional[int] = None


class SupplierMasterPage(BaseModel):
    items: List[SupplierMasterOut]
    page: OffsetPage


# ---------------------------------------------------------------------------
# Invoice search -- request
# ---------------------------------------------------------------------------
class InvoiceFilters(BaseModel):
    model_config = Strict

    status: Optional[List[InvoiceStatus]] = Field(None, min_length=1, max_length=6)
    supplier_codes: Optional[List[str]] = Field(None, min_length=1, max_length=25)
    issued_from: Optional[date] = None
    issued_to: Optional[date] = None
    min_total: Optional[Decimal] = Field(None, ge=0, le=10_000_000, decimal_places=2)
    max_total: Optional[Decimal] = Field(None, ge=0, le=10_000_000, decimal_places=2)
    currency: Optional[str] = Field(None, pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def _check_ranges(self):
        if (
            self.min_total is not None
            and self.max_total is not None
            and self.max_total < self.min_total
        ):
            raise ValueError("max_total must be greater than or equal to min_total")
        if self.issued_from and self.issued_to and self.issued_to < self.issued_from:
            raise ValueError("issued_to must be on or after issued_from")
        return self


class InvoiceInclude(BaseModel):
    model_config = Strict

    supplier: bool = True
    line_items: bool = True
    allocations: bool = True


class InvoiceSearchRequest(BaseModel):
    model_config = Strict

    filters: InvoiceFilters = Field(default_factory=InvoiceFilters)
    include: InvoiceInclude = Field(default_factory=InvoiceInclude)
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
class AllocationOut(BaseModel):
    cost_center: str
    cost_center_name: str
    gl_account: str
    project_code: Optional[str] = None
    percentage: Decimal
    amount: Decimal


class InvoiceLineOut(BaseModel):
    line_number: int
    description: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal
    allocations: Optional[List[AllocationOut]] = None


class InvoiceSupplierOut(BaseModel):
    supplier_code: str
    name: str
    country: str
    country_code: str
    tax_id: Optional[str] = None
    address: AddressOut


class InvoiceOut(BaseModel):
    invoice_id: int
    invoice_number: str
    status: InvoiceStatus
    currency: str
    issue_date: date
    due_date: date
    total_amount: Decimal
    notes: Optional[str] = None
    created_at: datetime
    supplier: Optional[InvoiceSupplierOut] = None
    line_items: Optional[List[InvoiceLineOut]] = None


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
    included: List[str]


class InvoiceSearchResponse(BaseModel):
    data: List[InvoiceOut]
    page: CursorPage
    meta: SearchMeta

