from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    password_salt = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Vendor(Base):
    """Vendor master data."""

    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    vendor_number = Column(String, unique=True, nullable=False, index=True)
    vendor_name = Column(String, nullable=False, index=True)
    vendor_address = Column(String, nullable=False)
    vendor_post_code = Column(String, nullable=False)
    vendor_country = Column(String, nullable=False, index=True)
    vendor_group = Column(String, nullable=False, index=True)
    vendor_tax_number = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    invoices = relationship("Invoice", back_populates="vendor")


class Account(Base):
    """Chart-of-accounts master data.

    Deliberately flat/denormalised -- account_set and account_group are real
    hierarchy dimensions in a chart of accounts, but this table carries them
    inline on each account row rather than as separate joined tables, the way
    a real ERP master-data extract usually looks.
    """

    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    account_number = Column(String, unique=True, nullable=False, index=True)
    account_name = Column(String, nullable=False)
    account_group_number = Column(String, nullable=False, index=True)
    account_group_name = Column(String, nullable=False)
    account_set_id = Column(String, nullable=False, index=True)
    account_set_name = Column(String, nullable=False)

    postings = relationship("Posting", back_populates="account")


class Invoice(Base):
    """The header. One invoice belongs to one vendor."""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String, unique=True, nullable=False, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=False, index=True)
    accounting_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    vendor = relationship("Vendor", back_populates="invoices")
    line_items = relationship(
        "InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan"
    )


class InvoiceLineItem(Base):
    """The purchasing line -- what was actually bought, not the accounting impact."""

    __tablename__ = "invoice_line_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False, index=True)
    line_item = Column(Integer, nullable=False)  # sequence number within the invoice
    purchasing_line_description = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)

    invoice = relationship("Invoice", back_populates="line_items")
    # Cascade is load-bearing: without it, deleting an invoice orphans postings,
    # and SQLite won't complain since PRAGMA foreign_keys is off by default.
    postings = relationship(
        "Posting", back_populates="line_item", cascade="all, delete-orphan"
    )


class Posting(Base):
    """One GL posting under a line item.

    Signed line_amount rather than separate debit/credit columns (positive =
    debit, negative = credit) -- every invoice's postings sum to exactly zero,
    the way a real double-entry journal entry balances.
    """

    __tablename__ = "postings"

    id = Column(Integer, primary_key=True, index=True)
    line_item_id = Column(
        Integer, ForeignKey("invoice_line_items.id"), nullable=False, index=True
    )
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    line_amount = Column(Numeric(14, 2), nullable=False)

    line_item = relationship("InvoiceLineItem", back_populates="postings")
    account = relationship("Account", back_populates="postings")
