"""STARTER -- Error-handling challenges E1, E2, E3.

Run it:   python training/starters/03_error_handling.py
"""
import os
import time

import requests

BASE_URL = os.environ.get("WORKSHOP_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
USERNAME = os.environ.get("WORKSHOP_USERNAME", "student")
PASSWORD = os.environ.get("WORKSHOP_PASSWORD", "student-pass-123")

session = requests.Session()
_auth = session.post(
    f"{BASE_URL}/v1/auth/token",
    data={"username": USERNAME, "password": PASSWORD},
    timeout=30,
)
_auth.raise_for_status()
TOKEN = _auth.json()["access_token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
print(f"Connected to {BASE_URL} as {USERNAME}\n")


# ---------------------------------------------------------------------------
# E1 -- provoke some errors and read them properly
# ---------------------------------------------------------------------------
print("E1  Provoking errors\n")

# Here is one, already broken on purpose: page_size 0 and a 4-letter currency.
bad = session.post(
    f"{BASE_URL}/v1/invoices/search",
    json={"page_size": 0, "filters": {"currency": "EURO"}},
    headers=HEADERS,
    timeout=30,
)
print(f"  status: {bad.status_code}")
print(f"  body  : {bad.text[:400]}\n")

# TODO 1: Every /v1 error has the same shape:
#           {"error": {"code", "message", "status", "request_id",
#                      "retryable", "details": [...]}}
#         Pull out error.code and error.request_id and print them.
#         The request_id is what someone running the API needs in order to find
#         your failed call in their logs -- so any exception you raise should
#         include it.
#
# TODO 2: Now provoke each of these and note the status code and error.code:
#           - no Authorization header at all      on /v1/whoami
#           - Authorization: Bearer garbage       on /v1/whoami
#           - an invoice number that doesn't exist on /v1/invoices/{number}
#         Two of those are about authentication and they return DIFFERENT codes.
#         Which is which, and does the difference make sense to you?
#
# TODO 3: Compare against a legacy endpoint: GET /invoices/999999
#         What does its error body give you that the /v1 one doesn't -- and
#         what does it NOT give you?


# ---------------------------------------------------------------------------
# E2 -- retry what is worth retrying
# ---------------------------------------------------------------------------
print("E2  A flaky endpoint\n")

# This endpoint fails roughly every third call, per user, with 503.
for i in range(4):
    r = session.get(
        f"{BASE_URL}/v1/unstable/invoices",
        params={"page_size": 1},
        headers=HEADERS,
        timeout=60,
    )
    print(f"  call {i + 1}: {r.status_code}" +
          (f"  Retry-After: {r.headers.get('retry-after')}" if not r.ok else ""))
print()

# TODO 4: Write a function that fetches this endpoint and RETRIES on failure,
#         so it succeeds even though the endpoint keeps breaking.
#
#         Make the wait grow between attempts (0.25s, 0.5s, 1s, 2s...) rather
#         than hammering immediately -- and add a little randomness, so that
#         ten people retrying don't all hit the server at the same instant.
#
#         If the response has a Retry-After header, use that number instead of
#         guessing. The server is telling you how long to wait.
#
#         Prove it: run 20 extracts and get 20 successes.

def fetch_with_retry(max_attempts=5):
    """TODO: your retry loop here."""
    raise NotImplementedError


# ---------------------------------------------------------------------------
# E3 -- don't retry what can never succeed
# ---------------------------------------------------------------------------
# TODO 5: Your retry loop above will happily retry ANY failure. That is wrong.
#         A 422 means your request is malformed -- waiting and sending the
#         identical request again will fail identically, five times, slowly.
#
#         Write:
#
#             def should_retry(status: int) -> bool:
#                 ...
#
#         Decide for each of: 401, 404, 422, 429, 500, 503.
#         Rule of thumb: is the problem at your end or theirs, and could
#         waiting plausibly change the outcome?
#
#         Then wire it into fetch_with_retry and prove a 422 fails in
#         milliseconds rather than after five attempts. Time it.
