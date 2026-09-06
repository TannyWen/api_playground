import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class InvoiceStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    paid = "paid"
    overdue = "overdue"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    contact_email = Column(String, nullable=False)
    country = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    invoices = relationship(
        "Invoice", back_populates="supplier", cascade="all, delete-orphan"
    )
    # Master-data enrichment used by the /v1 surface. Kept in side tables rather
    # than extra columns here, because Base.metadata.create_all() creates missing
    # tables but never ALTERs existing ones -- and there is no migration tool.
    profile = relationship(
        "SupplierProfile",
        back_populates="supplier",
        uselist=False,
        cascade="all, delete-orphan",
    )
    contacts = relationship(
        "SupplierContact", back_populates="supplier", cascade="all, delete-orphan"
    )


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String, unique=True, nullable=False, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    status = Column(Enum(InvoiceStatus), default=InvoiceStatus.draft, index=True)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False)
    currency = Column(String, default="USD")
    total_amount = Column(Numeric(12, 2), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    supplier = relationship("Supplier", back_populates="invoices")
    line_items = relationship(
        "InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    description = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(12, 2), nullable=False)

    invoice = relationship("Invoice", back_populates="line_items")
    # The delete-orphan cascade is load-bearing: without it, DELETE /invoices/{id}
    # leaves orphaned allocation rows behind, and SQLite will not complain because
    # PRAGMA foreign_keys is off by default.
    allocations = relationship(
        "InvoiceLineAllocation",
        back_populates="line_item",
        cascade="all, delete-orphan",
    )


class SupplierProfile(Base):
    """1:1 master-data record for a supplier: business keys and lifecycle fields."""

    __tablename__ = "supplier_profiles"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(
        Integer, ForeignKey("suppliers.id"), nullable=False, unique=True, index=True
    )
    supplier_code = Column(String, nullable=False, unique=True, index=True)
    country_code = Column(String(2), nullable=False, index=True)
    vat_number = Column(String, nullable=True)
    duns = Column(String, nullable=True)
    payment_terms = Column(String, nullable=False, default="NET30", index=True)
    default_currency = Column(String(3), nullable=False, default="EUR")
    status = Column(String, nullable=False, default="active", index=True)
    is_preferred = Column(Boolean, nullable=False, default=False, index=True)
    address_line1 = Column(String, nullable=True)
    address_city = Column(String, nullable=True)
    address_postal_code = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, index=True)

    supplier = relationship("Supplier", back_populates="profile")


class SupplierContact(Base):
    """1:N contacts for a supplier -- the array in the master-data payload."""

    __tablename__ = "supplier_contacts"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)

    supplier = relationship("Supplier", back_populates="contacts")


class InvoiceLineAllocation(Base):
    """1:N cost splits under a line item -- the third nesting level.

    Seeded so that the allocation amounts sum exactly to the parent line_total,
    with any rounding remainder pushed onto the last allocation.
    """

    __tablename__ = "invoice_line_allocations"

    id = Column(Integer, primary_key=True, index=True)
    line_item_id = Column(
        Integer, ForeignKey("invoice_line_items.id"), nullable=False, index=True
    )
    cost_center = Column(String, nullable=False, index=True)
    cost_center_name = Column(String, nullable=False)
    gl_account = Column(String, nullable=False, index=True)
    project_code = Column(String, nullable=True)
    percentage = Column(Numeric(5, 2), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)

    line_item = relationship("InvoiceLineItem", back_populates="allocations")
