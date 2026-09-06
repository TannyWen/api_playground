from fastapi import FastAPI

from app.database import Base, engine
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
        "Start at `GET /v1/ping`, then `POST /v1/auth/token` "
        "(form-encoded, not JSON) for a bearer token."
    ),
    version="2.0.0",
)

# Adds an X-Request-Id response header to every request.
app.add_middleware(RequestIdMiddleware)

install_v1_error_handlers(app)

app.include_router(v1_router)
