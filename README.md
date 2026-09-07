# Procurement Invoice API (teaching project)

A FastAPI + SQLite API modeling procurement invoices, built for teaching REST
API concepts: bearer token auth, pagination, filtering, and error handling.

Everything lives under **`/v1`** (see
[`training/WORKBOOK.md`](training/WORKBOOK.md) for the workshop that runs
against it): cursor and offset pagination, a structured error envelope, rate
limiting, and deliberately injected failure.

## Setup

```bash
python -m venv .venv          # requires Python 3.12 -- see runtime.txt
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

Or, on Windows, just run [`run_api.ps1`](run_api.ps1) — it creates the venv,
installs dependencies, seeds the database, and starts the server in one step.

## Seed / clear data

```bash
python manage.py seed                          # 118 suppliers, 613 invoices
python manage.py seed --suppliers 20 --invoices 200
python manage.py seed --fresh                  # wipe and rebuild
python manage.py clear                         # wipe all data
python manage.py doctor                        # read-only health check
```

For the workshop, generate one account per participant:

```bash
python manage.py seed-users --members alice,bob,carol
python manage.py seed-users --count 8          # -> trainee01 .. trainee08
```

## Run the API

```bash
uvicorn app.main:app --reload
```

Docs: http://127.0.0.1:8000/docs

## Auth

All endpoints except `/v1/ping` and `/v1/auth/token` require a bearer token,
issued as a real JWT.

1. `python manage.py seed` creates two fixed accounts (`student` /
   `student-pass-123` and `instructor` / `instructor-pass-456`) for local
   development. Passwords are stored as a salted PBKDF2 hash and are not
   recoverable afterward. For per-participant credentials, use
   `manage.py seed-users` instead.
2. Exchange credentials for a token — **form-encoded, not JSON**:

   ```bash
   curl -X POST http://127.0.0.1:8000/v1/auth/token \
     -d "username=student&password=student-pass-123"
   ```

   Response: `{"access_token": "...", "token_type": "bearer", "expires_at": "..."}`

3. Use it:

   ```
   Authorization: Bearer <access_token>
   ```

Tokens expire after 60 minutes by default (`ACCESS_TOKEN_EXPIRE_MINUTES` env
var). The signing key is a fixed value baked into `app/security.py`, so
tokens survive a server restart with no configuration needed. Set
`JWT_SECRET_KEY` explicitly (it always overrides the fixed default) if this
ever guards real data instead of the seeded training dataset.

## Endpoints

| Method | Path                              | Notes                                     |
|--------|------------------------------------|--------------------------------------------|
| GET    | `/v1/ping`                         | No auth. Liveness check.                    |
| POST   | `/v1/auth/token`                   | No auth. Form-encoded credential exchange.  |
| GET    | `/v1/whoami`                       | Who you are, and when your token expires.   |
| GET    | `/v1/master-data/suppliers`        | Offset pagination, `limit` capped at 50.    |
| POST   | `/v1/invoices/search`              | Cursor pagination, `page_size` capped at 25. Filters in the body. |
| GET    | `/v1/invoices/{invoice_number}`    | One invoice, fully expanded, by business key. |
| GET    | `/v1/unstable/invoices`            | Fails ~1 in 3 calls, on purpose.             |
| GET    | `/v1/unstable/throttled-invoices`  | Deliberately tight rate limit.               |

Every response returns a structured error envelope on failure:
`{"error": {"code", "message", "status", "request_id", "retryable", "details"}}`.

## Workshop material

See [`training/`](training/) for the participant workbook, a Postman
collection, reference solutions, and pre-saved sample responses.
