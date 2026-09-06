from decimal import Decimal
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.auth import require_token
from app.database import Base, engine, get_db
from app.security import create_access_token, verify_password
from app.v1.errors import install_v1_error_handlers
from app.v1.middleware import RequestIdMiddleware
from app.v1.router import router as v1_router

try:
    Base.metadata.create_all(bind=engine)
except Exception:
    pass

app = FastAPI(
    title="Procurement Invoice API",
    description=(
        "A teaching API for procurement invoices, backed by SQLite. "
        "**/v1 is the workshop surface** -- start at `GET /v1/ping`, then "
        "`POST /v1/auth/token` (form-encoded, not JSON) for a bearer token. "
        "The unversioned endpoints are the original API, kept for comparison: "
        "they return bare `detail` errors, while /v1 returns a structured "
        "envelope carrying a request_id."
    ),
    version="1.1.0",
)

# Adds an X-Request-Id response header to every request. Header-only, so legacy
# response bodies are unchanged.
app.add_middleware(RequestIdMiddleware)

# Registered app-wide (FastAPI has no per-router handlers) but each one returns
# FastAPI's default response for any path outside /v1, so the original endpoints
# keep their exact current error format.
install_v1_error_handlers(app)

app.include_router(v1_router)


# ---------------------------------------------------------------------------
# Health (no auth) — useful to show the contrast with protected endpoints.
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth — exchange seeded credentials for a real, expiring bearer token.
# ---------------------------------------------------------------------------
@app.post("/auth/token", response_model=schemas.TokenOut, tags=["auth"])
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(models.User.username == form_data.username).first()
    if not user or not verify_password(
        form_data.password, user.password_hash, user.password_salt
    ):
        raise HTTPException(status_code=401, detail="Incorrect username or password")

    token, expires_at = create_access_token(subject=user.username)
    return schemas.TokenOut(access_token=token, expires_at=expires_at)


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------
@app.get(
    "/suppliers",
    response_model=schemas.Page[schemas.SupplierOut],
    tags=["suppliers"],
)
def list_suppliers(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    country: Optional[str] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    q = db.query(models.Supplier)
    if country:
        q = q.filter(models.Supplier.country == country)
    total = q.count()
    items = q.order_by(models.Supplier.id).offset(offset).limit(limit).all()
    return schemas.Page(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total,
    )


@app.get(
    "/suppliers/{supplier_id}",
    response_model=schemas.SupplierOut,
    tags=["suppliers"],
)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    supplier = db.query(models.Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@app.get(
    "/suppliers/{supplier_id}/invoices",
    response_model=schemas.Page[schemas.InvoiceOut],
    tags=["suppliers"],
)
def list_supplier_invoices(
    supplier_id: int,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    supplier = db.query(models.Supplier).get(supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    q = db.query(models.Invoice).filter(models.Invoice.supplier_id == supplier_id)
    total = q.count()
    items = q.order_by(models.Invoice.id).offset(offset).limit(limit).all()
    return schemas.Page(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total,
    )


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------
@app.get(
    "/invoices",
    response_model=schemas.Page[schemas.InvoiceOut],
    tags=["invoices"],
)
def list_invoices(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[models.InvoiceStatus] = None,
    supplier_id: Optional[int] = None,
    min_amount: Optional[Decimal] = None,
    max_amount: Optional[Decimal] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    q = db.query(models.Invoice)
    if status:
        q = q.filter(models.Invoice.status == status)
    if supplier_id:
        q = q.filter(models.Invoice.supplier_id == supplier_id)
    if min_amount is not None:
        q = q.filter(models.Invoice.total_amount >= min_amount)
    if max_amount is not None:
        q = q.filter(models.Invoice.total_amount <= max_amount)

    total = q.count()
    items = q.order_by(models.Invoice.id).offset(offset).limit(limit).all()
    return schemas.Page(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total,
    )


@app.get(
    "/invoices/{invoice_id}",
    response_model=schemas.InvoiceDetailOut,
    tags=["invoices"],
)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    invoice = (
        db.query(models.Invoice)
        .options(
            joinedload(models.Invoice.supplier), joinedload(models.Invoice.line_items)
        )
        .filter(models.Invoice.id == invoice_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@app.post(
    "/invoices",
    response_model=schemas.InvoiceDetailOut,
    status_code=201,
    tags=["invoices"],
)
def create_invoice(
    payload: schemas.InvoiceCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    supplier = db.query(models.Supplier).get(payload.supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    existing = (
        db.query(models.Invoice)
        .filter(models.Invoice.invoice_number == payload.invoice_number)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Invoice number already exists")

    line_items = [
        models.InvoiceLineItem(
            description=li.description,
            quantity=li.quantity,
            unit_price=li.unit_price,
            line_total=li.unit_price * li.quantity,
        )
        for li in payload.line_items
    ]
    total_amount = sum((li.line_total for li in line_items), Decimal("0"))

    invoice = models.Invoice(
        invoice_number=payload.invoice_number,
        supplier_id=payload.supplier_id,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
        currency=payload.currency,
        notes=payload.notes,
        total_amount=total_amount,
        line_items=line_items,
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@app.patch(
    "/invoices/{invoice_id}/status",
    response_model=schemas.InvoiceOut,
    tags=["invoices"],
)
def update_invoice_status(
    invoice_id: int,
    payload: schemas.InvoiceStatusUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    invoice = db.query(models.Invoice).get(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = payload.status
    db.commit()
    db.refresh(invoice)
    return invoice


@app.delete("/invoices/{invoice_id}", status_code=204, tags=["invoices"])
def delete_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    invoice = db.query(models.Invoice).get(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    db.delete(invoice)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Stats — demonstrate aggregation endpoints beyond plain CRUD.
# ---------------------------------------------------------------------------
@app.get("/stats/summary", response_model=schemas.SummaryOut, tags=["stats"])
def stats_summary(
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    total_invoices = db.query(models.Invoice).count()
    total_suppliers = db.query(models.Supplier).count()
    total_amount = db.query(func.coalesce(func.sum(models.Invoice.total_amount), 0)).scalar()

    by_status_rows = (
        db.query(
            models.Invoice.status,
            func.count(models.Invoice.id),
            func.coalesce(func.sum(models.Invoice.total_amount), 0),
        )
        .group_by(models.Invoice.status)
        .all()
    )
    by_status = [
        schemas.StatusSummary(status=status, count=count, total_amount=amount)
        for status, count, amount in by_status_rows
    ]

    return schemas.SummaryOut(
        total_invoices=total_invoices,
        total_suppliers=total_suppliers,
        total_amount=total_amount,
        by_status=by_status,
    )


@app.get(
    "/stats/top-suppliers",
    response_model=list[schemas.TopSupplierOut],
    tags=["stats"],
)
def top_suppliers(
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
    _: str = Depends(require_token),
):
    rows = (
        db.query(
            models.Supplier.id,
            models.Supplier.name,
            func.count(models.Invoice.id),
            func.coalesce(func.sum(models.Invoice.total_amount), 0),
        )
        .join(models.Invoice, models.Invoice.supplier_id == models.Supplier.id)
        .group_by(models.Supplier.id)
        .order_by(func.sum(models.Invoice.total_amount).desc())
        .limit(limit)
        .all()
    )
    return [
        schemas.TopSupplierOut(
            supplier_id=sid,
            supplier_name=name,
            invoice_count=count,
            total_amount=amount,
        )
        for sid, name, count, amount in rows
    ]
