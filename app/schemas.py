from datetime import date, datetime
from decimal import Decimal
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

from app.models import InvoiceStatus

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    limit: int
    offset: int
    has_more: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class SupplierBase(BaseModel):
    name: str
    contact_email: str
    country: str


class SupplierCreate(SupplierBase):
    pass


class SupplierOut(SupplierBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class LineItemBase(BaseModel):
    description: str
    quantity: int
    unit_price: Decimal


class LineItemCreate(LineItemBase):
    pass


class LineItemOut(LineItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_total: Decimal


class InvoiceBase(BaseModel):
    invoice_number: str
    supplier_id: int
    issue_date: date
    due_date: date
    currency: str = "USD"
    notes: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    line_items: List[LineItemCreate]


class InvoiceStatusUpdate(BaseModel):
    status: InvoiceStatus


class InvoiceOut(InvoiceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: InvoiceStatus
    total_amount: Decimal
    created_at: datetime


class InvoiceDetailOut(InvoiceOut):
    supplier: SupplierOut
    line_items: List[LineItemOut]


class StatusSummary(BaseModel):
    status: InvoiceStatus
    count: int
    total_amount: Decimal


class SummaryOut(BaseModel):
    total_invoices: int
    total_suppliers: int
    total_amount: Decimal
    by_status: List[StatusSummary]


class TopSupplierOut(BaseModel):
    supplier_id: int
    supplier_name: str
    invoice_count: int
    total_amount: Decimal
